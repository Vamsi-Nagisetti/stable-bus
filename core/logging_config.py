import logging
import logging.config
import os
from pathlib import Path


class LoggingConfig:

    @staticmethod
    def setup_logging() -> None:

        log_dir = Path(os.getenv("LOG_DIR", "logs"))
        log_dir.mkdir(parents=True, exist_ok=True)

        log_level = os.getenv("LOG_LEVEL", "INFO").upper()

        logging_config = {
            "version": 1,
            "disable_existing_loggers": False,

            "filters": {
                "request_context": {
                    "()": "core.request_context.RequestContextFilter"
                }
            },

            "formatters": {
                "standard": {
                    "format": (
                        "%(asctime)s | %(levelname)s | "
                        "%(name)s | request_id=%(request_id)s | "
                        "%(message)s"
                    ),
                    "datefmt": "%Y-%m-%dT%H:%M:%S",
                },
            },

            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": log_level,
                    "formatter": "standard",
                    "filters": ["request_context"],
                },

                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": log_level,
                    "formatter": "standard",
                    "filters": ["request_context"],
                    "filename": str(log_dir / "stablebus.log"),
                    "maxBytes": 10 * 1024 * 1024,
                    "backupCount": 5,
                    "encoding": "utf-8",
                },

                "error_file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": "ERROR",
                    "formatter": "standard",
                    "filters": ["request_context"],
                    "filename": str(log_dir / "stablebus-error.log"),
                    "maxBytes": 10 * 1024 * 1024,
                    "backupCount": 5,
                    "encoding": "utf-8",
                },
            },

            "root": {
                "level": log_level,
                "handlers": ["console", "file", "error_file"],
            },
        }

        logging.config.dictConfig(logging_config)