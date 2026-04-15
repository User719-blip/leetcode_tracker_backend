import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.admin import router as admin_router
from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.leaderboard import router as leaderboard_router
from app.api.routes.leetcode import router as leetcode_router
from app.core.config import get_settings
from app.core.refresh_token_maintenance import cleanup_refresh_tokens, mark_cleanup_failure
from app.db.session import SessionLocal

settings = get_settings()



def _run_refresh_token_cleanup() -> int:
    db = SessionLocal()
    try:
        return cleanup_refresh_tokens(db, retention_days=settings.refresh_token_cleanup_retention_days)
    finally:
        db.close()


async def _refresh_token_cleanup_loop(stop_event: asyncio.Event) -> None:
    if settings.refresh_token_cleanup_interval_minutes <= 0:
        return

    interval_seconds = settings.refresh_token_cleanup_interval_minutes * 60
    while not stop_event.is_set():
        try:
            _run_refresh_token_cleanup()
        except Exception as exc:
            mark_cleanup_failure(str(exc))

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = asyncio.Event()
    cleanup_task = asyncio.create_task(_refresh_token_cleanup_loop(stop_event))

    try:
        try:
            _run_refresh_token_cleanup()
        except Exception as exc:
            mark_cleanup_failure(str(exc))
        yield
    finally:
        stop_event.set()
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(leetcode_router, prefix=settings.api_v1_prefix)
app.include_router(admin_router, prefix=settings.api_v1_prefix)
app.include_router(leaderboard_router, prefix=settings.api_v1_prefix)
