# Task Sniffer --- Implementation Plan

**Project:** Task Sniffer / Work-Bot Hunter\
**Target repository:** `/home/retro/Projects/web/Task_Sniffer`\
**Plan status:** Proposed --- verify findings against the current
checkout before implementation\
**Mode:** Staged implementation with tests, review gates, and no
unapproved production changes

------------------------------------------------------------------------

## 1. Purpose

Turn the read-only codebase audit into a controlled implementation
sequence that improves security, ingestion reliability, Kenyan-market
risk detection, salary matching, Telegram notifications, and source
coverage without destabilizing working functionality.

This document is a plan, not evidence that the reported defects have
been independently verified or fixed. The implementation agent must
inspect the current code and tests before changing anything.

## 2. Operating rules

1.  Work from the repository's actual current state. Do not assume every
    audit claim is correct.
2.  Begin each phase with a short, targeted inspection of the relevant
    code, schemas, callers, configuration, and tests.
3.  Make the smallest change set that resolves the verified issue.
4.  Add regression tests before or alongside each fix.
5.  Run focused tests, then the full test suite where practical. Report
    existing failures separately.
6.  Do not deploy, alter production data, run destructive migrations,
    rotate credentials, or change production configuration without
    explicit authorization.
7.  Never print secrets, bot tokens, passwords, signing keys, or full
    environment files in reports or logs.
8.  Do not make external network requests during a read-only audit
    unless explicitly authorized. Tests for remote integrations should
    use mocks or fixtures.
9.  Keep the `backend/` application as the primary implementation unless
    repository evidence shows otherwise. Do not remove `src/` until all
    imports, scripts, tests, and operational entry points have been
    traced.
10. Do not add a new dependency or AI model unless the need is
    demonstrated and approved.
11. Every new outbound URL fetch must use the existing centralized URL
    safety policy, including redirects and any discovered
    canonical/application URLs.
12. Treat the Phase 2 DNS fail-open and DNS rebinding/TOCTOU concerns as
    unresolved until code and tests prove otherwise.

## 3. Phase overview

  -------------------------------------------------------------------------------
  Phase            Focus                         Priority Gate to proceed
  ---------------- ---------------- --------------------- -----------------------
  0                Baseline                     Mandatory Current state, tests,
                   verification and                       config, and DB targets
                   backup                                 identified

  1                Authentication                      P0 Protected routes reject
                   and                                    invalid/expired tokens
                   exposed-route                          
                   security                               

  2                Ingestion                           P0 No active source is
                   registry and ATS                       unconfigured;
                   configuration                          configured boards
                                                          produce validated
                                                          records in
                                                          fixtures/tests

  3                Telegram alert                      P0 Repeated scheduler runs
                   deduplication                          do not resend the same
                   and links                              user/job alert

  4                Telegram                            P1 `/apply` uses a real
                   application                            candidate identity and
                   identity / FK                          persists validly
                   integrity                              

  5                Risk engine:                        P1 Aggregator/ATS listings
                   domains and                            do not receive false
                   company identity                       mismatch flags

  6                Risk engine:                        P1 Currency/period-aware
                   Kenya-aware                            rules and contextual
                   compensation and                       scam tests pass
                   fraud signals                          

  7                Matching engine:                    P1 Salary fields,
                   salary and                             currencies, periods,
                   location                               and Kenyan
                                                          remote/location rules
                                                          are consistent

  8                Small                               P2 Type-hint and
                   maintenance                            shell-script
                   fixes                                  regressions fixed

  9                Source expansion                    P2 Each new source has a
                                                          verified access method,
                                                          tests, provenance, and
                                                          monitoring

  10               Legacy tree                         P3 No active imports
                   cleanup and                            depend on removed
                   release                                legacy code; release
                   verification                           checklist passes
  -------------------------------------------------------------------------------

**Recommended execution order:** Phase 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8
→ 9 → 10.\
Do not bundle unrelated phases into a single large refactor.

------------------------------------------------------------------------

## 4. Phase 0 --- Baseline verification

### Objectives

-   Confirm the audit applies to the current checkout.
-   Identify the correct test command, runtime entry point, database
    configuration, and migration approach.
-   Establish a baseline before edits.

### Tasks

-   Inspect `git status`, recent commits, and the diff; do not discard
    user changes.
-   Locate the actual FastAPI application object and startup command.
-   Identify test configuration and run the current test suite.
-   Determine how database URLs are selected in development, test, and
    production.
-   Inspect ORM models and migration tooling before proposing schema
    changes.
-   Confirm whether production-like database claims refer to a local
    SQLite file, a test database, or a live database.
-   Verify current URL safety behavior and document DNS fail-open /
    rebinding status.
-   Check whether any secrets have been committed or exposed in logs. Do
    not reproduce them.

### Deliverables

-   Baseline report: current commit, dirty files, test results, entry
    point, database targets, and confirmed findings.
-   Per-phase file list and risk assessment.

### Gate

No implementation until the baseline is recorded and any user changes
are protected.

------------------------------------------------------------------------

## 5. Phase 1 --- Authentication and route security (P0)

### Audit targets

-   `backend/api/deps.py`
-   `backend/security/`
-   API routers and dependencies
-   User ORM model and token configuration
-   Authentication tests

### Tasks

1.  Trace every route using `get_current_user` and determine whether it
    is externally reachable or protected by another verified layer.
2.  Confirm the token format, signing algorithm, secret/key
    configuration, expiry claim, and user identifier claim expected by
    `decode_access_token`.
3.  Replace placeholder identity behavior with actual signature and
    expiry verification using existing security utilities.
4.  Load the real user from the database and reject missing, malformed,
    expired, invalid-signature, or unknown-user tokens with appropriate
    `401` responses.
5.  Return `403` where a valid identity lacks authorization, if
    role/permission checks exist.
6.  Fail safely when required auth configuration is missing; never
    silently fall back to placeholder authentication.
7.  Ensure logs do not contain bearer tokens or sensitive claims.
8.  Add tests for valid tokens, tampered tokens, expired tokens, missing
    tokens, unknown users, missing configuration, and route protection.

### Acceptance criteria

-   Invalid and expired bearer tokens cannot access protected routes.
-   Valid tokens resolve to the correct database user.
-   No production path accepts a fixed placeholder user identity.
-   Existing public endpoints remain public only when intentionally
    configured.
-   Authentication and authorization behavior is covered by automated
    tests.

### Gate

Do not deploy while any production-protected route accepts arbitrary
bearer tokens or placeholder identities.

------------------------------------------------------------------------

## 6. Phase 2 --- Ingestion registry and ATS configuration (P0)

### A. CareerPoint Kenya registration mismatch

Inspect: - `backend/sources/registry.py` -
`backend/scrapers/factory.py` - `backend/scrapers/adapters/` -
`backend/services/ingestion.py` - source registry/factory tests

Tasks: 1. Confirm whether `careerpointkenya` is active and approved but
lacks an adapter or explicit legacy policy. 2. If no safe, tested
adapter exists, disable the source and mark it for review rather than
repeatedly generating ingestion errors. 3. Implement an adapter only
after verifying the source's permitted access method, allowed domains,
pagination/sitemap behavior, and individual job URL patterns. 4. Ensure
adapter output passes centralized URL safety, redirect validation,
job-page validation, and persistence gates. 5. Add a test asserting that
every active crawlable source can build an adapter or has an explicit
supported configuration.

### B. Greenhouse and Ashby board configuration

Tasks: 1. Confirm that the adapter expects board identifiers and that
`extra_urls` is the intended configuration field. 2. Verify each
proposed employer board identifier against a fixture or mocked public
response; do not assume names are valid board IDs. 3. Prefer a
maintainable configuration source over embedding an arbitrary list
directly in factory logic. 4. Add tests for an empty board list, valid
board list, invalid board identifier, API error, and zero-result
response. 5. Record per-board success, failures, and jobs found so "zero
jobs" is diagnosable.

### Acceptance criteria

-   No active crawlable source repeatedly fails because it has no
    adapter/policy.
-   Greenhouse/Ashby configuration is explicit, testable, and does not
    treat search pages as individual job records.
-   Existing validation and SSRF protections remain in the path.
-   Tests cover registry/factory consistency and zero-result reporting.

------------------------------------------------------------------------

## 7. Phase 3 --- Telegram alert deduplication and job links (P0)

### Audit targets

-   `backend/telegram/notify.py`
-   Telegram user and alert models
-   Scheduler/Celery configuration
-   Database migration conventions
-   Telegram tests

### Tasks

1.  Confirm the alert cadence and whether multiple workers or
    overlapping scheduled runs are possible.
2.  Add durable per-user/per-job delivery tracking, preferably a
    dedicated table with:
    -   Telegram user foreign key
    -   job foreign key
    -   sent/delivery status
    -   timestamp
    -   unique constraint on `(telegram_user_id, job_id)` (or an
        equivalent idempotency key)
3.  Check existing delivery records before sending an alert.
4.  Make concurrent sends safe using a transaction/unique constraint or
    an equivalent idempotency strategy.
5.  Decide how to handle failed sends: do not mark as delivered before
    the send succeeds; prevent endless retries and record retryable
    failures safely.
6.  Include a safe clickable job URL, preferring a verified application
    URL, then a verified canonical/detail URL. Never fabricate a URL.
7.  Escape or safely format untrusted job/company text for Telegram's
    selected parse mode.
8.  Keep messages within Telegram length limits and provide a useful
    fallback when no valid URL exists.
9.  Test repeated runs, concurrent runs, failed delivery, missing URLs,
    formatting edge cases, and multiple users.

### Acceptance criteria

-   A successful user/job alert is not resent on every scheduler cycle.
-   Different users can each receive the same job once.
-   Failed sends can be retried according to a documented policy.
-   Every alert includes a verified usable link when one exists.
-   No live Telegram message is sent by tests.

------------------------------------------------------------------------

## 8. Phase 4 --- Telegram `/apply` candidate identity and foreign keys (P1)

### Audit targets

-   `backend/telegram/handlers.py`
-   `TelegramUser`, `Candidate`, and `Application` models
-   Web account linking/authentication flow
-   ORM relationships and migrations

### Tasks

1.  Verify the actual foreign-key relationships and reproduce the
    reported ID mismatch in a test database.
2.  Define an explicit identity-linking strategy between Telegram users
    and candidate profiles.
3.  Prefer a nullable `candidate_id` foreign key on `TelegramUser` or an
    existing account-linking mechanism if it fits the current schema.
4.  Do not assume Telegram numeric IDs equal database candidate IDs.
5.  Do not silently create duplicate candidate profiles or link accounts
    by unverified email/phone.
6.  If no verified candidate link exists, explain the linking/onboarding
    step and do not create an invalid `Application`.
7.  Add tests for linked user, unlinked user, nonexistent job, duplicate
    application, and FK integrity.

### Acceptance criteria

-   `/apply` never assigns a Telegram-user primary key to
    `Application.candidate_id`.
-   Applications are visible to the correct candidate in the web
    dashboard.
-   Linking cannot attach an application to another user's candidate
    profile.

------------------------------------------------------------------------

## 9. Phase 5 --- Risk engine domain and company-identity calibration (P1)

### Audit targets

-   `backend/risk/engine.py`
-   Source registry / source provenance metadata
-   Risk engine tests and scoring thresholds

### Tasks

1.  Separate source-host trust from employer identity verification. A
    trusted aggregator is not proof that an individual vacancy or
    employer is legitimate.
2.  Add verified domains for supported Kenyan sources and government
    portals only after confirming the exact hostnames and ownership.
3.  Use exact-host or carefully implemented subdomain matching; avoid
    unsafe string suffix checks that could accept lookalike domains.
4.  Treat ATS and aggregator hosts as distribution platforms. Do not
    require the employer name to match the ATS hostname.
5.  Where possible, compare the declared employer against employer
    metadata and the actual destination, while preserving a review state
    when evidence is insufficient.
6.  Keep source reputation as one signal, not a guarantee that a job is
    safe.
7.  Add tests for legitimate employer listings on aggregators, direct
    company domains, lookalike domains, unknown domains, subdomains, and
    missing company names.

### Acceptance criteria

-   Legitimate jobs posted through known aggregators/ATS platforms do
    not receive a company-domain mismatch flag solely because the host
    differs from the employer.
-   Lookalike domains are not trusted.
-   Trust reduces only the appropriate risk signals; it does not bypass
    other scam checks.

------------------------------------------------------------------------

## 10. Phase 6 --- Kenya-aware salary risk and fraud signals (P1)

### A. Compensation checks

Tasks: 1. Inspect the salary schema and parser output: currency,
minimum, maximum, and period (hourly, monthly, annual, contract, or
unknown). 2. Do not compare raw values to USD thresholds unless currency
and period are known. 3. Define configurable thresholds by currency and
salary period, based on documented assumptions and conservative bounds.
4. Normalize annual/monthly/hourly values only when conversion
assumptions are valid; otherwise mark the check as inconclusive. 5. Use
the salary currency field only when it is trustworthy. Do not infer KES
solely because a listing appears on a Kenyan website. 6. Avoid emitting
a dollar sign or USD description for an amount whose currency is unknown
or KES. 7. Test KES monthly salaries, KES annual salaries, USD annual
salaries, unknown currency, negotiable salary, ranges, and malformed
salary strings.

### B. Kenya-specific scam indicators

Potential signals include application/interview/registration fees,
requests to pay for medical certificates or uniforms, and suspicious
mobile-money payment instructions.

Tasks: 1. Add these as contextual signals, not unconditional keyword
bans. 2. Distinguish a request for the candidate to pay money from
neutral discussion of M-Pesa or fees in unrelated context. 3. Treat
requests for application or recruitment fees as high-risk evidence; do
not assume every occurrence of a payment-related word proves fraud. 4.
Government-source claims require verified provenance. A fee demand on an
official-looking but unverified domain must not be treated as verified
government fraud evidence without checking the domain. 5. Do not
automatically assign risk score 100 solely because a payment-related
term and `.go.ke` appear. Require explicit evidence of a candidate
payment demand and reliable source context. 6. Keep risk explanations
evidence-based and expose the matched text/context for audit. 7. Test
true positives, benign mentions, quoted warnings about scams, negation,
government impersonation, and lookalike domains.

### Acceptance criteria

-   Normal Kenyan salary ranges are not flagged as USD astronomical
    salaries.
-   Risk findings identify the evidence that triggered the rule.
-   Benign mentions of M-Pesa or medical examinations do not
    automatically block a job.
-   High-risk payment requests increase risk appropriately without
    bypassing the overall scoring policy.

------------------------------------------------------------------------

## 11. Phase 7 --- Matching engine salary and location consistency (P1)

### A. Salary schema and currency

Tasks: 1. Inspect the actual types and structures accepted by
`_salary_filter`; determine whether callers pass ORM objects or
dictionaries. 2. Support the actual `salary_min`, `salary_max`,
`salary_currency`, and `salary_period` fields without relying
exclusively on a free-text `salary` field. 3. Normalize candidate and
job salary periods before comparison when enough data exists. 4. Use a
configured exchange-rate provider or timestamped configurable rates with
a known update policy. Do not hardcode illustrative exchange rates as
permanent facts. 5. If currency or period is unknown, use a
neutral/unknown score or documented fallback rather than comparing
incompatible raw values. 6. Preserve existing score semantics unless a
change is explicitly tested and documented. 7. Test KES candidate
preferences versus USD jobs, monthly versus annual salaries, missing
salary, salary ranges, and unknown currency.

### B. Kenya location normalization

Tasks: 1. Add normalized location data for Kenyan counties and selected
cities/sub-counties only where useful and maintainable. 2. Distinguish
county-level, city/neighborhood-level, and country-wide remote
eligibility. 3. Treat "remote within Kenya" as compatible with
candidates in Kenya, but not as a match for every worldwide remote
restriction. 4. Preserve location eligibility language such as "must
reside in the US," "Africa only," or "Kenya residents only." 5. Avoid
broad substring matching that equates unrelated locations. 6. Test
Nairobi neighborhoods, Mombasa, Kisumu, Nakuru, Eldoret, country-wide
remote, worldwide remote, and explicitly restricted remote jobs.

### Acceptance criteria

-   Salary comparisons do not compare incompatible currencies or periods
    as if they were the same unit.
-   Matching handles structured salary fields correctly.
-   Location matches reflect actual geographic and remote-work
    eligibility.

------------------------------------------------------------------------

## 12. Phase 8 --- Small maintenance fixes (P2)

### A. `Optional` import

-   Inspect `backend/parsers/__init__.py` and project
    Python-version/type-annotation conventions.
-   Add the missing import or use the project's consistent
    future-annotations approach.
-   Test `typing.get_type_hints(parse_salary_range)` and existing parser
    behavior.

### B. `bot.sh`

-   Inspect the script, virtual environment name, process management
    approach, and actual start/stop commands.
-   Resolve the repository root relative to the script file rather than
    a stale absolute path.
-   Do not assume the environment directory is named `venv`; verify the
    repository's actual environment convention.
-   Quote paths and use safe process handling.
-   Test path resolution without stopping or starting a production
    process.

### Acceptance criteria

-   Type-hint introspection succeeds.
-   Script paths work when launched from another working directory.
-   No unintended process is killed or started during verification.

------------------------------------------------------------------------

## 13. Phase 9 --- Source expansion (P2, after stability work)

### Candidate integrations

Prioritize based on access reliability, relevant unique-job yield, and
maintenance cost: - Remotive public API - We Work Remotely RSS - Remote
OK public feed/API, subject to current terms and format - Workable
public job boards - SmartRecruiters public posting API - BambooHR /
Recruitee public boards where permitted - Official Kenyan public-sector
portals such as TSC and MyGov - UN careers sources where an authorized,
stable access method exists - LinkedIn only through permitted,
authorized access; do not bypass login, access controls, or anti-bot
measures

### Per-source checklist

1.  Verify current terms, robots/access rules, and API/feed
    documentation.
2.  Record access method, allowed hostnames, rate limits, attribution
    needs, and source provenance.
3.  Build or configure an isolated adapter with explicit host policy and
    timeouts.
4.  Validate every discovered job URL through the centralized safety
    policy, including redirects.
5.  Preserve source IDs and identity-bearing query parameters where
    required.
6.  Extract detail, canonical, and application URLs separately; do not
    invent application links.
7.  Test pagination, duplicates, malformed entries, closed listings,
    empty responses, and remote/location eligibility.
8.  Measure unique valid jobs, relevance, freshness, application-link
    validity, failure rate, and runtime.
9.  Disable a source safely when configuration is missing or errors
    exceed a threshold.
10. Avoid enabling sources solely because they appear in a suggested
    list.

### LinkedIn note

Treat LinkedIn as a separate access/permissions decision. Do not build
or enable a scraper that bypasses login, anti-bot controls, rate limits,
or contractual restrictions. A source registry entry alone does not mean
the source is technically or legally available for ingestion.

### Acceptance criteria

-   Each source has an explicit access method and policy.
-   New sources do not bypass SSRF protections or validation gates.
-   Source value is measured by valid, unique, relevant jobs rather than
    raw count.

------------------------------------------------------------------------

## 14. Phase 10 --- Legacy tree cleanup and release verification (P3)

### Legacy cleanup

1.  Search for all imports from `src/`, including scripts, tests, CI
    configuration, docs, and cron/scheduler entry points.
2.  Identify whether `test_pipeline.py` is still used by developers or
    automation.
3.  Migrate remaining diagnostic utilities only after parity tests
    exist.
4.  Archive or remove `src/` only after a separate review and explicit
    approval.
5.  Do not combine deletion of legacy code with unrelated behavior
    changes.

### Security and release verification

-   Confirm JWT validation and route authorization tests pass.
-   Confirm DNS failures fail closed for outbound URL fetches.
-   Review DNS rebinding/TOCTOU mitigation; pin validated IPs while
    preserving TLS hostname verification, or use a suitable secure
    egress layer. If not fully mitigated, document the residual risk and
    explicitly block release or obtain informed risk acceptance.
-   Confirm every redirect hop and any canonical/application URL fetch
    uses the same outbound safety policy.
-   Confirm active sources have valid adapters/policies.
-   Confirm alert delivery is idempotent.
-   Confirm no credentials appear in source, logs, or test artifacts.
-   Confirm database migrations are reversible and tested against a
    disposable database.
-   Run focused tests, full test suite, static checks configured by the
    project, and a manual smoke test in a non-production environment.
-   Verify frontend root route separately from API health endpoints if
    the UI still returns `404`.
-   Do not deploy or alter production databases without explicit
    authorization.

### Release gate

Release only when all P0 issues are resolved, tests pass, migrations are
reviewed, and residual security risks have been addressed or explicitly
accepted by the responsible owner.

------------------------------------------------------------------------

## 15. Suggested issue tracker structure

Create one issue per bounded task rather than a single mega-task:

-   `TS-001` Baseline verification and confirmed-findings report
-   `TS-002` Replace placeholder API authentication
-   `TS-003` Reconcile active source registry and adapter factory
-   `TS-004` Configure and test Greenhouse/Ashby boards
-   `TS-005` Add idempotent Telegram alert delivery tracking
-   `TS-006` Include verified job URLs in Telegram alerts
-   `TS-007` Repair Telegram-to-candidate identity mapping
-   `TS-008` Separate source-host trust from employer identity checks
-   `TS-009` Make compensation risk rules currency/period aware
-   `TS-010` Add contextual Kenya-specific scam signals
-   `TS-011` Repair matching salary schema and currency handling
-   `TS-012` Normalize Kenya location and remote eligibility
-   `TS-013` Fix parser type hints and `bot.sh` path handling
-   `TS-014` Add and evaluate new source integrations
-   `TS-015` Audit legacy `src/` dependencies and plan cleanup
-   `TS-016` Final security/release readiness review

Each issue should include scope, files inspected, tests, acceptance
criteria, and explicit non-goals.

------------------------------------------------------------------------

## 16. Implementation-agent prompt

Use the following instruction when handing the plan to Cursor/Codex:

> Read `IMPLEMENTATION_PLAN.md` completely. First perform Phase 0 only
> in read-only mode. Verify each audit claim against the current
> repository and report evidence, relevant files, tests, dependencies,
> and risks. Do not edit files, install packages, modify databases,
> change environment variables, contact external services, or deploy.
> After presenting the baseline report, stop and wait for approval. Once
> approved, implement one phase at a time in the stated order, with
> focused tests and a concise change report after each phase. Preserve
> unrelated user changes and do not proceed to the next phase until its
> acceptance criteria are met. Never expose secrets. Production changes
> require separate explicit authorization.

------------------------------------------------------------------------

## 17. Definition of done

Task Sniffer is ready for a controlled release when: - Protected routes
validate real identities and authorization. - All active ingestion
sources have valid adapters/policies and measurable outcomes. - Job
identity and application URLs remain distinct and validated. - Telegram
notifications are idempotent and actionable. - Telegram applications map
to real candidate profiles. - Risk rules account for currency, salary
period, source provenance, and contextual evidence. - Matching uses
structured salary data and compatible currency/periods. - Kenya location
and remote eligibility are normalized conservatively. - New sources are
permitted, tested, monitored, and evaluated for unique relevant yield. -
DNS/SSRF residual risks are mitigated or explicitly accepted. -
Regression tests and release checks pass. - No production data changes
or deployment occur without authorization.
