# TASK SNIFFER — PHASE 1: URL IDENTITY AND REGRESSION TESTS

## Objective

Begin fixing the confirmed URL correctness defects identified in the completed forensic audit.

Work exclusively on URL normalization, job identity extraction, URL classification, and regression tests for these behaviors.

Do not attempt a complete scraper rewrite.

## Step 1 — Establish the baseline

Inspect the current implementations and existing tests for:

- `backend/services/normalizer.py`
- `backend/sources/urls.py`
- `backend/scrapers/factory.py`
- Existing URL normalization and source-adapter tests

Confirm the current behavior of `JobNormalizer._normalize_url`, `_extract_source_job_id`, `classify_url`, and `identify_job_url`.

Run the relevant existing tests before editing. Record any pre-existing failures.

## Step 2 — Write regression tests first

Add tests covering the following cases.

### A. Query-based job identity

Test URLs such as:

- `https://stripe.com/jobs/search?gh_jid=7993151`
- `https://www.fuzu.com/kenya/jobs/x?job_id=42`

Requirements:

- Never silently discard a parameter that is required to identify the job.
- Extract `7993151` and `42` as identifiers when the corresponding source configuration establishes their meaning.
- Never infer the job ID from a generic path segment such as `search` or `jobs` when a valid source-specific identifier is available.
- Do not assume every query parameter is an identity parameter.
- Preserve existing correct behavior for ordinary slug-based job URLs.

Important: preserving a query parameter does not establish that the URL is a valid job-detail page. Classification and validation remain separate responsibilities.

### B. ATS URL classification

Add parametrized tests for known valid patterns:

- Ashby: `https://jobs.ashbyhq.com/openai/abc-123`
- Workable: `https://apply.workable.com/acme/j/ABC123/`
- Remotive: `https://remotive.com/remote-jobs/software-dev/some-role-123`

Also test rejection of obvious non-detail pages:

- Search results
- Company profile pages
- Careers landing pages without a job identifier
- Category and pagination pages

Do not reject a valid job solely because its path doesn't contain the generic words `job`, `jobs`, or `careers`.

Use explicit, source-aware patterns where appropriate. Do not solve false negatives by accepting every URL.

### C. Normalization stability

Test that applying the intended normalization process twice produces the same result.

Verify:

- Fragments are handled consistently.
- Tracking parameters are removed only according to explicit policy.
- Job identity parameters survive.
- URL schemes and hosts are normalized safely.
- Distinct jobs do not collapse into the same normalized URL.

### D. Greenhouse regression

Add a regression test for:

`https://stripe.com/jobs/search?gh_jid=7993151`

Confirm that its query-based identifier is preserved, while the URL is not automatically accepted as a valid job-detail page just because it contains `gh_jid`.

Do not implement the full Greenhouse repair in this phase.

## Step 3 — Implement the smallest necessary fixes

After the tests demonstrate the failures:

- Remove destructive blanket query-string stripping from the normalizer.
- Introduce source-aware job identifier extraction where necessary.
- Correct ATS classification using explicit patterns.
- Preserve existing interfaces unless a change is demonstrably necessary.
- Keep normalization, classification, page validation, and persistence gating as separate responsibilities.

Do not hardcode assumptions about one source into a shared normalizer if they would break other sources.

## Constraints

- Do not modify the database schema.
- Do not alter ingestion persistence behavior yet.
- Do not change application URL extraction yet.
- Do not introduce new scraping sources.
- Do not install dependencies.
- Do not rewrite adapters unrelated to these tests.
- Do not delete or overwrite database records.
- Do not weaken existing security or domain validation.
- Inspect the repository's actual implementation before deciding how to make changes.

## Verification

Run the focused tests, followed by the relevant existing test suite.

Report:

1. Confirmed baseline failures.
2. Files modified.
3. Tests added.
4. Tests passing and failing.
5. Any compatibility concerns.
6. Remaining known URL pipeline defects.
7. Exact commands used to run tests.

Do not claim a test passed unless it was actually executed.

Finish with a concise summary of the changes. Do not proceed to Phase 2 without a separate review.

# TASK SNIFFER — PHASE 2: VALIDATION GATING AND REDIRECT ENFORCEMENT

## Objective

Implement Phase 2 of the scraper reliability improvements.

Phase 1 addressed URL identity and classification. This phase ensures that fetched candidates are validated correctly and that invalid or suspicious pages cannot enter normal job storage.

The primary production path is:

`run.py` → `backend.api.app:app` → `POST /sources/{name}/ingest` or Celery `scrape_all_sources` → `backend.services.ingestion.IngestionEngine`.

Trace the actual current implementation before editing.

## Scope

Focus on:

- `backend/services/ingestion.py`
- `backend/sources/urls.py`
- `backend/scrapers/adapter.py` or the actual adapter module
- Relevant existing tests
- Quarantine/review support only if an existing mechanism can safely be reused

Do not implement Phase 3 application URL extraction or undertake a general scraper rewrite.

## 1. Make validation a persistence gate

Inspect `_process_listing`, `_fetch_and_validate`, and `_persist_job`.

Currently, validation results are reportedly informational and invalid candidates can still be persisted.

Change the flow so that:

- A candidate is fetched and validated before normal persistence.
- Only candidates meeting the established acceptance policy can enter normal job storage.
- An invalid candidate cannot create a new normal job record.
- An invalid candidate cannot overwrite a previously valid record.
- Existing valid records remain available when a subsequent fetch fails.
- Validation failures are observable through structured logs or existing ingestion result reporting.

Do not merely set `url_status` and continue persisting the job as normal.

### Handling uncertain outcomes

Do not treat every validation failure as proof that a job is invalid.

Distinguish at least:

- `VALID`: sufficient evidence that the destination is a job-detail page.
- `INVALID`: affirmative evidence that the destination is not an acceptable job page.
- `UNKNOWN`: insufficient evidence to make a safe determination.

Examples:

- A confirmed search page is invalid as a job-detail destination.
- A confirmed removed job is invalid for new active-job ingestion.
- A network timeout is unknown, not proof that the job is invalid.
- An HTTP 403 or 429 is not, by itself, proof that the URL is wrong.
- An inconclusive anti-bot response is unknown.
- A generic HTTP 200 is not sufficient evidence of a valid job.

Adapt these categories to the repository's existing enums and schema where possible. Do not make unnecessary schema changes.

## 2. Enforce redirect policy

Inspect existing HTTP client configuration and redirect handling.

Implement or reuse a bounded redirect-resolution mechanism. Preserve:

- Original discovered URL
- Final response URL
- Redirect chain, if supported by the existing model or ingestion result

After redirects:

1. Reclassify the final URL.
2. Check the final destination against the source's configured domain policy.
3. Detect redirects to search pages, homepages, login pages, unrelated destinations, and known interstitials.
4. Reject unsafe or clearly unrelated destinations.
5. Treat uncertain redirect outcomes as `UNKNOWN`.

Do not assume all cross-domain redirects are invalid. Some sources legitimately send applicants to external ATS providers. Distinguish a job-detail fetch redirect from a separate application link, and use explicit, source-aware domain policies.

Prevent redirect loops and excessive hop counts. Respect existing HTTP client timeout and resource limits.

Do not introduce unrestricted crawling or fetch arbitrary URLs without checking the existing SSRF protections. Reject unsupported schemes and unsafe destinations, including loopback, private, link-local, and other prohibited IP ranges where applicable. Consider DNS rebinding and redirects when enforcing network-address restrictions.

## 3. Validate HTTP responses and page content

Inspect response status, content type, and available page evidence.

Implement proportionate checks for:

- HTTP response status
- HTML content type for HTML job-detail pages
- Empty or malformed responses
- Search, category, homepage, and company-profile pages
- Login and signup pages
- Captcha and anti-bot interstitials
- Expired or removed jobs
- Relevant job-detail evidence, using source-specific rules where possible

Do not require every legitimate job page to contain every signal.

Prefer multiple independent signals, such as:

- Expected source-specific URL pattern
- Job title and employer evidence
- JobPosting structured data
- Recognizable job-detail page structure
- Explicit removed/expired indicators

Do not mistake a transient server error or anti-bot response for definitive evidence that a job no longer exists.

Do not bypass CAPTCHAs, authentication, access controls, or anti-bot protections. Mark inconclusive responses as `UNKNOWN` and report them appropriately.

## 4. Domain policy and legacy adapters

Audit how `_LegacyAdapter` and the source factory supply `allowed_domains` and `job_url_patterns`.

Do not silently fall back to the candidate's own hostname and treat it as trusted.

For sources without a trustworthy domain or URL policy:

- Fail closed for acceptance into normal storage, or
- Return `UNKNOWN` and skip normal persistence until the source configuration is corrected.

Do not break unrelated, currently supported adapters. Add explicit source configuration only when supported by repository evidence.

Do not indiscriminately reject legitimate third-party ATS job pages.

## 5. Preserve existing valid data

Review the same-source and cross-source update paths in `_persist_job`.

Ensure an invalid or unknown candidate cannot overwrite a previously validated canonical/final URL or otherwise downgrade a valid record.

Do not delete records, bulk-edit databases, or run migrations unless they are strictly required and separately justified.

Preserve current deduplication and transaction semantics unless a change is necessary for validation safety.

## 6. Tests required before completion

Write or update tests for at least:

1. A valid job-detail page is eligible for normal persistence.
2. A confirmed search page is not persisted as a job.
3. A company homepage or careers landing page is not persisted as a job.
4. A 404 response is rejected for new active-job ingestion.
5. A 403 or 429 is classified as inconclusive unless source-specific evidence proves otherwise.
6. A `text/plain` error response is not accepted as an HTML job page.
7. A Cloudflare/CAPTCHA-style interstitial returning HTTP 200 is not accepted as a valid job.
8. An off-policy redirect is rejected or marked unknown according to the evidence and configured policy.
9. A legitimate external ATS destination is handled according to explicit source configuration.
10. A redirect loop or excessive redirect chain is bounded safely.
11. A timeout does not mark an existing valid job as expired or overwrite its valid URL.
12. Invalid and unknown candidates cannot overwrite existing valid records.
13. Missing source configuration cannot silently disable domain validation.
14. SSRF safeguards remain effective for redirects and destination resolution.

Use mocked HTTP responses for deterministic offline tests. Avoid depending on live external websites.

## 7. Verification

Run the focused validation and ingestion tests, followed by the relevant existing test suite.

Inspect both the direct ingestion API path and the Celery ingestion path to verify that they use the same enforced validation rules.

Report:

- Files changed
- Validation policy implemented
- Redirect policy implemented
- Test commands and actual results
- Any regressions or unresolved failures
- How unknown candidates are handled
- Whether quarantine is implemented or candidates are safely skipped
- Remaining work for Phase 3

## Constraints

- Do not implement application URL extraction in this phase.
- Do not perform a historical database cleanup.
- Do not add new job sources.
- Do not disable existing security controls.
- Do not claim success without running tests.
- Keep changes limited to validation, redirect enforcement, and persistence safety.

Complete Phase 2 and stop for review. Do not begin Phase 3 automatically.



# Task Sniffer — Phase 3: URL Extraction and Identity Resolution

You are working in the existing Task Sniffer / Work-Bot Hunter repository. Implement Phase 3 only.

## Objective

Correctly identify and store each job's:
- Job detail URL
- Canonical URL
- Application URL
- Source job ID

These are distinct concepts. A URL that identifies a job posting must not automatically be treated as a verified application URL.

Phase 1 fixed URL normalization and query-based job identity. Phase 2 introduced validation gating and redirect enforcement. Preserve both implementations and all existing passing tests.

## Before Implementation

1. Inspect the current Git diff and the implementations of:
   - `backend/services/normalizer.py`
   - `backend/sources/urls.py`
   - `backend/services/ingestion.py`
   - `backend/scrapers/adapter.py`
   - `ListingItem`, `JobNormalizer`, `JobDeduplicator`, and relevant job models/schemas.
2. Locate `find_explicit_apply_url`, `apply_hint`, `application_url`, `original_url`, and `canonicalize_url`.
3. Trace the actual ingestion flow from listing discovery through fetching, normalization, validation, persistence, and deduplication.
4. Confirm which URL fields are already available in the database. Do not assume the schema from field names alone.

Do not start by rewriting the scraper or normalizer.

## 1. Establish URL semantics

Use these definitions consistently:

- `detail_url`: The actual page for one specific job posting.
- `canonical_url`: The normalized, preferred identity URL for that posting, when one can be reliably established.
- `application_url`: The destination explicitly intended for applying to the job.
- `source_job_id`: The source's stable identifier, when available.
- `original_url`: The originally discovered URL, retained according to existing model semantics.

Inspect the existing model before choosing field names or adding fields. Reuse existing fields where appropriate. Do not introduce redundant columns.

Never:
- Use a search, category, company-careers, or homepage URL as a job detail URL.
- Treat a URL as an application URL merely because it returns HTTP 200.
- Replace a valid application URL with the detail URL during an unsuccessful extraction.
- Strip query parameters that identify a job.
- blindly trust canonical tags or JSON-LD URLs without validating them.

## 2. Implement explicit application URL extraction

Activate and integrate the existing `find_explicit_apply_url` and `ListingItem.apply_hint` mechanisms where appropriate.

Extract application links from:
- Explicit apply buttons and anchors.
- Relevant link attributes and application forms.
- Source adapter metadata.
- JSON-LD or structured metadata when it explicitly provides a relevant application destination.

Resolve relative URLs against the correct response/page URL.

Rank evidence by reliability. Prefer a validated, explicit application destination over an inferred link. Reject obvious navigation, login, search, unrelated company pages, and unsafe URLs.

If no trustworthy application URL is found:
- Store `NULL` or preserve the existing value according to the current data model and update semantics.
- Do not fabricate a verified application URL.
- Do not overwrite a previously valid URL with a weaker fallback.

Support external ATS application destinations when the source configuration explicitly permits them. Do not assume the application host must always match the listing host.

## 3. Canonical URL and JSON-LD extraction

Implement extraction for:
- `link[rel="canonical"]`
- JSON-LD `JobPosting.url`
- JSON-LD application-related fields only where their meaning is explicit and reliable.

Handle:
- Relative and absolute URLs.
- Multiple canonical tags.
- Malformed JSON-LD.
- Multiple JSON-LD objects and arrays.
- Missing fields and malformed markup.
- Tracking parameters versus job-identity parameters.
- Canonical URLs pointing to a search page, homepage, unrelated job, or disallowed host.

Canonical and JSON-LD values are evidence, not automatically trusted truth. Validate candidates with the existing URL policy and identity checks.

When extracted values conflict, use a documented precedence policy and record why a candidate was selected or rejected.

Do not allow a canonical tag to override a trustworthy source-specific job ID with an unrelated identity.

## 4. Correct URL identity handling

Preserve Phase 1 behavior:
- Retain query parameters required for job identity, including ATS-specific identifiers such as `gh_jid`.
- Remove tracking parameters only through an explicit, tested policy.
- Avoid generic path segments such as `search`, `jobs`, and `careers` becoming source job IDs.
- Ensure identity extraction is deterministic.
- Avoid deriving unstable IDs from mutable job titles if a stable URL or source identifier is available.

Keep the source job ID, canonical URL, and application URL separate. A query-based ATS job ID must not cause a search URL to be accepted as a job-detail URL.

## 5. Integrate with Phase 2 validation and persistence

All extracted URLs must pass the applicable safety, domain, and destination validation rules from Phase 2.

- Do not bypass validation because a URL came from JSON-LD or a canonical tag.
- Do not fetch untrusted destinations before applying the existing SSRF safeguards.
- Do not persist non-VALID job candidates as normal records.
- Do not let `INVALID` or `NEEDS_REVIEW` candidates overwrite previously valid records.
- Do not deactivate an existing job because application URL extraction failed.
- Keep API and Celery ingestion behavior consistent.

Preserve existing transaction and deduplication semantics unless a specific defect is demonstrated.

## 6. Tests

Add deterministic offline tests covering:

1. Explicit apply button with an absolute URL.
2. Relative application URL resolution.
3. External ATS application URL accepted only when allowed by policy.
4. Missing application link does not fabricate one.
5. Failed extraction preserves an existing valid application URL.
6. Canonical URL extraction and normalization.
7. Canonical tag pointing to a search page is rejected.
8. Multiple or malformed canonical tags.
9. Valid JSON-LD `JobPosting.url`.
10. Malformed JSON-LD and multiple JSON-LD objects.
11. Conflicting canonical, JSON-LD, and source URLs.
12. Tracking parameters removed without destroying job identity.
13. Greenhouse `gh_jid` identity remains intact.
14. Search and company-careers URLs are never accepted as individual job detail pages.
15. Invalid extracted URLs cannot bypass Phase 2 validation.
16. API and Celery ingestion use the same URL extraction rules.

Use mocks and fixtures. Do not depend on live websites.

## Constraints

- No broad scraper rewrite.
- No auto-apply functionality.
- No historical database cleanup.
- No bulk record updates.
- No unrelated frontend or API redesign.
- No schema migration unless essential. If the current schema cannot safely represent the required URL semantics, stop and report the limitation and smallest proposed migration before implementing it.
- Preserve backward compatibility where practical.
- Do not weaken Phase 1 or Phase 2 security checks to make tests pass.

## Acceptance criteria

- Detail, canonical, and application URLs are not conflated.
- A verified application URL is only stored when supported by trustworthy evidence.
- Missing or invalid extraction cannot damage existing valid data.
- Phase 1 and Phase 2 tests continue passing.
- New tests cover the cases above.

## Final report

Return:
1. Files changed and why.
2. URL precedence and validation policy.
3. How missing and conflicting URLs are handled.
4. Test commands and actual results.
5. Any schema limitations.
6. Remaining Phase 4 work.

Stop after Phase 3. Do not begin Phase 4.

# Task Sniffer — Phase 4: Source Configuration, ATS Reliability, Deduplication and Data Repair

You are working in the existing Task Sniffer / Work-Bot Hunter repository. Implement Phase 4 only after reviewing the completed Phase 1, Phase 2, and Phase 3 implementations.

## Objective

Complete the source-specific URL policies, fix ATS integration defects, improve safe deduplication, and provide a reversible strategy for historical bad job URLs.

Do not rebuild the ingestion architecture. Reuse the existing normalizer, validation gate, URL extraction logic, and ingestion engine.

## Before Implementation

1. Inspect the current Git diff and test results from Phases 1–3.
2. Inspect:
   - `backend/scrapers/adapter.py`
   - `backend/sources/urls.py`
   - `backend/services/normalizer.py`
   - `backend/services/ingestion.py`
   - Source adapter/factory configuration
   - `JobDeduplicator` and persistence/upsert logic
   - Database models, constraints, and indexes
   - Greenhouse, Ashby, Jobicy, and MyJobsKenya integrations.
3. Inspect the actual database schema and existing backup/export mechanisms.
4. Identify which source configurations are currently missing or incomplete.

Do not infer that a source is safe merely because it appears in a known ATS category. Confirm its actual URL patterns and API response structure.

## 1. Complete source-specific domain policies

Review every registered adapter, including `_LegacyAdapter`.

Configure explicit, evidence-based:
- Allowed listing domains.
- Allowed external ATS domains.
- Job detail URL patterns.
- Known search, category, company-careers, and non-job URL patterns.
- Source-specific identity query parameters, where required.

Prioritize the known gaps:
- Greenhouse
- Ashby
- Jobicy
- MyJobsKenya

Also audit other currently registered sources for equivalent configuration gaps.

Requirements:
- Do not auto-add the candidate hostname to the allow-list.
- Do not use broad wildcards that trust unrelated domains.
- Permit legitimate external ATS destinations only when explicitly configured.
- Distinguish an unconfigured source from a source that has been validated and configured.
- Keep fail-closed behavior for missing or invalid policy configuration.
- Report unconfigured sources clearly so they can be fixed rather than silently producing no results.

Add tests for accepted and rejected URL patterns for each changed source.

## 2. Fix Greenhouse and other ATS URL construction

Investigate the Greenhouse `absolute_url` handling defect.

Known failure pattern:
- Search or company-careers URLs containing `gh_jid` have been persisted as job pages.
- Historical records include Stripe search URLs and Databricks company-careers URLs that were incorrectly treated as individual jobs.

Use actual API payloads and existing fixtures to determine the correct URL semantics.

Requirements:
- Preserve the Greenhouse job identifier.
- Construct or select a true individual job detail URL using a documented, source-appropriate method.
- Do not blindly trust `absolute_url` if it points to a search or careers listing page.
- Validate the constructed detail URL with the existing Phase 2 policy.
- Keep application URL extraction separate from detail URL construction.
- Add regression fixtures for Stripe, Databricks, and other representative Greenhouse records.
- Audit Ashby and other ATS adapters for similar mistakes.

Do not invent URL patterns unsupported by the source's API or known format.

## 3. Repair deduplication safely

Inspect `JobDeduplicator` and determine why it is broken, unused, or ineffective in the current ingestion flow.

Implement conservative deduplication using the strongest available identifiers in a clear precedence order, such as:
1. Stable source job ID within its source namespace.
2. A validated ATS identifier.
3. A validated canonical/detail URL.
4. A carefully constrained fallback using normalized company, title, and location.

Requirements:
- Do not merge records solely because their titles match.
- Do not treat generic URLs such as `/jobs`, `/search`, or `/careers` as unique job identity.
- Do not destroy cross-source provenance.
- Do not overwrite a good application URL or canonical URL with a weaker value.
- Make repeated ingestion idempotent.
- Prevent duplicate creation during concurrent ingestion where the existing architecture supports safe constraints or transactional protection.
- Inspect existing unique constraints before proposing database changes.

If safe deduplication requires a schema migration or uniqueness constraint, document the specific race condition and proposed migration first. Do not silently migrate production data.

Add tests for repeated ingestion, conflicting identifiers, cross-source matches, and unrelated jobs sharing titles.

## 4. Historical database audit and repair plan

Historical data must be audited separately from live ingestion.

First, produce a read-only audit of the existing database:
- Count records with generic search/careers URLs.
- Identify invalid, empty, duplicated, or suspicious detail URLs.
- Identify records where `application_url` equals a generic listing URL.
- Identify records with inconsistent source IDs and URL identities.
- Distinguish confirmed invalid records from uncertain candidates.
- Report counts by source and error category.

Use the actual database path/configuration discovered from the repository. Never assume a production or development database path without verification.

### Repair safeguards

Do not perform a bulk update immediately.

First create:
- A machine-readable audit report.
- A proposed repair mapping for each affected record.
- Before/after values for every field that would change.
- A reason and confidence level for each proposed correction.
- A rollback strategy.

Only repair a record automatically when its replacement URL can be established reliably from stored source identifiers or trustworthy source data. Do not guess URLs from company names or job titles.

For uncertain records, leave them unchanged and classify them for manual review or re-ingestion.

If any destructive or production-data operation is necessary, stop and request explicit approval before execution. Do not delete jobs merely because a URL is currently unavailable.

Do not modify production records as part of the initial audit.

## 5. Observability and operational safety

Ensure ingestion results and logs distinguish:
- Valid jobs persisted.
- Invalid candidates rejected.
- Unknown/review candidates withheld.
- Missing source configuration.
- Redirect or domain-policy rejection.
- ATS URL construction failures.
- Duplicate records skipped or updated.
- Existing records protected from invalid overwrites.

Avoid logging secrets, tokens, cookies, or unnecessary personal data.

Do not turn temporary HTTP failures into permanent job removals. Reuse the Phase 2 status policy and safe update behavior.

## 6. Tests and regression verification

Add deterministic tests for:
- Every newly configured source's domain and URL patterns.
- Greenhouse individual job URL construction.
- Search/careers URLs rejected as detail URLs.
- ATS identity query parameters preserved.
- Ashby URL classification and identifier extraction.
- Jobicy and MyJobsKenya configuration behavior.
- Missing source configuration fails closed.
- Deduplication is idempotent.
- Same title does not incorrectly merge different jobs.
- Invalid candidates cannot overwrite valid records.
- Existing valid application URLs survive failed refreshes.
- Historical audit mode makes no database changes.
- Proposed repair output includes original values and rollback information.

Run the existing test suite, including all Phase 1–3 tests. Use offline fixtures and mocks; do not depend on live websites.

## Constraints

- No broad scraper rewrite.
- No auto-apply feature.
- No frontend redesign.
- No live production database cleanup without explicit approval.
- No unreviewed schema migration.
- No fabricated source URLs.
- No weakening validation or SSRF controls to improve ingestion counts.
- Do not classify all previously rejected candidates as valid just to increase results.
- Preserve API/Celery consistency.

## Acceptance criteria

- All registered sources have explicit, reviewable URL/domain policy or are clearly reported as unconfigured.
- Greenhouse no longer persists generic search/careers URLs as individual job pages.
- Deduplication is conservative, deterministic, and tested.
- Historical records are audited before any repair is applied.
- Repair proposals are reversible and uncertain records are not guessed.
- Phase 1–3 regressions remain green.

## Final report

Return:
1. Files changed.
2. Source policy changes and evidence.
3. ATS defects corrected.
4. Deduplication strategy and remaining limitations.
5. Historical audit counts and report location.
6. Whether any database records were changed.
7. Test commands and actual results.
8. Remaining risks and recommended follow-up.

Stop after Phase 4.

# Task Sniffer — Phase 5: End-to-End Verification and Production Readiness

Act as a senior backend engineer and security reviewer. Verify the completed Task Sniffer / Work-Bot Hunter implementation after Phases 1–4.

## Objective

Determine whether the full job-ingestion system is correct, secure, resilient, observable, and ready for deployment.

This phase is primarily verification and targeted hardening—not another architectural rewrite.

## Step 1: Establish the baseline

Inspect the current Git status and diff, project architecture, configuration, database models, and existing tests.

Trace the actual production execution path:

source discovery → HTTP fetching → redirect enforcement → URL validation → detail/application URL extraction → normalization → deduplication → persistence → API/Celery reporting.

Identify any differences between the implemented behavior and the documented behavior from Phases 1–4.

Do not trust earlier implementation reports without checking the code.

## Step 2: End-to-end correctness

Create deterministic integration tests using mocked HTTP responses and an isolated test database.

Verify:
- Valid individual job postings are persisted.
- Search, category, company-careers, expired, and invalid pages are rejected.
- Unknown or temporarily unavailable pages are withheld without corrupting existing records.
- Detail, canonical, and application URLs remain distinct and correctly validated.
- ATS-specific identifiers survive normalization.
- Redirects cannot bypass domain or SSRF protections.
- Duplicate ingestion does not create duplicate jobs.
- Cross-source records are not incorrectly merged.
- Invalid updates cannot overwrite valid records.
- API ingestion and Celery ingestion apply the same policies.
- One failing source does not prevent other sources from completing.
- Job removal or expiration is based on reliable evidence rather than a single transient fetch failure.

Test negative cases as thoroughly as successful ingestion.

## Step 3: Security review

Audit:
- URL parsing and redirect destinations.
- SSRF protections, including DNS resolution behavior and intermediate redirects.
- Domain allow-list configuration.
- SQL injection risks and parameterized queries.
- Authentication and authorization on ingestion/admin endpoints.
- Secrets, tokens, and sensitive values in logs.
- Resource limits, response-size limits, timeouts, and retry behavior.
- Concurrency and transactional consistency.

Do not claim DNS-level SSRF protection exists unless it is implemented and verified. Document residual risks explicitly.

Do not weaken existing validation to make sources pass.

## Step 4: Resilience and performance

Inspect:
- Connection pooling and HTTP client reuse.
- Concurrency and worker limits.
- Retry policies and backoff for transient failures.
- Handling of HTTP 403, 429, 5xx, timeouts, and malformed content.
- Large responses and unexpected content types.
- Database query efficiency and appropriate existing indexes.
- Ingestion behavior when a source or worker fails.

Use reproducible local benchmarks where practical. Report measured results and test conditions; do not invent performance improvements.

Only make targeted changes supported by a confirmed defect.

## Step 5: Observability

Ensure the system can distinguish:
- Jobs discovered.
- Jobs validated and persisted.
- Invalid candidates rejected.
- Review-needed candidates withheld.
- Duplicate records skipped or updated.
- Source configuration failures.
- HTTP, parsing, validation, database, and worker errors.

Check that logs and metrics are actionable and do not expose secrets. Avoid unnecessary logging of personal data.

## Step 6: Release readiness

Verify:
- Full regression suite passes.
- API and worker startup paths work in the intended environment.
- Required dependencies and configuration are documented.
- Database migrations, if any, are reviewed and reversible.
- Backup and rollback procedures exist.
- Historical repair work has been reviewed and does not run unexpectedly during startup or ingestion.

Use an isolated test environment. Do not modify production data, run destructive commands, deploy, or change production infrastructure without explicit authorization.

## Scope restrictions

- No broad rewrite.
- No auto-apply feature.
- No unrelated frontend changes.
- No speculative optimization.
- No destructive database cleanup.
- No unapproved schema migration.
- Do not report a check as passed unless it was actually executed.
- Distinguish verified facts, inferred risks, and untested areas.

## Deliverables

Provide:
1. End-to-end architecture and data-flow findings.
2. Critical, high, medium, and low severity issues.
3. Exact files and functions associated with each confirmed issue.
4. Tests added or changed.
5. Exact commands executed and actual test results.
6. Performance measurements with test conditions, where available.
7. Remaining security, reliability, and source-coverage limitations.
8. A final go/no-go recommendation with explicit release blockers.
9. A concise deployment and rollback checklist.

Implement only narrowly scoped fixes for confirmed defects. Stop when verification is complete and report any remaining blockers. Do not begin a new phase.