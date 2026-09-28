from app.cups_helper import queue_has_jobs


def test_queue_has_jobs_detects_active_jobs():
    output = "Rollo_X1040USB-123 user\nRollo_X1040USB-456 user\n"
    assert queue_has_jobs(output, "Rollo_X1040USB") is True


def test_queue_has_jobs_ignores_idle_queue():
    output = ""
    assert queue_has_jobs(output, "Rollo_X1040USB") is False


def test_queue_has_jobs_ignores_other_printers():
    output = "Canon-10 user\n"
    assert queue_has_jobs(output, "Rollo_X1040USB") is False
