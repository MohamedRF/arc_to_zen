from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Tab:
    id: str
    url: str
    title: str
    folder: tuple[str, ...] = ()  # Source folder IDs, not names.
    pinned: bool = True
    essential: bool = False


@dataclass(frozen=True)
class Folder:
    id: str
    name: str
    parent: str | None
    children: tuple[str, ...]
    collapsed: bool = True


@dataclass
class Space:
    id: str
    name: str
    profile: str
    icon: str = ""
    color: tuple[int, int, int] | None = None
    tabs: list[Tab] = field(default_factory=list)
    folders: list[Folder] = field(default_factory=list)
    roots: list[str] = field(default_factory=list)


@dataclass
class ArcData:
    spaces: list[Space]
    fingerprint: str
    warnings: Counter = field(default_factory=Counter)

    def summary(self) -> dict[str, Any]:
        return {
            "spaces": len(self.spaces),
            "profiles": len({s.profile for s in self.spaces}),
            "tabs": sum(len(s.tabs) for s in self.spaces),
            "essentials": sum(t.essential for s in self.spaces for t in s.tabs),
            "open_tabs": sum(not t.pinned for s in self.spaces for t in s.tabs),
            "folders": sum(len(s.folders) for s in self.spaces),
            "warnings": dict(self.warnings),
        }


@dataclass(frozen=True)
class Options:
    history: bool = True
    bookmarks: bool = True
    forms: bool = True
    favicons: bool = True
    cookies: bool = False
    replace: bool = False


class BridgeError(Exception):
    """A user-presentable error. Messages must not include browser contents."""
