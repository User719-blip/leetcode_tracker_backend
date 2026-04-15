import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.rate_limiter import rate_limiter
from app.core.refresh_token_maintenance import active_refresh_family_count, cleanup_refresh_tokens
from app.core.security_audit import log_security_event
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_token
from app.db.session import get_db
from app.models.refresh_token import RefreshToken
from app.schemas.auth import AdminLoginRequest, LogoutAllRequest, LogoutRequest, RefreshTokenRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _to_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _revoke_token(token: RefreshToken, now: datetime, reason: str, revoked_by: str) -> None:
    if token.revoked_at is None:
        token.revoked_at = now
    token.revocation_reason = reason
    token.revoked_by = revoked_by


def _revoke_token_family(db: Session, family_id: uuid.UUID, reason: str, revoked_by: str) -> None:
    now = datetime.now(timezone.utc)
    family_tokens = db.execute(
        select(RefreshToken).where(RefreshToken.family_id == family_id)
    ).scalars().all()

    for token in family_tokens:
        _revoke_token(token, now=now, reason=reason, revoked_by=revoked_by)

    db.commit()


def _revoke_admin_tokens(db: Session, admin_email: str, reason: str, revoked_by: str) -> None:
    now = datetime.now(timezone.utc)
    tokens = db.execute(
        select(RefreshToken).where(RefreshToken.admin_email == admin_email)
    ).scalars().all()

    for token in tokens:
        _revoke_token(token, now=now, reason=reason, revoked_by=revoked_by)

    db.commit()


@router.post("/admin/login", response_model=TokenResponse)
def admin_login(payload: AdminLoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    ip = _client_ip(request)
    rate_limiter.hit(f"auth:login:ip:{ip}", limit=20, window_seconds=60)

    email = payload.email.lower()
    rate_limiter.hit(f"auth:login:email:{email}", limit=10, window_seconds=60)

    if email not in settings.admin_emails_list:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not settings.admin_password or payload.password != settings.admin_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    cleanup_refresh_tokens(db, retention_days=settings.refresh_token_cleanup_retention_days)
    active_family_count = active_refresh_family_count(db, email)
    if (
        settings.max_active_refresh_token_families_per_admin > 0
        and active_family_count >= settings.max_active_refresh_token_families_per_admin
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many active admin sessions",
        )

    access_token = create_access_token(subject=email)
    refresh_token, token_hash, family_id, expires_at = create_refresh_token(subject=email)

    db_token = RefreshToken(
        token_hash=token_hash,
        admin_email=email,
        family_id=family_id,
        expires_at=expires_at,
    )
    db.add(db_token)
    db.commit()

    log_security_event(
        "auth.login.success",
        admin_email=email,
        family_id=str(family_id),
        ip=ip,
    )

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh_access_token(payload: RefreshTokenRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    ip = _client_ip(request)
    rate_limiter.hit(f"auth:refresh:ip:{ip}", limit=40, window_seconds=60)
    token_hash_prefix = hash_token(payload.refresh_token)[:16]
    rate_limiter.hit(f"auth:refresh:token:{token_hash_prefix}", limit=20, window_seconds=60)

    try:
        token_payload = decode_token(payload.refresh_token)
    except ValueError as exc:
        log_security_event(
            "auth.refresh.failure",
            reason="invalid_token",
            ip=ip,
            token_hash_prefix=token_hash_prefix,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

    if token_payload.get("typ") != "refresh":
        log_security_event(
            "auth.refresh.failure",
            reason="invalid_type",
            ip=ip,
            token_hash_prefix=token_hash_prefix,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token type")

    email = str(token_payload.get("sub", "")).lower()
    if email not in settings.admin_emails_list:
        log_security_event(
            "auth.refresh.failure",
            reason="forbidden",
            ip=ip,
            token_hash_prefix=token_hash_prefix,
            admin_email=email,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    token_family_claim = str(token_payload.get("fam", "")).strip()
    token_id_claim = str(token_payload.get("jti", "")).strip()
    if not token_family_claim or not token_id_claim:
        log_security_event(
            "auth.refresh.failure",
            reason="missing_claims",
            ip=ip,
            token_hash_prefix=token_hash_prefix,
            admin_email=email,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    incoming_hash = hash_token(payload.refresh_token)
    db_token = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == incoming_hash)
    ).scalar_one_or_none()

    if not db_token:
        log_security_event(
            "auth.refresh.failure",
            reason="unrecognized_token",
            ip=ip,
            token_hash_prefix=token_hash_prefix,
            admin_email=email,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token not recognized")

    now = datetime.now(timezone.utc)
    if db_token.revoked_at is not None:
        family_id = db_token.family_id if isinstance(db_token.family_id, uuid.UUID) else uuid.UUID(str(db_token.family_id))
        # A revoked token being reused indicates possible token theft; revoke the entire family.
        db_token.reused_detected_at = now
        _revoke_token_family(db, family_id, reason="reuse_detected", revoked_by="security")
        log_security_event(
            "auth.refresh.reuse_detected",
            admin_email=email,
            family_id=str(family_id),
            token_hash_prefix=token_hash_prefix,
            ip=ip,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")
    if _to_utc_aware(db_token.expires_at) <= now:
        log_security_event(
            "auth.refresh.failure",
            reason="expired",
            admin_email=email,
            family_id=str(db_token.family_id),
            token_hash_prefix=token_hash_prefix,
            ip=ip,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    if str(db_token.family_id) != token_family_claim:
        log_security_event(
            "auth.refresh.failure",
            reason="family_mismatch",
            admin_email=email,
            family_id=str(db_token.family_id),
            token_hash_prefix=token_hash_prefix,
            ip=ip,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    family_id = db_token.family_id if isinstance(db_token.family_id, uuid.UUID) else uuid.UUID(str(db_token.family_id))
    new_refresh_token, new_hash, _, new_exp = create_refresh_token(subject=email, family_id=family_id)

    replacement = RefreshToken(
        token_hash=new_hash,
        admin_email=email,
        family_id=family_id,
        expires_at=new_exp,
    )
    db.add(replacement)
    db.flush()

    _revoke_token(db_token, now=now, reason="rotated", revoked_by="system")
    db_token.last_used_at = now
    db_token.replaced_by_id = replacement.id
    db.commit()

    log_security_event(
        "auth.refresh.success",
        admin_email=email,
        family_id=str(family_id),
        token_jti=token_id_claim,
        token_hash_prefix=token_hash_prefix,
        ip=ip,
    )

    access_token = create_access_token(subject=email)
    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: LogoutRequest, request: Request, db: Session = Depends(get_db)) -> None:
    ip = _client_ip(request)
    rate_limiter.hit(f"auth:logout:ip:{ip}", limit=60, window_seconds=60)

    incoming_hash = hash_token(payload.refresh_token)
    token_row = db.execute(select(RefreshToken).where(RefreshToken.token_hash == incoming_hash)).scalar_one_or_none()
    if token_row:
        _revoke_token(token_row, now=datetime.now(timezone.utc), reason="logout", revoked_by="user")
        db.commit()


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(payload: LogoutAllRequest, request: Request, db: Session = Depends(get_db)) -> None:
    ip = _client_ip(request)
    rate_limiter.hit(f"auth:logout-all:ip:{ip}", limit=30, window_seconds=60)

    incoming_hash = hash_token(payload.refresh_token)
    token_row = db.execute(select(RefreshToken).where(RefreshToken.token_hash == incoming_hash)).scalar_one_or_none()
    if token_row:
        admin_email = token_row.admin_email
        _revoke_admin_tokens(db, admin_email=admin_email, reason="logout_all", revoked_by="user")
        log_security_event(
            "auth.logout_all",
            admin_email=admin_email,
            family_id=str(token_row.family_id),
            ip=ip,
        )
