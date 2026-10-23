from __future__ import annotations

import hashlib
import os
import shutil
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from . import __version__
from .arc import extract
from .cookies import import_cookies
from .favicons import collect
from .io import read_json, write_json
from .models import BridgeError, Options
from .paths import ensure_closed, safe_runtime_location
from .secrets import ArcKey, export_passwords
from .standard import import_forms, import_places
from .zen import import_sidebar, validate_template, verify_sidebar

IGNORED_LOCKS = {".parentlock", "parent.lock", "lock", ".DS_Store"}
Progress = Callable[[str], None]
DEFAULT_OPTIONS = Options()


@dataclass(frozen=True)
class Result:
    run: Path
    profile: Path
    report: dict


def inventory(root: Path) -> dict[str, dict]:
    result = {}
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = [d for d in directories if d not in IGNORED_LOCKS]
        for name in [*directories, *files]:
            p = Path(current) / name
            if name in IGNORED_LOCKS:
                continue
            if p.is_symlink():
                raise BridgeError("Browser-folder symlinks are not supported; no live files were changed.")
            if p.is_file():
                h = hashlib.sha256()
                with p.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        h.update(block)
                result[str(p.relative_to(root))] = {"size": p.stat().st_size, "sha256": h.hexdigest()}
    return result


def copy_verified(source: Path, destination: Path) -> dict:
    expected = inventory(source)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(*IGNORED_LOCKS))
    os.chmod(destination, 0o700)
    if inventory(destination) != expected or inventory(source) != expected:
        raise BridgeError(
            "A browser folder changed during backup. The backup is not trusted; close both browsers and retry."
        )
    return expected


def ensure_inputs(arc: Path, target: Path, runtime: Path) -> None:
    if arc.is_symlink() or target.is_symlink():
        raise BridgeError("Choose browser folders directly rather than through symlinks.")
    arc, target = arc.resolve(), target.resolve()
    if arc == target or arc.is_relative_to(target) or target.is_relative_to(arc):
        raise BridgeError("Arc and Zen folders must be separate.")
    safe_runtime_location(runtime, arc, target)
    validate_template(target)


def migrate(
    arc: Path,
    target: Path,
    runtime: Path,
    options: Options = DEFAULT_OPTIONS,
    progress: Progress = lambda _: None,
) -> Result:
    arc, target, runtime = (
        arc.expanduser().absolute(),
        target.expanduser().absolute(),
        runtime.expanduser().absolute(),
    )
    ensure_inputs(arc, target, runtime)
    ensure_closed()
    progress("Checking source and target file manifests…")
    source_manifest, target_manifest = inventory(arc), inventory(target)
    preview = extract(arc)
    critical = {
        "missing_item_references",
        "unsupported_sidebar_items",
        "missing_sidebar_section",
        "unpinned_folder_structure_flattened",
    }
    if any(preview.warnings[k] for k in critical):
        raise BridgeError(
            "The Arc sidebar contains unsupported or missing structure. Review the scan warnings; migration is blocked to avoid an incomplete copy."
        )
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(runtime, 0o700)
    progress("Checking space for full browser-folder backups…")
    required = (
        sum(v["size"] for v in source_manifest.values())
        + 3 * sum(v["size"] for v in target_manifest.values())
        + 100 * 1024 * 1024
    )
    if shutil.disk_usage(runtime).free < required or shutil.disk_usage(target.parent).free < 2 * sum(
        v["size"] for v in target_manifest.values()
    ):
        raise BridgeError("There is not enough free space for verified backups and staging.")
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    run = runtime / "runs" / run_id
    run.mkdir(parents=True, mode=0o700)
    stage = target.parent / (".arc2zen-stage-" + run_id)
    rollback = target.parent / (".arc2zen-before-" + run_id)
    destination = target if options.replace else target.parent / ("arc-bridge-" + run_id)
    key = None
    committed = False
    try:
        progress("Backing up Arc locally and checking file hashes…")
        arc_manifest = copy_verified(arc, run / "arc-source")
        progress("Backing up the complete Zen profile and checking file hashes…")
        zen_manifest = copy_verified(target, run / "zen-before")
        write_json(run / "backup-manifest.json", {"arc": arc_manifest, "zen": zen_manifest})
        ensure_closed()
        if arc_manifest != source_manifest or zen_manifest != target_manifest:
            raise BridgeError("A browser changed after the preview. No migration was committed.")
        shutil.copytree(run / "zen-before", stage)
        os.chmod(stage, 0o700)
        source = run / "arc-source"
        data = extract(source)
        if data.fingerprint != preview.fingerprint:
            raise BridgeError("Arc changed after scanning. Run the scan again.")
        progress("Rebuilding spaces, Essentials, nested folders, and both session stores…")
        images, unavailable = collect(source, data) if options.favicons else ({}, 0)
        contexts = import_sidebar(stage, data, images)
        progress("Importing selected bookmarks, history, and saved form data…")
        standard = import_places(source, stage, options)
        if options.forms:
            standard.update(import_forms(source, stage))
        cookies = {}
        if options.cookies:
            progress("Approve Arc Safe Storage in the macOS Keychain prompt…")
            key = ArcKey.request()
            cookies = import_cookies(source, stage, contexts, key)
        progress("Comparing every migrated URL, folder path, and workspace…")
        verification = verify_sidebar(stage, data)
        report = {
            "app_version": __version__,
            "run_id": run_id,
            "mode": "replace" if options.replace else "new-profile",
            "options": asdict(options),
            "source": data.summary(),
            "verification": verification,
            "standard_data": standard,
            "cookies": cookies,
            "favicons_unavailable": unavailable,
            "limitations": [
                "Native password CSV preparation is a separate explicit action; passwords are not imported by this migration step.",
                "Passkeys, extension vaults/settings, IndexedDB/local storage, the Arc archive interface, and Arc-only features are not copied.",
                "Partitioned cookies are excluded; websites may require sign-in again.",
                "Workspace color matching is approximate; Zen is not a pixel-identical Arc clone.",
            ],
        }
        write_json(run / "report.json", report)
        write_json(
            run / "recovery.json",
            {
                "version": 1,
                "mode": report["mode"],
                "target": str(destination),
                "template": str(target),
                "rollback": str(rollback),
                "run_id": run_id,
            },
        )
        ensure_closed()
        if inventory(target) != target_manifest or inventory(arc) != source_manifest:
            raise BridgeError(
                "A browser folder changed during migration. The staged result was not committed."
            )
        progress("Committing the verified profile…")
        if options.replace:
            os.replace(target, rollback)
            try:
                os.replace(stage, target)
            except BaseException:
                os.replace(rollback, target)
                raise
        else:
            if destination.exists():
                raise BridgeError("The new profile destination already exists.")
            os.replace(stage, destination)
        committed = True
        # The immutable success marker is written only after the directory commit.
        write_json(run / "committed.json", {"profile": str(destination), "run_id": run_id})
        progress("Migration complete. Full backups and the count-only report are saved locally.")
        return Result(run, destination, report)
    except BridgeError:
        raise
    except Exception:
        # Database and filesystem errors can contain values or local paths.
        raise BridgeError(
            "Migration stopped on a file or database error. Original browser folders and completed backups were retained. See the compatibility guide; no browser content was logged."
        ) from None
    finally:
        if key is not None:
            key.close()
        if not committed and stage.exists():
            # Keep failed staging for recovery; do not discard potentially useful data.
            retained = run / "uncommitted-profile"
            if not retained.exists():
                shutil.move(str(stage), str(retained))


def prepare_passwords(run: Path) -> tuple[Path, dict]:
    if not (run / "committed.json").exists():
        raise BridgeError("Choose a completed migration run first.")
    destination = run / "password-transfer" / "arc-passwords.csv"
    if destination.exists():
        raise BridgeError(
            "A password-transfer CSV already exists. Finish its import and delete it before preparing another."
        )
    key = ArcKey.request()
    try:
        report = export_passwords(run / "arc-source", destination, key)
        write_json(run / "password-summary.json", report)
        return destination, report
    finally:
        key.close()


def delete_password_transfer(run: Path) -> None:
    (run / "password-transfer" / "arc-passwords.csv").unlink(missing_ok=True)


def restore(run: Path, progress: Progress = lambda _: None) -> Path:
    ensure_closed()
    record = read_json(run / "recovery.json")
    if record.get("version") != 1 or record.get("mode") != "replace" or not (run / "committed.json").exists():
        raise BridgeError(
            "Recovery is for completed replacement runs. New-profile runs leave the original profile unchanged."
        )
    backup, target = run / "zen-before", Path(record["target"])
    if not target.is_absolute() or target.is_symlink() or backup.is_symlink():
        raise BridgeError("Recovery requires direct, absolute browser paths without symlinks.")
    validate_template(backup)
    validate_template(target)
    current_manifest = inventory(target)
    expected = read_json(run / "backup-manifest.json")["zen"]
    if inventory(backup) != expected:
        raise BridgeError("The backup no longer matches its recorded hashes. Recovery stopped.")
    staged = target.parent / (".bridge-restore-" + uuid.uuid4().hex)
    retained = target.parent / (".bridge-replaced-" + uuid.uuid4().hex)
    progress("Verifying and staging the original Zen backup…")
    copy_verified(backup, staged)
    ensure_closed()
    if inventory(target) != current_manifest:
        raise BridgeError("The current profile changed during recovery. No profile was replaced.")
    os.replace(target, retained)
    try:
        os.replace(staged, target)
    except BaseException:
        os.replace(retained, target)
        raise
    write_json(run / "restored.json", {"restored": True, "retained_new_profile": str(retained)})
    return target
