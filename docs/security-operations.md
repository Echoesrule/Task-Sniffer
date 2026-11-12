# Security Operations

Operational runbook for the security controls in Task Sniffer. It covers secret
generation, key rotation, administrator provisioning, deployment hardening, and
the behaviour of sessions, CSRF protection, and authentication rate limits.

See also [`security-notes.md`](security-notes.md) for known residual risks.

## Secrets

The application reads configuration from the process environment (and `.env`
for local development). In production, `SECRET_KEY` **must** come from the
process environment or a secret manager; a value supplied only by `.env` is
rejected at startup.

| Secret | Purpose | Required in production |
|--------|---------|------------------------|
| `SECRET_KEY` | JWT signing key | Yes |
| `ENCRYPTION_KEY` | AES-256-GCM key for uploaded CVs | Yes |
| `POSTGRES_PASSWORD` | PostgreSQL password | When using Compose/PostgreSQL |
| `REDIS_PASSWORD` | Redis authentication | When using Compose/Redis |
| `TELEGRAM_BOT_TOKEN` | Telegram bot API | Only if the bot is enabled |

### Generate secrets

Run these on a trusted machine and store the output in a secret manager. Never
commit them, paste them into tickets, or reuse them between environments.

```bash
# JWT signing key (48 random bytes, URL-safe)
python -c 'import secrets; print(secrets.token_urlsafe(48))'

# CV encryption key (exactly 32 random bytes, URL-safe base64)
python -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'

# PostgreSQL and Redis passwords
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Production validation rejects an empty `SECRET_KEY`, placeholder/development
markers, keys shorter than 32 characters, and low-entropy values. `ENCRYPTION_KEY`
must decode to exactly 32 bytes.

### Delivering secrets

- Docker Compose: export the values in the environment that runs
  `docker compose`, or use an env file that is not committed (`chmod 600`).
  Compose fails fast when required values are missing.
- Bare metal / systemd: use `EnvironmentFile=` pointing at a root-owned file
  with mode `600`, or an `ExecStart` wrapper that loads secrets from a vault.
- Kubernetes: mount secrets as files or inject them with your secret manager's
  CSI driver. Do not bake them into images or manifests.

### Local development

If `SECRET_KEY` is empty in development, the process generates an ephemeral key
at startup. Tokens issued before a restart become invalid. This is intentional:
there is no shared, well-known development signing key.

## Key rotation

### Rotating `SECRET_KEY`

Rotating the signing key invalidates every outstanding access token. That is the
point: it is also the emergency response for a suspected token compromise.

1. Generate a new key (see above) and store it in the secret manager.
2. Update the deployment environment (or the non-committed env file).
3. Restart every API process. With multiple workers or replicas, restart them
   together; a mixed fleet will reject tokens signed by the other key.
4. Verify login succeeds and that a token issued before the rotation is rejected
   with HTTP 401.
5. Remove the old key from the secret manager after the rollback window.

No database change is required. If you need to revoke tokens without rotating
the key (for example, after removing a user), increment that user's
`token_version`, or use the logout endpoint, which does the same for the current
session.

### Rotating `ENCRYPTION_KEY`

CV files are encrypted at rest with the key in `ENCRYPTION_KEY`. The application
supports only one active key at a time, so rotation is a re-encryption job, not a
configuration flip.

1. Back up the database and the CV volume together.
2. Keep the current key available until every file has been re-encrypted.
3. Stop CV uploads (scale the API down or put the upload route behind
   maintenance) so no new files are written with the old key mid-rotation.
4. Generate the new key and run the re-encryption procedure for your deployment.
   The bundled `scripts/encrypt_legacy_cvs.py` migrates plaintext files to the
   configured key; it is **not** a key-to-key rotation tool. If you already have
   encrypted files under the old key, decrypt with the old key and re-encrypt
   with the new key using an operator-reviewed script, verifying each file before
   deleting the old copy.
5. Update `ENCRYPTION_KEY`, restart the API and workers, and verify an authorized
   CV download.
6. Retain the old key in escrow until backups that contain old-key ciphertext
   have expired.

Losing the CV key makes encrypted documents unrecoverable. Back it up separately
from the database and test restoration periodically.

## Administrator provisioning

Registration always creates a regular `user`; roles are never accepted from the
registration request. Provision or promote an administrator with the CLI:

```bash
# Interactive (password is never echoed or passed as an argument)
python scripts/create_admin.py --email admin@example.com

# Non-interactive, password supplied by a secret manager
python scripts/create_admin.py --email admin@example.com --password-stdin < /run/secrets/admin_password

# Promote an existing account without changing its password
python scripts/create_admin.py --email existing@example.com --promote

# Inside Compose
docker compose exec api python scripts/create_admin.py --email admin@example.com
```

The CLI applies the same password policy as registration and refuses to read a
password from a non-interactive terminal unless `--password-stdin` is used. It
never overwrites an existing password implicitly.

Administrator-only capabilities include:

- `POST /sources/ingest`, `/sources/{name}/pause`, `/sources/{name}/resume`
- `GET /sources/{name}/errors`
- `POST /jobs/{id}/analyze` (rewrites shared job risk fields)
- Telegram `/stats` and `/sources` (restricted to `TELEGRAM_ADMIN_CHAT_IDS`)

Authenticated non-admins receive HTTP 403 for these endpoints.

## Sessions, cookies, and CSRF

The browser frontend authenticates with an HttpOnly session cookie. API clients
may continue to send `Authorization: Bearer <token>`; bearer requests are not
subject to CSRF checks.

- The access cookie is `HttpOnly` and `SameSite` configurable via
  `COOKIE_SAMESITE` (`lax` by default). Set `COOKIE_SECURE=true` behind HTTPS.
- Access tokens default to 15 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES`). Logging
  out increments the user's `token_version`, so previously issued tokens stop
  working even if a copy was captured.
- Cookie-authenticated unsafe methods (`POST`, `PUT`, `PATCH`, `DELETE`) must
  send the double-submit token: the `csrf_token` cookie value in the
  `X-CSRF-Token` header. The frontend reads the cookie and sets the header
  automatically.
- `POST /auth/login` and `POST /auth/register` are exempt from the CSRF check
  because they establish or bootstrap the session.
- CORS uses explicit origins from `CORS_ORIGINS` with credentials enabled.
  Wildcard origins are not used.

If the frontend and API are on different sites, use `COOKIE_SAMESITE=none` with
`COOKIE_SECURE=true`. Prefer same-site deployment when possible.

## Authentication rate limiting

Login, registration, and Telegram link-code attempts are throttled. Limits are
stored in Redis when it is reachable, so they apply across API workers and
replicas. Configure:

| Variable | Default | Meaning |
|----------|---------|---------|
| `AUTH_RATE_LIMIT_ATTEMPTS` | 5 | Login attempts per window |
| `AUTH_RATE_LIMIT_WINDOW_SECONDS` | 900 | Login window |
| `REGISTRATION_RATE_LIMIT_ATTEMPTS` | 5 | Registrations per window |
| `REGISTRATION_RATE_LIMIT_WINDOW_SECONDS` | 3600 | Registration window |
| `TELEGRAM_LINK_ATTEMPTS` | 5 | Link attempts per window |
| `TELEGRAM_LINK_WINDOW_SECONDS` | 900 | Link window |

In production, a missing or unreachable Redis backend fails closed (HTTP 429/503
rather than unlimited attempts). In development the limiter falls back to a
process-local counter. Always deploy Redis with authentication and without a
public port when relying on shared limits.

## Telegram account linking

Passwords are never accepted through Telegram. Generate a short-lived,
single-use code in the web app (**Settings → Telegram**), then send
`/link <code>` to the bot. Codes are stored hashed, expire after
`TELEGRAM_LINK_CODE_TTL_SECONDS` (10 minutes by default), and are consumed
atomically so two chats cannot redeem the same code.

Set `TELEGRAM_ADMIN_CHAT_IDS` to a comma-separated list of chat IDs allowed to
run global operational commands. Unlinked or non-admin users cannot read global
statistics or the source list through the bot.

## Deployment hardening

The bundled `Dockerfile` is a multi-stage build:

- Build tools (`build-essential`) exist only in the builder stage.
- The runtime image copies the finished virtualenv and runs as unprivileged UID
  `10001` (`app`), with no shell login.
- A healthcheck probes `/health`.

`docker-compose.yml` applies these defaults:

- PostgreSQL and Redis have **no published host ports**; they are reachable only
  on the Compose network. Use `docker compose exec db psql ...` or
  `docker compose exec redis redis-cli ...` for maintenance.
- Redis requires a password (`REDIS_PASSWORD`) and uses append-only persistence.
- PostgreSQL requires `POSTGRES_USER`/`POSTGRES_PASSWORD`; Compose refuses to
  start without them.
- Services run with `no-new-privileges` and restart unless stopped.
- The API, worker, and beat services run Alembic migrations or Celery without
  bind-mounting the source tree.

Operational notes:

- Set `COOKIE_SECURE=true` and terminate TLS at a reverse proxy before exposing
  the API. `COOKIE_SECURE=false` is only for local HTTP development.
- Restrict inbound access to the API port at the firewall/security group level.
- If an existing `cv_data` volume was created by an older image, fix ownership
  once: `docker compose run --rm --user root api chown -R 10001:10001 /data/cvs`.
- Do not expose PostgreSQL or Redis publicly. If a host tool must reach them,
  use an SSH tunnel or `docker compose exec` rather than publishing the port.

## Dependency security

Run `npm audit --omit=dev` in `frontend/` and `pip-audit` against the backend
virtualenv as part of release checks. The lockfile is pinned and should be
installed with `npm ci`.

As of this revision, `npm audit --omit=dev` reports one high-severity advisory
for the `postcss` copy bundled inside Next.js (`next/node_modules/postcss`
8.4.31, GHSA-qx2v-qp2m-jg93 and related source-map advisories). The top-level
`postcss` dependency is already on 8.5.26 and Next.js itself is on the patched
15.5.29 release. The bundled copy is only used by the Next.js build pipeline,
which processes the repository's own CSS rather than untrusted user input, so it
is not reachable at runtime. npm only offers a fix by upgrading to Next.js 16,
a breaking major change; track that upgrade separately and re-run the audit
afterwards. Do not silence the advisory in configuration.
- Back up `pgdata`, `redisdata`, and `cv_data` consistently. Keep the CV key in
  a separate secret store from the backups.

## Local file permissions

For a bare-metal SQLite deployment, restrict the database, `.env`, Telegram
persistence, and CV storage to the service account:

```bash
chmod 600 .env work_bot_hunter.db
chmod 700 data/cvs
```

Run the API as a dedicated unprivileged user, not as root.
