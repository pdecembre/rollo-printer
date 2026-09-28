import argparse
import logging
import sys
from pathlib import Path

from PySide6 import QtWidgets

from app.cups_helper import PRINTER_NAME, current_copies
from app.tray import TrayApp


def configure_logging():
    log_dir = Path.home() / ".rollo-printer"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "runtime.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8")],
    )
    logging.getLogger("rollo_printer").setLevel(logging.INFO)


def status_mode():
    value = current_copies()
    if value is None:
        print(f"{PRINTER_NAME}: unknown")
        return 1
    print(f"{PRINTER_NAME}: {value} copies")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Rollo print helper")
    parser.add_argument("--status", action="store_true", help="Print current copy value and exit")
    args = parser.parse_args()

    if args.status:
        return status_mode()

    configure_logging()
    logging.info("Starting Rollo printer helper")
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    tray_app = TrayApp(app)
    tray_app.show()
    logging.info("Tray icon started for printer %s", PRINTER_NAME)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
