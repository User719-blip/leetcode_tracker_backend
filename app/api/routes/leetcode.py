from fastapi import APIRouter

from app.schemas.leetcode import LeetCodeStatsResponse, UsernameRequest
from app.services.leetcode_client import fetch_leetcode_stats

router = APIRouter(prefix="/leetcode", tags=["leetcode"])


@router.post("/fetch", response_model=LeetCodeStatsResponse)
async def fetch_user_stats(payload: UsernameRequest) -> LeetCodeStatsResponse:
    stats = await fetch_leetcode_stats(payload.username)
    return LeetCodeStatsResponse(**stats)
