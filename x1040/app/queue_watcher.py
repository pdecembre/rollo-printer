import time

from app.cups_helper import check_queue_has_jobs, reset_to_default


class QueueWatcher:
    def __init__(self, poll_interval: float = 2.0):
        self.poll_interval = poll_interval
        self.running = True

    def stop(self):
        self.running = False

    def run(self):
        while self.running:
            if not check_queue_has_jobs():
                reset_to_default()
                return
            time.sleep(self.poll_interval)
