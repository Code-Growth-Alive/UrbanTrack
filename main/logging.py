"""
Logging helpers shared by settings, middleware and services.

Two things live here:

* a request-correlation context so every log line emitted while handling a
  request carries the same ``request_id`` (also returned as an HTTP header);
* an optional JSON formatter for production log collectors, plus a tiny
  :func:`audit` helper for business events (certifications, memberships...).
"""

import contextvars
import json
import logging
from datetime import datetime, timezone

_request_id = contextvars.ContextVar("request_id", default="-")

_audit_logger = logging.getLogger("urbantrack.audit")

_RESERVED_LOG_KEYS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "taskName",
    "message",
    "asctime",
    "request_id",
    "event",
    "fields",
}


def set_request_id(request_id):
    """Bind ``request_id`` to the current context and return the reset token."""
    return _request_id.set(request_id)


def reset_request_id(token):
    """Restore the previous request id (call in a ``finally`` block)."""
    _request_id.reset(token)


def get_request_id():
    """Return the request id bound to the current context."""
    return _request_id.get()


class RequestIDFilter(logging.Filter):
    """Expose the current request id on every record."""

    def filter(self, record):
        if not getattr(record, "request_id", None):
            record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, suitable for log collectors."""

    _EXTRA_FIELDS = ("method", "path", "status_code", "duration_ms", "user_id", "ip")

    def format(self, record):
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for field in self._EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        event = getattr(record, "event", None)
        if event is not None:
            payload["event"] = event
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            for key, value in fields.items():
                if key not in payload and key not in _RESERVED_LOG_KEYS:
                    payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def audit(event, **fields):
    """
    Record a business/audit event on the ``urbantrack.audit`` logger.

    Values are logged as key/value pairs (``None`` values are skipped). Keep
    identifiers rather than personal data: ``user_id``, ``project_id``...
    """
    clean = {key: value for key, value in fields.items() if value is not None}
    details = " ".join(f"{key}={value}" for key, value in sorted(clean.items()))
    _audit_logger.info(
        "event=%s %s",
        event,
        details,
        extra={"event": event, "fields": clean},
    )
