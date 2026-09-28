from __future__ import annotations

from PySide6 import QtGui, QtWidgets

from app.cups_helper import PRINTER_NAME, current_copies, reset_to_default, set_copies


class TrayApp(QtWidgets.QSystemTrayIcon):
    def __init__(self, app: QtWidgets.QApplication):
        super().__init__(self._make_icon())
        self.app = app
        self._menu = QtWidgets.QMenu()
        self._current_value = current_copies() or 1
        self._setup_menu()
        self.setContextMenu(self._menu)
        self.activated.connect(self._on_activated)
        self._update_status_text()

    @staticmethod
    def _make_icon() -> QtGui.QIcon:
        pixmap = QtGui.QPixmap(32, 32)
        pixmap.fill(QtGui.QColor("#2d7ff9"))
        painter = QtGui.QPainter(pixmap)
        painter.setPen(QtGui.QPen(QtGui.QColor("white"), 2))
        painter.drawRect(8, 8, 16, 16)
        painter.drawLine(8, 16, 24, 16)
        painter.end()
        return QtGui.QIcon(pixmap)

    def _refresh_current_value(self):
        value = current_copies()
        if value is not None:
            self._current_value = value
        self._update_status_text()
        self._setup_menu()

    def _update_status_text(self):
        self.setToolTip(f"Rollo printer helper\nPrinter: {PRINTER_NAME}\nCurrent copies: {self._current_value}")

    def _setup_menu(self):
        self._menu.clear()

        status_action = self._menu.addAction(f"Status: {self._current_value} copies")
        status_action.setEnabled(False)

        refresh_action = self._menu.addAction("Refresh current value")
        refresh_action.triggered.connect(self._refresh_current_value)

        self._menu.addSeparator()

        for value in [1, 2, 3, 4, 5, 10]:
            action = self._menu.addAction(f"# of pages to print: {value}")
            action.triggered.connect(lambda checked=False, v=value: self._set_copies(v))

        self._menu.addSeparator()

        custom_action = self._menu.addAction("# of pages to print")
        custom_action.triggered.connect(self._prompt_for_custom_value)

        self._menu.addSeparator()

        reset_action = self._menu.addAction("Reset to 1")
        reset_action.triggered.connect(self._reset_to_default)

        self._menu.addSeparator()
        quit_action = self._menu.addAction("Quit")
        quit_action.triggered.connect(self.app.quit)

    def _set_copies(self, value: int):
        if set_copies(value):
            self._current_value = value
            self._update_status_text()
            self._setup_menu()

    def _reset_to_default(self):
        if reset_to_default():
            self._current_value = 1
            self._update_status_text()
            self._setup_menu()

    def _prompt_for_custom_value(self):
        value, ok = QtWidgets.QInputDialog.getInt(
            None,
            "# of pages to print",
            "Enter number of copies:",
            self._current_value,
            1,
            100,
            1,
        )
        if ok:
            self._set_copies(value)

    def _on_activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.Trigger:
            self._menu.popup(QtGui.QCursor.pos())

    def show(self):
        super().show()
