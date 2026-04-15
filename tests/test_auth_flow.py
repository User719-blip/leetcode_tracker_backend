from fastapi.testclient import TestClient

from app.api.routes import auth as auth_routes


def _login(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/auth/admin/login",
        json={"email": "admin@example.com", "password": "test-password"},
    )
    assert response.status_code == 200
    return response.json()


def test_auth_refresh_rotation_and_logout_all(client: TestClient) -> None:
    login_payload = _login(client)
    initial_refresh = login_payload["refresh_token"]

    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": initial_refresh})
    assert refreshed.status_code == 200
    refreshed_payload = refreshed.json()
    rotated_refresh = refreshed_payload["refresh_token"]
    assert rotated_refresh != initial_refresh

    logout_all_response = client.post("/api/v1/auth/logout-all", json={"refresh_token": rotated_refresh})
    assert logout_all_response.status_code == 204

    # After logout-all, the same refresh token must not be usable anymore.
    reused = client.post("/api/v1/auth/refresh", json={"refresh_token": rotated_refresh})
    assert reused.status_code == 401


def test_auth_refresh_reuse_detection_revokes_family(client: TestClient) -> None:
    login_payload = _login(client)
    token_1 = login_payload["refresh_token"]

    rotate_once = client.post("/api/v1/auth/refresh", json={"refresh_token": token_1})
    assert rotate_once.status_code == 200
    token_2 = rotate_once.json()["refresh_token"]

    # Reusing an already-rotated refresh token triggers family-wide revocation.
    reuse_attempt = client.post("/api/v1/auth/refresh", json={"refresh_token": token_1})
    assert reuse_attempt.status_code == 401

    # The latest token in the same family should also be rejected after reuse detection.
    token_2_after_reuse = client.post("/api/v1/auth/refresh", json={"refresh_token": token_2})
    assert token_2_after_reuse.status_code == 401


def test_auth_active_family_cap_blocks_additional_login(client: TestClient) -> None:
    auth_routes.settings.max_active_refresh_token_families_per_admin = 1

    first_login = client.post(
        "/api/v1/auth/admin/login",
        json={"email": "admin@example.com", "password": "test-password"},
    )
    assert first_login.status_code == 200

    second_login = client.post(
        "/api/v1/auth/admin/login",
        json={"email": "admin@example.com", "password": "test-password"},
    )
    assert second_login.status_code == 429