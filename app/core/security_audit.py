import json
import logging
from datetime import datetime, timezone

from app.core.tracing import get_trace_id


_LOGGER = logging.getLogger("security")


def log_security_event(event_type: str, **fields: object) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        **fields,
    }
    trace = get_trace_id()
    if trace:
        payload["trace_id"] = trace

    _LOGGER.info(json.dumps(payload, default=str, separators=(",", ":")))