from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .arc import extract
from .engine import delete_password_transfer, migrate, prepare_passwords, restore
from .models import BridgeError, Options
from .paths import defaults, discover_profiles

STYLE = """
QWidget { color: #243247; font-family: ".AppleSystemUIFont", "Segoe UI", sans-serif; font-size: 13px; }
QMainWindow, QWidget#canvas, QScrollArea { background: #f3f5f9; }
QLabel { background: transparent; }
QLabel#title { color: #17243b; font-size: 28px; font-weight: 700; }
QLabel#muted { color: #5d6c80; }
QLabel#field { color: #42536b; font-size: 12px; font-weight: 600; }
QLabel#step { color: #1b2b45; font-weight: 700; font-size: 16px; }
QLabel#stepNumber { color: #365fd4; background: #edf2ff; border-radius: 8px; font-weight: 700; }
QLabel#badge { color: #246953; background: #e5f3ec; border-radius: 10px; padding: 6px 12px; font-size: 11px; font-weight: 600; }
QLabel#demoBadge { color: #8b5b18; background: #fff1d9; border-radius: 8px; padding: 7px 12px; font-size: 11px; font-weight: 600; }
QFrame#sidebar { background: #17243b; border: none; }
QFrame#sidebar QLabel { color: #b4c1d5; }
QFrame#sidebar QLabel#brand { color: #ffffff; font-size: 21px; font-weight: 700; }
QFrame#sidebar QLabel#brandMark { color: #ffffff; background: #365fd4; border-radius: 12px; font-size: 22px; font-weight: 700; }
QFrame#sidebar QLabel#railHeading { color: #8498b8; font-size: 10px; font-weight: 700; }
QPushButton#navigation { background: transparent; border: 1px solid transparent; color: #c8d4e7; text-align: left; padding: 12px 10px; }
QPushButton#navigation:hover, QPushButton#navigation:checked { background: #273b5c; color: #ffffff; border: 1px solid #344d73; }
QPushButton#navigation:focus { border: 1px solid #9eb5ff; }
QFrame#card { background: #ffffff; border: 1px solid #dce3ed; border-radius: 12px; }
QFrame#stats { background: #f5f7fc; border: 1px solid #e4e9f2; border-radius: 8px; }
QLabel#statValue { color: #233e78; font-size: 23px; font-weight: 700; }
QLineEdit, QComboBox { background: #ffffff; border: 1px solid #cbd5e3; border-radius: 6px; padding: 8px 10px; min-height: 18px; selection-background-color: #365fd4; selection-color: white; }
QLineEdit:focus, QComboBox:focus { border: 1px solid #365fd4; }
QLineEdit:read-only { background: #f8faff; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow { image: url("__ASSET_PATH__/chevron.svg"); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: #ffffff; color: #243247; selection-background-color: #edf2ff; selection-color: #233e78; }
QPushButton { background: #ffffff; color: #354862; border: 1px solid #cbd5e3; border-radius: 6px; padding: 8px 13px; min-height: 18px; font-weight: 600; }
QPushButton:hover { background: #edf2ff; border-color: #a8bbee; }
QPushButton:pressed { background: #dfe8ff; }
QPushButton:focus { border: 1px solid #365fd4; }
QPushButton:disabled { color: #8994a5; background: #f5f7fa; border-color: #e2e7ef; }
QPushButton#primary, QPushButton#scan { background: #365fd4; color: #ffffff; border: 1px solid #365fd4; }
QPushButton#primary { padding: 10px 20px; }
QPushButton#primary:hover, QPushButton#scan:hover { background: #294cb5; }
QPushButton#primary:disabled, QPushButton#scan:disabled { background: #e4eaf7; border-color: #d9e1f2; color: #7788ad; }
QCheckBox { spacing: 7px; padding: 3px 0; background: transparent; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #aebdd0; border-radius: 4px; background: #ffffff; }
QCheckBox::indicator:checked { background: #365fd4; border-color: #365fd4; image: url("__ASSET_PATH__/check.svg"); }
QCheckBox::indicator:disabled { background: #e2e7ef; border-color: #cbd5e3; }
QCheckBox:focus { color: #365fd4; }
QTableWidget { background: #ffffff; alternate-background-color: #f8faff; border: 1px solid #e0e6ef; border-radius: 6px; gridline-color: #edf0f5; selection-background-color: #e7eeff; selection-color: #233e78; }
QTableWidget::item { padding: 6px 10px; }
QHeaderView::section { background: #f1f4f9; color: #596b84; border: none; border-bottom: 1px solid #e0e6ef; padding: 8px 10px; font-size: 11px; font-weight: 600; }
QPlainTextEdit { background: #f8faff; border: 1px solid #e0e6ef; border-radius: 6px; color: #53647e; padding: 8px; font-family: "SF Mono", "Menlo", monospace; font-size: 11px; }
QProgressBar { border: none; border-radius: 3px; background: #e7edf7; max-height: 5px; min-height: 5px; }
QProgressBar::chunk { background: #365fd4; border-radius: 3px; }
QScrollBar:vertical { background: #f3f5f9; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: #c6d0df; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QMessageBox, QFileDialog { background: #f3f5f9; }
""".replace("__ASSET_PATH__", (Path(__file__).parent / "assets").as_posix())


class Worker(QThread):
    progress = Signal(str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            self.done.emit(self.operation(self.progress.emit))
        except BridgeError as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit(
                "An unsupported file or database stopped this operation. No browser content was logged."
            )


def label(text: str, name: str = "muted", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def card(number: str, title: str):
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 14, 20, 14)
    layout.setSpacing(8)
    row = QHBoxLayout()
    badge = label(number, "stepNumber")
    badge.setFixedSize(30, 30)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    row.addWidget(badge)
    row.addSpacing(4)
    row.addWidget(label(title, "step"))
    row.addStretch()
    layout.addLayout(row)
    return frame, layout


class Window(QMainWindow):
    def __init__(self, demo: bool = False):
        super().__init__()
        self.setWindowTitle("arc_to_zen")
        self.resize(1240, 1040)
        self.setMinimumSize(1000, 760)
        self.demo = demo
        self.preview = None
        self.result = None
        self.worker = None
        self.demo_root = None
        arc, zen_root, self.runtime = defaults()
        profile_choices = []
        if demo:
            from .demo import create

            self.demo_root = tempfile.TemporaryDirectory(prefix="arc-to-zen-demo-", dir="/tmp")
            arc, target = create(Path(self.demo_root.name))
            profile_choices = [("Fictional Zen · demo only", target)]
        else:
            profile_choices = discover_profiles(zen_root)

        shell = QWidget()
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        self.setCentralWidget(shell)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(212)
        rail = QVBoxLayout(sidebar)
        rail.setContentsMargins(22, 30, 22, 24)
        rail.setSpacing(12)
        mark = label("a → z", "brandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(70, 56)
        rail.addWidget(mark)
        rail.addWidget(label("arc_to_zen", "brand"))
        rail.addWidget(label("Your browser, continued.", wrap=True))
        rail.addSpacing(36)
        rail.addWidget(label("MIGRATION WORKFLOW", "railHeading"))
        self.navigation = []
        self.sections = []
        for index, text in enumerate(
            ("01   Browser setup", "02   Review && select", "03   Migrate && verify")
        ):
            button = QPushButton(text)
            button.setObjectName("navigation")
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(lambda checked=False, index=index: self.go_to_step(index))
            self.navigation.append(button)
            rail.addWidget(button)
        self.navigation[0].setChecked(True)
        rail.addStretch()
        rail.addWidget(label("LOCAL BY DESIGN", "railHeading"))
        rail.addWidget(label("Your data stays on this Mac. No account. No uploads.", wrap=True))
        rail.addSpacing(8)
        rail.addWidget(label(f"Version {__version__}"))
        shell_layout.addWidget(sidebar)

        container = QWidget()
        container.setObjectName("canvas")
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidget(container)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        shell_layout.addWidget(self.scroll, 1)
        layout = QVBoxLayout(container)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(14)
        header = QHBoxLayout()
        intro = QVBoxLayout()
        intro.setSpacing(6)
        intro.addWidget(label("A new home for your Arc.", "title"))
        intro.addWidget(label("Move your spaces to Zen with a backup at every step."))
        header.addLayout(intro, 1)
        header.addWidget(
            label("FICTIONAL DEMO" if demo else "●  On-device migration", "demoBadge" if demo else "badge")
        )
        layout.addLayout(header)
        layout.addSpacing(2)

        frame, body = card("01", "Connect your browsers")
        self.sections.append(frame)
        source_row = QHBoxLayout()
        self.arc_path = QLineEdit(str(arc))
        self.arc_path.setAccessibleName("Arc data folder")
        self.arc_path.textChanged.connect(self.invalidate)
        browse_arc = QPushButton("Browse…")
        browse_arc.setEnabled(not demo)
        self.arc_path.setReadOnly(demo)
        browse_arc.clicked.connect(self.browse_source)
        source_row.addWidget(self.arc_path, 1)
        source_row.addWidget(browse_arc)
        source_row.insertWidget(0, label("Arc folder", "field"))
        body.addLayout(source_row)
        target_row = QHBoxLayout()
        self.zen_profiles = QComboBox()
        self.zen_profiles.setAccessibleName("Zen template profile")
        for name, path in profile_choices:
            self.zen_profiles.addItem(name, str(path))
        self.zen_profiles.currentIndexChanged.connect(self.invalidate)
        browse_zen = QPushButton("Browse…")
        browse_zen.setEnabled(not demo)
        browse_zen.clicked.connect(self.browse_target)
        target_row.addWidget(self.zen_profiles, 1)
        target_row.addWidget(browse_zen)
        target_row.insertWidget(0, label("Zen profile", "field"))
        body.addLayout(target_row)
        self.browse_buttons = (browse_arc, browse_zen)
        self.mode = QComboBox()
        self.mode.setAccessibleName("Migration destination mode")
        self.mode.addItems(
            ["Create a separate Zen profile — recommended", "Update selected profile — full backup required"]
        )
        self.mode.currentIndexChanged.connect(self.invalidate)
        body.addWidget(self.mode)
        hint = QLabel("Arc is read-only. A separate profile keeps your existing Zen setup intact.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        body.addWidget(hint)
        layout.addWidget(frame)

        frame, body = card("02", "Review your migration")
        self.sections.append(frame)
        row = QHBoxLayout()
        self.scan_button = QPushButton("Scan Arc")
        self.scan_button.setObjectName("scan")
        self.scan_button.clicked.connect(self.scan)
        row.addWidget(self.scan_button)
        self.summary = QLabel("Scan to review your spaces. Keychain is never accessed during a scan.")
        self.summary.setObjectName("muted")
        self.summary.setWordWrap(True)
        row.addWidget(self.summary, 1)
        body.addLayout(row)
        self.stats = {}
        stats_frame = QFrame()
        stats_frame.setObjectName("stats")
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(16, 8, 16, 8)
        for key, title in (
            ("spaces", "Spaces"),
            ("tabs", "Tabs"),
            ("essentials", "Essentials"),
            ("folders", "Folders"),
        ):
            column = QVBoxLayout()
            column.setSpacing(0)
            value = label("—", "statValue")
            self.stats[key] = value
            column.addWidget(value)
            column.addWidget(label(title, "field"))
            stats_layout.addLayout(column, 1)
        body.addWidget(stats_frame)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Arc space", "Profile", "Tabs / Essentials", "Folders"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAccessibleName("Arc spaces to migrate")
        self.table.verticalHeader().setDefaultSectionSize(31)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setFixedHeight(166)
        body.addWidget(self.table)
        body.addWidget(label("INCLUDE IN MIGRATION", "field"))
        options_row = QHBoxLayout()
        self.options = {}
        for name, option_label in [
            ("history", "History"),
            ("bookmarks", "Bookmarks"),
            ("forms", "Form history"),
            ("favicons", "Favicons"),
            ("cookies", "Cookies · Keychain approval"),
        ]:
            control = QCheckBox(option_label)
            control.setChecked(name != "cookies")
            self.options[name] = control
            options_row.addWidget(control)
        body.addLayout(options_row)
        hint = QLabel("Passwords are transferred separately after migration using Zen’s native importer.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        body.addWidget(hint)
        layout.addWidget(frame)

        frame, body = card("03", "Migrate with confidence")
        self.sections.append(frame)
        status_row = QHBoxLayout()
        self.status = label("Ready when you are", "field", wrap=True)
        status_row.addWidget(self.status, 1)
        status_row.addWidget(label("Backup  →  Stage  →  Verify  →  Commit"))
        body.addLayout(status_row)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        body.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(64)
        self.log.setAccessibleName("Migration progress log")
        self.log.setPlaceholderText(
            "Migration progress appears here. Private browser content stays out of logs."
        )
        body.addWidget(self.log)
        actions = QHBoxLayout()
        self.restore_button = QPushButton("Restore backup…")
        self.restore_button.setEnabled(not demo)
        self.restore_button.clicked.connect(self.recover)
        actions.addWidget(self.restore_button)
        actions.addStretch()
        self.migrate_button = QPushButton("Back up and migrate")
        self.migrate_button.setObjectName("primary")
        self.migrate_button.setEnabled(False)
        self.migrate_button.clicked.connect(self.transfer)
        actions.addWidget(self.migrate_button)
        body.addLayout(actions)
        completion = QHBoxLayout()
        self.open_button = QPushButton("Open migrated Zen")
        self.open_button.clicked.connect(self.open_zen)
        self.password_button = QPushButton("Prepare passwords…")
        self.password_button.clicked.connect(self.passwords)
        self.delete_button = QPushButton("Delete password CSV")
        self.delete_button.clicked.connect(self.delete_passwords)
        self.report_button = QPushButton("Open report")
        self.report_button.clicked.connect(self.open_report)
        for button in (self.open_button, self.password_button, self.delete_button, self.report_button):
            button.setEnabled(False)
            completion.addWidget(button)
        self.completion = QWidget()
        self.completion.setLayout(completion)
        completion.setContentsMargins(0, 0, 0, 0)
        self.completion.hide()
        body.addWidget(self.completion)
        layout.addWidget(frame)
        footer = QLabel(
            "Full local backups · Verified before commit · "
            + ("Demo data only; migration disabled" if demo else "Quit Arc and Zen before migrating")
        )
        footer.setObjectName("muted")
        footer.setWordWrap(True)
        layout.addWidget(footer)
        layout.addStretch()
        if demo:
            self.scan()

    def go_to_step(self, index: int):
        self.scroll.ensureWidgetVisible(self.sections[index], 0, 16)

    def invalidate(self):
        self.preview = None
        if hasattr(self, "migrate_button"):
            self.migrate_button.setEnabled(False)
            self.table.setRowCount(0)
            for value in self.stats.values():
                value.setText("—")
            self.summary.setText("Browser selection changed. Scan Arc to refresh your preview.")
            self.status.setText("Scan required")

    def browse_source(self):
        if self.demo:
            return
        selected = QFileDialog.getExistingDirectory(self, "Arc data folder", self.arc_path.text())
        if selected:
            self.arc_path.setText(selected)

    def browse_target(self):
        if self.demo:
            return
        selected = QFileDialog.getExistingDirectory(self, "Initialized Zen profile")
        if selected:
            self.zen_profiles.addItem(Path(selected).name, selected)
            self.zen_profiles.setCurrentIndex(self.zen_profiles.count() - 1)

    def scan(self):
        try:
            self.preview = extract(Path(self.arc_path.text()).expanduser())
            stats = self.preview.summary()
            self.summary.setText("Preview ready. Review the counts and choose what to bring.")
            for key, value in self.stats.items():
                value.setText(str(stats[key]))
            self.status.setText(
                "Demo preview · migration disabled"
                if self.demo
                else "Preview ready · quit both browsers to continue"
            )
            self.table.setRowCount(len(self.preview.spaces))
            for row, space in enumerate(self.preview.spaces):
                values = [
                    space.icon + " " + space.name,
                    space.profile,
                    f"{len(space.tabs)} / {sum(t.essential for t in space.tabs)}",
                    str(len(space.folders)),
                ]
                for column, value in enumerate(values):
                    self.table.setItem(row, column, QTableWidgetItem(value))
            self.migrate_button.setEnabled(not self.demo and self.zen_profiles.currentData() is not None)
            if stats["warnings"]:
                self.log.appendPlainText("Source warnings (counts): " + json.dumps(stats["warnings"]))
        except BridgeError as error:
            self.invalidate()
            self.error(str(error))
        except Exception:
            self.invalidate()
            self.error("The selected Arc folder has an unsupported or unreadable sidebar.")

    def start(self, operation, success):
        self.scan_button.setEnabled(False)
        self.migrate_button.setEnabled(False)
        self.restore_button.setEnabled(False)
        self.password_button.setEnabled(False)
        self.status.setText("Operation in progress…")
        self.arc_path.setEnabled(False)
        self.zen_profiles.setEnabled(False)
        self.mode.setEnabled(False)
        self.open_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        for control in (*self.options.values(), *self.browse_buttons):
            control.setEnabled(False)
        self.progress.setRange(0, 0)
        self.worker = Worker(operation, self)
        self.worker.progress.connect(self.log.appendPlainText)
        self.worker.done.connect(success)
        self.worker.done.connect(self.operation_succeeded)
        self.worker.failed.connect(self.error)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def operation_succeeded(self, _):
        if self.status.text() == "Operation in progress…":
            self.status.setText("Operation completed successfully")

    def worker_finished(self):
        self.progress.setRange(0, 1)
        self.progress.setValue(0 if self.status.text().startswith("Operation stopped") else 1)
        self.arc_path.setEnabled(True)
        self.zen_profiles.setEnabled(True)
        self.mode.setEnabled(True)
        for control in self.options.values():
            control.setEnabled(True)
        for button in self.browse_buttons:
            button.setEnabled(not self.demo)
        self.open_button.setEnabled(self.result is not None)
        self.delete_button.setEnabled(
            self.result is not None and (self.result.run / "password-transfer/arc-passwords.csv").exists()
        )
        self.scan_button.setEnabled(True)
        self.restore_button.setEnabled(not self.demo)
        self.password_button.setEnabled(self.result is not None)
        self.migrate_button.setEnabled(
            self.preview is not None and not self.demo and self.zen_profiles.currentData() is not None
        )

    def transfer(self):
        if self.demo or self.preview is None:
            return
        target = self.zen_profiles.currentData()
        if not target:
            self.error("Select an initialized Zen profile.")
            return
        options = Options(
            **{name: control.isChecked() for name, control in self.options.items()},
            replace=self.mode.currentIndex() == 1,
        )
        message = (
            "This will back up Arc and the complete Zen profile, then "
            + ("update the selected Zen profile" if options.replace else "create a separate Zen profile")
            + ". Existing Zen data is retained. Quit both browsers first.\n\n"
            + (
                "Cookies require macOS Keychain approval; expired and partitioned cookies are skipped.\n\n"
                if options.cookies
                else ""
            )
            + "Continue with the reviewed counts?"
        )
        if QMessageBox.question(self, "Review migration", message) != QMessageBox.StandardButton.Yes:
            return
        source = Path(self.arc_path.text()).expanduser()
        self.start(
            lambda progress: migrate(source, Path(target), self.runtime, options, progress), self.completed
        )

    def completed(self, result):
        self.result = result
        self.status.setText("Migration complete · verification passed")
        self.completion.show()
        verified = result.report["verification"]
        self.log.appendPlainText(
            f"Verified {verified['verified_tabs']} tabs and {verified['verified_folders']} folder paths. Missing tabs: 0."
        )
        for button in (self.open_button, self.password_button, self.report_button):
            button.setEnabled(True)

    def passwords(self):
        if self.result is None:
            return
        message = "This requests Arc Safe Storage access from macOS and prepares a local plaintext CSV in a private folder. No passwords are uploaded.\n\nImport it using Zen → Settings → Import Data → Passwords from CSV, then click Delete password CSV here. Conflicting saved passwords are never silently overwritten. Prepare the CSV?"
        if QMessageBox.question(self, "Prepare password transfer", message) != QMessageBox.StandardButton.Yes:
            return
        run = self.result.run
        self.start(lambda _: prepare_passwords(run), self.passwords_ready)

    def passwords_ready(self, value):
        path, summary = value
        self.delete_button.setEnabled(True)
        self.log.appendPlainText(
            f"Prepared {summary['distinct_logins']} distinct logins. Native import is still required."
        )
        QMessageBox.information(
            self,
            "Import with Zen",
            f"Choose Passwords from CSV in Zen's Import Data window.\n\nFile: {path}\n\nDelete the CSV after import. arc_to_zen has not imported these passwords into Zen yet.",
        )
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def delete_passwords(self):
        if self.result:
            delete_password_transfer(self.result.run)
            self.delete_button.setEnabled(False)
            self.log.appendPlainText("Known temporary password CSV removed.")

    def open_zen(self):
        if self.result:
            subprocess.Popen(
                [
                    "/usr/bin/open",
                    "-na",
                    "/Applications/Zen.app",
                    "--args",
                    "-profile",
                    str(self.result.profile),
                ]
            )

    def open_report(self):
        if self.result:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.result.run / "report.json")))

    def recover(self):
        if self.demo:
            return
        selected = QFileDialog.getExistingDirectory(self, "Choose a completed arc_to_zen replacement run")
        if not selected:
            return
        if (
            QMessageBox.question(
                self,
                "Restore original Zen profile",
                "Restore the verified pre-migration backup? The current profile will be retained separately. Quit both browsers first.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.start(
            lambda progress: restore(Path(selected), progress),
            lambda _: self.log.appendPlainText(
                "Original Zen profile restored; the replaced profile was retained separately."
            ),
        )

    def error(self, message):
        self.status.setText("Operation stopped · review the message below")
        self.log.appendPlainText(message)
        QMessageBox.warning(self, "arc_to_zen", message)

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(
                self,
                "Migration in progress",
                "Wait for the current backup or migration to finish. Closing during a profile commit is not supported.",
            )
            event.ignore()
            return
        if self.result and (self.result.run / "password-transfer/arc-passwords.csv").exists():
            QMessageBox.information(
                self,
                "Temporary password file remains",
                "A private plaintext password CSV is still in this migration run. Finish Zen's native import, then delete it using arc_to_zen or Finder.",
            )
        event.accept()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="Show fictional fixtures; migration is disabled")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("arc_to_zen")
    app.setOrganizationName("arc_to_zen")
    app.setStyle("Fusion")
    app.setFont(QFont(".AppleSystemUIFont", 13))
    app.setStyleSheet(STYLE)
    window = Window(args.demo)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
