from datetime import datetime, timedelta, timezone
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.refresh_token_maintenance import cleanup_refresh_tokens, get_refresh_cleanup_status
from app.models.refresh_token import RefreshToken


def _admin_auth_header(client: TestClient) -> dict[str, str]:
    login_response = client.post(
        "/api/v1/auth/admin/login",
        json={"email": "admin@example.com", "password": "test-password"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_monitor_endpoint_without_external_urls(client: TestClient) -> None:
    response = client.get("/api/v1/health/monitor", headers=_admin_auth_header(client))
    assert response.status_code == 200
    payload = response.json()

    assert payload["configured_external_checks_count"] == 0
    assert payload["requested_external_checks_count"] == 0
    assert any(check["name"] == "refresh_cleanup_job" for check in payload["checks"])
    assert any(check["name"] == "rate_limiter" for check in payload["checks"])


def test_monitor_endpoint_with_extra_urls(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health/monitor",
        params={"extra_urls": "https://example.com"},
        headers=_admin_auth_header(client),
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["requested_external_checks_count"] == 1
    assert any(check["name"] == "extra_1" for check in payload["checks"])


def test_cleanup_refresh_tokens_removes_old_rows(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    family_a = uuid.uuid4()
    family_b = uuid.uuid4()

    old_revoked = RefreshToken(
        token_hash="old-revoked",
        admin_email="admin@example.com",
        family_id=family_a,
        expires_at=now + timedelta(days=2),
        revoked_at=now - timedelta(days=40),
    )
    old_expired = RefreshToken(
        token_hash="old-expired",
        admin_email="admin@example.com",
        family_id=family_a,
        expires_at=now - timedelta(days=40),
    )
    active = RefreshToken(
        token_hash="active-token",
        admin_email="admin@example.com",
        family_id=family_b,
        expires_at=now + timedelta(days=5),
    )

    db_session.add_all([old_revoked, old_expired, active])
    db_session.commit()

    deleted = cleanup_refresh_tokens(db_session, retention_days=30)
    assert deleted == 2

    remaining = db_session.query(RefreshToken).all()
    assert len(remaining) == 1
    assert remaining[0].token_hash == "active-token"

    status = get_refresh_cleanup_status()
    assert status["ok"] is True