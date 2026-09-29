"""Tests for the CUPS layer.

Each test here pins down a bug that actually shipped, so it cannot come back.
"""

import subprocess

import pytest

from app import cups_helper
from app.cups_helper import parse_copies, queue_has_jobs


# --- parse_copies -----------------------------------------------------------
# lpoptions prints ONE space-separated line. The original code split on
# "copies=" and int()'d the remainder, so it returned None for every real
# printer and the UI permanently showed "unavailable".

REAL_LPOPTIONS_LINE = (
    "copies=3 device-uri=usb://Rollo/X1040 finishings=3 job-cancel-after=10800 "
    "number-up=1 printer-info=Rollo_X1040_USB printer-is-accepting-jobs=true "
    "printer-make-and-model='Rollo X1040 Label Printer'"
)


def test_parse_copies_reads_real_single_line_output():
    assert parse_copies(REAL_LPOPTIONS_LINE) == 3


def test_parse_copies_handles_copies_at_end_of_line():
    assert parse_copies("number-up=1 copies=7") == 7


def test_parse_copies_returns_none_when_absent():
    assert parse_copies("device-uri=usb://Rollo/X1040 number-up=1") is None


def test_parse_copies_is_not_fooled_by_a_similar_key():
    # "job-copies=9" must not be mistaken for the copies option.
    assert parse_copies("job-copies=9 copies=2") == 2


def test_parse_copies_ignores_empty_output():
    assert parse_copies("") is None


# --- queue_has_jobs ---------------------------------------------------------

def test_queue_has_jobs_detects_active_jobs():
    output = "Rollo_X1040_USB-123 user 1024 Mon 01 Jan\nRollo_X1040_USB-124 user 2048 Mon 01 Jan\n"
    assert queue_has_jobs(output, "Rollo_X1040_USB") is True


def test_queue_has_jobs_ignores_idle_queue():
    assert queue_has_jobs("", "Rollo_X1040_USB") is False


def test_queue_has_jobs_ignores_other_printers():
    assert queue_has_jobs("Canon-10 user 512 Mon 01 Jan\n", "Rollo_X1040_USB") is False


# --- printer detection ------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_detection_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(cups_helper, "_cached_printer", None)
    monkeypatch.delenv("ROLLO_PRINTER", raising=False)
    # Point the override file somewhere that does not exist, so a real one on
    # the developer's machine cannot influence the tests.
    monkeypatch.setattr(cups_helper, "PRINTER_OVERRIDE_FILE", tmp_path / "absent")
    yield


def test_detect_printer_finds_queue_with_underscore(monkeypatch):
    monkeypatch.setattr(cups_helper, "list_queues", lambda: ["Canon", "Rollo_X1040_USB"])
    assert cups_helper.detect_printer(refresh=True) == "Rollo_X1040_USB"


def test_detect_printer_finds_queue_without_underscore(monkeypatch):
    # The docs and the code disagreed on this name; detection must accept both.
    monkeypatch.setattr(cups_helper, "list_queues", lambda: ["Rollo_X1040USB"])
    assert cups_helper.detect_printer(refresh=True) == "Rollo_X1040USB"


def test_detect_printer_matches_on_model_number_alone(monkeypatch):
    monkeypatch.setattr(cups_helper, "list_queues", lambda: ["X1040"])
    assert cups_helper.detect_printer(refresh=True) == "X1040"


def test_detect_printer_returns_none_when_absent(monkeypatch):
    monkeypatch.setattr(cups_helper, "list_queues", lambda: ["Canon", "HP_LaserJet"])
    assert cups_helper.detect_printer(refresh=True) is None


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("ROLLO_PRINTER", "My_Custom_Queue")
    monkeypatch.setattr(cups_helper, "list_queues", lambda: ["Rollo_X1040_USB"])
    assert cups_helper.detect_printer(refresh=True) == "My_Custom_Queue"


# --- set_copies verification ------------------------------------------------
# lpoptions exits 0 even for a queue that does not exist, writing a junk entry
# to ~/.cups/lpoptions. The old code trusted that exit code, so a wrong queue
# name reported success and silently did nothing.

def _fake_run(returncode=0, stdout="", stderr=""):
    return lambda command: subprocess.CompletedProcess(command, returncode, stdout, stderr)


def test_set_copies_refuses_a_nonexistent_queue(monkeypatch):
    calls = []
    monkeypatch.setattr(cups_helper, "list_queues", lambda: ["Canon"])
    monkeypatch.setattr(cups_helper, "_run", lambda cmd: calls.append(cmd) or _fake_run()(cmd))
    assert cups_helper.set_copies(3, "Rollo_X1040_USB") is False
    assert not any("lpoptions" in c[0] and "-o" in c for c in calls), "must not write to a missing queue"


def test_set_copies_fails_when_value_does_not_stick(monkeypatch):
    monkeypatch.setattr(cups_helper, "list_queues", lambda: ["Rollo_X1040_USB"])
    # lpoptions "succeeds" but the read-back still says 1.
    monkeypatch.setattr(cups_helper, "_run", _fake_run(0, "copies=1 number-up=1"))
    assert cups_helper.set_copies(3, "Rollo_X1040_USB") is False


def test_set_copies_succeeds_when_value_is_verified(monkeypatch):
    monkeypatch.setattr(cups_helper, "list_queues", lambda: ["Rollo_X1040_USB"])
    monkeypatch.setattr(cups_helper, "_run", _fake_run(0, "copies=3 number-up=1"))
    assert cups_helper.set_copies(3, "Rollo_X1040_USB") is True


def test_set_copies_rejects_zero_and_negative(monkeypatch):
    monkeypatch.setattr(cups_helper, "list_queues", lambda: ["Rollo_X1040_USB"])
    assert cups_helper.set_copies(0, "Rollo_X1040_USB") is False
    assert cups_helper.set_copies(-2, "Rollo_X1040_USB") is False


def test_missing_cups_binary_is_survived(monkeypatch):
    def boom(*_args, **_kwargs):
        raise FileNotFoundError("lpstat")

    monkeypatch.setattr(cups_helper.subprocess, "run", boom)
    assert cups_helper.list_queues() == []
    assert cups_helper.current_copies("Rollo_X1040_USB") is None
