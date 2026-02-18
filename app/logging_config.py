import logging
import logging.config
from typing import Any

from app.config import settings

_DEFAULT_LOG_RECORD_KEYS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())


class ContextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {
            k: v
            for k, v in record.__dict__.items()
            if k not in _DEFAULT_LOG_RECORD_KEYS and k not in {"message", "asctime"}
        }
        if not extras:
            return base
        context = " ".join(f"{k}={v}" for k, v in sorted(extras.items()))
        return f"{base} {context}"


def _build_logging_dict() -> dict[str, Any]:
    root_level = settings.LOG_LEVEL.upper()
    crawler_level = settings.CRAWLER_LOG_LEVEL.upper()

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "()": "app.logging_config.ContextFormatter",
                "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
            }
        },
        "root": {
            "handlers": ["console"],
            "level": root_level,
        },
        "loggers": {
            "app": {
                "level": crawler_level,
                "propagate": True,
            }
        },
    }


def configure_logging() -> None:
    logging.config.dictConfig(_build_logging_dict())
    logging.getLogger(__name__).info(
        "Logging configured",
        extra={
            "root_level": settings.LOG_LEVEL.upper(),
            "crawler_level": settings.CRAWLER_LOG_LEVEL.upper(),
        },
    )
