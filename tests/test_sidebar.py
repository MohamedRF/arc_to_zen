from collections import Counter

import pytest

from arc2zen_bridge.arc import extract
from arc2zen_bridge.io import read_json, read_session, write_json, write_session
from arc2zen_bridge.models import BridgeError
from arc2zen_bridge.zen import import_sidebar, stable_id, verify_sidebar


def test_empty_spaces_essentials_only_shared_profiles_and_unused_profile(demo_paths):
    arc, _ = demo_paths
    data = extract(arc)
    assert [s.name for s in data.spaces] == ["Home", "Research", "Reading", "Sandbox (unused profile)"]
    assert data.summary() == {
        "spaces": 4,
        "profiles": 3,
        "tabs": 7,
        "essentials": 3,
        "open_tabs": 1,
        "folders": 3,
        "warnings": {},
    }
    assert len(data.spaces[1].tabs) == 1  # Essentials-only space, never dropped.
    assert len(data.spaces[2].tabs) == 0  # Empty space still retained.


def test_nested_paths_order_empty_anchors_and_both_stores(demo_paths):
    arc, zen = demo_paths
    data = extract(arc)
    contexts = import_sidebar(zen, data)
    assert len(set(contexts.values())) == 3
    value = read_session(zen / "zen-sessions.jsonlz4")
    generated = [t for t in value["tabs"] if t.get("zenWorkspace") == stable_id("space", "space-home")]
    assert [t["entries"][0]["url"].split("/")[-1] for t in generated] == [
        "essential-mail",
        "tab-guide",
        "tab-reference",
        "tab-notes",
        "about:blank",
        "tab-open",
    ]
    assert next(t for t in generated if t["entries"][0]["url"].endswith("tab-open"))["pinned"] is False
    assert verify_sidebar(zen, data)["missing_tabs"] == 0
    assert any(t["zenSyncId"] == "existing-tab" for t in value["tabs"])
    assert [s["name"] for s in value["spaces"]][:1] == ["Existing Zen"]


def test_reimport_refreshes_owned_data_without_duplicates(demo_paths):
    arc, zen = demo_paths
    data = extract(arc)
    import_sidebar(zen, data)
    first = read_session(zen / "zen-sessions.jsonlz4")
    import_sidebar(zen, data)
    second = read_session(zen / "zen-sessions.jsonlz4")
    assert Counter(t["zenSyncId"] for t in first["tabs"]) == Counter(t["zenSyncId"] for t in second["tabs"])
    assert len(read_json(zen / "containers.json")["identities"]) == 3
    assert verify_sidebar(zen, data)["verified_tabs"] == 7


def test_verifier_catches_open_tabs_missing_from_second_store(demo_paths):
    arc, zen = demo_paths
    data = extract(arc)
    import_sidebar(zen, data)
    value = read_session(zen / "sessionstore.jsonlz4")
    value["windows"][0]["tabs"] = [
        t for t in value["windows"][0]["tabs"] if t.get("zenSyncId") != stable_id("tab", "tab-open")
    ]
    write_session(zen / "sessionstore.jsonlz4", value)
    with pytest.raises(BridgeError, match="matching migrated tabs"):
        verify_sidebar(zen, data)


def test_verifier_catches_wrong_folder_and_pin_state(demo_paths):
    arc, zen = demo_paths
    data = extract(arc)
    import_sidebar(zen, data)
    value = read_session(zen / "zen-sessions.jsonlz4")
    tab = next(t for t in value["tabs"] if t["zenSyncId"] == stable_id("tab", "tab-guide"))
    tab["groupId"] = None
    tab["pinned"] = False
    write_session(zen / "zen-sessions.jsonlz4", value)
    with pytest.raises(BridgeError, match="failed verification"):
        verify_sidebar(zen, data)


def test_duplicate_space_names_have_distinct_ids(demo_paths):
    arc, zen = demo_paths
    path = arc / "StorableSidebar.json"
    raw = read_json(path)
    raw["sidebar"]["containers"][1]["spaces"][3]["title"] = "Home"
    write_json(path, raw)
    data = extract(arc)
    import_sidebar(zen, data)
    assert verify_sidebar(zen, data)["verified_tabs"] == 7
    value = read_session(zen / "zen-sessions.jsonlz4")
    assert len([s for s in value["spaces"] if s["name"] == "Home"]) == 2


def test_cyclic_folder_reference_is_rejected(demo_paths):
    arc, _ = demo_paths
    path = arc / "StorableSidebar.json"
    raw = read_json(path)
    entries = raw["sidebar"]["containers"][1]["items"]
    index = entries.index("folder-library")
    entries[index + 1]["childrenIds"].append("folder-library")
    write_json(path, raw)
    with pytest.raises(BridgeError, match="cyclic"):
        extract(arc)
