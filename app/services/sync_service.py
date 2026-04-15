from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.snapshot import Snapshot
from app.models.user import User
from app.services.leetcode_client import fetch_leetcode_stats


async def run_daily_sync(db: Session) -> dict[str, int]:
    users = db.execute(select(User)).scalars().all()
    success_count = 0
    error_count = 0

    for user in users:
        try:
            stats = await fetch_leetcode_stats(user.username)
            upsert_snapshot(db, str(user.id), stats)
            success_count += 1
        except Exception:
            error_count += 1

    return {"success_count": success_count, "error_count": error_count}


def upsert_snapshot(db: Session, user_id: str, stats: dict[str, int]) -> None:
    today = date.today()
    stmt = insert(Snapshot).values(
        user_id=user_id,
        date=today,
        easy=stats["easy"],
        medium=stats["medium"],
        hard=stats["hard"],
        total=stats["total"],
        ranking=stats["ranking"],
    )

    stmt = stmt.on_conflict_do_update(
        constraint="uq_snapshot_user_date",
        set_={
            "easy": stmt.excluded.easy,
            "medium": stmt.excluded.medium,
            "hard": stmt.excluded.hard,
            "total": stmt.excluded.total,
            "ranking": stmt.excluded.ranking,
        },
    )

    db.execute(stmt)
    db.commit()


def get_latest_snapshots(db: Session) -> list[dict]:
    latest_date_subq = select(
        Snapshot.user_id,
        func.max(Snapshot.date).label("max_date"),
    ).group_by(Snapshot.user_id).subquery()

    query = (
        select(Snapshot, User.username)
        .join(User, Snapshot.user_id == User.id)
        .join(
            latest_date_subq,
            and_(
                Snapshot.user_id == latest_date_subq.c.user_id,
                Snapshot.date == latest_date_subq.c.max_date,
            ),
        )
        .order_by(Snapshot.total.desc(), Snapshot.ranking.asc())
    )

    rows = db.execute(query).all()
    return [
        {
            "user_id": snap.user_id,
            "username": username,
            "date": snap.date,
            "easy": snap.easy,
            "medium": snap.medium,
            "hard": snap.hard,
            "total": snap.total,
            "ranking": snap.ranking,
        }
        for snap, username in rows
    ]


def get_weekly_comparison(db: Session) -> list[dict]:
    latest = get_latest_snapshots(db)
    output: list[dict] = []

    for row in latest:
        previous = (
            db.execute(
                select(Snapshot)
                .where(Snapshot.user_id == row["user_id"], Snapshot.date < row["date"])
                .order_by(Snapshot.date.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

        previous_total = previous.total if previous else None
        delta_total = row["total"] - (previous_total or 0)

        output.append(
            {
                "user_id": row["user_id"],
                "username": row["username"],
                "date": row["date"],
                "total": row["total"],
                "previous_total": previous_total,
                "delta_total": delta_total,
            }
        )

    return output
