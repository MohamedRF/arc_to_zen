import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from arc2zen_bridge.gui import Window  # noqa: E402


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
