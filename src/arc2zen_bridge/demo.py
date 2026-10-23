"""Fictional browser fixtures used by tests and the explicit --demo preview."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .io import write_json, write_session
from .standard import CHROME_EPOCH, url_hash


def create(root: Path) -> tuple[Path, Path]:
    arc, zen = root / "Arc", root / "zen" / "Profiles" / "demo.default"
    arc.mkdir(parents=True, exist_ok=True)
    zen.mkdir(parents=True, exist_ok=True)
    items = {
        "home-pins": {"childrenIds": ["folder-library", "tab-notes", "folder-empty"]},
        "home-open": {"childrenIds": ["tab-open"]},
        "research-pins": {"childrenIds": []},
        "research-open": {"childrenIds": []},
        "reading-pins": {"childrenIds": []},
        "reading-open": {"childrenIds": []},
        "folder-library": {
            "title": "Library",
            "data": {"list": {}},
            "childrenIds": ["tab-guide", "folder-nested"],
        },
        "folder-nested": {"title": "Reference", "data": {"list": {}}, "childrenIds": ["tab-reference"]},
        "folder-empty": {"title": "Later", "data": {"list": {}}, "childrenIds": []},
        "ess-default": {"childrenIds": ["essential-mail"]},
        "ess-research": {"childrenIds": ["essential-search"]},
        "ess-unused": {"childrenIds": ["essential-unused"]},
    }
    for key, title in [
        ("tab-notes", "Notes"),
        ("tab-open", "Open article"),
        ("tab-guide", "Guide"),
        ("tab-reference", "Reference"),
        ("essential-mail", "Mail"),
        ("essential-search", "Search"),
        ("essential-unused", "Old workspace"),
    ]:
        items[key] = {
            "title": title,
            "data": {"tab": {"savedURL": "https://example.test/" + key, "savedTitle": title}},
            "childrenIds": [],
        }

    def custom(key):
        return {"custom": {"_0": {"directoryBasename": key}}}

    spaces = {
        "space-home": {
            "title": "Home",
            "profile": {"default": True},
            "customInfo": {"iconType": {"emoji_v2": "🏡"}},
            "containerIDs": ["unpinned", "home-open", "pinned", "home-pins"],
        },
        "space-research": {
            "title": "Research",
            "profile": custom("Profile 1"),
            "customInfo": {"iconType": {"emoji_v2": "🔬"}},
            "containerIDs": ["pinned", "research-pins", "unpinned", "research-open"],
        },
        "space-reading": {
            "title": "Reading",
            "profile": custom("Profile 1"),
            "customInfo": {"iconType": {"emoji_v2": "📖"}},
            "containerIDs": ["pinned", "reading-pins", "unpinned", "reading-open"],
        },
    }

    def flatten(value):
        return [item for pair in value.items() for item in pair]

    write_json(
        arc / "StorableSidebar.json",
        {
            "sidebar": {
                "containers": [
                    {"global": {}},
                    {
                        "items": flatten(items),
                        "spaces": flatten(spaces),
                        "topAppsContainerIDs": [
                            {"default": True},
                            "ess-default",
                            custom("Profile 1"),
                            "ess-research",
                            custom("Profile 2"),
                            "ess-unused",
                        ],
                    },
                ]
            }
        },
    )
    write_json(
        arc / "User Data" / "Local State",
        {
            "profile": {
                "info_cache": {
                    "Default": {"name": "Home"},
                    "Profile 1": {"name": "Research"},
                    "Profile 2": {"name": "Sandbox"},
                }
            }
        },
    )
    state = {
        "spaces": [
            {
                "uuid": "existing-space",
                "name": "Existing Zen",
                "icon": "🌱",
                "containerTabId": 0,
                "theme": {"type": "gradient", "gradientColors": [], "opacity": 0.5, "texture": 0},
            }
        ],
        "tabs": [
            {
                "zenSyncId": "existing-tab",
                "zenWorkspace": "existing-space",
                "entries": [{"url": "https://example.test/existing", "title": "Existing Zen tab"}],
                "index": 1,
                "pinned": False,
            }
        ],
        "folders": [],
        "groups": [],
    }
    write_session(zen / "zen-sessions.jsonlz4", state)
    session = {
        "version": ["sessionrestore", 1],
        "windows": [{**state, "selected": 1, "activeZenSpace": "existing-space"}],
        "cookies": [],
        "_closedWindows": [],
        "session": {},
    }
    write_session(zen / "sessionstore.jsonlz4", session)
    write_session(zen / "sessionstore-backups/recovery.jsonlz4", session)
    write_json(zen / "containers.json", {"version": 8, "lastUserContextId": 0, "identities": []})
    (zen / "prefs.js").write_text("// Fictional test profile.\n")
    (zen.parent.parent / "profiles.ini").write_text(
        "[Profile0]\nName=Fictional Zen\nIsRelative=1\nPath=Profiles/demo.default\n"
    )
    for name in ("Default", "Profile 1", "Profile 2"):
        profile = arc / "User Data" / name
        profile.mkdir(parents=True)
        with sqlite3.connect(profile / "History") as db:
            db.executescript(
                "CREATE TABLE urls(id INTEGER PRIMARY KEY,url TEXT,title TEXT,typed_count INTEGER); CREATE TABLE visits(id INTEGER PRIMARY KEY,url INTEGER,visit_time INTEGER,from_visit INTEGER,transition INTEGER);"
            )
            db.execute(
                "INSERT INTO urls VALUES(1,?,?,1)", ("https://example.test/history", "Fictional history")
            )
            db.execute("INSERT INTO visits VALUES(1,1,?,0,1)", (CHROME_EPOCH + 1_700_000_000_000_000,))
        with sqlite3.connect(profile / "Web Data") as db:
            db.execute(
                "CREATE TABLE autofill(name TEXT,value TEXT,date_created INTEGER,date_last_used INTEGER,count INTEGER)"
            )
            db.execute("INSERT INTO autofill VALUES('search','fictional example',1700000000,1700000001,1)")
        with sqlite3.connect(profile / "Login Data") as db:
            db.execute(
                "CREATE TABLE logins(origin_url TEXT,username_value TEXT,password_value BLOB,blacklisted_by_user INTEGER)"
            )
    write_json(
        arc / "User Data/Default/Bookmarks",
        {
            "roots": {
                "bookmark_bar": {
                    "type": "folder",
                    "name": "Bookmarks Bar",
                    "children": [
                        {
                            "type": "url",
                            "name": "Example guide",
                            "url": "https://example.test/bookmark",
                            "date_added": str(CHROME_EPOCH + 1_700_000_000_000_000),
                        }
                    ],
                }
            }
        },
    )
    with sqlite3.connect(zen / "places.sqlite") as db:
        db.executescript("""
            CREATE TABLE moz_origins(id INTEGER PRIMARY KEY,prefix TEXT,host TEXT,frecency INTEGER,recalc_frecency INTEGER DEFAULT 0,recalc_alt_frecency INTEGER DEFAULT 0,UNIQUE(prefix,host));
            CREATE TABLE moz_places(id INTEGER PRIMARY KEY,url TEXT,title TEXT,rev_host TEXT,guid TEXT UNIQUE,url_hash INTEGER,origin_id INTEGER REFERENCES moz_origins(id),visit_count INTEGER DEFAULT 0,last_visit_date INTEGER,typed INTEGER DEFAULT 0,foreign_count INTEGER DEFAULT 0,recalc_frecency INTEGER DEFAULT 0,recalc_alt_frecency INTEGER DEFAULT 0);
            CREATE TABLE moz_historyvisits(id INTEGER PRIMARY KEY,from_visit INTEGER,place_id INTEGER REFERENCES moz_places(id),visit_date INTEGER,visit_type INTEGER,session INTEGER,source INTEGER DEFAULT 0);
            CREATE INDEX visits_place ON moz_historyvisits(place_id);
            CREATE TABLE moz_bookmarks(id INTEGER PRIMARY KEY,type INTEGER,fk INTEGER REFERENCES moz_places(id),parent INTEGER,position INTEGER,title TEXT,dateAdded INTEGER,lastModified INTEGER,guid TEXT UNIQUE);
            INSERT INTO moz_bookmarks VALUES(1,2,NULL,0,0,'Other Bookmarks',0,0,'unfiled_____');
        """)
        db.execute("INSERT INTO moz_origins(id,prefix,host,frecency) VALUES(1,'https://','example.test',1)")
        db.execute(
            "INSERT INTO moz_places(id,url,title,rev_host,guid,url_hash,origin_id) VALUES(1,?,'Existing','.tset.elpmaxe','existing____',?,1)",
            ("https://example.test/existing", url_hash("https://example.test/existing")),
        )
    with sqlite3.connect(zen / "formhistory.sqlite") as db:
        db.execute(
            "CREATE TABLE moz_formhistory(id INTEGER PRIMARY KEY,fieldname TEXT,value TEXT,timesUsed INTEGER,firstUsed INTEGER,lastUsed INTEGER,guid TEXT)"
        )
    with sqlite3.connect(zen / "cookies.sqlite") as db:
        db.execute(
            "CREATE TABLE moz_cookies(id INTEGER PRIMARY KEY,originAttributes TEXT,name TEXT,value TEXT,host TEXT,path TEXT,expiry INTEGER,lastAccessed INTEGER,creationTime INTEGER,isSecure INTEGER,isHttpOnly INTEGER,sameSite INTEGER,schemeMap INTEGER,updateTime INTEGER,UNIQUE(name,host,path,originAttributes))"
        )
    return arc, zen


def public_preview(data) -> dict:
    """Only synthetic data should be used for repository screenshots."""
    return json.loads(json.dumps(data.summary()))
