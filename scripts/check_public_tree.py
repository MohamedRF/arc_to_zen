"""Fail closed on source-tree browser exports, personal paths, or credential tokens."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SUFFIXES = {".csv", ".sqlite", ".db", ".json", ".jsonlz4", ".bak", ".log"}
SENSITIVE = [
    re.compile(p, re.IGNORECASE)
    for p in [
        "/" + "Users" + r"/[^\s/]+/",
        r"[A-Z0-9._%+-]+@(?:gmail|outlook|hotmail)\.com",
        r"gh[pousr]_[A-Za-z0-9]{25,}",
        r"github_pat_[A-Za-z0-9_]{30,}",
        r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----",
    ]
]


def main() -> int:
    paths = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
        )
        .decode()
        .split("\0")
    )
    paths = sorted({name for name in paths if name and (ROOT / name).is_file()})
    failed = []
    for name in filter(None, paths):
        path = ROOT / name
        if path.suffix in FORBIDDEN_SUFFIXES or any(
            part in ("browser-data", "backups", "runtime", ".venv", "dist")
            for part in path.relative_to(ROOT).parts
        ):
            failed.append(name + ": browser/runtime artifact must not be tracked")
            continue
        if path.suffix.lower() in (".png", ".icns"):
            if name not in {"docs/preview.png", "assets/icon.icns"}:
                failed.append(name + ": review and explicitly allow-list synthetic images")
            continue  # Reviewed, fictional app previews and original icon only.
        value = path.read_text(encoding="utf-8", errors="replace")
        for pattern in SENSITIVE:
            if pattern.search(value):
                failed.append(name + ": possible private path or credential (value redacted)")
                break
    if failed:
        print("\n".join(failed))
        return 1
    print(
        f"Privacy check passed for {len([p for p in paths if p])} source files. No browser exports or credential patterns detected."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
