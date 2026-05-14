import logging
import sys

def setup_logging(level: int = logging.INFO) -> None:
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.basicConfig(
        stream=sys.stdout,
        level=level,
        format=fmt,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)