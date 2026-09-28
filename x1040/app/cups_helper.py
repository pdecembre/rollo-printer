import logging
import subprocess
from typing import Optional

PRINTER_NAME = "Rollo_X1040_USB"

logger = logging.getLogger("rollo_printer")


def _run_command(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def set_copies(count: int) -> bool:
    if count < 1:
        logger.warning("Attempted to set invalid copy count: %s", count)
        return False
    cmd = ["lpoptions", "-p", PRINTER_NAME, "-o", f"copies={count}"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        logger.info("Set %s copies for printer %s", count, PRINTER_NAME)
    else:
        logger.error("Failed to set copies=%s for %s: %s", count, PRINTER_NAME, result.stderr.strip())
    return result.returncode == 0


def reset_to_default() -> bool:
    logger.info("Resetting printer %s to default copies=1", PRINTER_NAME)
    return set_copies(1)


def queue_has_jobs(lpstat_output: str, printer_name: str = PRINTER_NAME) -> bool:
    lines = (line.strip() for line in lpstat_output.splitlines())
    for line in lines:
        if not line:
            continue
        if line.startswith(printer_name):
            return True
    return False


def check_queue_has_jobs() -> bool:
    output = _run_command(["lpstat", "-o", PRINTER_NAME])
    return queue_has_jobs(output, PRINTER_NAME)


def current_copies() -> Optional[int]:
    output = _run_command(["lpoptions", "-p", PRINTER_NAME])
    if not output:
        return None
    for line in output.splitlines():
        if "copies=" in line:
            try:
                value = line.split("copies=")[-1].strip()
                return int(value)
            except ValueError:
                continue
    return None
