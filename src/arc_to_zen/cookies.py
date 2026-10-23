from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter
from pathlib import Path

from .io import integrity, read_session, readonly_db, write_session
from .models import BridgeError
from .paths import source_profile
from .secrets import ArcKey
from .standard import CHROME_EPOCH


def import_cookies(source: Path, profile: Path, contexts: dict[str, int], key: ArcKey) -> dict:
    path = profile / "cookies.sqlite"
    if not path.exists():
        raise BridgeError("Zen's cookie database is missing. Initialize the profile first.")
    counts, sessions = Counter(), []
    now = int(time.time())
    with sqlite3.connect(path) as db:
        for profile_key, cid in contexts.items():
            arc_profile = source_profile(source, profile_key)
            cookie_db = arc_profile / "Cookies"
            if not cookie_db.exists():
                cookie_db = arc_profile / "Network" / "Cookies"
            if not cookie_db.exists():
                continue
            with readonly_db(cookie_db) as src:
                version = int(src.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0])
                # Older Chromium databases declare encrypted_value as TEXT.
                columns = [row[1] for row in src.execute("PRAGMA table_info(cookies)")]
                if not {
                    "encrypted_value",
                    "host_key",
                    "is_persistent",
                    "expires_utc",
                    "source_scheme",
                    "samesite",
                }.issubset(columns):
                    raise BridgeError("An Arc cookie schema is unsupported.")
                # Column names come from SQLite schema, quote them defensively.
                query = (
                    "SELECT "
                    + ",".join(
                        "CAST(encrypted_value AS BLOB) AS encrypted_value"
                        if c == "encrypted_value"
                        else '"' + c.replace('"', '""') + '"'
                        for c in columns
                    )
                    + " FROM cookies"
                )
                for row in src.execute(query):
                    r = dict(row)
                    if r.get("top_frame_site_key"):
                        counts["partitioned_cookies_skipped"] += 1
                        continue
                    expiry = (r["expires_utc"] - CHROME_EPOCH) // 1_000_000
                    if r["is_persistent"] and expiry <= now:
                        counts["expired_cookies_skipped"] += 1
                        continue
                    value = (
                        key.decrypt(r["encrypted_value"], r["host_key"], version)
                        if r["encrypted_value"]
                        else r["value"]
                    )
                    # Chromium's unspecified value uses Lax-by-default behavior.
                    # Do not turn it into an explicit unrestricted cookie.
                    same_site = 1 if r["samesite"] == -1 else r["samesite"]
                    if same_site not in (0, 1, 2) or r["source_scheme"] not in (0, 1, 2):
                        counts["unsupported_cookie_attributes"] += 1
                        continue
                    if r["is_persistent"]:
                        attributes = f"^userContextId={cid}"
                        existing = db.execute(
                            "SELECT 1 FROM moz_cookies WHERE name=? AND host=? AND path=? AND originAttributes=?",
                            (r["name"], r["host_key"], r["path"], attributes),
                        ).fetchone()
                        if existing:
                            counts["existing_cookies_preserved"] += 1
                            continue
                        db.execute(
                            "INSERT INTO moz_cookies(originAttributes,name,value,host,path,expiry,lastAccessed,creationTime,isSecure,isHttpOnly,sameSite,schemeMap,updateTime) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                attributes,
                                r["name"],
                                value,
                                r["host_key"],
                                r["path"],
                                expiry,
                                max(0, r["last_access_utc"] - CHROME_EPOCH),
                                max(0, r["creation_utc"] - CHROME_EPOCH),
                                r["is_secure"],
                                r["is_httponly"],
                                same_site,
                                r["source_scheme"],
                                int(time.time() * 1_000_000),
                            ),
                        )
                        counts["persistent_cookies"] += 1
                    else:
                        sessions.append(
                            {
                                "host": r["host_key"],
                                "name": r["name"],
                                "value": value,
                                "path": r["path"],
                                "secure": bool(r["is_secure"]),
                                "httponly": bool(r["is_httponly"]),
                                "originAttributes": {"userContextId": cid},
                                "sameSite": same_site,
                                "schemeMap": r["source_scheme"],
                            }
                        )
                        counts["session_cookies"] += 1
        db.commit()
    for session_path in (profile / "sessionstore.jsonlz4", profile / "sessionstore-backups/recovery.jsonlz4"):
        if not session_path.exists():
            continue
        value = read_session(session_path)

        def cookie_key(cookie):
            return (
                cookie["host"],
                cookie.get("path", ""),
                cookie.get("name", ""),
                json.dumps(cookie.get("originAttributes", {}), sort_keys=True),
            )

        existing = {cookie_key(c) for c in value.get("cookies", [])}
        value.setdefault("cookies", []).extend(c for c in sessions if cookie_key(c) not in existing)
        write_session(session_path, value)
    integrity(path)
    return dict(counts)
