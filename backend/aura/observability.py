"""Structured logging + trace context propagation.

`structlog` is the default; the OpenTelemetry exporter is wired only when
`AURA_APPINSIGHTS_CONNECTION_STRING` is set, keeping local dev zero-config.
"""

from __future__ import annotations

import logging
import os
import sys
from contextvars import ContextVar
from uuid import UUID, uuid4

import structlog

_trace_id_var: ContextVar[str] = ContextVar("aura_trace_id", default="")


def current_trace_id() -> str:
    return _trace_id_var.get()


def new_trace_id() -> str:
    trace = uuid4().hex
    _trace_id_var.set(trace)
    return trace


def bind_trace_id(trace_id: str | UUID) -> str:
    val = trace_id.hex if isinstance(trace_id, UUID) else str(trace_id)
    _trace_id_var.set(val)
    return val


def _inject_trace_id(_, __, event_dict: dict[str, object]) -> dict[str, object]:
    trace = _trace_id_var.get()
    if trace:
        event_dict.setdefault("trace_id", trace)
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _inject_trace_id,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )

    conn = os.environ.get("AURA_APPINSIGHTS_CONNECTION_STRING")
    if conn:
        _try_init_appinsights(conn)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def _try_init_appinsights(connection_string: str) -> None:
    """Best-effort App Insights wiring.

    Soft-fails if `azure-monitor-opentelemetry` is not installed so the core
    application remains operational without observability extras.
    """
    try:
        from azure.monitor.opentelemetry import (  # type: ignore[import-not-found]
            configure_azure_monitor,
        )

        configure_azure_monitor(connection_string=connection_string)
    except ImportError:
        get_logger("aura.observability").warning(
            "azure-monitor-opentelemetry not installed; App Insights disabled"
        )
