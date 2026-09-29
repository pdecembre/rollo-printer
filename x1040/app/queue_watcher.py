"""Background watcher that restores copies=1 once printing has finished.

The naive version of this ("reset as soon as the queue is empty") is wrong:
at the moment the user picks 3 copies the queue is *always* empty, so it
resets before they ever hit print. This watcher therefore runs in two
phases -- wait for a job to appear, then wait for it to drain.
"""

import logging
import threading
from typing import Callable, Optional

from app.cups_helper import check_queue_has_jobs, reset_to_default

logger = logging.getLogger("rollo_printer")

STATE_IDLE = "idle"
STATE_WAITING = "waiting"
STATE_PRINTING = "printing"


class QueueWatcher:
    """Watches the print queue on a daemon thread.

    Callbacks fire on the watcher thread, so a GUI caller must marshal them
    onto the main thread (the tray does this with a Qt signal).
    """

    def __init__(
        self,
        poll_interval: float = 2.0,
        arm_timeout: float = 900.0,
        settle_polls: int = 2,
        on_state_change: Optional[Callable[[str], None]] = None,
        on_reset: Optional[Callable[[bool, str], None]] = None,
    ):
        self.poll_interval = poll_interval
        self.arm_timeout = arm_timeout
        self.settle_polls = max(1, settle_polls)
        self.on_state_change = on_state_change
        self.on_reset = on_reset

        self._armed = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._state = STATE_IDLE

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_armed(self) -> bool:
        return self._armed.is_set()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="rollo-queue-watcher", daemon=True)
        self._thread.start()
        logger.info("Queue watcher thread started")

    def arm(self):
        """Begin watching; called after the user raises the copy count."""
        logger.info("Queue watcher armed; waiting for a print job")
        self._armed.set()

    def cancel(self):
        """Stop watching without resetting the copy count."""
        if self._armed.is_set():
            logger.info("Queue watcher cancelled")
        self._armed.clear()
        self._set_state(STATE_IDLE)

    def stop(self):
        self._stop.set()
        self._armed.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.poll_interval + 1)

    def _set_state(self, state: str):
        if state == self._state:
            return
        self._state = state
        if self.on_state_change:
            try:
                self.on_state_change(state)
            except Exception:
                logger.exception("on_state_change callback failed")

    def _sleep(self, seconds: float) -> bool:
        """Interruptible sleep. Returns False if we were asked to stop."""
        return not self._stop.wait(seconds)

    def _run(self):
        while not self._stop.is_set():
            # Park cheaply until somebody arms us.
            if not self._armed.wait(timeout=1.0):
                continue
            if self._stop.is_set():
                break
            self._watch_one_cycle()

    def _watch_one_cycle(self):
        # Phase 1: wait for a job to show up.
        self._set_state(STATE_WAITING)
        waited = 0.0
        saw_job = False
        while self._armed.is_set() and not self._stop.is_set():
            if check_queue_has_jobs():
                saw_job = True
                break
            if waited >= self.arm_timeout:
                logger.info("No print job within %ss; resetting copies anyway", self.arm_timeout)
                break
            if not self._sleep(self.poll_interval):
                return
            waited += self.poll_interval

        if not self._armed.is_set() or self._stop.is_set():
            return

        # Phase 2: wait for the queue to drain, and stay drained.
        if saw_job:
            self._set_state(STATE_PRINTING)
            logger.info("Print job detected; waiting for the queue to drain")
            empty_polls = 0
            while self._armed.is_set() and not self._stop.is_set():
                if check_queue_has_jobs():
                    empty_polls = 0
                else:
                    empty_polls += 1
                    # Require several consecutive empty polls so we don't
                    # reset in the gap between two jobs of one print run.
                    if empty_polls >= self.settle_polls:
                        break
                if not self._sleep(self.poll_interval):
                    return
            if not self._armed.is_set() or self._stop.is_set():
                return

        reason = "printing finished" if saw_job else "timed out waiting for a print job"
        success = reset_to_default()
        if success:
            logger.info("Copies restored to 1 (%s)", reason)
        else:
            logger.error("Failed to restore copies to 1 (%s)", reason)

        self._armed.clear()
        self._set_state(STATE_IDLE)
        if self.on_reset:
            try:
                self.on_reset(success, reason)
            except Exception:
                logger.exception("on_reset callback failed")
