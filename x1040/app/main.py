#!/usr/bin/env python3
"""Entry point for the Rollo copy helper.

Design rule, learned the hard way on the Zorin laptop: never depend on the
system tray. GNOME has no built-in tray, so a tray-only app can run happily
and be completely invisible. The window is the primary interface; the tray
icon is a bonus that appears only when the desktop actually supports it.
"""

import argparse
import logging
import os
import platform
import sys
import traceback
from pathlib import Path

# Launchers invoke this file by path (".../app/main.py"), which puts the app
# directory itself on sys.path -- not its parent -- so "import app.*" fails
# with ModuleNotFoundError before anything else runs. Put the package parent
# on the path first so the app starts however it is launched.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import cups_helper
from app.cups_helper import (
    current_copies,
    detect_printer,
    list_queues,
    queue_exists,
    reset_to_default,
    save_printer_override,
    set_copies,
)
from app.queue_watcher import STATE_IDLE, STATE_PRINTING, STATE_WAITING, QueueWatcher

LOG_DIR = Path.home() / ".rollo-printer"
LOG_PATH = LOG_DIR / "runtime.log"

logger = logging.getLogger("rollo_printer")


def configure_logging(verbose: bool = False) -> None:
    """Send everything -- including crashes and Qt errors -- to the log file.

    The previous version only captured logging calls, so a traceback or a Qt
    fatal error vanished without a trace and the app looked like it had
    simply done nothing.
    """
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    try:
        file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError as exc:
        print(f"Warning: cannot write {LOG_PATH}: {exc}", file=sys.stderr)

    # Only echo to stderr when a human is watching. The launcher redirects
    # stderr into this very log file, so adding the handler unconditionally
    # writes every line twice.
    if sys.stderr is not None and sys.stderr.isatty():
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(fmt)
        root.addHandler(stream_handler)

    def excepthook(exc_type, exc_value, exc_tb):
        logging.critical("Unhandled exception:\n%s", "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = excepthook


def environment_report() -> str:
    """Everything needed to debug a machine we cannot log into."""
    printer = detect_printer(refresh=True)
    queues = list_queues()
    lines = [
        "=== Rollo printer helper diagnostics ===",
        f"Python           : {sys.version.split()[0]} ({sys.executable})",
        f"Platform         : {platform.platform()}",
        f"User / Home      : {os.environ.get('USER', '?')} / {Path.home()}",
        "",
        "--- Desktop session ---",
        f"XDG_SESSION_TYPE : {os.environ.get('XDG_SESSION_TYPE', '<unset>')}",
        f"XDG_CURRENT_DESKTOP: {os.environ.get('XDG_CURRENT_DESKTOP', '<unset>')}",
        f"DISPLAY          : {os.environ.get('DISPLAY', '<unset>')}",
        f"WAYLAND_DISPLAY  : {os.environ.get('WAYLAND_DISPLAY', '<unset>')}",
        f"XAUTHORITY       : {os.environ.get('XAUTHORITY', '<unset>')}",
        f"QT_QPA_PLATFORM  : {os.environ.get('QT_QPA_PLATFORM', '<unset>')}",
        "",
        "--- Printing ---",
        f"Queues visible   : {', '.join(queues) if queues else '(none)'}",
        f"Rollo queue      : {printer or 'NOT FOUND'}",
        f"Current copies   : {current_copies() if printer else 'n/a'}",
        f"Override file    : {cups_helper.PRINTER_OVERRIDE_FILE} "
        f"({'present' if cups_helper.PRINTER_OVERRIDE_FILE.is_file() else 'absent'})",
        "",
        "--- Qt / tray ---",
    ]

    try:
        from PySide6 import QtCore, QtWidgets

        lines.append(f"PySide6          : {QtCore.__version__} (Qt {QtCore.qVersion()})")
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        lines.append(f"Qt platform      : {app.platformName()}")
        lines.append(f"Tray available   : {QtWidgets.QSystemTrayIcon.isSystemTrayAvailable()}")
    except Exception as exc:  # noqa: BLE001 - diagnostics must never crash
        lines.append(f"PySide6          : NOT USABLE -- {exc.__class__.__name__}: {exc}")

    lines.append("")
    lines.append(f"Log file         : {LOG_PATH}")
    return "\n".join(lines)


def status_mode() -> int:
    printer = detect_printer(refresh=True)
    if not printer:
        print("No Rollo printer queue found.")
        queues = list_queues()
        print(f"Queues visible to CUPS: {', '.join(queues) if queues else '(none)'}")
        return 1
    value = current_copies(printer)
    if value is None:
        print(f"{printer}: copy count unreadable")
        return 1
    print(f"{printer}: {value} copies")
    return 0


def build_gui():
    """Imported lazily so --status and --diagnose work without a display."""
    from PySide6 import QtCore, QtGui, QtWidgets

    from app.icon import APP_NAME, app_icon

    class WatcherBridge(QtCore.QObject):
        """Marshals watcher-thread callbacks onto the GUI thread."""

        state_changed = QtCore.Signal(str)
        reset_done = QtCore.Signal(bool, str)

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle(APP_NAME)
            self.setWindowIcon(app_icon())
            self.setMinimumWidth(460)

            self._tray_available = False
            self._announced_tray = False

            self.bridge = WatcherBridge()
            self.bridge.state_changed.connect(self._on_watcher_state)
            self.bridge.reset_done.connect(self._on_watcher_reset)

            self.watcher = QueueWatcher(
                on_state_change=self.bridge.state_changed.emit,
                on_reset=self.bridge.reset_done.emit,
            )
            self.watcher.start()

            central = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(central)
            layout.setSpacing(10)

            # --- Printer selection -------------------------------------
            printer_box = QtWidgets.QGroupBox("Printer")
            printer_layout = QtWidgets.QVBoxLayout(printer_box)
            self.printer_combo = QtWidgets.QComboBox()
            printer_layout.addWidget(self.printer_combo)

            printer_buttons = QtWidgets.QHBoxLayout()
            use_button = QtWidgets.QPushButton("Use this printer")
            use_button.clicked.connect(self._use_selected_printer)
            printer_buttons.addWidget(use_button)
            rescan_button = QtWidgets.QPushButton("Rescan")
            rescan_button.clicked.connect(self._reload_printers)
            printer_buttons.addWidget(rescan_button)
            printer_layout.addLayout(printer_buttons)
            layout.addWidget(printer_box)

            # --- Copies -------------------------------------------------
            copies_box = QtWidgets.QGroupBox("Number of pages to print")
            copies_layout = QtWidgets.QVBoxLayout(copies_box)

            quick = QtWidgets.QHBoxLayout()
            for value in (1, 2, 3, 4, 5, 10):
                button = QtWidgets.QPushButton(str(value))
                button.setFixedWidth(44)
                button.clicked.connect(lambda _checked=False, v=value: self.apply_copies(v))
                quick.addWidget(button)
            quick.addStretch()
            copies_layout.addLayout(quick)

            custom = QtWidgets.QHBoxLayout()
            self.copies_input = QtWidgets.QSpinBox()
            self.copies_input.setRange(1, 999)
            self.copies_input.setPrefix("Copies: ")
            custom.addWidget(self.copies_input)
            set_button = QtWidgets.QPushButton("Set")
            set_button.clicked.connect(lambda: self.apply_copies(self.copies_input.value()))
            custom.addWidget(set_button)
            reset_button = QtWidgets.QPushButton("Reset to 1")
            reset_button.clicked.connect(self._reset)
            custom.addWidget(reset_button)
            copies_layout.addLayout(custom)

            self.auto_reset = QtWidgets.QCheckBox("Automatically reset to 1 after printing finishes")
            self.auto_reset.setChecked(True)
            copies_layout.addWidget(self.auto_reset)
            layout.addWidget(copies_box)

            # --- Status -------------------------------------------------
            self.status_label = QtWidgets.QLabel()
            self.status_label.setWordWrap(True)
            self.status_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            layout.addWidget(self.status_label)

            self.watcher_label = QtWidgets.QLabel()
            self.watcher_label.setWordWrap(True)
            layout.addWidget(self.watcher_label)

            self.tray_hint = QtWidgets.QLabel()
            self.tray_hint.setWordWrap(True)
            self.tray_hint.setStyleSheet("color: palette(mid);")
            layout.addWidget(self.tray_hint)

            bottom = QtWidgets.QHBoxLayout()
            diag_button = QtWidgets.QPushButton("Diagnostics")
            diag_button.clicked.connect(self._show_diagnostics)
            bottom.addWidget(diag_button)
            bottom.addStretch()

            self.quit_button = QtWidgets.QPushButton("Quit")
            self.quit_button.clicked.connect(self.quit_app)
            bottom.addWidget(self.quit_button)

            self.close_button = QtWidgets.QPushButton("Close")
            self.close_button.setDefault(True)
            self.close_button.clicked.connect(self.close)
            bottom.addWidget(self.close_button)
            layout.addLayout(bottom)

            central.setLayout(layout)
            self.setCentralWidget(central)

            self.tray = None
            self._reload_printers()
            self._on_watcher_state(STATE_IDLE)

            # Keep the display honest if the value is changed elsewhere.
            self._timer = QtCore.QTimer(self)
            self._timer.timeout.connect(self.refresh)
            self._timer.start(5000)

        # --- printer handling ------------------------------------------
        def _reload_printers(self):
            self.printer_combo.clear()
            queues = list_queues()
            self.printer_combo.addItems(queues)
            detected = detect_printer(refresh=True)
            if detected and detected in queues:
                self.printer_combo.setCurrentText(detected)
            self.refresh()

        def _use_selected_printer(self):
            name = self.printer_combo.currentText().strip()
            if not name:
                return
            if save_printer_override(name):
                self.refresh()
                self.notify(f"Now using printer: {name}")
            else:
                self.warn("Could not save the printer choice. See the log.")

        # --- copies handling -------------------------------------------
        def apply_copies(self, value: int):
            printer = detect_printer()
            if not printer:
                self.warn(
                    "No Rollo printer queue was found, so the copy count cannot be set.\n\n"
                    "Pick the right printer above and press 'Use this printer'."
                )
                return
            if not set_copies(value, printer):
                self.warn(
                    f"Could not set {value} copies on '{printer}'.\n\n"
                    "The setting was not applied. See Diagnostics for details."
                )
                self.refresh()
                return

            self.copies_input.setValue(value)
            self.refresh()
            if value > 1 and self.auto_reset.isChecked():
                self.watcher.arm()
                self.notify(f"Set to {value} copies. Print now - it will reset to 1 afterwards.")
            else:
                self.watcher.cancel()
                self.notify(f"Set to {value} copies.")

        def _reset(self):
            self.watcher.cancel()
            printer = detect_printer()
            if not printer or not reset_to_default(printer):
                self.warn("Could not reset the copy count. See Diagnostics for details.")
            self.refresh()

        # --- status ------------------------------------------------------
        def refresh(self):
            printer = detect_printer()
            if not printer:
                queues = list_queues()
                self.status_label.setText(
                    "<b style='color:#c0392b'>No Rollo printer found.</b><br>"
                    f"Queues CUPS can see: {', '.join(queues) if queues else '(none)'}<br>"
                    "Choose the correct one above and press 'Use this printer'."
                )
                return
            if not queue_exists(printer):
                self.status_label.setText(
                    f"<b style='color:#c0392b'>Printer '{printer}' no longer exists.</b><br>"
                    "Press Rescan and choose the correct printer."
                )
                return
            value = current_copies(printer)
            shown = value if value is not None else "unreadable"
            self.status_label.setText(f"<b>Printer:</b> {printer}<br><b>Current copies:</b> {shown}")
            if value is not None and not self.copies_input.hasFocus():
                self.copies_input.setValue(value)
            if self.tray:
                self.tray.sync(printer, value)

        def _on_watcher_state(self, state: str):
            messages = {
                STATE_IDLE: "Auto-reset: idle.",
                STATE_WAITING: "Auto-reset: armed - waiting for you to print.",
                STATE_PRINTING: "Auto-reset: printing - will restore 1 copy when done.",
            }
            self.watcher_label.setText(messages.get(state, ""))

        def _on_watcher_reset(self, success: bool, reason: str):
            self.refresh()
            if success:
                self.notify(f"Copies restored to 1 ({reason}).")
            else:
                self.warn(f"Could not restore copies to 1 ({reason}). See Diagnostics.")

        # --- helpers -------------------------------------------------------
        def notify(self, message: str):
            logger.info(message)
            self.statusBar().showMessage(message, 8000)
            if self.tray and self.tray.supportsMessages():
                self.tray.showMessage("Rollo Printer Copies", message, self.tray.icon(), 5000)

        def warn(self, message: str):
            logger.error(message.replace("\n", " "))
            QtWidgets.QMessageBox.warning(self, "Rollo Printer Copies", message)

        def _show_diagnostics(self):
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle("Diagnostics")
            dialog.resize(640, 480)
            dialog_layout = QtWidgets.QVBoxLayout(dialog)
            text = QtWidgets.QPlainTextEdit(environment_report())
            text.setReadOnly(True)
            text.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
            dialog_layout.addWidget(text)
            copy_button = QtWidgets.QPushButton("Copy to clipboard")
            copy_button.clicked.connect(lambda: QtWidgets.QApplication.clipboard().setText(text.toPlainText()))
            dialog_layout.addWidget(copy_button)
            dialog.exec()

        def configure_for_tray(self, available: bool):
            """Close means 'hide to the tray' only when there IS a tray."""
            self._tray_available = available
            if available:
                self.close_button.setText("Close")
                self.close_button.setToolTip("Hide this window. The app keeps running in the tray.")
                self.quit_button.setVisible(True)
                self.tray_hint.setText(
                    "Closing this window leaves the app running in the background. "
                    "Click the printer icon in the system tray to open it again."
                )
            else:
                self.close_button.setText("Close")
                self.close_button.setToolTip("Close the app.")
                self.quit_button.setVisible(False)
                self.tray_hint.setText(
                    "This desktop has no system tray, so closing the window closes the app. "
                    "Re-open it from the applications menu whenever you need it."
                )

        def quit_app(self):
            logger.info("Quit requested from the window")
            self._tray_available = False
            if self.tray:
                self.tray.hide()
            self.watcher.stop()
            QtWidgets.QApplication.instance().quit()

        def closeEvent(self, event):
            # Only hide to the tray if there genuinely is a tray to hide in,
            # otherwise the app would vanish with no way to get it back.
            if self._tray_available and self.tray is not None:
                event.ignore()
                self.hide()
                if not self._announced_tray:
                    self._announced_tray = True
                    if self.tray.supportsMessages():
                        self.tray.showMessage(
                            APP_NAME,
                            "Still running. Click the printer icon in the tray to open it again.",
                            self.tray.icon(),
                            5000,
                        )
                return
            self.watcher.stop()
            event.accept()
            QtWidgets.QApplication.instance().quit()

    return MainWindow


def main() -> int:
    parser = argparse.ArgumentParser(description="Rollo print helper")
    parser.add_argument("--status", action="store_true", help="Print the current copy value and exit")
    parser.add_argument("--diagnose", action="store_true", help="Print a full environment report and exit")
    parser.add_argument("--set", type=int, metavar="N", help="Set the copy count from the command line and exit")
    parser.add_argument("--tray-only", action="store_true", help="Start hidden, if a system tray is available")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    configure_logging(args.verbose)

    if args.status:
        return status_mode()

    if args.diagnose:
        print(environment_report())
        return 0

    if args.set is not None:
        printer = detect_printer(refresh=True)
        if not printer:
            print("No Rollo printer queue found.", file=sys.stderr)
            return 1
        if not set_copies(args.set, printer):
            print(f"Failed to set {args.set} copies on {printer}.", file=sys.stderr)
            return 1
        print(f"{printer}: {args.set} copies")
        return 0

    logger.info("Starting Rollo printer helper")

    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        logger.error("No GUI session detected (DISPLAY and WAYLAND_DISPLAY are both unset)")
        print(
            "No desktop session detected. Start this from a logged-in desktop,\n"
            "or use --status / --set N / --diagnose from a terminal.",
            file=sys.stderr,
        )
        return 1

    try:
        from PySide6 import QtWidgets
    except ImportError as exc:
        logger.critical("PySide6 is not installed: %s", exc)
        print(
            f"PySide6 is not installed in this Python ({sys.executable}).\n"
            "Re-run the installer, or use the simple launcher instead.",
            file=sys.stderr,
        )
        return 1

    from app.icon import APP_ID, APP_NAME, app_icon

    window_class = build_gui()
    # argv[0] becomes the X11 WM_CLASS instance name; passing the real argv
    # makes the taskbar label the window "python3" with a generic icon.
    app = QtWidgets.QApplication([APP_ID])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    # Matches rollo-copies.desktop, which is how Wayland finds the icon.
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(app_icon())

    window = window_class()

    tray_available = QtWidgets.QSystemTrayIcon.isSystemTrayAvailable()
    logger.info("System tray available: %s", tray_available)

    if tray_available:
        from app.tray import TrayApp

        window.tray = TrayApp(app, window)
        window.tray.show()
        app.setQuitOnLastWindowClosed(False)
        window.configure_for_tray(True)
    else:
        # No tray on this desktop, so the window IS the app. Closing it quits,
        # and we must never start hidden or the user sees nothing at all.
        logger.warning("No system tray on this desktop; running as a normal window")
        app.setQuitOnLastWindowClosed(True)
        window.configure_for_tray(False)

    if args.tray_only and tray_available:
        logger.info("Starting hidden in the system tray")
    else:
        window.show()
        window.raise_()
        window.activateWindow()

    window.refresh()
    exit_code = app.exec()
    window.watcher.stop()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
