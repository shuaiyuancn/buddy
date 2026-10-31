import sys
import logging
import threading
import pytest
from logging.handlers import RotatingFileHandler
from unittest.mock import patch

import src.logger


@pytest.fixture
def isolated_logging(tmp_path):
    """Run setup_logging against a temp folder and restore global logging/stdio state afterwards."""
    root = logging.getLogger()
    saved = (list(root.handlers), root.level, sys.stdout, sys.stderr, sys.excepthook, threading.excepthook)
    root.handlers = []
    with patch("src.logger.LOGS_DIR", tmp_path), patch("src.logger.LOG_FILE", tmp_path / "buddy.log"):
        yield tmp_path
    for h in root.handlers:
        h.close()
    root.handlers, root.level = saved[0], saved[1]
    sys.stdout, sys.stderr, sys.excepthook, threading.excepthook = saved[2:]


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
