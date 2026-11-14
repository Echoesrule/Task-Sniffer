# Task Sniffer — Security Audit

**Type:** Read-only source security audit  
**Scope:** Whole repository at `140e5d0` (`fix/ingestion-source-status`), current working tree  
**Method:** Manual source review, control/taint-path tracing, targeted configuration checks. No code was modified and no live exploitation was performed.  
**Date:** 2026-11-11

---

## 1. Decision Summary

The application has solid primitives in several areas — parameterized SQLAlchemy queries, HS256 JWT verification with an explicit algorithm list, passlib password hashing, AES-256-GCM CV encryption with AAD, UUID-based CV filenames, a per-hop SSRF policy for outbound fetches, and no raw-HTML sink in the frontend. The main weaknesses are **authorization boundaries and operational controls**, not parser-level injection.

The highest-impact issues are:

1. **No administrator/operator role exists.** Any self-registered user can trigger global source ingestion, pause/resume sources, and rewrite global job risk fields.
2. **Production secret validation accepts a guessable placeholder** as long as it is 32 characters, and the local `.env` uses exactly such a value.

Neither issue requires a memory-corruption or injection primitive. Both are reachable with a normal account or a forged token.

**Overall risk: High for a production deployment; Medium for a single-user local deployment.**

---

## 2. Findings

| ID | Severity | Finding |
|----|----------|---------|
| H-01 | High | Broken function-level authorization on source control and global job mutation |
| H-02 | High | Production `SECRET_KEY` validation accepts low-entropy placeholders |
| M-01 | Medium | No authentication rate limiting, lockout, or meaningful password policy |
| M-02 | Medium | Telegram `/link` accepts a plaintext password in chat with no throttling |
| M-03 | Medium | CV upload buffers the whole body before the size check |
| M-04 | Medium | Source pause/resume is a no-op for scheduled ingestion |
| M-05 | Medium | JWT stored in `localStorage`; no server-side logout or revocation |
| M-06 | Medium | Unauthenticated source inventory and raw ingestion-error disclosure |
| M-07 | Medium | Telegram `/stats` and `/sources` are unauthenticated |
| M-08 | Medium | Container and network hardening gaps (root, exposed Postgres/Redis) |
| M-09 | Medium | Local secret and database file permissions are world-readable |
| L-01 | Low | Client-supplied `match_score` / `risk_score` on application creation |
| L-02 | Low | Dependencies are lower-bound-only; no lockfile |
| L-03 | Low | `PicklePersistence` enables local-write-to-RCE |
| L-04 | Low | Dead redirect helper bypasses the SSRF policy |
| L-05 | Low | CORS allows every origin (no credentials) |
| L-06 | Informational | Residual DNS-rebinding/TOCTOU window in the SSRF policy |

---

### H-01 — Broken function-level authorization on source control and global job mutation

**Severity:** High  
**Area:** API authorization / multi-user isolation  
**CWE:** CWE-285 (Improper Authorization), CWE-862 (Missing Authorization)

**Evidence**

- `backend/api/deps.py:92-96` — the authenticated principal is returned with `"role": getattr(user, "role", "user") or "user"`. The `User` model has no `role` column, so every user is `"user"`.
- `backend/api/routes/auth.py:36-66` — registration is open to anyone and immediately returns a valid token.
- `backend/api/routes/sources.py:162-180` — `POST /sources/{name}/ingest` requires only `get_current_user`. It accepts `force` and `limit` (up to 500).
- `backend/api/routes/sources.py:183-197` — `POST /sources/{name}/pause` requires only `get_current_user` and mutates the global `Source` row.
- `backend/api/routes/sources.py:200-223` — `POST /sources/{name}/resume` requires only `get_current_user`.
- `backend/api/routes/jobs.py:215-251` — `POST /jobs/{job_id}/analyze` requires only `get_current_user` and writes `job.risk_score`, `job.risk_level`, `job.risk_flags_list`, and `job.analyzed_at` on the shared `Job` row.

**Attack path**

1. Register at `POST /auth/register`; receive a bearer token.
2. Enumerate sources with `GET /sources` (also unauthenticated — see M-06).
3. Call `POST /sources/{name}/ingest` repeatedly with `limit=500`, or with `force=true` to bypass registry-level pauses that are not `permission_blocked`/`DISABLED`.
4. Pause or resume any source row, or rewrite the risk classification of any job.

**Impact**

- Resource abuse: repeated ingestion triggers outbound scraping, CPU work, and database writes. There is no per-user quota or rate limit.
- Third-party impact: an attacker can force traffic to job boards, potentially violating rate limits or terms of service.
- Global integrity: source status and job risk fields are shared state; any account can change them.
- Availability: pause/resume and forced ingestion can disrupt scheduled collection.
- This is not arbitrary SSRF: `name` must exist in the static registry, so the target set is limited to configured job sources.

**Fix**

- Add an explicit `role` (or `is_admin`) column to `User` and an `require_admin` dependency.
- Require admin for `ingest`, `pause`, `resume`, and `analyze`; keep read-only source health available to normal users if needed.
- Add per-user and global rate limits to ingestion endpoints, plus an audit log of who triggered each run.
- Close or gate registration (invite, email verification, or explicit admin approval) if the deployment is not intended to be public.
- Return `403` rather than silently allowing the operation.

**Verification**

- Integration test: a non-admin token calling each mutation endpoint must receive `403`.
- Integration test: an admin token must succeed and produce an audit record.

---

### H-02 — Production `SECRET_KEY` validation accepts low-entropy placeholders

**Severity:** High  
**Area:** Authentication / configuration  
**CWE:** CWE-521 (Weak Password Requirements), CWE-1188 (Insecure Default Initialization)

**Evidence**

- `backend/config.py:70-89` — in production the validator rejects only the exact strings `{"change-me", "changeme", "secret", "development"}` and otherwise checks only `len(secret_key) >= 32`.
- `.env:12` — the local value is `change-me-to-a-random-secret-key`, which is exactly 32 characters.
- `docker-compose.yml:38-40` — the API, worker, and beat services run with `APP_ENV: production` and pass `SECRET_KEY` from `.env`.
- Verified locally with the project virtualenv: `Settings(app_env="production", secret_key="change-me-to-a-random-secret-key", encryption_key=<valid 32-byte key>)` is accepted.

**Attack path**

1. Deploy the provided Compose stack with a `.env` derived from the sample/default.
2. An attacker who knows or guesses the placeholder signs an HS256 token with `sub` set to a known user's email or ID.
3. `get_current_user` (`backend/api/deps.py:56-96`) accepts the token and resolves the user from the database.

**Impact**

- Full account impersonation for any known email or user ID.
- Because there is no server-side revocation (M-05), a forged token remains valid for the configured 60 minutes.
- The weakness is conditional: the current `.env` also contains an invalid `ENCRYPTION_KEY`, so the production validator would fail startup until that key is fixed. An operator who fixes only the encryption key and leaves `SECRET_KEY` unchanged is exposed.

**Fix**

- Replace the exact-string blocklist with an entropy/pattern check: reject values containing `change`, `example`, `secret`, `password`, `default`, `test`, or `dev`, and reject any value that appears in documentation.
- Require production secrets to come from the environment or a secret manager, not `.env`.
- Consider generating and printing a one-time secret only in development, and refusing to start in production if the value matches a known placeholder prefix.
- Rotate the current key and invalidate all issued tokens.

**Verification**

- Unit test: `Settings(app_env="production", secret_key="change-me-to-a-random-secret-key", ...)` must raise.
- Unit test: a 32-byte random base64/urlsafe value must be accepted.

---

### M-01 — No authentication rate limiting, lockout, or meaningful password policy

**Severity:** Medium  
**Area:** Authentication  
**CWE:** CWE-307 (Improper Restriction of Excessive Authentication Attempts), CWE-521

**Evidence**

- `backend/api/routes/auth.py:19-26` — registration requires only `password: min_length=6`; login has no length policy.
- `backend/api/routes/auth.py:36-48` — registration returns a distinct `400` when the email already exists, enabling account enumeration.
- No rate limiter is configured anywhere in `backend/api` or `backend/security` (grep for `slowapi`, `Limiter`, `rate_limit` found only source-rate fields).
- `frontend/src/app/login/page.tsx:36` — the client enforces the same 6-character minimum.

**Attack path**

- Credential stuffing or online brute force against `POST /auth/login`.
- Enumeration of registered emails through `POST /auth/register`.
- Weak passwords are accepted and immediately produce a token.

**Impact**

- Account takeover through password guessing or reused credentials.
- User enumeration supports targeted phishing and credential stuffing.
- No lockout means an attacker can sustain attempts indefinitely.

**Fix**

- Add per-IP and per-account rate limiting with exponential backoff on login and registration.
- Add temporary lockout or CAPTCHA after repeated failures.
- Raise the minimum password length (12+) and screen against common-password lists.
- Return a generic response for registration conflicts, or move to email-verification flow.
- Consider MFA for accounts with sensitive data.

**Verification**

- Integration test: repeated failed logins eventually return `429`.
- Integration test: registration with an existing email does not reveal existence.

---

### M-02 — Telegram `/link` accepts a plaintext password in chat with no throttling

**Severity:** Medium  
**Area:** Telegram bot / credential handling  
**CWE:** CWE-522 (Insufficiently Protected Credentials), CWE-307

**Evidence**

- `backend/telegram/handlers.py:163-214` — `/link <email> <password>` reads the password from `context.args`, verifies it against `User.hashed_password`, and replies in the same chat.
- There is no rate limit, delay, or lockout on repeated `/link` attempts.
- Bot messages are stored in Telegram's cloud and are readable by the bot operator; bot chats are not end-to-end encrypted.

**Attack path**

- A user types their web password into a Telegram chat, where it persists in chat history and Telegram infrastructure.
- An attacker with access to the bot or the chat can attempt repeated `/link` guesses; success links the victim's web account to the attacker's Telegram identity.

**Impact**

- Credential exposure beyond the web application.
- Account linking is an identity-binding operation; a successful guess gives the attacker `/apply` and `/my_applications` access as the victim.
- No throttling makes guessing practical if the password is weak (see M-01).

**Fix**

- Replace password entry with a short-lived, single-use link code generated in the authenticated web UI and entered in Telegram (or a deep link with a signed token).
- Never accept passwords in chat.
- Add rate limiting and a per-chat failure counter.
- Delete messages containing credentials where the Telegram API allows it.

**Verification**

- Manual test: `/link` no longer accepts a password argument.
- Integration test: an expired or reused link code is rejected.

---

### M-03 — CV upload buffers the whole body before the size check

**Severity:** Medium  
**Area:** File upload / availability  
**CWE:** CWE-400 (Uncontrolled Resource Consumption), CWE-434 (Unrestricted Upload)

**Evidence**

- `backend/api/routes/candidates.py:141-146` — `content = await file.read()` reads the entire upload into memory, then compares `len(content)` to `MAX_CV_BYTES`.
- There is no `Content-Length` check or server-level request-body limit in the route.
- `backend/api/routes/candidates.py:130-139` — the content type is taken from the client-supplied `UploadFile.content_type`; no magic-byte validation is performed.
- `backend/api/routes/candidates.py:151-157` — only the filename suffix is validated, after the body has already been read.

**Attack path**

- An authenticated user uploads a very large file (or many concurrent uploads) to exhaust API memory or disk.
- A file with an allowed suffix but arbitrary content is stored and later served as `application/octet-stream`.

**Impact**

- Authenticated denial of service against the API process.
- Disk exhaustion through repeated uploads.
- Content-type spoofing; the stored file is not verified to be a PDF/DOC/DOCX.

**Fix**

- Enforce a maximum `Content-Length` and stream the upload to a temporary file with a hard byte cap; abort as soon as the cap is exceeded.
- Add a reverse-proxy body limit.
- Sniff magic bytes (`%PDF`, OLE header, ZIP/OOXML signature) before encryption and storage.
- Add a per-user upload quota and clean up abandoned temp files.
- Consider antivirus/CDR scanning for a multi-user deployment.

**Verification**

- Integration test: an upload larger than `MAX_CV_BYTES` is rejected without buffering the full body.
- Integration test: a `.pdf` file with non-PDF magic bytes is rejected.

---

### M-04 — Source pause/resume is a no-op for scheduled ingestion

**Severity:** Medium  
**Area:** Operational control / ingestion  
**CWE:** CWE-693 (Protection Mechanism Failure)

**Evidence**

- `backend/api/routes/sources.py:183-197` and `200-223` — pause/resume write `Source.source_status`, `pause_reason`, and `retry_at` to the database.
- `backend/services/ingestion.py:159-177` — `run_source` reads the in-memory `SourceConfig` from the registry and evaluates `config.permission_blocked` and `config.source_status`; it never loads the database row's `source_status` or `pause_reason`.
- `backend/api/app.py:23-49` — `sync_registry_sources` updates `enabled`, `access_method`, `permission_status`, `robots_status`, `terms_status`, `provenance`, `rate_limit`, `requires_auth`, and `last_audited`, but not `source_status` or `pause_reason`.
- `backend/services/ingestion.py:166-177` — `force=true` bypasses `refuse_reason` for sources that are not `permission_blocked` or `DISABLED`, including registry-level pauses.

**Attack path / failure mode**

- An operator pauses a source through the API to stop collection (e.g., during an incident or after a terms-of-service complaint).
- The scheduler still calls `run_source`; because the registry config is unchanged, collection continues.
- Conversely, an authenticated user can force a registry-paused source to run.

**Impact**

- The pause control cannot be relied on for incident response, rate-limit mitigation, or legal/ToS compliance.
- Operators may believe collection has stopped when it has not.
- This is a correctness and safety issue, not direct data compromise.

**Fix**

- Make the database row authoritative for runtime status, or sync `source_status`/`pause_reason` into the registry before each run.
- Check the database status inside `run_source` and refuse when `PAUSED`, regardless of `force`.
- Separate "policy blocked" (never forceable) from "operator paused" (forceable only by an admin with an audit record).
- Add a regression test that pauses a source, runs the scheduler path, and asserts no fetch occurs.

**Verification**

- Integration test: after `POST /sources/{name}/pause`, a scheduled `run_source` performs no outbound request.

---

### M-05 — JWT stored in `localStorage`; no server-side logout or revocation

**Severity:** Medium  
**Area:** Session management  
**CWE:** CWE-522, CWE-613 (Insufficient Session Expiration)

**Evidence**

- `frontend/src/services/api.ts:3-10` — `getAuthToken` reads `auth_token`/`access_token` from `localStorage`.
- `frontend/src/services/api.ts:85-103` — login/register write the token to `localStorage`; `logout` only removes it client-side.
- `backend/security/__init__.py:25-42` — tokens are HS256 with an `exp` claim; there is no `jti`, token version, or denylist.
- `backend/config.py:21` — the default lifetime is 60 minutes.

**Attack path**

- Any XSS or malicious browser extension can read `localStorage` and exfiltrate the token.
- A stolen token remains valid until expiry; logout on one device does not invalidate it.
- Deactivation (`is_active=False`) is enforced on every request by the database lookup in `get_current_user`, but there is no way to revoke a token for a still-active account, and a password change does not invalidate existing tokens.

**Impact**

- Token theft converts any frontend injection into full account takeover for up to 60 minutes.
- No way to revoke a compromised session short of rotating `SECRET_KEY` (which invalidates all users).

**Fix**

- Prefer an `HttpOnly`, `Secure`, `SameSite=Lax/Strict` cookie for the access token, or keep the access token in memory and use a rotating refresh token in an `HttpOnly` cookie.
- Add a `token_version` or `jti` denylist and a server-side logout endpoint.
- Shorten access-token lifetime (5–15 minutes) with refresh rotation.
- Add a strict CSP to reduce XSS impact.
- Note: no current raw-HTML sink was found, so this is a latent risk rather than an active XSS chain.

**Verification**

- Manual test: logout invalidates the token server-side.
- Manual test: a token copied to another browser stops working after logout/rotation.

---

### M-06 — Unauthenticated source inventory and raw ingestion-error disclosure

**Severity:** Medium  
**Area:** Information disclosure  
**CWE:** CWE-200

**Evidence**

- `backend/api/routes/sources.py:89-159` — `GET /sources` has no auth dependency and returns source names, URLs, tiers, permission/robots status, pause reasons, last errors, job counts, and application counts.
- `backend/api/routes/sources.py:226-248` — `GET /sources/{name}/urls` has no auth dependency.
- `backend/api/routes/sources.py:251-278` — `GET /sources/{name}/errors` has no auth dependency and returns raw `error_message` and `job_url` values.

**Impact**

- Reveals the complete ingestion surface, including sources that are paused, restricted, or under review.
- Raw error messages can contain internal URLs, stack details, or request metadata useful for follow-on attacks.
- Application counts and source health may reveal business activity.

**Fix**

- Require authentication for source inventory and URL stats; require admin for raw errors.
- Return redacted error classes/messages to non-admin users.
- Strip query strings and credentials from `job_url` before returning it.

**Verification**

- Integration test: unauthenticated requests to all three endpoints return `401`.

---

### M-07 — Telegram `/stats` and `/sources` are unauthenticated

**Severity:** Medium  
**Area:** Telegram bot / information disclosure  
**CWE:** CWE-306 (Missing Authentication for Critical Function)

**Evidence**

- `backend/telegram/handlers.py:431-464` — `/stats` queries global job/application counts and per-source counts with no `_ensure_user` or linked-account check.
- `backend/telegram/handlers.py:467-486` — `/sources` lists every source, its tier, enabled status, and job count with no authentication.

**Impact**

- Any Telegram user who discovers the bot can enumerate the deployment's sources and global activity.
- Combined with `/link` (M-02), this gives an attacker reconnaissance before credential guessing.

**Fix**

- Require an active, linked `TelegramUser` for `/stats` and `/sources`, or restrict them to configured admin chat IDs.
- Return only user-scoped data to non-admin users.

**Verification**

- Manual test: an unlinked chat receives a permission-denied response.

---

### M-08 — Container and network hardening gaps

**Severity:** Medium  
**Area:** Deployment  
**CWE:** CWE-250 (Execution with Unnecessary Privileges), CWE-306

**Evidence**

- `Dockerfile:1-16` — the image runs as root (no `USER`), and `build-essential` is installed in the runtime image (`Dockerfile:5-7`).
- `docker-compose.yml:10-11` — PostgreSQL is published on `0.0.0.0:5432`.
- `docker-compose.yml:20-23` — Redis is published on `0.0.0.0:6379` with no authentication.
- `docker-compose.yml:49-51, 75-77, 101-102` — `./backend` is bind-mounted into the API, worker, and beat containers in production.
- `backend/workers/celery_app.py:16-19` — Celery uses JSON serialization and `accept_content=["json"]`, which mitigates pickle-based task injection.

**Impact**

- Container compromise yields root inside the container and easier host interaction via bind mounts.
- Exposed Redis allows reading/flushing broker data and injecting JSON tasks into registered Celery tasks (for example, triggering ingestion), plus denial of service.
- Exposed PostgreSQL is directly attackable with the configured credentials.
- `build-essential` expands the attack surface and image size.

**Fix**

- Create a non-root user and switch to it; remove `build-essential` from the runtime stage (multi-stage build).
- Do not publish `5432`/`6379`; use an internal Compose network only.
- Require Redis authentication and bind it to the internal interface.
- Remove production bind mounts; bake code into the image.
- Add `read_only`, `no-new-privileges`, and resource limits where practical.

**Verification**

- `docker compose config` shows no host-published database/Redis ports.
- `docker run --rm <image> id` shows a non-root UID.

---

### M-09 — Local secret and database file permissions are world-readable

**Severity:** Medium (local deployment)  
**Area:** Host hygiene  
**CWE:** CWE-732 (Incorrect Permission Assignment)

**Evidence**

- `stat` on the working tree: `.env` is mode `664`; `work_bot_hunter.db` and `work_hunter.db` are mode `644`.
- `.env` contains a populated `TELEGRAM_BOT_TOKEN` and the placeholder `SECRET_KEY`/`ENCRYPTION_KEY`.
- The SQLite databases contain user records, password hashes, candidate profiles, and applications.
- These files are correctly untracked/ignored (`.gitignore:15,20`), so this is a host-level exposure, not a repository leak.

**Impact**

- Any local user or process can read the bot token, signing secret, and password hashes.
- Password hashes are PBKDF2/bcrypt and therefore slow to crack, but offline cracking is still possible.
- A leaked bot token allows full control of the Telegram bot.

**Fix**

- Set `.env` to `600` and database files to `600` (or a dedicated service account with `640`).
- Rotate the Telegram bot token and any secret that was readable.
- Run the service under a dedicated low-privilege account.
- Consider a secret manager for production.

**Verification**

- `stat -c '%a' .env *.db` returns `600` (or stricter).

---

### L-01 — Client-supplied `match_score` / `risk_score` on application creation

**Severity:** Low  
**Area:** Data integrity  
**CWE:** CWE-472 (External Control of Assumed-Immutable Web Parameter)

**Evidence**

- `backend/api/schemas.py:211-217` — `ApplicationCreate` accepts `match_score` and `risk_score` from the client.
- `backend/api/routes/applications.py:113-121` — both values are copied directly into the new `Application` row.

**Impact**

- A user can record arbitrary scores on their own applications. This affects only their own data, but it undermines analytics and any downstream decisions based on those scores.

**Fix**

- Remove both fields from the create schema and compute them server-side from the candidate/job pair, or ignore client values.

**Verification**

- Integration test: posting scores has no effect on the stored row.

---

### L-02 — Dependencies are lower-bound-only; no lockfile

**Severity:** Low  
**Area:** Supply chain  
**CWE:** CWE-1104 (Use of Unmaintained Third-Party Components)

**Evidence**

- `requirements.txt:1-23` — every dependency uses `>=` with no upper bound or hash.
- No lockfile (`requirements.lock`, `poetry.lock`, `uv.lock`, etc.) is present.
- `python-jose[cryptography]>=3.3.0` permits versions with known algorithm-confusion/JWT-bomb issues before 3.4.0. The code does pass an explicit `algorithms=["HS256"]` list (`backend/security/__init__.py:40`), which mitigates the algorithm-confusion class.

**Impact**

- Non-reproducible builds; a compromised or broken upstream release can enter production.
- A fresh install may resolve to an untested version.

**Fix**

- Pin exact versions and generate a lockfile with hashes.
- Run `pip-audit` or Dependabot/Trivy in CI.
- Raise the `python-jose` floor to a patched version, or migrate to `PyJWT`.

**Verification**

- CI installs from the lockfile and fails on hash mismatch.

---

### L-03 — `PicklePersistence` enables local-write-to-RCE

**Severity:** Low  
**Area:** Telegram bot  
**CWE:** CWE-502 (Deserialization of Untrusted Data)

**Evidence**

- `backend/telegram/bot.py:50-58` — `PicklePersistence(filepath=.../data/tg_persistence.pkl)` loads and saves bot state with `pickle`.

**Impact**

- Anyone who can write `data/tg_persistence.pkl` (local user, compromised backup, or another service sharing the volume) can achieve code execution in the bot process on the next start.
- Not remotely reachable through the application's own API.

**Fix**

- Restrict the `data/` directory to the service account (`700`).
- Consider a non-pickle persistence backend or accept the risk explicitly.
- Never restore the file from an untrusted source.

**Verification**

- `stat -c '%a' data/tg_persistence.pkl` is `600` and the directory is `700`.

---

### L-04 — Dead redirect helper bypasses the SSRF policy

**Severity:** Low (latent)  
**Area:** SSRF defense  
**CWE:** CWE-918

**Evidence**

- `backend/scrapers/adapter.py:172-198` — `request_with_redirect` calls `resolve_redirects` and then performs `client.get(chain.final_url)` without a per-hop safety check.
- `backend/sources/urls.py:600-622` — `resolve_redirects` relies on `follow_redirects=True` and does not validate intermediate hops.
- Grep confirms `request_with_redirect` and `resolve_redirects` are not called anywhere in production code.

**Impact**

- No current exploit path. If the helper is wired into a future adapter, it would reintroduce redirect-based SSRF and bypass the stronger `fetch_with_policy` path.

**Fix**

- Delete the dead helpers, or rewrite `request_with_redirect` to use `fetch_with_policy` so every hop is validated.

**Verification**

- Static check: no references to `resolve_redirects` outside the SSRF module.

---

### L-05 — CORS allows every origin (no credentials)

**Severity:** Low  
**Area:** Browser security policy  
**CWE:** CWE-942 (Permissive Cross-domain Policy)

**Evidence**

- `backend/api/app.py:125-131` — `allow_origins=["*"]`, `allow_credentials=False`, all methods and headers allowed.

**Impact**

- Because bearer tokens are used and credentials are disabled, this is not directly exploitable for authenticated cross-origin reads. It does allow any website to call public endpoints and increases exposure if the auth model later moves to cookies.

**Fix**

- Restrict `allow_origins` to the deployed frontend origin(s) via configuration.
- Keep `allow_credentials=False` unless cookie auth is adopted, in which case origins must be explicit.

**Verification**

- Preflight from an unlisted origin is rejected.

---

### L-06 — Residual DNS-rebinding/TOCTOU window in the SSRF policy

**Severity:** Informational  
**Area:** SSRF defense  
**CWE:** CWE-367

**Evidence**

- `backend/sources/urls.py` validates resolved IPs and fails closed on DNS errors; `fetch_with_policy` checks each redirect hop.
- The HTTP client resolves the hostname again when connecting, so a malicious DNS server could change the answer between validation and connection.
- This residual risk is already documented in `docs/security-notes.md`.

**Impact**

- Theoretically allows a configured source hostname to resolve to a private address after validation. Exploitation requires control of the source's DNS, which is a high bar and outside the normal user-controlled input path.

**Fix**

- Pin the validated IP for the connection while preserving TLS SNI/Host, or route outbound fetches through an egress proxy that enforces the policy.

---

## 3. Positive Controls Verified

These were checked and are working as intended; they should not be regressed:

- **SQL injection:** all reviewed queries use SQLAlchemy expressions/parameters; no string-built SQL was found.
- **JWT verification:** `decode_access_token` passes `algorithms=["HS256"]` explicitly (`backend/security/__init__.py:40`), preventing algorithm confusion.
- **Password storage:** passlib with `pbkdf2_sha256`/`bcrypt` (`backend/security/__init__.py:12`).
- **CV path traversal:** stored names are server-generated UUIDs; client filenames are reduced with `os.path.basename`; suffixes are allow-listed (`backend/api/routes/candidates.py:148-167`).
- **CV encryption:** AES-256-GCM with AAD and a production key-length check (`backend/security/cv_encryption.py`, `backend/config.py:82-88`).
- **CV authorization:** download/delete/metadata are scoped to the authenticated user's candidate (`backend/api/routes/candidates.py:191-240`).
- **Application authorization:** read/update queries join `Candidate` and filter by `user_id`, preventing IDOR (`backend/api/routes/applications.py:137-180`).
- **SSRF policy:** DNS failures fail closed; redirects are validated per hop; private/link-local targets are rejected (`backend/sources/urls.py`).
- **Job links:** the frontend restricts schemes to `http(s)` and status to `VALID` (`frontend/src/lib/job-links.ts`).
- **No raw HTML sink:** grep found no `dangerouslySetInnerHTML` or `innerHTML` usage; job descriptions render as JSX text.
- **CSRF:** bearer-token auth and no cookie-based session mean classic CSRF is not applicable today.
- **Secret files:** `.env`, databases, logs, and PIDs are untracked and ignored by git.

---

## 4. Remediation Order

1. **H-01:** add an admin role and enforce it on source control and job analysis; rate-limit ingestion.
2. **H-02:** harden production secret validation and rotate the current `SECRET_KEY`.
3. **M-01/M-02:** add authentication rate limiting and replace the Telegram password flow with a one-time link code.
4. **M-04:** make pause/resume actually stop scheduled ingestion.
5. **M-03/M-05:** stream CV uploads with a hard cap; move tokens out of `localStorage` and add revocation.
6. **M-06/M-07:** require authentication for source/error and Telegram global-data endpoints.
7. **M-08/M-09:** container hardening, close published DB/Redis ports, fix file permissions.
8. **Low items:** schema integrity, dependency pinning, dead-code removal, CORS allow-list.

---

## 5. Uncovered Limits

This audit is static and source-driven. The following were **not** performed and could change the conclusions:

- No dynamic penetration testing, fuzzing, or live exploitation against a running instance.
- No dependency vulnerability scan (`pip-audit`, Trivy, OSV) or container image scan.
- No frontend production build, CSP review, or browser-based XSS testing.
- No live Telegram bot testing (token validation, chat permissions, message retention).
- No cloud/IAM/network review beyond the provided Compose file.
- No load testing to quantify the CV-upload or ingestion DoS impact.
- No review of the legacy `src/` tree beyond confirming it is deprecated and not on the active import path.

**Bottom line:** fix H-01 and H-02 before exposing this deployment to more than one trusted user. The remaining items are defense-in-depth and operational hygiene, with M-04 being the most important correctness gap for anyone relying on the pause control.
