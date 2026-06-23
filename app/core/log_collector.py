from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, List

from app.core.tracing import get_trace_id

_MAX_ENTRIES = 200
_logs: Deque[Dict[str, object]] = deque(maxlen=_MAX_ENTRIES)


class InMemoryLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:  # type: ignore[override]
        try:
            msg = record.getMessage()
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": msg,
                "trace_id": getattr(record, "trace_id", None),
            }
            _logs.append(entry)
        except Exception:
            # avoid logging failures
            pass


def get_recent_logs(limit: int = 5) -> List[Dict[str, object]]:
    if limit <= 0:
        return []
    items = list(_logs)[-limit:]
    # return newest-first
    return list(reversed(items))
