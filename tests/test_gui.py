import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from arc_to_zen.gui import Window  # noqa: E402


def test_demo_uses_fictional_data_and_disables_write_actions():
    app = QApplication.instance() or QApplication([])
    window = Window(demo=True)
    assert window.preview.summary()["tabs"] == 7
    assert window.table.rowCount() == 4
    assert window.arc_path.isReadOnly()
    assert not window.migrate_button.isEnabled()
    assert not window.restore_button.isEnabled()
    assert not window.password_button.isEnabled()
    window.recover()  # Must return without showing a picker or touching profiles.
    window.show()
    app.processEvents()
    table_bottom = window.table.geometry().bottom()
    checkbox_top = window.options["history"].geometry().top()
    assert table_bottom < checkbox_top
    window.close()


def test_changing_destination_clears_stale_preview():
    app = QApplication.instance() or QApplication([])
    window = Window(demo=True)
    window.mode.setCurrentIndex(1)
    app.processEvents()
    assert window.preview is None
    assert window.table.rowCount() == 0
    assert all(value.text() == "—" for value in window.stats.values())
    assert not window.migrate_button.isEnabled()
    window.scan()
    assert window.preview.summary()["tabs"] == 7
    assert window.stats["tabs"].text() == "7"
    assert not window.migrate_button.isEnabled()
    window.close()


def test_workflow_navigation_keeps_migration_actions_reachable_in_small_window():
    from arc_to_zen.gui import STYLE

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = Window(demo=True)
    window.resize(1000, 760)
    window.show()
    app.processEvents()
    assert window.scroll.widget().width() <= window.scroll.viewport().width()
    window.navigation[2].click()
    app.processEvents()
    assert window.navigation[2].isChecked()
    point = window.migrate_button.mapTo(window.scroll.viewport(), window.migrate_button.rect().center())
    assert window.scroll.viewport().rect().contains(point)
    window.close()
