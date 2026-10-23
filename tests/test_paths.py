from arc_to_zen.paths import defaults


def test_runtime_name_and_legacy_backup_discovery(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    support = tmp_path / "Library/Application Support"
    assert defaults() == (support / "Arc", support / "zen", support / "arc_to_zen")
    legacy = support / "Arc2Zen Bridge"
    legacy.mkdir(parents=True)
    assert defaults()[2] == legacy
