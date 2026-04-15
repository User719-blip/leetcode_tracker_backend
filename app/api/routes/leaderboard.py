from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.snapshot import Snapshot
from app.models.user import User
from app.schemas.leaderboard import GlobalStats, LeaderboardEntry, WeeklyComparisonEntry
from app.schemas.snapshot import SnapshotResponse
from app.services.sync_service import get_latest_snapshots, get_weekly_comparison

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("/latest", response_model=list[LeaderboardEntry])
def latest_leaderboard(db: Session = Depends(get_db)) -> list[LeaderboardEntry]:
    rows = get_latest_snapshots(db)
    return [LeaderboardEntry.model_validate(row) for row in rows]


@router.get("/weekly", response_model=list[WeeklyComparisonEntry])
def weekly_comparison(db: Session = Depends(get_db)) -> list[WeeklyComparisonEntry]:
    rows = get_weekly_comparison(db)
    return [WeeklyComparisonEntry.model_validate(row) for row in rows]


@router.get("/global", response_model=GlobalStats)
def global_stats(db: Session = Depends(get_db)) -> GlobalStats:
    users_count = db.execute(select(func.count()).select_from(User)).scalar() or 0
    latest = get_latest_snapshots(db)
    total_solved = sum(int(row["total"]) for row in latest)
    total_hard = sum(int(row["hard"]) for row in latest)
    return GlobalStats(users=int(users_count), total_solved=total_solved, total_hard=total_hard)


@router.get("/users/{user_id}/snapshots", response_model=list[SnapshotResponse])
def user_snapshots(user_id: UUID, db: Session = Depends(get_db)) -> list[SnapshotResponse]:
    rows = (
        db.execute(select(Snapshot).where(Snapshot.user_id == user_id).order_by(Snapshot.date.asc()))
        .scalars()
        .all()
    )
    return [
        SnapshotResponse(
            user_id=row.user_id,
            date=row.date,
            easy=row.easy,
            medium=row.medium,
            hard=row.hard,
            total=row.total,
            ranking=row.ranking,
        )
        for row in rows
    ]
