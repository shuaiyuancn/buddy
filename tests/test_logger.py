import sys
import logging
import threading
import warnings
import pytest
from logging.handlers import RotatingFileHandler
from unittest.mock import MagicMock, patch

import src.logger


@pytest.fixture
def isolated_logging(tmp_path):
    """Run setup_logging against a temp folder and restore global logging/stdio/warnings state afterwards."""
    root = logging.getLogger()
    saved = (list(root.handlers), root.level, sys.stdout, sys.stderr, sys.excepthook, threading.excepthook, warnings.showwarning)
    root.handlers = []
    with patch("src.logger.LOGS_DIR", tmp_path), patch("src.logger.LOG_FILE", tmp_path / "buddy.log"):
        yield tmp_path
    for h in root.handlers:
        h.close()
    root.handlers, root.level = saved[0], saved[1]
    sys.stdout, sys.stderr, sys.excepthook, threading.excepthook, warnings.showwarning = saved[2:]


def _flush():
    for h in logging.getLogger().handlers:
        h.flush()


def test_log_rolls_at_one_megabyte(isolated_logging):
    src.logger.setup_logging()
    handler = next(h for h in logging.getLogger().handlers if isinstance(h, RotatingFileHandler))
    assert handler.maxBytes == 1024 * 1024
    assert handler.backupCount >= 1

    line = "x" * 1000
    for _ in range(1200):  # ~1.2 MB of log lines
        logging.getLogger("buddy.test").info(line)
    _flush()

    assert (isolated_logging / "buddy.log.1").exists()
    assert (isolated_logging / "buddy.log").stat().st_size <= 1024 * 1024


def test_prints_and_uncaught_thread_errors_reach_the_log(isolated_logging):
    src.logger.setup_logging()
    print("hello from a print call")

    def boom():
        raise RuntimeError("worker blew up")

    t = threading.Thread(target=boom, name="buddy_worker_test")
    t.start()
    t.join()
    _flush()

    content = (isolated_logging / "buddy.log").read_text(encoding="utf-8")
    assert "Buddy v" in content and "starting" in content
    assert "hello from a print call" in content
    assert "worker blew up" in content and "buddy_worker_test" in content


def test_setup_is_idempotent(isolated_logging):
    src.logger.setup_logging()
    src.logger.setup_logging()
    file_handlers = [h for h in logging.getLogger().handlers if isinstance(h, RotatingFileHandler)]
    assert len(file_handlers) == 1


def test_capture_discontinuities_are_summarised_and_other_warnings_unaffected(isolated_logging):
    previous_showwarning = MagicMock()
    warnings.showwarning = previous_showwarning  # restored by the fixture
    src.logger.setup_logging()

    # soundcard emits a SoundcardRuntimeWarning instance; one per late capture read
    for _ in range(5):
        warnings.showwarning(RuntimeWarning("data discontinuity in recording"), RuntimeWarning, "mediafoundation.py", 750)
    other = UserWarning("something else")
    warnings.showwarning(other, UserWarning, "elsewhere.py", 12)
    _flush()

    content = (isolated_logging / "buddy.log").read_text(encoding="utf-8")
    assert content.count("audio: 1 capture discontinuity in the last 60 s") == 1
    assert "data discontinuity in recording" not in content
    previous_showwarning.assert_called_once_with(other, UserWarning, "elsewhere.py", 12, None, None)


def test_discontinuity_summary_reports_at_most_once_per_interval():
    now = [1000.0]
    log = MagicMock()
    summary = src.logger._DiscontinuitySummary(log, interval_sec=60.0, clock=lambda: now[0])

    summary.record()  # the first one is reported right away
    threads = [threading.Thread(target=lambda: [summary.record() for _ in range(250)]) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert log.warning.call_count == 1

    now[0] += 61
    summary.record()

    messages = [c.args[0] for c in log.warning.call_args_list]
    assert messages == [
        "audio: 1 capture discontinuity in the last 60 s",
        "audio: 1001 capture discontinuities in the last 61 s",
    ]
