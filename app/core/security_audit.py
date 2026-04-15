import json
import logging
from datetime import datetime, timezone


_LOGGER = logging.getLogger("security")


def log_security_event(event_type: str, **fields: object) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        **fields,
    }
    _LOGGER.info(json.dumps(payload, default=str, separators=(",", ":")))