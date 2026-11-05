import json
import logging
import re
import secrets
from datetime import UTC, datetime

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_TRACEPARENT = re.compile(r"^(?P<version>[0-9a-f]{2})-(?P<trace>[0-9a-f]{32})-[0-9a-f]{16}-(?P<flags>[0-9a-f]{2})$")
_LOG_FIELDS = (
    "deployment_environment",
    "duration_ms",
    "error_type",
    "experiment_variant",
    "http_method",
    "http_path",
    "http_status",
    "request_id",
    "trace_id",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in _LOG_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # The default Uvicorn access logger includes client IP addresses; the structured middleware replaces it.
    logging.getLogger("uvicorn.access").disabled = True


def request_id_from_header(value: str | None) -> str:
    return value if value and _REQUEST_ID.fullmatch(value) else secrets.token_hex(16)


def trace_context(value: str | None) -> tuple[str, str]:
    match = _TRACEPARENT.fullmatch(value or "")
    if match and match.group("trace") != "0" * 32:
        trace_id = match.group("trace")
        flags = match.group("flags")
    else:
        trace_id = secrets.token_hex(16)
        flags = "01"
    return trace_id, f"00-{trace_id}-{secrets.token_hex(8)}-{flags}"
