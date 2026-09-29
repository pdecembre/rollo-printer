"""CUPS integration for the Rollo copy helper.

Every function here is deliberately defensive. This app is installed on a
laptop we cannot log into, so a silent failure is far worse than a loud one.
Two CUPS behaviours drive the design:

1. ``lpoptions -p <queue> -o copies=N`` exits 0 even when <queue> does not
   exist -- it just writes a junk entry into ~/.cups/lpoptions. So a wrong
   queue name looks like success and does nothing. Every write is verified
   by reading the value back.
2. ``lpoptions -p <queue>`` prints a single space-separated line, not one
   option per line, so the value has to be pulled out with a pattern.
"""

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("rollo_printer")

CONFIG_DIR = Path.home() / ".rollo-printer"
PRINTER_OVERRIDE_FILE = CONFIG_DIR / "printer"

# A queue is treated as the Rollo if its name looks like either of these.
ROLLO_PATTERN = re.compile(r"rollo|x1040", re.IGNORECASE)

# lpoptions prints one line: "copies=1 device-uri=... printer-info=...".
COPIES_PATTERN = re.compile(r"(?:^|\s)copies=(\d+)")

COMMAND_TIMEOUT = 10

_cached_printer: Optional[str] = None


def _run(command: List[str]) -> subprocess.CompletedProcess:
    """Run a command, never raise, and always log a failure."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=COMMAND_TIMEOUT,
        )
    except FileNotFoundError:
        logger.error("Command not found: %s. Is CUPS installed?", command[0])
        return subprocess.CompletedProcess(command, 127, "", f"{command[0]}: not found")
    except subprocess.TimeoutExpired:
        logger.error("Command timed out after %ss: %s", COMMAND_TIMEOUT, " ".join(command))
        return subprocess.CompletedProcess(command, 124, "", "timed out")
    if result.returncode != 0:
        logger.warning("Command failed (%s): %s -- %s", result.returncode, " ".join(command), result.stderr.strip())
    return result


def list_queues() -> List[str]:
    """Every print queue CUPS knows about."""
    result = _run(["lpstat", "-e"])
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def detect_printer(refresh: bool = False) -> Optional[str]:
    """Resolve the Rollo queue name.

    Order of precedence, so a surprise on the target laptop can always be
    corrected without editing source:
      1. ROLLO_PRINTER environment variable
      2. ~/.rollo-printer/printer  (one line, the queue name)
      3. auto-detection from `lpstat -e`
    """
    global _cached_printer
    if _cached_printer and not refresh:
        return _cached_printer

    override = os.environ.get("ROLLO_PRINTER", "").strip()
    if override:
        logger.info("Using printer from ROLLO_PRINTER: %s", override)
        _cached_printer = override
        return _cached_printer

    try:
        if PRINTER_OVERRIDE_FILE.is_file():
            value = PRINTER_OVERRIDE_FILE.read_text(encoding="utf-8").strip()
            if value:
                logger.info("Using printer from %s: %s", PRINTER_OVERRIDE_FILE, value)
                _cached_printer = value
                return _cached_printer
    except OSError as exc:
        logger.warning("Could not read %s: %s", PRINTER_OVERRIDE_FILE, exc)

    queues = list_queues()
    matches = [q for q in queues if ROLLO_PATTERN.search(q)]
    if matches:
        if len(matches) > 1:
            logger.warning("Several Rollo-like queues found (%s); using the first", ", ".join(matches))
        logger.info("Auto-detected printer queue: %s", matches[0])
        _cached_printer = matches[0]
        return _cached_printer

    logger.error("No Rollo queue found. Queues visible to CUPS: %s", ", ".join(queues) or "(none)")
    return None


def save_printer_override(name: str) -> bool:
    """Pin the queue name so detection is skipped next launch."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        PRINTER_OVERRIDE_FILE.write_text(f"{name}\n", encoding="utf-8")
    except OSError as exc:
        logger.error("Could not save printer override: %s", exc)
        return False
    global _cached_printer
    _cached_printer = name
    logger.info("Saved printer override: %s", name)
    return True


def queue_exists(name: Optional[str] = None) -> bool:
    name = name or detect_printer()
    if not name:
        return False
    return name in list_queues()


def current_copies(name: Optional[str] = None) -> Optional[int]:
    """Read the queue's current default copy count, or None if unreadable."""
    name = name or detect_printer()
    if not name:
        return None
    result = _run(["lpoptions", "-p", name])
    if result.returncode != 0:
        return None
    return parse_copies(result.stdout)


def parse_copies(lpoptions_output: str) -> Optional[int]:
    """Pull `copies=N` out of lpoptions' single-line output."""
    match = COPIES_PATTERN.search(lpoptions_output)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def set_copies(count: int, name: Optional[str] = None) -> bool:
    """Set the default copy count, and verify it actually took effect.

    Returns False -- loudly -- if the queue is missing or the value did not
    stick, rather than trusting lpoptions' exit code.
    """
    if count < 1:
        logger.warning("Refusing to set invalid copy count: %s", count)
        return False

    name = name or detect_printer()
    if not name:
        logger.error("Cannot set copies: no Rollo printer queue found")
        return False

    if not queue_exists(name):
        logger.error(
            "Cannot set copies: queue %r does not exist. lpoptions would report "
            "success and do nothing. Visible queues: %s",
            name, ", ".join(list_queues()) or "(none)",
        )
        return False

    result = _run(["lpoptions", "-p", name, "-o", f"copies={count}"])
    if result.returncode != 0:
        logger.error("lpoptions failed for %s: %s", name, result.stderr.strip())
        return False

    # lpoptions exits 0 far too easily, so confirm by reading the value back.
    readback = current_copies(name)
    if readback != count:
        logger.error("Set copies=%s on %s but read back %s", count, name, readback)
        return False

    logger.info("Set %s copies for printer %s (verified)", count, name)
    return True


def reset_to_default(name: Optional[str] = None) -> bool:
    logger.info("Resetting printer copies to 1")
    return set_copies(1, name)


def queue_has_jobs(lpstat_output: str, printer_name: Optional[str] = None) -> bool:
    """True if lpstat's job listing mentions a job for this printer."""
    printer_name = printer_name or detect_printer()
    if not printer_name:
        return False
    for line in lpstat_output.splitlines():
        line = line.strip()
        if line and line.startswith(printer_name):
            return True
    return False


def check_queue_has_jobs(name: Optional[str] = None) -> bool:
    name = name or detect_printer()
    if not name:
        return False
    result = _run(["lpstat", "-o", name])
    if result.returncode != 0:
        # An unreadable queue is reported as idle; the watcher handles the
        # ambiguity with its own timeout rather than spinning forever.
        return False
    return queue_has_jobs(result.stdout, name)
