"""
HTTP access logging with request correlation.

Every request gets a ``request_id`` (reused from an incoming ``X-Request-ID``
when it is safe, generated otherwise). The id is bound to the logging context,
returned in the response header, and attached to the one-line access log so a
report from a user can be traced to the exact request and its error trail.
"""

import logging
import re
import time
import uuid

from django.conf import settings

from main.logging import reset_request_id, set_request_id

logger = logging.getLogger("urbantrack.requests")

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,128}$")
_DEFAULT_SKIP_PATHS = ("/static/", "/media/", "/favicon.ico")


def _request_id(request):
    incoming = request.headers.get("X-Request-ID", "")
    if _REQUEST_ID_PATTERN.match(incoming):
        return incoming
    return uuid.uuid4().hex


def _client_ip(request):
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR", "-")


class RequestLogMiddleware:
    """Log one line per HTTP request and propagate its correlation id."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = _request_id(request)
        request.request_id = request_id
        token = set_request_id(request_id)
        started_at = time.perf_counter()

        try:
            if request.path.startswith(self._skip_paths):
                return self.get_response(request)

            try:
                response = self.get_response(request)
            except Exception:
                self._log(request, status_code=500, started_at=started_at, exc_info=True)
                raise

            self._log(request, status_code=response.status_code, started_at=started_at)
            response["X-Request-ID"] = request_id
            return response
        finally:
            reset_request_id(token)

    @property
    def _skip_paths(self):
        return tuple(getattr(settings, "LOG_SKIP_PATHS", _DEFAULT_SKIP_PATHS))

    @staticmethod
    def _log(request, *, status_code, started_at, exc_info=False):
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        user = getattr(request, "user", None)
        user_id = user.pk if getattr(user, "is_authenticated", False) else None
        extra = {
            "request_id": request.request_id,
            "method": request.method,
            "path": request.path,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "user_id": user_id,
            "ip": _client_ip(request),
        }
        message = (
            f"method={request.method} path={request.path} status={status_code} "
            f"duration_ms={duration_ms} user_id={user_id} ip={extra['ip']}"
        )
        level = logging.ERROR if status_code >= 500 else logging.WARNING
        if status_code < 400:
            level = logging.INFO
        logger.log(level, message, extra=extra, exc_info=exc_info)
