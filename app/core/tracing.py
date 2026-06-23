from __future__ import annotations

import uuid
import logging
from contextvars import ContextVar
from typing import Callable

from fastapi import Request

TRACE_ID: ContextVar[str | None] = ContextVar("trace_id", default=None)


def new_trace_id() -> str:
    return uuid.uuid4().hex


def get_trace_id() -> str | None:
    return TRACE_ID.get()


class TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Attach trace_id to logging records when available
        trace_id = TRACE_ID.get()
        setattr(record, "trace_id", trace_id)
        return True


async def trace_id_middleware(request: Request, call_next: Callable):
    trace = request.headers.get("X-Trace-Id") or new_trace_id()
    token = TRACE_ID.set(trace)
    try:
        response = await call_next(request)
        # echo back trace id for client correlation
        response.headers["X-Trace-Id"] = trace
        return response
    finally:
        TRACE_ID.reset(token)
