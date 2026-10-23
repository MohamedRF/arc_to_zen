from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
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
QWidget { background: #111a20; color: #e7eff2; font-size: 13px; }
QLabel#eyebrow { color: #67dcc2; font-size: 12px; font-weight: 700; }
QLabel#title { font-size: 32px; font-weight: 700; }
QLabel#muted { color: #a1b3bc; }
QLabel#step { color: #67dcc2; font-weight: 700; font-size: 15px; }
QFrame#card { background: #1b2830; border: 1px solid #30414a; border-radius: 13px; }
QFrame#card QLabel, QFrame#card QCheckBox { background: transparent; }
QLineEdit, QComboBox { background: #111c23; border: 1px solid #40535e; border-radius: 7px; padding: 9px; selection-background-color: #176d60; }
QPushButton { background: #263b45; border: 1px solid #40535e; border-radius: 7px; padding: 9px 14px; font-weight: 600; }
QPushButton:hover { background: #35505e; }
QPushButton:disabled { color: #6e858f; background: #1c2a32; }
QPushButton#primary { background: #67dcc2; color: #102720; border: none; padding: 12px 22px; }
QPushButton#primary:hover { background: #96efdb; }
QPushButton#primary:disabled { background: #2b514a; color: #8baba4; }
QCheckBox { spacing: 8px; padding: 3px; }
QTableWidget { background: #142129; border: 1px solid #30414a; border-radius: 7px; gridline-color: #30414a; }
QHeaderView::section { background: #263b45; color: #bdd0d8; border: none; padding: 7px; }
QPlainTextEdit { background: #10191f; border: 1px solid #30414a; border-radius: 7px; color: #b5c8d0; padding: 7px; font-size: 12px; }
QProgressBar { border: none; border-radius: 3px; background: #263b45; max-height: 5px; }
QProgressBar::chunk { background: #67dcc2; border-radius: 3px; }
QMessageBox, QFileDialog { background: #1b2830; }
"""


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


def card(title: str):
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 15, 18, 15)
    heading = QLabel(title)
    heading.setObjectName("step")
    layout.addWidget(heading)
    return frame, layout


class Window(QMainWindow):
    def __init__(self, demo: bool = False):
        super().__init__()
        self.setWindowTitle("Arc2Zen Bridge")
        self.resize(1070, 910)
        self.setMinimumSize(850, 760)
        self.demo = demo
        self.preview = None
        self.result = None
        self.worker = None
        self.demo_root = None
        arc, zen_root, self.runtime = defaults()
        profile_choices = []
        if demo:
            from .demo import create

            self.demo_root = tempfile.TemporaryDirectory(prefix="arc2zen-bridge-demo-", dir="/tmp")
            arc, target = create(Path(self.demo_root.name))
            profile_choices = [("Fictional Zen · demo only", target)]
        else:
            profile_choices = discover_profiles(zen_root)

        container = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(container)
        self.setCentralWidget(scroll)
        layout = QVBoxLayout(container)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(14)
        eyebrow = QLabel("ARC2ZEN BRIDGE  /  LOCAL FIRST")
        eyebrow.setObjectName("eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("Bring your Arc with you.")
        title.setObjectName("title")
        layout.addWidget(title)
        subtitle = QLabel("Spaces, Essentials, folders, and more. Backed up first. Verified before commit.")
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)

        frame, body = card("01  Choose your browser folders")
        source_row = QHBoxLayout()
        self.arc_path = QLineEdit(str(arc))
        self.arc_path.setAccessibleName("Arc data folder")
        self.arc_path.textChanged.connect(self.invalidate)
        browse_arc = QPushButton("Arc folder…")
        browse_arc.setEnabled(not demo)
        self.arc_path.setReadOnly(demo)
        browse_arc.clicked.connect(self.browse_source)
        source_row.addWidget(self.arc_path, 1)
        source_row.addWidget(browse_arc)
        body.addLayout(source_row)
        target_row = QHBoxLayout()
        self.zen_profiles = QComboBox()
        self.zen_profiles.setAccessibleName("Zen template profile")
        for name, path in profile_choices:
            self.zen_profiles.addItem(name, str(path))
        self.zen_profiles.currentIndexChanged.connect(self.invalidate)
        browse_zen = QPushButton("Zen profile…")
        browse_zen.setEnabled(not demo)
        browse_zen.clicked.connect(self.browse_target)
        target_row.addWidget(self.zen_profiles, 1)
        target_row.addWidget(browse_zen)
        body.addLayout(target_row)
        self.mode = QComboBox()
        self.mode.setAccessibleName("Migration destination mode")
        self.mode.addItems(
            ["Create a separate Zen profile — recommended", "Update selected profile — full backup required"]
        )
        body.addWidget(self.mode)
        hint = QLabel(
            "Arc is read-only. Existing Zen workspaces are retained; Bridge-owned workspaces can be refreshed."
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        body.addWidget(hint)
        layout.addWidget(frame)

        frame, body = card("02  Preview and choose what to bring")
        row = QHBoxLayout()
        self.scan_button = QPushButton("Scan Arc")
        self.scan_button.clicked.connect(self.scan)
        row.addWidget(self.scan_button)
        self.summary = QLabel("A scan reads your sidebar and shows counts. It never accesses Keychain.")
        self.summary.setObjectName("muted")
        self.summary.setWordWrap(True)
        row.addWidget(self.summary, 1)
        body.addLayout(row)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Arc space", "Profile", "Tabs / Essentials", "Folders"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setFixedHeight(165)
        body.addWidget(self.table)
        options_row = QHBoxLayout()
        self.options = {}
        for name, label in [
            ("history", "History"),
            ("bookmarks", "Bookmarks"),
            ("forms", "Form history"),
            ("favicons", "Favicons"),
            ("cookies", "Cookies · Keychain approval"),
        ]:
            control = QCheckBox(label)
            control.setChecked(name != "cookies")
            self.options[name] = control
            options_row.addWidget(control)
        body.addLayout(options_row)
        hint = QLabel(
            "Passwords use a separate native-import step after migration. Passkeys, extension vaults, and Arc-only features need separate setup."
        )
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        body.addWidget(hint)
        layout.addWidget(frame)

        frame, body = card("03  Back up, migrate, and verify")
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        body.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(100)
        self.log.setPlaceholderText(
            "Count-only progress appears here. URLs, usernames, passwords, and cookie values stay out of logs."
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
        body.addLayout(completion)
        layout.addWidget(frame)
        footer = QLabel(
            f"v{__version__}  ·  No uploads, telemetry, or forced browser shutdown  ·  "
            + ("FICTIONAL DEMO — migration disabled" if demo else "Quit Arc and Zen before migrating")
        )
        footer.setObjectName("muted")
        layout.addWidget(footer)
        if demo:
            self.scan()

    def invalidate(self):
        self.preview = None
        if hasattr(self, "migrate_button"):
            self.migrate_button.setEnabled(False)

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
            self.summary.setText(
                f"{stats['spaces']} spaces · {stats['tabs']} tabs · {stats['essentials']} Essentials · {stats['folders']} folders"
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
            self.table.resizeColumnsToContents()
            self.migrate_button.setEnabled(not self.demo and self.zen_profiles.currentData() is not None)
            if stats["warnings"]:
                self.log.appendPlainText("Source warnings (counts): " + json.dumps(stats["warnings"]))
        except BridgeError as error:
            self.error(str(error))
        except Exception:
            self.error("The selected Arc folder has an unsupported or unreadable sidebar.")

    def start(self, operation, success):
        self.scan_button.setEnabled(False)
        self.migrate_button.setEnabled(False)
        self.restore_button.setEnabled(False)
        self.password_button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.worker = Worker(operation, self)
        self.worker.progress.connect(self.log.appendPlainText)
        self.worker.done.connect(success)
        self.worker.failed.connect(self.error)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def worker_finished(self):
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.scan_button.setEnabled(True)
        self.restore_button.setEnabled(True)
        self.password_button.setEnabled(self.result is not None)
        self.migrate_button.setEnabled(self.preview is not None and not self.demo)

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
            f"Choose Passwords from CSV in Zen's Import Data window.\n\nFile: {path}\n\nDelete the CSV after import. Bridge has not imported these passwords into Zen yet.",
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
        selected = QFileDialog.getExistingDirectory(self, "Choose a completed Bridge replacement run")
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
        self.log.appendPlainText(message)
        QMessageBox.warning(self, "Arc2Zen Bridge", message)

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
                "A private plaintext password CSV is still in this migration run. Finish Zen's native import, then delete it using Bridge or Finder.",
            )
        event.accept()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="Show fictional fixtures; migration is disabled")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Arc2Zen Bridge")
    app.setOrganizationName("Arc2Zen Bridge")
    app.setStyleSheet(STYLE)
    window = Window(args.demo)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
