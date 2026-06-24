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


class MostActiveUserEntry(BaseModel):
    user_id: UUID
    username: str
    active_days: int
    total_solved: int


class GlobalTrendEntry(BaseModel):
    date: date
    easy: int
    medium: int
    hard: int
    total: int
    user_count: int


class DifficultyDistribution(BaseModel):
    easy: int
    medium: int
    hard: int
    total: int
    easy_pct: float
    medium_pct: float
    hard_pct: float


class MostImprovedPlayerEntry(BaseModel):
    user_id: UUID
    username: str
    improvement: int
    start_total: int
    end_total: int
    percentage: str


class AnalyticsDashboardResponse(BaseModel):
    most_active_users: list[MostActiveUserEntry]
    global_trends: list[GlobalTrendEntry]
    difficulty_distribution: DifficultyDistribution
    most_improved_player: MostImprovedPlayerEntry | None
