import pytest

from app.core.config import Settings


def _base_prod_settings() -> Settings:
    return Settings(
        app_name="leetcode-tracker-api",
        app_env="prod",
        api_v1_prefix="/api/v1",
        allowed_origins="https://app.example.com",
        allowed_origin_regex=r"^https://app\.example\.com$",
        database_url="postgresql+psycopg2://user:pass@db:5432/leetcode_tracker",
        jwt_secret_key="this_is_a_long_and_secure_secret_key_123",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=120,
        jwt_refresh_token_expire_days=14,
        redis_url="redis://localhost:6379/0",
        rate_limit_redis_prefix="leetcode_tracker:ratelimit",
        max_active_refresh_token_families_per_admin=3,
        refresh_token_cleanup_interval_minutes=60,
        refresh_token_cleanup_retention_days=30,
        monitor_check_urls="",
        monitor_http_timeout_seconds=5,
        admin_emails="admin@example.com",
        admin_password="a_strong_password",
        leetcode_graphql_url="https://leetcode.com/graphql",
    )


def test_prod_settings_validation_accepts_secure_values() -> None:
    settings = _base_prod_settings()
    settings.validate()


def test_prod_settings_validation_rejects_insecure_defaults() -> None:
    settings = _base_prod_settings()
    settings.jwt_secret_key = "change_this_in_production"
    settings.admin_password = "change_me"
    settings.allowed_origins = "*"
    settings.admin_emails = ""

    with pytest.raises(ValueError) as exc:
        settings.validate()

    message = str(exc.value)
    assert "JWT_SECRET_KEY" in message
    assert "ADMIN_PASSWORD" in message
    assert "ALLOWED_ORIGINS" in message
    assert "ADMIN_EMAILS" in message


def test_non_prod_settings_skip_strict_validation() -> None:
    settings = _base_prod_settings()
    settings.app_env = "dev"
    settings.jwt_secret_key = "short"
    settings.admin_password = ""
    settings.allowed_origins = "*"
    settings.admin_emails = ""

    settings.validate()