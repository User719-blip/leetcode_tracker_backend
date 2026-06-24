from collections import defaultdict
from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.snapshot import Snapshot
from app.models.user import User
from app.schemas.leaderboard import (
    AnalyticsDashboardResponse,
    DifficultyDistribution,
    GlobalStats,
    GlobalTrendEntry,
    LeaderboardEntry,
    MostActiveUserEntry,
    MostImprovedPlayerEntry,
    WeeklyComparisonEntry,
)
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


@router.get("/dashboard", response_model=AnalyticsDashboardResponse)
def analytics_dashboard(
    trend_days: int = 90,
    active_users_limit: int = 10,
    db: Session = Depends(get_db),
) -> AnalyticsDashboardResponse:
    latest_rows = get_latest_snapshots(db)
    latest_by_user = {row["user_id"]: row for row in latest_rows}

    if not latest_rows:
        return AnalyticsDashboardResponse(
            most_active_users=[],
            global_trends=[],
            difficulty_distribution=DifficultyDistribution(
                easy=0,
                medium=0,
                hard=0,
                total=0,
                easy_pct=0,
                medium_pct=0,
                hard_pct=0,
            ),
            most_improved_player=None,
        )

    today = date.today()
    trend_start = today - timedelta(days=trend_days)
    active_start = today - timedelta(days=30)
    snapshot_start = min(trend_start, active_start)

    snapshot_rows = (
        db.execute(
            select(Snapshot, User.username)
            .join(User, Snapshot.user_id == User.id)
            .where(Snapshot.date >= snapshot_start)
            .order_by(Snapshot.user_id.asc(), Snapshot.date.asc())
        )
        .all()
    )

    snapshots_by_user: dict[UUID, list[dict]] = defaultdict(list)
    trend_groups: dict[date, dict[str, int]] = {}

    for snapshot, username in snapshot_rows:
        row = {
            "user_id": snapshot.user_id,
            "username": username,
            "date": snapshot.date,
            "easy": snapshot.easy,
            "medium": snapshot.medium,
            "hard": snapshot.hard,
            "total": snapshot.total,
            "ranking": snapshot.ranking,
        }
        snapshots_by_user[snapshot.user_id].append(row)

        if snapshot.date >= trend_start:
            group = trend_groups.setdefault(
                snapshot.date,
                {
                    "easy": 0,
                    "medium": 0,
                    "hard": 0,
                    "total": 0,
                    "user_count": 0,
                },
            )
            group["easy"] += snapshot.easy
            group["medium"] += snapshot.medium
            group["hard"] += snapshot.hard
            group["total"] += snapshot.total
            group["user_count"] += 1

    most_active_users: list[MostActiveUserEntry] = []
    best_player: MostImprovedPlayerEntry | None = None
    max_improvement = 0

    for user_id, snapshots in snapshots_by_user.items():
        active_snapshots = [snap for snap in snapshots if snap["date"] >= active_start]

        if active_snapshots:
            most_active_users.append(
                MostActiveUserEntry(
                    user_id=user_id,
                    username=active_snapshots[-1]["username"],
                    active_days=len({snap["date"] for snap in active_snapshots}),
                    total_solved=int(active_snapshots[-1]["total"]),
                )
            )

        if len(active_snapshots) < 2:
            continue

        start_total = int(active_snapshots[0]["total"])
        end_total = int(active_snapshots[-1]["total"])
        improvement = end_total - start_total

        if improvement > max_improvement:
            max_improvement = improvement
            percentage = f"{(improvement / start_total) * 100:.1f}" if start_total > 0 else "0"
            best_player = MostImprovedPlayerEntry(
                user_id=user_id,
                username=active_snapshots[-1]["username"],
                improvement=improvement,
                start_total=start_total,
                end_total=end_total,
                percentage=percentage,
            )

    most_active_users.sort(
        key=lambda item: (-item.active_days, -item.total_solved)
    )
    most_active_users = most_active_users[:active_users_limit]

    global_trends = [
        GlobalTrendEntry(
            date=trend_date,
            easy=values["easy"],
            medium=values["medium"],
            hard=values["hard"],
            total=values["total"],
            user_count=values["user_count"],
        )
        for trend_date, values in sorted(trend_groups.items())
    ]

    total_easy = sum(int(row["easy"]) for row in latest_rows)
    total_medium = sum(int(row["medium"]) for row in latest_rows)
    total_hard = sum(int(row["hard"]) for row in latest_rows)
    total = total_easy + total_medium + total_hard

    difficulty_distribution = DifficultyDistribution(
        easy=total_easy,
        medium=total_medium,
        hard=total_hard,
        total=total,
        easy_pct=(total_easy / total) * 100 if total > 0 else 0,
        medium_pct=(total_medium / total) * 100 if total > 0 else 0,
        hard_pct=(total_hard / total) * 100 if total > 0 else 0,
    )

    return AnalyticsDashboardResponse(
        most_active_users=most_active_users,
        global_trends=global_trends,
        difficulty_distribution=difficulty_distribution,
        most_improved_player=best_player,
    )


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
