"""The application icon.

The desktop shows "python3" with a generic gear unless the app states its own
identity, so this is used for the window, the taskbar and the tray. A themed
printer icon is preferred; the drawn fallback exists because icon themes on
minimal desktops do not always carry one.
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui

APP_ID = "rollo-copies"          # must match rollo-copies.desktop
APP_NAME = "Rollo Page Count"

_THEME_NAMES = ("printer", "printer-symbolic", "document-print", "printers")


def _draw_printer(size: int) -> QtGui.QPixmap:
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    s = size / 64.0

    outline = QtGui.QPen(QtGui.QColor("#44506a"), max(1.0, 2 * s))

    # Sheet feeding in at the top.
    painter.setPen(outline)
    painter.setBrush(QtGui.QColor("#ffffff"))
    painter.drawRect(QtCore.QRectF(19 * s, 5 * s, 26 * s, 14 * s))

    # Printer body.
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(QtGui.QColor("#2d7ff9"))
    painter.drawRoundedRect(QtCore.QRectF(5 * s, 18 * s, 54 * s, 24 * s), 4 * s, 4 * s)

    # Status light.
    painter.setBrush(QtGui.QColor("#7ef0b2"))
    painter.drawEllipse(QtCore.QRectF(49 * s, 23 * s, 5 * s, 5 * s))

    # Printed sheet coming out of the front.
    painter.setPen(outline)
    painter.setBrush(QtGui.QColor("#ffffff"))
    painter.drawRect(QtCore.QRectF(17 * s, 36 * s, 30 * s, 23 * s))

    # Lines of text on the printed sheet.
    painter.setPen(QtGui.QPen(QtGui.QColor("#93a0b5"), max(1.0, 2 * s)))
    for y in (43, 49, 55):
        painter.drawLine(QtCore.QPointF(22 * s, y * s), QtCore.QPointF(42 * s, y * s))

    painter.end()
    return pixmap


def app_icon() -> QtGui.QIcon:
    for name in _THEME_NAMES:
        icon = QtGui.QIcon.fromTheme(name)
        if not icon.isNull() and icon.availableSizes():
            return icon
    icon = QtGui.QIcon()
    for size in (16, 22, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_draw_printer(size))
    return icon
