import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage", "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def setup_logging() -> None:
    """ 
        The -8 in %(levelname)-8s means "left-align, minimum 8 characters wide" — 
        so all levels (DEBUG, INFO, WARNING, ERROR) line up neatly in the log file.
        A real log line would look like this:
        2026-02-19 21:30:45 | WARNING  | app.api.deps | Auth failed: jti not whitelisted (revoked/logged out) — jti=abc-123, user_id=def-456
    """
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "app.log"),
        maxBytes=5 * 1024 * 1024,  # 5 MB per file
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
