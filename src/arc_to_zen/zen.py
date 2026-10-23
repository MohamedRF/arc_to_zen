from __future__ import annotations

import copy
import time
import uuid
from collections import Counter
from pathlib import Path

from .io import read_json, read_session, write_json, write_session
from .models import ArcData, BridgeError

NAMESPACE = uuid.UUID("967c2341-2981-4bd6-bf0c-66299a782d1c")


def stable_id(kind: str, source: str) -> str:
    return "{" + str(uuid.uuid5(NAMESPACE, kind + ":" + source)) + "}"


def tab_url(tab: dict) -> str:
    entries = tab.get("entries", [])
    if not entries:
        return ""
    return entries[min(max(tab.get("index", 1) - 1, 0), len(entries) - 1)].get("url", "")


def validate_template(profile: Path) -> None:
    if not profile.is_dir() or not (profile / "zen-sessions.jsonlz4").exists():
        raise BridgeError("Choose an initialized Zen profile. Open and quit Zen once first.")
    value = read_session(profile / "zen-sessions.jsonlz4")
    if not all(isinstance(value.get(k), list) for k in ("tabs", "spaces", "folders", "groups")):
        raise BridgeError("The Zen workspace schema is unsupported; no files were changed.")
    session = profile / "sessionstore.jsonlz4"
    if not session.exists() or not read_session(session).get("windows"):
        raise BridgeError("Zen has no saved window. Open a normal window and quit Zen first.")


def contexts(profile: Path, source_profiles: list[str]) -> dict[str, int]:
    path = profile / "containers.json"
    value = read_json(path) if path.exists() else {"version": 8, "lastUserContextId": 0, "identities": []}
    previous = profile / "arc2zen-bridge-state.json"
    old = read_json(previous).get("contexts", {}) if previous.exists() else {}
    identities = value.setdefault("identities", [])
    existing = {i["userContextId"] for i in identities}
    next_id = max([value.get("lastUserContextId", 0), *[i for i in existing if 0 < i < 4294967295]])
    result = {}
    colors = ["blue", "orange", "green", "purple", "pink", "turquoise", "red"]
    for index, key in enumerate(source_profiles):
        if key in old and old[key] in existing:
            result[key] = old[key]
            continue
        next_id += 1
        result[key] = next_id
        identities.append(
            {
                "userContextId": next_id,
                "public": True,
                "icon": "fingerprint",
                "color": colors[index % len(colors)],
                "name": "Arc · " + key,
            }
        )
    value["lastUserContextId"] = next_id
    write_json(path, value)
    return result


def create_tab(source, space_id: str, context: int, image: str | None) -> dict:
    entry = {"url": source.url, "title": source.title}
    value = {
        "entries": [entry],
        "index": 1,
        "lastAccessed": int(time.time() * 1000),
        "pinned": source.pinned,
        "hidden": False,
        "zenWorkspace": space_id,
        "zenSyncId": stable_id("tab", source.id),
        "zenEssential": source.essential,
        "userContextId": context,
        "zenDefaultUserContextId": context,
        "zenIsEmpty": False,
        "attributes": {},
        "userTypedValue": None,
        "userTypedClear": 0,
    }
    if source.folder:
        value["groupId"] = stable_id("folder", source.folder[-1])
    if source.pinned:
        value["_zenPinnedInitialState"] = {"entry": entry.copy()}
    if image:
        value["image"] = image
        if source.pinned:
            value["_zenPinnedInitialState"]["image"] = image
    return value


def import_sidebar(profile: Path, data: ArcData, images: dict[tuple[str, str], str] | None = None) -> dict:
    validate_template(profile)
    path = profile / "zen-sessions.jsonlz4"
    value = read_session(path)
    state_path = profile / "arc2zen-bridge-state.json"
    previous = read_json(state_path) if state_path.exists() else {}
    old_workspaces = set(previous.get("workspace_ids", []))
    old_tabs = set(previous.get("tab_ids", []))
    old_folders = set(previous.get("folder_ids", []))
    # Only refresh data owned by a previous Bridge run. Existing Zen data remains.
    for key, ids, field in (
        ("spaces", old_workspaces, "uuid"),
        ("tabs", old_tabs, "zenSyncId"),
        ("folders", old_folders, "id"),
        ("groups", old_folders, "id"),
    ):
        value[key] = [v for v in value[key] if v.get(field) not in ids]
    context_map = contexts(profile, list(dict.fromkeys(s.profile for s in data.spaces)))
    generated_tabs, generated_folders, generated_groups, generated_spaces = [], [], [], []
    for space in data.spaces:
        sid = stable_id("space", space.id)
        ctx = context_map[space.profile]
        theme = {"type": "gradient", "gradientColors": [], "opacity": 0.8, "texture": 0}
        if space.color is not None:
            theme["gradientColors"] = [
                {
                    "c": list(space.color),
                    "isCustom": False,
                    "algorithm": "",
                    "isPrimary": True,
                    "lightness": 50,
                    "type": "explicit-lightness",
                }
            ]
        generated_spaces.append(
            {
                "uuid": sid,
                "name": space.name,
                "icon": space.icon,
                "containerTabId": ctx,
                "theme": theme,
                "hasCollapsedPinnedTabs": False,
            }
        )
        folders = {f.id: f for f in space.folders}
        tabs = {t.id: t for t in space.tabs}
        ordered = []
        for source in space.tabs:
            if source.essential:
                ordered.append(create_tab(source, sid, ctx, (images or {}).get((space.profile, source.url))))

        def walk(
            ids: list | tuple,
            folders=folders,
            tabs=tabs,
            ordered=ordered,
            sid=sid,
            ctx=ctx,
            profile_key=space.profile,
        ) -> None:
            previous_sibling = None
            for item_id in ids:
                if item_id in folders:
                    folder = folders[item_id]
                    fid = stable_id("folder", folder.id)
                    empty_ids = []
                    # Firefox tab groups require a tab anchor even when a group
                    # contains only nested groups. Put it at the right position.
                    if not any(child in tabs for child in folder.children):
                        anchor_id = stable_id("anchor", folder.id)
                        empty_ids.append(anchor_id)
                        ordered.append(
                            {
                                "entries": [{"url": "about:blank", "title": ""}],
                                "index": 1,
                                "pinned": True,
                                "hidden": True,
                                "zenIsEmpty": True,
                                "zenEssential": False,
                                "zenWorkspace": sid,
                                "zenSyncId": anchor_id,
                                "userContextId": ctx,
                                "zenDefaultUserContextId": ctx,
                                "groupId": fid,
                                "attributes": {"zen-empty-tab": "true"},
                            }
                        )
                    generated_folders.append(
                        {
                            "id": fid,
                            "name": folder.name,
                            "pinned": True,
                            "splitViewGroup": False,
                            "collapsed": folder.collapsed,
                            "saveOnWindowClose": True,
                            "parentId": stable_id("folder", folder.parent) if folder.parent else None,
                            "prevSiblingInfo": previous_sibling,
                            "emptyTabIds": empty_ids,
                            "userIcon": "",
                            "workspaceId": sid,
                        }
                    )
                    generated_groups.append(
                        {
                            "id": fid,
                            "name": folder.name,
                            "pinned": True,
                            "splitView": False,
                            "collapsed": folder.collapsed,
                            "saveOnWindowClose": True,
                            "color": "zen-workspace-color",
                        }
                    )
                    walk(folder.children)
                    previous_sibling = {"type": "group", "id": fid}
                elif item_id in tabs and not tabs[item_id].essential:
                    tab = tabs[item_id]
                    ordered.append(create_tab(tab, sid, ctx, (images or {}).get((profile_key, tab.url))))
                    previous_sibling = {"type": "tab", "id": stable_id("tab", tab.id)}

        walk(space.roots)
        generated_tabs.extend(ordered)
    if len({t["zenSyncId"] for t in generated_tabs}) != len(generated_tabs):
        raise BridgeError("The source contains conflicting tab IDs; migration was not committed.")
    value["spaces"].extend(generated_spaces)
    value["tabs"].extend(generated_tabs)
    value["folders"].extend(generated_folders)
    value["groups"].extend(generated_groups)
    value["lastCollected"] = int(time.time() * 1000)
    write_session(path, value)

    for session_path in (
        profile / "sessionstore.jsonlz4",
        profile / "sessionstore-backups" / "recovery.jsonlz4",
    ):
        if not session_path.exists():
            continue
        session = read_session(session_path)
        windows = session.get("windows", [])
        if not windows:
            raise BridgeError("A Zen restore file has no window; migration was not committed.")
        for window in windows:
            window["tabs"] = [t for t in window.get("tabs", []) if t.get("zenSyncId") not in old_tabs]
            window["spaces"] = copy.deepcopy(value["spaces"])
            window["folders"] = copy.deepcopy(value["folders"])
            window["groups"] = copy.deepcopy(value["groups"])
            window["selected"] = min(max(1, window.get("selected", 1)), max(1, len(window["tabs"])))
        windows[0]["tabs"].extend(copy.deepcopy(generated_tabs))
        # Existing cookies and recently closed windows/tabs are retained.
        write_session(session_path, session)
    state = {
        "version": 1,
        "source_fingerprint": data.fingerprint,
        "contexts": context_map,
        "workspace_ids": [s["uuid"] for s in generated_spaces],
        "tab_ids": [t["zenSyncId"] for t in generated_tabs],
        "folder_ids": [f["id"] for f in generated_folders],
    }
    write_json(state_path, state)
    prefs = profile / "prefs.js"
    text = prefs.read_text() if prefs.exists() else ""
    # Last definition wins. No security, telemetry, or extension permissions change.
    text += '\nuser_pref("zen.workspaces.separate-essentials", true);\nuser_pref("privacy.userContext.enabled", true);\nuser_pref("zen.view.use-single-toolbar", true);\n'
    from .io import atomic_bytes

    atomic_bytes(prefs, text.encode())
    return context_map


def verify_sidebar(profile: Path, data: ArcData) -> dict:
    value = read_session(profile / "zen-sessions.jsonlz4")
    state = read_json(profile / "arc2zen-bridge-state.json")
    folders = {f["id"]: f for f in value["folders"]}

    def folder_path(fid: str | None, visiting: frozenset = frozenset()) -> tuple:
        if fid is None:
            return ()
        if fid in visiting or fid not in folders:
            raise BridgeError("Zen folder nesting failed verification.")
        f = folders[fid]
        return (*folder_path(f.get("parentId"), visiting | {fid}), fid)

    expected, actual = Counter(), Counter()
    expected_folders = set()
    for s in data.spaces:
        sid = stable_id("space", s.id)
        for t in s.tabs:
            expected[sid, tuple(stable_id("folder", f) for f in t.folder), t.url, t.pinned, t.essential] += 1
        expected_folders.update(stable_id("folder", f.id) for f in s.folders)
    for t in value["tabs"]:
        if t.get("zenSyncId") not in state["tab_ids"] or t.get("zenIsEmpty"):
            continue
        actual[
            t.get("zenWorkspace"),
            folder_path(t.get("groupId")),
            tab_url(t),
            bool(t.get("pinned")),
            bool(t.get("zenEssential")),
        ] += 1
    if expected != actual or not expected_folders.issubset(folders):
        raise BridgeError("Tab URLs, pin state, Essentials, or folder paths failed verification.")
    generated_spaces = [s for s in value["spaces"] if s["uuid"] in state["workspace_ids"]]
    if [s["uuid"] for s in generated_spaces] != [stable_id("space", s.id) for s in data.spaces]:
        raise BridgeError("Workspace order failed verification.")
    for s, target in zip(data.spaces, generated_spaces, strict=True):
        if (
            target["name"] != s.name
            or target.get("icon", "") != s.icon
            or target.get("containerTabId") != state["contexts"][s.profile]
        ):
            raise BridgeError("Workspace appearance or profile separation failed verification.")
    expected_sync = set(state["tab_ids"])
    for p in (profile / "sessionstore.jsonlz4", profile / "sessionstore-backups/recovery.jsonlz4"):
        if p.exists():
            present = {
                t.get("zenSyncId") for w in read_session(p).get("windows", []) for t in w.get("tabs", [])
            }
            if not expected_sync.issubset(present):
                raise BridgeError("Zen's two session stores do not contain matching migrated tabs.")
    return {
        "verified_tabs": sum(expected.values()),
        "verified_folders": len(expected_folders),
        "missing_tabs": 0,
        "workspace_order": "verified",
        "dual_sessions": "verified",
    }
