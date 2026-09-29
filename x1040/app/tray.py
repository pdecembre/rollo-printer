"""Optional system-tray surface.

This is a convenience layer only. GNOME (and therefore Zorin) has no
built-in system tray -- Qt needs the AppIndicator extension to provide
org.kde.StatusNotifierWatcher -- so the app must remain fully usable when
this class is never constructed. All real work lives in the main window.
"""

from __future__ import annotations

import logging

from PySide6 import QtGui, QtWidgets

from app.icon import APP_NAME, app_icon

logger = logging.getLogger("rollo_printer")


class TrayApp(QtWidgets.QSystemTrayIcon):
    def __init__(self, app: QtWidgets.QApplication, window):
        super().__init__(self._make_icon())
        self.app = app
        self.window = window
        self._printer = None
        self._value = None
        self._menu = QtWidgets.QMenu()
        self.setContextMenu(self._menu)
        self.activated.connect(self._on_activated)
        self._build_menu()

    @staticmethod
    def _make_icon() -> QtGui.QIcon:
        return app_icon()

    def sync(self, printer, value):
        """Called by the window whenever the printer or copy count changes."""
        if (printer, value) == (self._printer, self._value):
            return
        self._printer = printer
        self._value = value
        shown = value if value is not None else "unknown"
        self.setToolTip(f"{APP_NAME}\nPrinter: {printer}\nPages to print: {shown}")
        self._build_menu()

    def _build_menu(self):
        self._menu.clear()

        shown = self._value if self._value is not None else "unknown"
        status = self._menu.addAction(f"Currently printing {shown} page(s)")
        status.setEnabled(False)

        open_action = self._menu.addAction(f"Open {APP_NAME}")
        open_action.triggered.connect(self._show_window)
        self._menu.setDefaultAction(open_action)

        self._menu.addSeparator()
        for value in (1, 2, 3, 4, 5, 10):
            action = self._menu.addAction(f"# of pages to print: {value}")
            action.triggered.connect(lambda _checked=False, v=value: self.window.apply_copies(v))

        custom = self._menu.addAction("# of pages to print...")
        custom.triggered.connect(self._prompt_for_custom_value)

        self._menu.addSeparator()
        reset = self._menu.addAction("Reset to 1")
        reset.triggered.connect(lambda: self.window.apply_copies(1))

        self._menu.addSeparator()
        quit_action = self._menu.addAction("Quit")
        quit_action.triggered.connect(self._quit)

    def _show_window(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _prompt_for_custom_value(self):
        value, ok = QtWidgets.QInputDialog.getInt(
            self.window, "# of pages to print", "Enter number of copies:", self._value or 1, 1, 999, 1
        )
        if ok:
            self.window.apply_copies(value)

    def _on_activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.Trigger:
            if self.window.isVisible():
                self.window.hide()
            else:
                self._show_window()

    def _quit(self):
        logger.info("Quit requested from the tray menu")
        self.window.quit_app()
