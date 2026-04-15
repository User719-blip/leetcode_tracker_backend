from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models.refresh_token  # noqa: F401
import app.models.snapshot  # noqa: F401
import app.models.user  # noqa: F401
from app.api.routes import auth as auth_routes
from app.api.routes import health as health_routes
from app.core.rate_limiter import rate_limiter
from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    original_hit = rate_limiter.hit
    original_auth_settings = {
        "admin_emails": auth_routes.settings.admin_emails,
        "admin_password": auth_routes.settings.admin_password,
        "family_cap": auth_routes.settings.max_active_refresh_token_families_per_admin,
    }
    original_health_settings = {
        "monitor_check_urls": health_routes.settings.monitor_check_urls,
        "monitor_timeout": health_routes.settings.monitor_http_timeout_seconds,
    }

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    rate_limiter.hit = lambda key, limit, window_seconds: None
    auth_routes.settings.admin_emails = "admin@example.com"
    auth_routes.settings.admin_password = "test-password"
    auth_routes.settings.max_active_refresh_token_families_per_admin = 3
    health_routes.settings.monitor_check_urls = ""
    health_routes.settings.monitor_http_timeout_seconds = 1

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        rate_limiter.hit = original_hit
        auth_routes.settings.admin_emails = original_auth_settings["admin_emails"]
        auth_routes.settings.admin_password = original_auth_settings["admin_password"]
        auth_routes.settings.max_active_refresh_token_families_per_admin = original_auth_settings["family_cap"]
        health_routes.settings.monitor_check_urls = original_health_settings["monitor_check_urls"]
        health_routes.settings.monitor_http_timeout_seconds = original_health_settings["monitor_timeout"]