from pydantic import BaseModel, Field


class UsernameRequest(BaseModel):
    username: str = Field(min_length=1, max_length=30, pattern=r"^[a-zA-Z0-9_-]{1,30}$")


class LeetCodeStatsResponse(BaseModel):
    easy: int
    medium: int
    hard: int
    total: int
    ranking: int
