"""Offline imports into a staged Zen profile, never the live profile."""

from __future__ import annotations

import base64
import hashlib
import os
import sqlite3
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from .io import has_table, integrity, read_json, readonly_db
from .models import BridgeError, Options
from .paths import all_source_profiles

CHROME_EPOCH = 11_644_473_600_000_000
VISIT_TYPES = {0: 1, 1: 2, 2: 3, 3: 4, 4: 8, 5: 2, 6: 1, 7: 1, 8: 9, 9: 1, 10: 1}


def guid() -> str:
    return base64.urlsafe_b64encode(os.urandom(9)).decode()


def hash_string(value: bytes) -> int:
    result = 0
    for byte in value:
        result = (((((result << 5) | (result >> 27)) & 0xFFFFFFFF) ^ byte) * 0x9E3779B9) & 0xFFFFFFFF
    return result


def url_hash(url: str) -> int:
    """Mozilla Places HashURL, verified against the target before importing."""
    raw = url.encode()
    colon = raw[:50].find(b":")
    return hash_string(raw[:1500]) + (((hash_string(raw[:colon]) & 0xFFFF) << 32) if colon >= 0 else 0)


def import_places(source: Path, profile: Path, options: Options) -> dict:
    if not (options.history or options.bookmarks):
        return {}
    path = profile / "places.sqlite"
    if not path.exists():
        raise BridgeError("Zen's bookmarks/history database is missing. Initialize the profile first.")
    counts = Counter()
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        required = {"origin_id", "recalc_frecency", "recalc_alt_frecency", "url_hash"}
        fields = {r[1] for r in db.execute("PRAGMA table_info(moz_places)")}
        if not required.issubset(fields):
            raise BridgeError("This Zen Places schema is unsupported; no live files were changed.")
        if any(url_hash(u) != h for u, h in db.execute("SELECT url,url_hash FROM moz_places")):
            raise BridgeError("The target uses an unfamiliar URL hash format; standard-data import stopped.")
        places = {u: pid for pid, u in db.execute("SELECT id,url FROM moz_places")}
        origins = {
            (prefix, host): oid for oid, prefix, host in db.execute("SELECT id,prefix,host FROM moz_origins")
        }

        def place(url: str, title: str = "") -> int | None:
            if url in places:
                return places[url]
            try:
                parsed = urlsplit(url)
                hostname, port = parsed.hostname or "", parsed.port
            except ValueError:
                return None
            if parsed.scheme not in ("http", "https", "file", "ftp"):
                return None
            prefix = parsed.scheme + "://"
            host = hostname + ((":" + str(port)) if port else "")
            oid = origins.get((prefix, host))
            if oid is None:
                oid = db.execute(
                    "INSERT INTO moz_origins(prefix,host,frecency,recalc_frecency,recalc_alt_frecency) VALUES(?,?,0,1,1)",
                    (prefix, host),
                ).lastrowid
                origins[prefix, host] = oid
            pid = db.execute(
                "INSERT INTO moz_places(url,title,rev_host,guid,url_hash,origin_id,recalc_frecency,recalc_alt_frecency) VALUES(?,?,?,?,?,?,1,1)",
                (url, title, hostname[::-1] + ".", guid(), url_hash(url), oid),
            ).lastrowid
            places[url] = pid
            counts["new_places"] += 1
            return pid

        visits = {
            (pid, date, kind): vid
            for vid, pid, date, kind in db.execute(
                "SELECT id,place_id,visit_date,visit_type FROM moz_historyvisits"
            )
        }
        bookmark_parent = None
        now = int(time.time() * 1_000_000)

        def folder(name: str, parent: int) -> int:
            position = db.execute(
                "SELECT COALESCE(MAX(position),-1)+1 FROM moz_bookmarks WHERE parent=?", (parent,)
            ).fetchone()[0]
            return db.execute(
                "INSERT INTO moz_bookmarks(type,parent,position,title,dateAdded,lastModified,guid) VALUES(2,?,?,?,?,?,?)",
                (parent, position, name, now, now, guid()),
            ).lastrowid

        def bookmark(node: dict, parent: int) -> None:
            if node.get("type") == "folder":
                child_parent = folder(node.get("name") or "Folder", parent)
                for child in node.get("children", []):
                    bookmark(child, child_parent)
            elif node.get("type") == "url":
                pid = place(node["url"], node.get("name", ""))
                if pid is None:
                    counts["unsupported_bookmarks"] += 1
                    return
                position = db.execute(
                    "SELECT COALESCE(MAX(position),-1)+1 FROM moz_bookmarks WHERE parent=?", (parent,)
                ).fetchone()[0]
                date = max(0, int(node.get("date_added") or 0) - CHROME_EPOCH)
                db.execute(
                    "INSERT INTO moz_bookmarks(type,fk,parent,position,title,dateAdded,lastModified,guid) VALUES(1,?,?,?,?,?,?,?)",
                    (pid, parent, position, node.get("name", ""), date, now, guid()),
                )
                counts["bookmarks"] += 1

        # Bookmark files have their own fingerprint: history and sidebar changes
        # must not suppress new visits. Visits deduplicate on URL/date/type.
        ledger_path = profile / "arc2zen-bridge-standard.json"
        ledger = read_json(ledger_path) if ledger_path.exists() else {}
        bookmark_hash = hashlib.sha256()
        for arc_profile in all_source_profiles(source):
            bookmark_path = arc_profile / "Bookmarks"
            if bookmark_path.exists():
                bookmark_hash.update(arc_profile.name.encode())
                bookmark_hash.update(bookmark_path.read_bytes())
        fingerprint = bookmark_hash.hexdigest()
        prior = ledger.get(fingerprint, [])
        for arc_profile in all_source_profiles(source):
            history = arc_profile / "History"
            if options.history and history.exists():
                with readonly_db(history) as src:
                    urlmap = {}
                    for uid, url, title, typed in src.execute("SELECT id,url,title,typed_count FROM urls"):
                        pid = place(url, title)
                        urlmap[uid] = pid
                        if pid and typed:
                            db.execute("UPDATE moz_places SET typed=1 WHERE id=?", (pid,))
                    source_ids, parents = {}, []
                    for vid, uid, date, parent, transition in src.execute(
                        "SELECT id,url,visit_time,from_visit,transition FROM visits ORDER BY id"
                    ):
                        pid, date = urlmap.get(uid), date - CHROME_EPOCH
                        if pid is None or date <= 0:
                            counts["unsupported_history_visits"] += 1
                            continue
                        kind = VISIT_TYPES.get(transition & 255, 1)
                        identity = (pid, date, kind)
                        new_id = visits.get(identity)
                        if new_id is None:
                            new_id = db.execute(
                                "INSERT INTO moz_historyvisits(from_visit,place_id,visit_date,visit_type,session,source) VALUES(0,?,?,?,?,0)",
                                (pid, date, kind, 0),
                            ).lastrowid
                            visits[identity] = new_id
                            counts["history_visits"] += 1
                        else:
                            counts["duplicate_history_visits"] += 1
                        source_ids[vid] = new_id
                        if parent:
                            parents.append((new_id, parent))
                    for new_id, old_parent in parents:
                        if old_parent in source_ids:
                            db.execute(
                                "UPDATE moz_historyvisits SET from_visit=? WHERE id=? AND COALESCE(from_visit,0)=0",
                                (source_ids[old_parent], new_id),
                            )
            bookmarks = arc_profile / "Bookmarks"
            if options.bookmarks and "bookmarks" not in prior and bookmarks.exists():
                if bookmark_parent is None:
                    parent = db.execute("SELECT id FROM moz_bookmarks WHERE guid='unfiled_____'").fetchone()
                    if not parent:
                        raise BridgeError("Zen's bookmark root is missing.")
                    bookmark_parent = folder("Imported from Arc · " + time.strftime("%Y-%m-%d"), parent[0])
                child_parent = folder(arc_profile.name, bookmark_parent)
                for node in read_json(bookmarks).get("roots", {}).values():
                    if isinstance(node, dict) and node.get("children"):
                        bookmark(node, child_parent)
        db.execute(
            "UPDATE moz_places SET visit_count=(SELECT COUNT(*) FROM moz_historyvisits v WHERE v.place_id=moz_places.id AND v.visit_type NOT IN (0,4,7,8,9)), last_visit_date=(SELECT MAX(visit_date) FROM moz_historyvisits v WHERE v.place_id=moz_places.id), foreign_count=MAX(foreign_count,(SELECT COUNT(*) FROM moz_bookmarks b WHERE b.fk=moz_places.id)), recalc_frecency=1,recalc_alt_frecency=1"
        )
        db.commit()
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise BridgeError("Places foreign-key validation failed.")
    integrity(path)
    from .io import write_json

    ledger[fingerprint] = sorted(
        set(prior)
        | ({"history"} if options.history else set())
        | ({"bookmarks"} if options.bookmarks else set())
    )
    write_json(ledger_path, ledger)
    return dict(counts)


def import_forms(source: Path, profile: Path) -> dict:
    path = profile / "formhistory.sqlite"
    if not path.exists():
        raise BridgeError("Initialize Zen's saved form history before enabling its import.")
    added = 0
    with sqlite3.connect(path) as db:
        for arc_profile in all_source_profiles(source):
            source_db = arc_profile / "Web Data"
            if not source_db.exists():
                continue
            with readonly_db(source_db) as src:
                if not has_table(src, "autofill"):
                    continue
                for name, value, first, last, count in src.execute(
                    "SELECT name,value,date_created,date_last_used,count FROM autofill"
                ):
                    if not db.execute(
                        "SELECT 1 FROM moz_formhistory WHERE fieldname=? AND value=?", (name, value)
                    ).fetchone():
                        db.execute(
                            "INSERT INTO moz_formhistory(fieldname,value,timesUsed,firstUsed,lastUsed,guid) VALUES(?,?,?,?,?,?)",
                            (name, value, count, first * 1_000_000, last * 1_000_000, guid()),
                        )
                        added += 1
        db.commit()
    integrity(path)
    return {"form_entries": added}
