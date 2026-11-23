import logging

from app.config import Settings

_LOGGER_NAMES = ("app", "uvicorn", "uvicorn.error")


def configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
    for name in _LOGGER_NAMES:
        logging.getLogger(name).setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
