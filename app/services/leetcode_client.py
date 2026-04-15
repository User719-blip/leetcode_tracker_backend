from typing import Any

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings

settings = get_settings()


LEETCODE_QUERY = """
query getUserProfile($username: String!) {
  matchedUser(username: $username) {
    submitStats {
      acSubmissionNum {
        difficulty
        count
      }
    }
    profile {
      ranking
    }
  }
}
"""


async def fetch_leetcode_stats(username: str) -> dict[str, int]:
    payload = {"query": LEETCODE_QUERY, "variables": {"username": username}}

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            settings.leetcode_graphql_url,
            json=payload,
            headers={"Content-Type": "application/json", "Referer": "https://leetcode.com"},
        )

    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LeetCode API error: {response.status_code}",
        )

    result = response.json()
    matched_user = result.get("data", {}).get("matchedUser")
    if not matched_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found on LeetCode")

    stats = matched_user.get("submitStats", {}).get("acSubmissionNum", [])
    ranking = int(matched_user.get("profile", {}).get("ranking") or 0)

    parsed = _parse_difficulty_counts(stats)
    parsed["ranking"] = ranking
    return parsed


def _parse_difficulty_counts(stats: list[dict[str, Any]]) -> dict[str, int]:
    result = {"easy": 0, "medium": 0, "hard": 0, "total": 0}
    for item in stats:
        difficulty = item.get("difficulty")
        count = int(item.get("count") or 0)
        if difficulty == "Easy":
            result["easy"] = count
        elif difficulty == "Medium":
            result["medium"] = count
        elif difficulty == "Hard":
            result["hard"] = count
        elif difficulty == "All":
            result["total"] = count
    return result
