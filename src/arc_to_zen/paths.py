from __future__ import annotations

import configparser
import subprocess
from pathlib import Path

from .models import BridgeError


def defaults() -> tuple[Path, Path, Path]:
    support = Path.home() / "Library" / "Application Support"
    # Reuse existing run folders so upgrades keep previous backups discoverable.
    legacy = support / "Arc2Zen Bridge"
    runtime = legacy if legacy.exists() else support / "arc_to_zen"
    return support / "Arc", support / "zen", runtime


def discover_profiles(root: Path) -> list[tuple[str, Path]]:
    ini = root / "profiles.ini"
    if not ini.exists():
        return []
    config = configparser.ConfigParser(interpolation=None)
    config.read(ini)
    result = []
    preferred = [config[s].get("Default") for s in config.sections() if s.startswith("Install")]
    for section in config.sections():
        if not section.startswith("Profile"):
            continue
        p = config[section]
        path = Path(p.get("Path", ""))
        if p.get("IsRelative", "1") == "1":
            path = root / path
        if (path / "zen-sessions.jsonlz4").is_file():
            result.append((p.get("Name", "Zen profile"), path.resolve()))
    result.sort(
        key=lambda item: (
            str(item[1].relative_to(root.resolve())) not in preferred
            if item[1].is_relative_to(root.resolve())
            else True
        )
    )
    return result


def source_profile(root: Path, key: str) -> Path:
    if key in ("", ".", "..") or Path(key).name != key:
        raise BridgeError("An Arc profile name is unsafe; no files were changed.")
    base = (root / "User Data").resolve()
    path = base / key
    if path.is_symlink() or not path.resolve().is_relative_to(base):
        raise BridgeError("Arc profile symlinks are not supported.")
    return path


def all_source_profiles(root: Path) -> list[Path]:
    base = root / "User Data"
    if not base.exists():
        return []
    return sorted((p for p in base.iterdir() if p.is_dir() and not p.is_symlink()), key=lambda p: p.name)


def ensure_closed() -> None:
    result = subprocess.run(["/bin/ps", "-axo", "comm="], capture_output=True, text=True, check=True)
    running = result.stdout.splitlines()
    if any("/Arc.app/" in p or "/Zen.app/" in p for p in running):
        raise BridgeError(
            "Quit Arc and Zen completely before migration or recovery. arc_to_zen will not force-close them."
        )


def safe_runtime_location(runtime: Path, arc: Path, zen: Path) -> None:
    root = runtime.resolve()
    for browser in (arc.resolve(), zen.resolve()):
        if root == browser or root.is_relative_to(browser) or browser.is_relative_to(root):
            raise BridgeError("The backup/output folder must be separate from both browser folders.")
    for output in (root, zen.resolve()):
        if any((parent / ".git").exists() for parent in (output, *output.parents)):
            raise BridgeError(
                "Browser backups and migrated profiles cannot be written inside a Git repository."
            )
