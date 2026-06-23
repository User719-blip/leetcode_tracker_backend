from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings
from app.core.rate_limiter import rate_limiter
from app.core.refresh_token_maintenance import get_refresh_cleanup_status
from app.core.log_collector import get_recent_logs


@dataclass(slots=True)
class MonitorCheckResult:
    name: str
    ok: bool
    status_code: int | None = None
    message: str | None = None
    checked_at: str | None = None


_ALLOWED_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


@dataclass(frozen=True, slots=True)
class MonitorHttpCheckSpec:
    method: str
    url: str


def parse_monitor_http_check_specs(raw_value: str) -> list[MonitorHttpCheckSpec]:
    specs: list[MonitorHttpCheckSpec] = []
    for item in raw_value.split(","):
        raw_item = item.strip()
        if not raw_item:
            continue

        method = "GET"
        url = raw_item
        parts = raw_item.split(maxsplit=1)
        if len(parts) == 2 and parts[0].upper() in _ALLOWED_HTTP_METHODS:
            method = parts[0].upper()
            url = parts[1].strip()

        specs.append(MonitorHttpCheckSpec(method=method, url=url))

    return specs


def _check_http_url(name: str, url: str, timeout_seconds: int, method: str = "GET") -> MonitorCheckResult:
    request = Request(url, method=method)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return MonitorCheckResult(
                name=name,
                ok=200 <= int(response.status) < 300,
                status_code=int(response.status),
                checked_at=datetime.now(timezone.utc).isoformat(),
            )
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        return MonitorCheckResult(
            name=name,
            ok=False,
            message=str(reason),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        return MonitorCheckResult(
            name=name,
            ok=False,
            message=str(exc),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )


def build_monitor_report() -> dict[str, object]:
    settings = get_settings()
    checks: list[MonitorCheckResult] = []

    cleanup_status = get_refresh_cleanup_status()
    checks.append(
        MonitorCheckResult(
            name="refresh_cleanup_job",
            ok=bool(cleanup_status.get("ok", False)),
            message=cleanup_status.get("message") or None,
            checked_at=cleanup_status.get("last_run_at") or None,
        )
    )

    external_checks = parse_monitor_http_check_specs(settings.monitor_check_urls)
    for index, check_spec in enumerate(external_checks, start=1):
        checks.append(
            _check_http_url(
                name=f"external_{index}",
                url=check_spec.url,
                method=check_spec.method,
                timeout_seconds=settings.monitor_http_timeout_seconds,
            )
        )

    checks.append(
        MonitorCheckResult(
            name="rate_limiter",
            ok=True,
            message=rate_limiter.backend_name,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
    )

    overall_ok = all(check.ok for check in checks)
    # include dependency summary fields expected by the frontend monitor screen
    return {
        "status": "ok" if overall_ok else "degraded",
        "overall_ok": overall_ok,
        "configured_external_checks_count": len(external_checks),
        "checks": [asdict(check) for check in checks],
        "rate_limiter_backend": rate_limiter.backend_name,
        "redis_configured": bool(settings.redis_url.strip()),
        "refresh_token_cleanup_enabled": settings.refresh_token_cleanup_interval_minutes > 0,
        "refresh_token_cleanup_interval_minutes": settings.refresh_token_cleanup_interval_minutes,
        "refresh_token_cleanup_retention_days": settings.refresh_token_cleanup_retention_days,
        "max_active_refresh_token_families_per_admin": settings.max_active_refresh_token_families_per_admin,
        # expose a small set of recent logs for quick inspection in the monitor UI
        "recent_logs": get_recent_logs(5),
    }