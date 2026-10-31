import io
import sys
import logging
import threading
from logging.handlers import RotatingFileHandler

from src.config import LOGS_DIR
from src.version import __version__

LOG_FILE = LOGS_DIR / "buddy.log"
LOG_MAX_BYTES = 1024 * 1024  # Roll the log at 1 MB
LOG_BACKUP_COUNT = 3         # Keep buddy.log.1 .. buddy.log.3

_FORMAT = "%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s"


class _StreamToLogger(io.TextIOBase):
    """
    File-like object that forwards writes to a logger, one record per line.
    The windowed (console=False) exe has sys.stdout/sys.stderr set to None, so without this
    every print() and traceback in the app would vanish.
    """
    def __init__(self, logger: logging.Logger, level: int):
        self._logger = logger
        self._level = level
        self._buffer = ""
        self._lock = threading.Lock()

    def write(self, text: str) -> int:
        with self._lock:
            self._buffer += text
            *lines, self._buffer = self._buffer.split("\n")
        for line in lines:
            if line.strip():
                self._logger.log(self._level, line.rstrip())
        return len(text)

    def flush(self):
        with self._lock:
            line, self._buffer = self._buffer, ""
        if line.strip():
            self._logger.log(self._level, line.rstrip())


def setup_logging() -> logging.Logger:
    """
    Routes everything Buddy reports into a rolling log at %USERPROFILE%\\.buddy\\logs\\buddy.log:
    logging calls, print() output, uncaught exceptions on any thread, and Qt warnings.
    When a console is attached (running from source), output is mirrored there too.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return logging.getLogger("buddy")

    root.setLevel(logging.INFO)
    # Never let a logging failure (e.g. a locked file during rollover) write back into the redirected stderr
    logging.raiseExceptions = False
    formatter = logging.Formatter(_FORMAT)

    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console = sys.__stdout__
    if console is not None:
        console_handler = logging.StreamHandler(console)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    # Chatty third-party loggers stay at WARNING
    for noisy in ("httpx", "httpcore", "urllib3", "google_genai", "google.genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    sys.stdout = _StreamToLogger(logging.getLogger("stdout"), logging.INFO)
    sys.stderr = _StreamToLogger(logging.getLogger("stderr"), logging.WARNING)

    def log_uncaught(exc_type, exc, tb):
        logging.getLogger("buddy").critical("Uncaught exception", exc_info=(exc_type, exc, tb))

    def log_uncaught_thread(args):
        logging.getLogger("buddy").error(
            f"Uncaught exception in thread {args.thread.name if args.thread else '?'}",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback)
        )

    sys.excepthook = log_uncaught
    threading.excepthook = log_uncaught_thread

    try:
        from PySide6.QtCore import qInstallMessageHandler, QtMsgType
        qt_logger = logging.getLogger("qt")
        levels = {
            QtMsgType.QtDebugMsg: logging.DEBUG,
            QtMsgType.QtInfoMsg: logging.INFO,
            QtMsgType.QtWarningMsg: logging.WARNING,
            QtMsgType.QtCriticalMsg: logging.ERROR,
            QtMsgType.QtFatalMsg: logging.CRITICAL,
        }
        qInstallMessageHandler(lambda mode, context, message: qt_logger.log(levels.get(mode, logging.INFO), message))
    except Exception:
        pass

    logger = logging.getLogger("buddy")
    logger.info(f"===== Buddy v{__version__} starting (frozen={getattr(sys, 'frozen', False)}) =====")
    return logger
