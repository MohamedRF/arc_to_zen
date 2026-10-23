"""Build a self-contained app, ZIP, and DMG from source. No browser reads."""

from __future__ import annotations

import hashlib
import os
import platform
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from arc_to_zen import __version__

ROOT = Path(__file__).resolve().parents[1]


def icon(build: Path) -> Path:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    app = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(ROOT / "assets/icon.svg"))
    iconset = build / "arc_to_zen.iconset"
    iconset.mkdir(exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            pixels = size * scale
            image = QImage(pixels, pixels, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(0)
            painter = QPainter(image)
            renderer.render(painter, QRectF(0, 0, pixels, pixels))
            painter.end()
            image.save(str(iconset / f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"))
    output = build / "arc_to_zen.icns"
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(output)], check=True)
    del app
    return output


def main():
    if sys.platform != "darwin":
        raise SystemExit("Build the macOS app on macOS; core tests can run elsewhere.")
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    app_icon = icon(build)
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--windowed",
        "--onedir",
        "--name",
        "arc_to_zen",
        "--osx-bundle-identifier",
        "io.github.mohamedrf.arc-to-zen",
        "--icon",
        str(app_icon),
        "--paths",
        str(ROOT / "src"),
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(build / "pyinstaller"),
        "--specpath",
        str(build),
        "--collect-data",
        "arc_to_zen",
        "--add-data",
        str(ROOT / "LICENSE") + ":.",
        "--add-data",
        str(ROOT / "THIRD_PARTY_NOTICES.md") + ":.",
    ]
    for package in ("PySide6_Essentials", "shiboken6", "cryptography", "lz4"):
        args.extend(["--copy-metadata", package])
    args.append(str(ROOT / "scripts/launch_app.py"))
    subprocess.run(args, check=True, cwd=ROOT)
    application = ROOT / "dist/arc_to_zen.app"
    plist_path = application / "Contents/Info.plist"
    with plist_path.open("rb") as stream:
        plist = plistlib.load(stream)
    plist.update(
        CFBundleShortVersionString=__version__,
        CFBundleVersion="1",
        LSMinimumSystemVersion="14.0",
        NSHighResolutionCapable=True,
    )
    with plist_path.open("wb") as stream:
        plistlib.dump(plist, stream)
    subprocess.run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(application)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(application)], check=True)
    arch = "arm64" if platform.machine() == "arm64" else "x64"
    stem = f"arc_to_zen-{__version__}-macos-{arch}"
    archive = ROOT / "dist" / (stem + ".zip")
    subprocess.run(
        ["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(application), str(archive)], check=True
    )
    dmg_stage = build / "dmg-stage"
    if dmg_stage.exists():
        shutil.rmtree(dmg_stage)
    dmg_stage.mkdir()
    shutil.copytree(application, dmg_stage / application.name, symlinks=True)
    (dmg_stage / "Applications").symlink_to("/Applications", target_is_directory=True)
    image = ROOT / "dist" / (stem + ".dmg")
    subprocess.run(
        [
            "hdiutil",
            "create",
            "-volname",
            "arc_to_zen",
            "-srcfolder",
            str(dmg_stage),
            "-ov",
            "-format",
            "UDZO",
            str(image),
        ],
        check=True,
    )
    checksum = ROOT / "dist" / (stem + ".sha256")
    checksum.write_text(
        "".join(hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n" for p in (archive, image))
    )
    print(f"Built {application.name}, {archive.name}, {image.name}; verified ad-hoc code signature.")


if __name__ == "__main__":
    main()
