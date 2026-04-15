from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.api.routes import admin as admin_routes


def _admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        "/api/v1/auth/admin/login",
        json={"email": "admin@example.com", "password": "test-password"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_user_rejects_unknown_leetcode_username(client: TestClient, monkeypatch) -> None:
    async def fake_not_found(username: str) -> dict[str, int]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found on LeetCode")

    monkeypatch.setattr(admin_routes, "fetch_leetcode_stats", fake_not_found)

    response = client.post(
        "/api/v1/admin/users",
        json={"username": "ABCXD"},
        headers=_admin_headers(client),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found on LeetCode"


def test_create_user_accepts_valid_leetcode_username(client: TestClient, monkeypatch) -> None:
    async def fake_found(username: str) -> dict[str, int]:
        return {"easy": 1, "medium": 1, "hard": 1, "total": 3, "ranking": 123}

    monkeypatch.setattr(admin_routes, "fetch_leetcode_stats", fake_found)

    response = client.post(
        "/api/v1/admin/users",
        json={"username": "valid_user_123"},
        headers=_admin_headers(client),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["username"] == "valid_user_123"
    assert "id" in payload