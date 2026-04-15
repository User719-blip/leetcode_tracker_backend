from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings
from app.core.rate_limiter import rate_limiter
from app.core.refresh_token_maintenance import get_refresh_cleanup_status


@dataclass(slots=True)
class MonitorCheckResult:
    name: str
    ok: bool
    status_code: int | None = None
    message: str | None = None
    checked_at: str | None = None


def _check_http_url(name: str, url: str, timeout_seconds: int) -> MonitorCheckResult:
    request = Request(url, method="GET")
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

    external_urls = [url.strip() for url in settings.monitor_check_urls.split(",") if url.strip()]
    for index, url in enumerate(external_urls, start=1):
        checks.append(
            _check_http_url(
                name=f"external_{index}",
                url=url,
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
    return {
        "status": "ok" if overall_ok else "degraded",
        "overall_ok": overall_ok,
        "configured_external_checks_count": len(external_urls),
        "checks": [asdict(check) for check in checks],
    }