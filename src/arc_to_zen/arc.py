from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

from .io import read_json
from .models import ArcData, BridgeError, Folder, Space, Tab


def pairs(value) -> list[tuple]:
    if isinstance(value, dict):
        return list(value.items())
    if not isinstance(value, list) or len(value) % 2:
        raise BridgeError("Arc's sidebar has an unsupported key/value structure.")
    return list(zip(value[::2], value[1::2], strict=True))


def profile_key(value: dict | None) -> str:
    return (value or {}).get("custom", {}).get("_0", {}).get("directoryBasename", "Default")


def space_color(info: dict) -> tuple[int, int, int] | None:
    theme = info.get("windowTheme", {})
    background = theme.get("background", {}).get("single", {}).get("_0", {})
    color = (
        background.get("style", {})
        .get("color", {})
        .get("_0", {})
        .get("blendedSingleColor", {})
        .get("_0", {})
        .get("color")
    )
    color = color or theme.get("primaryColorPalette", {}).get("midTone")
    if color and all(k in color for k in ("red", "green", "blue")):
        return tuple(round(max(0, min(1, color[k])) * 255) for k in ("red", "green", "blue"))
    return None


def extract(root: Path) -> ArcData:
    sidebar = root / "StorableSidebar.json"
    if not sidebar.is_file():
        raise BridgeError("Choose the Arc folder containing StorableSidebar.json.")
    raw = sidebar.read_bytes()
    data = read_json(sidebar)
    containers = data.get("sidebar", {}).get("containers", [])
    container = next((c for c in containers if isinstance(c, dict) and "items" in c and "spaces" in c), None)
    if container is None:
        raise BridgeError("This Arc sidebar version is not supported; no files were changed.")
    items = dict(pairs(container["items"]))
    warnings = Counter()
    spaces: list[Space] = []
    for sid, source in pairs(container["spaces"]):
        info = source.get("customInfo", {})
        space = Space(
            str(sid),
            source.get("title") or "Untitled space",
            profile_key(source.get("profile")),
            info.get("iconType", {}).get("emoji_v2", ""),
            space_color(info),
        )
        visited: set[str] = set()

        def walk(ids: list[str], folder: tuple[str, ...], pinned: bool, visited=visited, space=space) -> None:
            for item_id in ids:
                if item_id in visited:
                    raise BridgeError("Arc's sidebar contains a repeated or cyclic item reference.")
                visited.add(item_id)
                item = items.get(item_id)
                if not item:
                    warnings["missing_item_references"] += 1
                    continue
                content = item.get("data", {})
                if "tab" in content:
                    url = content["tab"].get("savedURL")
                    if url:
                        space.tabs.append(
                            Tab(
                                item_id,
                                url,
                                item.get("title") or content["tab"].get("savedTitle") or "Untitled tab",
                                folder,
                                pinned,
                            )
                        )
                    else:
                        warnings["tabs_without_saved_url"] += 1
                elif "list" in content:
                    if not pinned:
                        warnings["unpinned_folder_structure_flattened"] += 1
                        walk(item.get("childrenIds", []), folder, pinned)
                        continue
                    child_ids = tuple(item.get("childrenIds", []))
                    space.folders.append(
                        Folder(
                            item_id,
                            item.get("title") or "Untitled folder",
                            folder[-1] if folder else None,
                            child_ids,
                            content["list"].get("isCollapsed", True),
                        )
                    )
                    walk(list(child_ids), (*folder, item_id), pinned)
                else:
                    warnings["unsupported_sidebar_items"] += 1

        sections = source.get("containerIDs", [])
        for marker in ("pinned", "unpinned"):
            if marker not in sections:
                warnings["missing_sidebar_section"] += 1
                continue
            index = sections.index(marker) + 1
            if index >= len(sections) or sections[index] not in items:
                raise BridgeError("An Arc space points to a missing section container.")
            roots = items[sections[index]].get("childrenIds", [])
            space.roots.extend(roots)
            walk(roots, (), marker == "pinned")
        # Empty spaces are meaningful; never filter them out.
        spaces.append(space)

    local_state = root / "User Data" / "Local State"
    names = read_json(local_state).get("profile", {}).get("info_cache", {}) if local_state.exists() else {}
    for raw_profile, container_id in pairs(container.get("topAppsContainerIDs", [])):
        profile = profile_key(raw_profile)
        matches = [s for s in spaces if s.profile == profile]
        children = items.get(container_id, {}).get("childrenIds", [])
        if not matches and children:
            label = names.get(profile, {}).get("name") or "Unused Arc profile"
            matches = [Space("unused-profile:" + profile, label + " (unused profile)", profile, "💼")]
            spaces.extend(matches)
        # Essentials are shared by an Arc profile. Store one copy in its first
        # workspace; Zen's container-specific Essentials show it in every space.
        if matches:
            for item_id in children:
                item = items.get(item_id, {})
                content = item.get("data", {}).get("tab", {})
                if content.get("savedURL"):
                    matches[0].tabs.append(
                        Tab(
                            item_id,
                            content["savedURL"],
                            item.get("title") or content.get("savedTitle") or "Untitled Essential",
                            (),
                            True,
                            True,
                        )
                    )
                else:
                    warnings["essentials_without_saved_url"] += 1
    if not spaces:
        raise BridgeError("No Arc spaces were found.")
    return ArcData(spaces, hashlib.sha256(raw).hexdigest(), warnings)
