"""structlog + Sentry configuration. Call configure_logging() once at process start."""

from __future__ import annotations

import logging
import sys

import structlog

from .config import settings

_configured = False


def _init_sentry() -> None:
    """No-op if SENTRY_DSN is blank (default for local dev)."""
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
    except ImportError:  # pragma: no cover — dep is in pyproject, but be safe
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment="local",
    )


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    _init_sentry()

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=settings.log_level,
    )

    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level),
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    configure_logging()
    return structlog.get_logger(name)
