from pathlib import Path

import pytest

from arc2zen_bridge.demo import create


@pytest.fixture
def browsers(tmp_path, monkeypatch):
    arc, zen = create(tmp_path / "fictional")
    # Tests operate only on generated fixtures, even when real browsers are open.
    monkeypatch.setattr("arc2zen_bridge.engine.ensure_closed", lambda: None)
    return arc, zen, tmp_path / "runtime"


@pytest.fixture
def demo_paths(tmp_path) -> tuple[Path, Path]:
    return create(tmp_path / "fictional")
