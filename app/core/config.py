import os
from pathlib import Path
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


# Load environment variables from the repository root .env for app and Alembic runs.
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")


@dataclass
class Settings:
    app_name: str
    app_env: str
    api_v1_prefix: str
    allowed_origins: str
    allowed_origin_regex: str
    database_url: str
    jwt_secret_key: str
    jwt_algorithm: str
    jwt_access_token_expire_minutes: int
    jwt_refresh_token_expire_days: int
    redis_url: str
    rate_limit_redis_prefix: str
    max_active_refresh_token_families_per_admin: int
    refresh_token_cleanup_interval_minutes: int
    refresh_token_cleanup_retention_days: int
    monitor_check_urls: str
    monitor_http_timeout_seconds: int
    admin_emails: str
    admin_password: str
    leetcode_graphql_url: str

    def validate(self) -> None:
        """Fail fast on unsafe production configuration."""
        if self.app_env.lower() != "prod":
            return

        errors: list[str] = []

        if self.jwt_secret_key == "change_this_in_production" or len(self.jwt_secret_key) < 32:
            errors.append("JWT_SECRET_KEY must be set to a strong value (>= 32 chars) in production")

        if not self.admin_emails_list:
            errors.append("ADMIN_EMAILS must include at least one admin email in production")

        if not self.admin_password or self.admin_password in {"change_me", "test-password"}:
            errors.append("ADMIN_PASSWORD must be set to a non-default value in production")

        if self.allowed_origins.strip() == "*":
            errors.append("ALLOWED_ORIGINS cannot be '*' in production")

        if errors:
            raise ValueError("Invalid production configuration: " + "; ".join(errors))

    @property
    def allowed_origins_list(self) -> list[str]:
        if not self.allowed_origins.strip():
            return ["*"]
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def admin_emails_list(self) -> list[str]:
        if not self.admin_emails.strip():
            return []
        return [email.strip().lower() for email in self.admin_emails.split(",") if email.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings(
        app_name=os.getenv("APP_NAME", "leetcode-tracker-api"),
        app_env=os.getenv("APP_ENV", "dev"),
        api_v1_prefix=os.getenv("API_V1_PREFIX", "/api/v1"),
        allowed_origins=os.getenv("ALLOWED_ORIGINS", "*"),
        allowed_origin_regex=os.getenv(
            "ALLOWED_ORIGIN_REGEX",
            r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        ),
        database_url=os.getenv(
            "DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/leetcode_tracker"
        ),
        jwt_secret_key=os.getenv("JWT_SECRET_KEY", "change_this_in_production"),
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        jwt_access_token_expire_minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "120")),
        jwt_refresh_token_expire_days=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "14")),
        redis_url=os.getenv("REDIS_URL", ""),
        rate_limit_redis_prefix=os.getenv("RATE_LIMIT_REDIS_PREFIX", "leetcode_tracker:ratelimit"),
        max_active_refresh_token_families_per_admin=int(
            os.getenv("MAX_ACTIVE_REFRESH_TOKEN_FAMILIES_PER_ADMIN", "3")
        ),
        refresh_token_cleanup_interval_minutes=int(os.getenv("REFRESH_TOKEN_CLEANUP_INTERVAL_MINUTES", "60")),
        refresh_token_cleanup_retention_days=int(os.getenv("REFRESH_TOKEN_CLEANUP_RETENTION_DAYS", "30")),
        monitor_check_urls=os.getenv("MONITOR_CHECK_URLS", ""),
        monitor_http_timeout_seconds=int(os.getenv("MONITOR_HTTP_TIMEOUT_SECONDS", "5")),
        admin_emails=os.getenv("ADMIN_EMAILS", ""),
        admin_password=os.getenv("ADMIN_PASSWORD", ""),
        leetcode_graphql_url=os.getenv("LEETCODE_GRAPHQL_URL", "https://leetcode.com/graphql"),
    )
    settings.validate()
    return settings
