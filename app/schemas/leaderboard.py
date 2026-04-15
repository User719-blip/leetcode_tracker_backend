from datetime import date
from uuid import UUID

from pydantic import BaseModel


class LeaderboardEntry(BaseModel):
    user_id: UUID
    username: str
    date: date
    easy: int
    medium: int
    hard: int
    total: int
    ranking: int


class WeeklyComparisonEntry(BaseModel):
    user_id: UUID
    username: str
    date: date
    total: int
    previous_total: int | None
    delta_total: int


class GlobalStats(BaseModel):
    users: int
    total_solved: int
    total_hard: int
