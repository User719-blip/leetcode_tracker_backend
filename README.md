# LeetCode Tracker API

FastAPI backend for the LeetCode tracker frontend.

## Run locally

1. Create a virtual environment and install dependencies from `requirements.txt`.
2. Copy `.env.example` to `.env` and set `DATABASE_URL`, `ADMIN_EMAILS`, and `ADMIN_PASSWORD`.
3. Run database migrations:
   - `alembic upgrade head`
4. Start the app:
   - `uvicorn app.main:app --reload`

## Frontend connection

The Flutter frontend connects to this API by building requests against a compile-time `API_BASE_URL`.

### Local development

- Frontend: `flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:8000`
- Backend: `uvicorn app.main:app --reload`
- Requests go to `http://localhost:8000/api/v1/...`

### Hosted deployment

- If the frontend is hosted on GitHub Pages and the backend is hosted elsewhere, set the frontend `API_BASE_URL` secret to the public backend origin, such as `https://api.yourdomain.com`.
- Update `ALLOWED_ORIGINS` in this backend to include the frontend origin, such as `https://user719-blip.github.io`.
- If both are behind one domain, proxy `/api/v1` to the backend and set `API_BASE_URL` to that shared origin.

The frontend does not need Supabase runtime variables anymore; it only needs the public API URL.

## Auth token lifecycle

This backend uses two JWTs:

- Access token (short-lived): controlled by `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`.
- Refresh token (long-lived): controlled by `JWT_REFRESH_TOKEN_EXPIRE_DAYS`.

Flow:

1. `POST /api/v1/auth/admin/login` returns access + refresh tokens.
2. Client uses access token for protected routes.
3. On access-token expiry, client calls `POST /api/v1/auth/refresh` with refresh token.
4. Refresh token is rotated on every successful refresh.
5. Old refresh token is revoked with audit metadata.

Security behavior:

- Refresh token hashes are stored in DB (`refresh_tokens`), not plaintext tokens.
- Reuse of a revoked refresh token triggers family-wide revocation (`reuse_detected`).
- `POST /api/v1/auth/logout` revokes one refresh token.
- `POST /api/v1/auth/logout-all` revokes all refresh tokens for the admin.
- Login is capped by `MAX_ACTIVE_REFRESH_TOKEN_FAMILIES_PER_ADMIN` so one admin cannot accumulate unlimited active sessions.
- A cleanup job removes expired/revoked refresh rows after `REFRESH_TOKEN_CLEANUP_RETENTION_DAYS`.

## Rate limiting

Rate limiting is enabled on auth and admin endpoints.

- If `REDIS_URL` is set and reachable, Redis-backed rate limiting is used.
- If Redis is unavailable, limiter automatically falls back to in-memory mode.

## CORS

Set `ALLOWED_ORIGINS` to every frontend origin that should be allowed to call this API. For example:

- Local dev: `http://localhost:3000,http://localhost:5173,http://localhost:8000`
- GitHub Pages: `https://user719-blip.github.io`
- Custom domain: `https://app.yourdomain.com`

For local Flutter web runs on dynamic ports, keep `ALLOWED_ORIGIN_REGEX` enabled (default):

- `ALLOWED_ORIGIN_REGEX=^https?://(localhost|127\\.0\\.0\\.1)(:\\d+)?$`

This prevents repeated preflight `OPTIONS ... 400` failures when the browser origin changes ports.

Environment variables:

- `REDIS_URL`: Redis connection URL (example: `redis://localhost:6379/0`).
- `RATE_LIMIT_REDIS_PREFIX`: key namespace prefix used in Redis.
- `MAX_ACTIVE_REFRESH_TOKEN_FAMILIES_PER_ADMIN`: maximum active refresh families allowed per admin email.
- `REFRESH_TOKEN_CLEANUP_INTERVAL_MINUTES`: how often the cleanup job runs.
- `REFRESH_TOKEN_CLEANUP_RETENTION_DAYS`: how long expired/revoked refresh rows are kept before deletion.
- `MONITOR_CHECK_URLS`: comma-separated list of extra HTTP endpoints to probe.
- `MONITOR_HTTP_TIMEOUT_SECONDS`: timeout for each monitor probe.

Cleanup job behavior:

- Runs once on app startup.
- Then runs on the configured interval in the API process.
- Deletes rows that are revoked or expired past the retention window.

## Monitoring

`GET /api/v1/health/monitor` returns a combined monitor report.

Access control:

- Requires a valid admin access token (`Authorization: Bearer <access_token>`).

It checks:

- Refresh cleanup heartbeat and last run status.
- Rate limiter backend mode.
- Optional external URLs configured through `MONITOR_CHECK_URLS`.

Use `MONITOR_CHECK_URLS` for any dependency that should be watched from inside this API process, such as a Supabase edge function health endpoint or a cron-triggered URL.

Check syntax:

- `GET https://example.com/health` uses a GET request.
- `POST https://example.com/functions/v1/daily-update` uses POST.
- If no method prefix is provided, GET is used by default.

This is useful for Supabase Edge Functions that return `405 Method Not Allowed` on GET but accept POST.

Security events are emitted as structured JSON logs for:

- Refresh success and failure.
- Refresh reuse detection.
- Logout-all actions.

## Main routes

- `GET /api/v1/health`
- `POST /api/v1/leetcode/fetch`
- `POST /api/v1/auth/admin/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/logout-all`
- `GET /api/v1/admin/users`
- `POST /api/v1/admin/users`
- `DELETE /api/v1/admin/users/{user_id}`
- `POST /api/v1/admin/sync/daily`
- `GET /api/v1/leaderboard/latest`
- `GET /api/v1/leaderboard/weekly`
- `GET /api/v1/leaderboard/global`
- `GET /api/v1/leaderboard/users/{user_id}/snapshots`
