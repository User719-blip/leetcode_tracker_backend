from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.core.rate_limiter import rate_limiter
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse
from app.services.leetcode_client import fetch_leetcode_stats
from app.services.sync_service import run_daily_sync

router = APIRouter(prefix="/admin", tags=["admin"])


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/users", response_model=list[UserResponse])
def list_users(request: Request, admin_email: str = Depends(get_current_admin), db: Session = Depends(get_db)) -> list[UserResponse]:
    ip = _client_ip(request)
    rate_limiter.hit(f"admin:list:{admin_email}:{ip}", limit=120, window_seconds=60)

    users = db.execute(select(User).order_by(User.username.asc())).scalars().all()
    return [UserResponse.model_validate(user) for user in users]


@router.post("/users", response_model=UserResponse)
async def create_user(
    payload: UserCreate,
    request: Request,
    admin_email: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> UserResponse:
    ip = _client_ip(request)
    rate_limiter.hit(f"admin:create:{admin_email}:{ip}", limit=30, window_seconds=60)

    existing = db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    # Validate against LeetCode before storing; prevents bad usernames from entering the system.
    await fetch_leetcode_stats(payload.username)

    user = User(username=payload.username)
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: UUID,
    request: Request,
    admin_email: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> None:
    ip = _client_ip(request)
    rate_limiter.hit(f"admin:delete:{admin_email}:{ip}", limit=30, window_seconds=60)

    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    db.delete(user)
    db.commit()


@router.post("/sync/daily")
async def daily_sync(
    request: Request,
    admin_email: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    ip = _client_ip(request)
    rate_limiter.hit(f"admin:sync:{admin_email}:{ip}", limit=5, window_seconds=60)

    result = await run_daily_sync(db)
    return {"message": "Stats updated", **result}
