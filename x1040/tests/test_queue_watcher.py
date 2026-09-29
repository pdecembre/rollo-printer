"""Tests for the auto-reset watcher.

The bug these pin down: the original watcher reset the copy count as soon as
the queue was empty -- which is always true at the moment the user picks a
count, so it reset before they ever printed.
"""

import time

import pytest

from app import queue_watcher
from app.queue_watcher import STATE_IDLE, STATE_PRINTING, STATE_WAITING, QueueWatcher


@pytest.fixture
def fake_queue(monkeypatch):
    state = {"jobs": False, "resets": 0}
    monkeypatch.setattr(queue_watcher, "check_queue_has_jobs", lambda *a, **k: state["jobs"])

    def _reset(*_a, **_k):
        state["resets"] += 1
        return True

    monkeypatch.setattr(queue_watcher, "reset_to_default", _reset)
    return state


def _watcher(**kwargs):
    defaults = dict(poll_interval=0.02, arm_timeout=10, settle_polls=2)
    defaults.update(kwargs)
    return QueueWatcher(**defaults)


def test_does_not_reset_before_a_job_appears(fake_queue):
    """The original bug: resetting immediately, before the user prints."""
    watcher = _watcher()
    watcher.start()
    watcher.arm()
    try:
        time.sleep(0.3)
        assert fake_queue["resets"] == 0
        assert watcher.state == STATE_WAITING
        assert watcher.is_armed
    finally:
        watcher.stop()


def test_resets_once_after_the_job_drains(fake_queue):
    states = []
    watcher = _watcher(on_state_change=states.append)
    watcher.start()
    watcher.arm()
    try:
        fake_queue["jobs"] = True
        time.sleep(0.2)
        assert watcher.state == STATE_PRINTING
        assert fake_queue["resets"] == 0

        fake_queue["jobs"] = False
        deadline = time.time() + 3
        while fake_queue["resets"] == 0 and time.time() < deadline:
            time.sleep(0.02)

        assert fake_queue["resets"] == 1
        assert watcher.state == STATE_IDLE
        assert not watcher.is_armed
        assert states == [STATE_WAITING, STATE_PRINTING, STATE_IDLE]
    finally:
        watcher.stop()


def test_survives_a_gap_between_two_jobs(fake_queue):
    """A brief empty poll between jobs must not trigger an early reset."""
    watcher = _watcher(settle_polls=5)
    watcher.start()
    watcher.arm()
    try:
        fake_queue["jobs"] = True
        time.sleep(0.15)
        fake_queue["jobs"] = False   # short gap
        time.sleep(0.04)
        fake_queue["jobs"] = True    # next job starts
        time.sleep(0.15)
        assert fake_queue["resets"] == 0, "reset during a gap between jobs"
    finally:
        watcher.stop()


def test_cancel_prevents_the_reset(fake_queue):
    watcher = _watcher()
    watcher.start()
    watcher.arm()
    try:
        time.sleep(0.1)
        watcher.cancel()
        fake_queue["jobs"] = True
        time.sleep(0.1)
        fake_queue["jobs"] = False
        time.sleep(0.2)
        assert fake_queue["resets"] == 0
        assert watcher.state == STATE_IDLE
    finally:
        watcher.stop()


def test_resets_after_timeout_if_nothing_is_printed(fake_queue):
    """Don't leave the printer stuck on 5 copies forever."""
    watcher = _watcher(arm_timeout=0.1)
    watcher.start()
    watcher.arm()
    try:
        deadline = time.time() + 3
        while fake_queue["resets"] == 0 and time.time() < deadline:
            time.sleep(0.02)
        assert fake_queue["resets"] == 1
        assert watcher.state == STATE_IDLE
    finally:
        watcher.stop()


def test_reset_callback_reports_the_reason(fake_queue):
    seen = []
    watcher = _watcher(arm_timeout=0.1, on_reset=lambda ok, why: seen.append((ok, why)))
    watcher.start()
    watcher.arm()
    try:
        deadline = time.time() + 3
        while not seen and time.time() < deadline:
            time.sleep(0.02)
        assert seen and seen[0][0] is True
        assert "timed out" in seen[0][1]
    finally:
        watcher.stop()
