import sqlite3

from arc_to_zen.models import Options
from arc_to_zen.standard import CHROME_EPOCH, import_forms, import_places, url_hash


def test_history_dedup_bookmark_hierarchy_and_forms(demo_paths):
    arc, zen = demo_paths
    result = import_places(arc, zen, Options())
    assert result["history_visits"] == 1
    assert result["duplicate_history_visits"] == 2
    assert result["bookmarks"] == 1
    assert import_forms(arc, zen) == {"form_entries": 1}
    assert import_forms(arc, zen) == {"form_entries": 0}
    again = import_places(arc, zen, Options())
    assert again.get("bookmarks", 0) == 0
    assert again.get("history_visits", 0) == 0
    with sqlite3.connect(zen / "places.sqlite") as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT COUNT(*) FROM moz_places WHERE url_hash=0").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM moz_bookmarks WHERE type=1").fetchone()[0] == 1


def test_new_history_imports_even_when_sidebar_unchanged(demo_paths):
    arc, zen = demo_paths
    import_places(arc, zen, Options())
    with sqlite3.connect(arc / "User Data/Default/History") as db:
        db.execute("INSERT INTO visits VALUES(2,1,?,1,0)", (CHROME_EPOCH + 1_700_000_001_000_000,))
    assert import_places(arc, zen, Options()).get("history_visits", 0) == 1


def test_unknown_target_hash_is_rejected_without_modification(demo_paths):
    import pytest

    from arc_to_zen.models import BridgeError

    arc, zen = demo_paths
    with sqlite3.connect(zen / "places.sqlite") as db:
        db.execute("UPDATE moz_places SET url_hash=1")
    with pytest.raises(BridgeError, match="unfamiliar URL hash"):
        import_places(arc, zen, Options())
    with sqlite3.connect(zen / "places.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM moz_historyvisits").fetchone()[0] == 0


def test_url_hash_uses_utf8_and_distinguishes_scheme():
    assert url_hash("https://example.test/") != url_hash("http://example.test/")
    assert url_hash("https://example.test/café") != url_hash("https://example.test/cafe")
    assert url_hash("https://example.test/a") >> 32 == url_hash("https://example.test/b") >> 32
