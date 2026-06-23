from dataclasses import asdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.core.config import get_settings
from app.core.monitoring import build_monitor_report, parse_monitor_http_check_specs, _check_http_url
from app.core.rate_limiter import rate_limiter
from app.core.refresh_token_maintenance import active_refresh_family_count
from app.db.session import get_db

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/deps")
def health_dependencies(
    admin_email: str | None = Query(default=None, description="Optional admin email to inspect"),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    response: dict[str, object] = {
        "status": "ok",
        "rate_limiter_backend": rate_limiter.backend_name,
        "redis_configured": bool(settings.redis_url.strip()),
        "refresh_token_cleanup_enabled": settings.refresh_token_cleanup_interval_minutes > 0,
        "refresh_token_cleanup_interval_minutes": settings.refresh_token_cleanup_interval_minutes,
        "refresh_token_cleanup_retention_days": settings.refresh_token_cleanup_retention_days,
        "max_active_refresh_token_families_per_admin": settings.max_active_refresh_token_families_per_admin,
    }

    if admin_email:
        response["active_refresh_families"] = active_refresh_family_count(db, admin_email.lower())

    return response


@router.get("/health/monitor")
def monitor_status(
    extra_urls: str | None = Query(default=None, description="Comma-separated extra URLs to probe"),
    _: str = Depends(get_current_admin),
) -> dict[str, object]:
    report = build_monitor_report()
    extra_check_specs = parse_monitor_http_check_specs(extra_urls or "")
    if extra_check_specs:
        extra_checks = [
            _check_http_url(
                name=f"extra_{index}",
                url=spec.url,
                method=spec.method,
                timeout_seconds=settings.monitor_http_timeout_seconds,
            )
            for index, spec in enumerate(extra_check_specs, start=1)
        ]
        report["checks"].extend([asdict(check) for check in extra_checks])
        report["requested_external_checks_count"] = len(extra_check_specs)
        report["status"] = "ok" if all(check.ok for check in extra_checks) and report["overall_ok"] else "degraded"
        report["overall_ok"] = report["status"] == "ok"
    else:
        report["requested_external_checks_count"] = 0

    return report
