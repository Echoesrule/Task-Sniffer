# Security Notes and Residual Risks

This document records the security posture after the remediation work and the
risks that remain open. Operational procedures live in
[`security-operations.md`](security-operations.md).

## Implemented controls

- **Authentication and sessions** — passwords use bcrypt with a minimum length
  and complexity policy; login, registration, and Telegram link attempts are
  rate limited (Redis-backed across workers in production, fail-closed when the
  backend is unavailable). Browser clients use an HttpOnly session cookie with
  a double-submit CSRF token; API clients may use bearer tokens. Access tokens
  default to 15 minutes and carry a per-user `token_version` so logout and
  password changes revoke previously issued tokens.
- **Authorization** — registration always creates the `user` role and rejects
  client-supplied roles. Source ingestion controls, source error details, and
  job risk analysis require the web `admin` role; global Telegram commands
  require a chat ID listed in `TELEGRAM_ADMIN_CHAT_IDS`. Application scores are
  derived server-side; client-supplied scores are rejected.
- **Account enumeration** — registration returns a generic `202` response for
  both new and existing addresses. Login uses a dummy password verification for
  unknown accounts to keep timing consistent.
- **Telegram linking** — `/link` accepts only a short-lived, single-use code
  issued by the authenticated web app. Codes are stored hashed and consumed
  atomically. Passwords are never accepted through Telegram.
- **SSRF and URL safety** — every fetch and redirect hop is checked for scheme,
  port, literal/private IP ranges, and resolved addresses. DNS resolution
  failures, timeouts, and empty answers fail closed and are reported as
  unverifiable rather than allowed.
- **CV uploads** — uploads are read in bounded chunks, validated by magic bytes
  and extension/MIME type, stored under UUID filenames, and encrypted at rest
  with AES-256-GCM. Errors returned to clients do not include filesystem paths.
- **Source control** — ingestion pause state is read from the database, so an
  API pause/resume is authoritative across processes and survives startup
  registry synchronization. A manual pause cannot be bypassed with `force`.
- **Error hygiene** — source error endpoints redact URLs, filesystem paths, and
  credential-looking values, and are restricted to administrators.
- **Deployment** — the runtime image is multi-stage and non-root, build tools
  are absent from the runtime layer, PostgreSQL and Redis are not published on
  host ports, and Redis requires a password.

## Residual risks

1. **DNS rebinding / TOCTOU**
   - Destination safety is validated before each request, but the HTTP client
     resolves the hostname again when it connects.
   - Risk: DNS could change between validation and connection, allowing access
     to a private or internal address.
   - Mitigation: run outbound traffic through an egress proxy that enforces the
     same destination policy, or pin the validated address while preserving TLS
     hostname verification and the correct `Host` header.

2. **Outbound policy coverage**
   - Confirm every fetch path (redirects, canonical tags, JSON-LD, application
     links, adapters) uses `fetch_with_policy`/the shared URL policy. New
     adapters must not call `httpx` directly for untrusted URLs.
   - Add deterministic tests when new fetch paths are introduced.

3. **Telegram delivery is at-least-once**
   - A process crash after Telegram accepts a message but before the delivery
     record is committed can cause a duplicate on retry. Telegram does not offer
     exactly-once delivery.

4. **Dependency pinning**
   - `requirements.txt` uses lower bounds rather than a fully locked,
     hash-verified dependency set. For a production release, build from a lock
     file and scan it for vulnerabilities before deployment.

5. **SQLite file permissions**
   - A bare-metal SQLite deployment must restrict `.env`, the database file,
     Telegram persistence, and CV storage to the service account. The Compose
     deployment uses named volumes instead.

## Verification

- Run the full regression suite after any security-relevant change:
  `pytest -q`.
- Reassess these items before a production release, and update this document
  when a residual risk is fixed or explicitly accepted.
