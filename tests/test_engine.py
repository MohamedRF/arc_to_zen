import os

import pytest

from arc_to_zen.engine import copy_verified, inventory, migrate, restore
from arc_to_zen.io import read_json
from arc_to_zen.models import BridgeError, Options
from arc_to_zen.paths import safe_runtime_location


def test_new_profile_preserves_sources_and_original_target(browsers):
    arc, zen, runtime = browsers
    arc_before, zen_before = inventory(arc), inventory(zen)
    result = migrate(arc, zen, runtime)
    assert result.profile != zen
    assert inventory(arc) == arc_before
    assert inventory(zen) == zen_before
    assert result.report["verification"]["verified_tabs"] == 7
    assert result.report["standard_data"]["history_visits"] == 1
    assert result.report["standard_data"]["bookmarks"] == 1
    assert result.report["standard_data"]["form_entries"] == 1
    assert (result.run / "committed.json").exists()
    assert inventory(result.run / "zen-before") == zen_before
    report = (result.run / "report.json").read_text()
    assert "example.test" not in report
    assert "fictional example" not in report
    assert "Home" not in report


def test_replace_and_restore_retains_both_versions(browsers):
    arc, zen, runtime = browsers
    before = inventory(zen)
    result = migrate(arc, zen, runtime, Options(replace=True))
    assert result.profile == zen
    assert inventory(zen) != before
    rollback = read_json(result.run / "recovery.json")["rollback"]
    assert os.path.isdir(rollback)
    restored = restore(result.run)
    assert restored == zen
    assert inventory(zen) == before
    assert os.path.isdir(read_json(result.run / "restored.json")["retained_new_profile"])


def test_failed_commit_rolls_target_back(browsers, monkeypatch):
    arc, zen, runtime = browsers
    before = inventory(zen)
    original = os.replace

    def fail_staging(source, destination):
        if str(source).split("/")[-1].startswith(".arc2zen-stage-"):
            raise OSError("simulated commit failure")
        return original(source, destination)

    monkeypatch.setattr("arc_to_zen.engine.os.replace", fail_staging)
    with pytest.raises(BridgeError):
        migrate(arc, zen, runtime, Options(replace=True))
    assert inventory(zen) == before
    assert not list(runtime.rglob("committed.json"))


def test_verification_failure_never_commits(browsers, monkeypatch):
    arc, zen, runtime = browsers
    before = inventory(zen)

    def fail(*_):
        raise BridgeError("simulated verification failure")

    monkeypatch.setattr("arc_to_zen.engine.verify_sidebar", fail)
    with pytest.raises(BridgeError, match="verification"):
        migrate(arc, zen, runtime)
    assert inventory(zen) == before
    assert not list(zen.parent.glob("arc-bridge-*"))


def test_backup_tampering_blocks_restore(browsers):
    arc, zen, runtime = browsers
    result = migrate(arc, zen, runtime, Options(replace=True))
    (result.run / "zen-before/prefs.js").write_text("tampered")
    current = inventory(zen)
    with pytest.raises(BridgeError, match="hashes"):
        restore(result.run)
    assert inventory(zen) == current


def test_output_inside_git_or_browser_is_rejected(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    with pytest.raises(BridgeError, match="Git repository"):
        safe_runtime_location(repo / "data", tmp_path / "arc", tmp_path / "zen")
    with pytest.raises(BridgeError, match="separate"):
        safe_runtime_location(tmp_path / "arc/output", tmp_path / "arc", tmp_path / "zen")


def test_external_symlink_is_rejected_without_copying(browsers, tmp_path):
    arc, zen, runtime = browsers
    (arc / "external").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(BridgeError, match="symlinks"):
        migrate(arc, zen, runtime)
    assert not runtime.exists()


@pytest.mark.parametrize(
    "name", ["SingletonSocket", "SingletonCookie", "SingletonLock", "RunningChromeVersion"]
)
def test_runtime_symlinks_are_excluded_from_verified_backups(tmp_path, name):
    source = tmp_path / "source"
    source.mkdir()
    (source / "data").write_bytes(b"browser data")
    # Missing targets reproduce the markers left behind after browser exit.
    (source / name).symlink_to(tmp_path / "missing")
    destination = tmp_path / "backup"
    expected = copy_verified(source, destination)
    assert set(expected) == {"data"}
    assert inventory(destination) == expected
    assert not (destination / name).is_symlink()
    assert (source / name).is_symlink()


def test_runtime_symlinks_do_not_block_migration_or_restore(browsers, tmp_path):
    arc, zen, runtime = browsers
    user_data = arc / "User Data"
    for name in ("SingletonSocket", "SingletonCookie", "SingletonLock", "RunningChromeVersion"):
        (user_data / name).symlink_to(tmp_path / "missing")
    # A directory target must also be skipped without following it.
    (user_data / "Default/SingletonSocket").symlink_to(tmp_path, target_is_directory=True)
    (zen / ".parentlock").symlink_to(tmp_path / "missing")
    arc_before, zen_before = inventory(arc), inventory(zen)
    result = migrate(arc, zen, runtime, Options(replace=True))
    assert inventory(result.run / "arc-source") == arc_before
    assert inventory(result.run / "zen-before") == zen_before
    assert not list((result.run / "arc-source").rglob("Singleton*"))
    assert result.report["verification"]["verified_tabs"] == 7
    assert restore(result.run) == zen
    assert inventory(zen) == zen_before
    assert inventory(arc) == arc_before
    assert (user_data / "SingletonSocket").is_symlink()


def test_browsers_running_blocks_before_backups(browsers, monkeypatch):
    arc, zen, runtime = browsers

    def running():
        raise BridgeError("Quit Arc and Zen")

    monkeypatch.setattr("arc_to_zen.engine.ensure_closed", running)
    with pytest.raises(BridgeError, match="Quit"):
        migrate(arc, zen, runtime)
    assert not runtime.exists()
