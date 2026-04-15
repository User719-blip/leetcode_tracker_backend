from datetime import datetime, timedelta, timezone
from threading import Lock

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken


_STATE_LOCK = Lock()
_LAST_CLEANUP_STATE: dict[str, object] = {
    "ok": True,
    "last_run_at": None,
    "deleted_rows": 0,
    "message": None,
}


def active_refresh_family_count(db: Session, admin_email: str, now: datetime | None = None) -> int:
    current_time = now or datetime.now(timezone.utc)
    stmt = select(func.count(func.distinct(RefreshToken.family_id))).where(
        RefreshToken.admin_email == admin_email,
        RefreshToken.revoked_at.is_(None),
        RefreshToken.expires_at > current_time,
    )
    return int(db.execute(stmt).scalar_one() or 0)


def cleanup_refresh_tokens(db: Session, retention_days: int, now: datetime | None = None) -> int:
    current_time = now or datetime.now(timezone.utc)
    cutoff = current_time - timedelta(days=max(retention_days, 0))

    stmt = delete(RefreshToken).where(
        (RefreshToken.revoked_at.is_not(None) & (RefreshToken.revoked_at <= cutoff))
        | (RefreshToken.expires_at <= cutoff)
    )
    result = db.execute(stmt)
    db.commit()
    deleted_rows = int(result.rowcount or 0)
    with _STATE_LOCK:
        _LAST_CLEANUP_STATE.update(
            {
                "ok": True,
                "last_run_at": current_time.isoformat(),
                "deleted_rows": deleted_rows,
                "message": None,
            }
        )
    return deleted_rows


def mark_cleanup_failure(message: str, now: datetime | None = None) -> None:
    current_time = now or datetime.now(timezone.utc)
    with _STATE_LOCK:
        _LAST_CLEANUP_STATE.update(
            {
                "ok": False,
                "last_run_at": current_time.isoformat(),
                "message": message,
            }
        )


def get_refresh_cleanup_status() -> dict[str, object]:
    with _STATE_LOCK:
        return dict(_LAST_CLEANUP_STATE)