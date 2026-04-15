from datetime import date
from uuid import UUID

from pydantic import BaseModel


class SnapshotResponse(BaseModel):
    user_id: UUID
    date: date
    easy: int
    medium: int
    hard: int
    total: int
    ranking: int
