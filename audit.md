# Task Sniffer — Scraper URL Pipeline Audit

**Type:** Read-only forensic audit
**Scope:** Scraping pipeline for job URL correctness (extraction → normalization → validation → application URL → storage)
**Method:** Repository code inspection, review of the two local SQLite databases (`work_bot_hunter.db`, `work_hunter.db`), and offline execution of the existing URL helpers.
**Status:** No code was modified. Findings only.

Active production path: `run.py` → `backend.api.app:app` → `POST /sources/{name}/ingest` or Celery `scrape_all_sources` → `backend.services.ingestion.IngestionEngine`. The `src/` tree is the legacy bot (deprecated per README) and is audited only where it explains stored data.

---

## 1. Executive Summary

The scraper is **not primarily weak at reading anchor tags**. Link *extraction* is source-specific and mostly works. The wrong-link problem is caused by the **URL pipeline being bypassed and by three forms of URL conflation**:

1. **Canonical/identity loss** — `JobNormalizer._normalize_url` deletes the entire query string (`re.sub(r"\?.*$", "", url)`), turning query-addressed job pages into listing pages and deriving `source_job_id` from the wrong path segment (`"search"`, `"jobs"`).
2. **Application URL = detail URL** — `application_url` is set to the scraped detail URL whenever no explicit apply hint exists. The real apply-extraction helper (`find_explicit_apply_url`) and the `apply_hint` field are **dead code**, so the apply URL is essentially never the true application target.
3. **Validation does not gate persistence** — invalid, search, off-domain, redirected, or anti-bot pages are still written to `jobs` with a non-VALID `url_status`; nothing quarantines them.

Compounding this, **every legacy source runs with empty `job_url_patterns` and `allowed_domains`**, so generic path heuristics both **accept wrong URLs** (company careers/search pages, embedded-ATS pages) and **reject correct ones** (Ashby, Workable, Remotive). The clearest real-world evidence is `work_hunter.db`: 99 Greenhouse jobs stored as `https://stripe.com/jobs/search?gh_jid=...` and 59 as `https://databricks.com/company/careers/open-positions/job?gh_jid=...` — search pages and company careers pages were stored as job URLs because `absolute_url` from the Greenhouse API was trusted.

**Verdict:** both, but extraction is the lesser half. The dominant failure is **validation + canonicalization + URL-field conflation**, with a source-specific `absolute_url` bug for Greenhouse.

---

## 2. Current URL Pipeline (Discovery → Storage)

| # | Stage | Function / module | Notes |
|---|-------|-------------------|-------|
| 1 | Source/listing URL | `backend/sources/registry.py` `SourceConfig.url`; adapter `listing_url` | audited registry |
| 2 | HTTP request | `JobSourceAdapter.fetch` / `JobSource.fetch_text`; httpx `follow_redirects=True` | no referer/cookie controls |
| 3 | Response handling | `IngestionEngine._fetch_and_validate` (`ingestion.py:308`) | uses `response.url` as final |
| 4 | Listing parsing | each adapter `_parse_page` (not base `parse_listing`) | `soup.find_all("a", href=True)` |
| 5 | Candidate extraction | adapter-local `_DETAIL` regex filter | `extract_candidate_urls` **unused in prod** |
| 6 | Relative→absolute | `backend/scrapers/adapters/_common.py:absolute` → `canonicalize_url(urljoin(...))` | |
| 7 | Redirect resolution | httpx auto-follow; `resolve_redirects` imported but **never called** | chain built inline at `ingestion.py:331` |
| 8 | Canonical detection | **none** — no `<link rel="canonical">`, no JSON-LD `url` | |
| 9 | Job-page validation | `backend/sources/urls.py:validate_job_page` via `adapter.validate_page` | result is informational only |
| 10 | Application URL extraction | `find_explicit_apply_url` **unused**; `ListingItem.apply_hint` **never populated** | falls back to detail URL |
| 11 | URL normalization | `canonicalize_url`; then `JobNormalizer._normalize_url` strips all query | second step is destructive |
| 12 | Dedup | `IngestionEngine._persist_job` (source+id, then fingerprint) | `JobDeduplicator` unused/broken |
| 13 | Storage | `Job.source_url/canonical_url/final_url/application_url/url_status` | `original_url` never set; no `discovered_url` |

Evidence of bypass: `extract_candidate_urls`, `find_explicit_apply_url`, and `request_with_redirect` are referenced only by tests and their own definitions.

---

## 3. Source-by-Source Findings

| Source | Extraction method | Expected URL | Current behavior | Risk | Evidence |
|--------|-------------------|--------------|------------------|------|----------|
| **fuzu** | `FuzuAdapter._parse_page`, `_DETAIL=r"/jobs/[a-z0-9-]+/?$"` | `/kenya/jobs/<slug>` | Correct; `source_url=canonical_url=final_url=application_url`, VALID | LOW | DB src=5, 3 rows VALID |
| **myjobmag** | `MyJobMagAdapter`, `_JOB_DETAIL=r"/job/[a-z0-9-]+$"`, skips `?` | `/job/<slug>` | Correct via HTML/RSS | LOW | DB src=7, 3 rows VALID |
| **corporatestaffing** | `_DETAIL=r"/(job|jobs|vacancy|position|opportunity)/[^/?#]+/?$"` | detail slug | Broad regex; no apply/canonical handling | MEDIUM | `adapters/corporatestaffing.py:22` |
| **kra** | `_DETAIL` careers regex | `/careers/<slug>`, apply at `erecruitment.kra.go.ke` | `application_url` falls back to detail URL; portal never extracted | HIGH | `adapters/kra.py:22`, `ingestion.py:431` |
| **psc** | `_DETAIL` membership regex | `/jobs/<slug>`, apply at `psckjobs.go.ke` | Same apply conflation | HIGH | `adapters/psc.py:22`, `registry.py:138` |
| **greenhouse** (legacy-wrapped) | API `item["absolute_url"]` | `boards.greenhouse.io/<board>/jobs/<id>` | Embedded boards return company **search/careers page** with `?gh_jid=` | **CRITICAL/HIGH** | `scrapers/greenhouse.py:47`; DB 99× `stripe.com/jobs/search?gh_jid=`, 59× `databricks.com/company/careers/...?gh_jid=` |
| **ashby** (legacy-wrapped) | API `item["url"]` | `jobs.ashbyhq.com/<board>/<id>` | URL correct in legacy DB, but backend `classify_url` labels it `unknown` → **dropped** | HIGH | classifier run below; `factory.py:42` empty patterns |
| **jobicy** (legacy-wrapped) | API `item["url"]` | `jobicy.com/jobs/<id>-<slug>` | Correct | LOW | DB 48 rows |
| **myjobskenya** (legacy-wrapped) | HTML `a[href*='/job/']` fallback | `/job/<slug>` | Generic anchor fallback can pick search/category links | MEDIUM | `scrapers/myjobs.py:34` |
| **brightermonday** (registered) | legacy `BrighterMondayScraper` `a[href*='/jobs/']`; stale `brightermonday.com` | `.co.ke/job/<slug>` | No adapter → `build_adapter` raises `KeyError`; legacy domain wrong | HIGH | `factory.py:18-36`; `scrapers/brightermonday.py:19`; `registry.py:183` |
| **careerpointkenya** (registered) | none | `.../job/<slug>` | No adapter in `ADAPTER_CLASSES` → `KeyError` (never runs) | MEDIUM | `factory.py:30-36` |
| **wellfound** | restricted | — | Not crawlable (by design) | LOW | `registry.py:198` |

Offline classifier evidence (existing helpers, real URLs):

```
https://stripe.com/jobs/search?gh_jid=7993151               -> search      -> REJECT
https://databricks.com/company/careers/open-positions/job?...-> job_detail  -> ACCEPT (company careers page)
https://www.coinbase.com/careers/positions/12345             -> job_detail  -> ACCEPT
https://jobs.ashbyhq.com/openai/abc-123                      -> unknown     -> REJECT (valid job)
https://apply.workable.com/acme/j/ABC123/                    -> unknown     -> REJECT (valid job)
https://remotive.com/remote-jobs/software-dev/some-role-123  -> unknown     -> REJECT (valid job)
```

Normalizer evidence:

```
https://stripe.com/jobs/search?gh_jid=7993151  -> url='https://stripe.com/jobs/search'  source_job_id='search'
https://www.fuzu.com/kenya/jobs/x?job_id=42    -> url='https://www.fuzu.com/kenya/jobs/x' source_job_id='jobs'
```

Database evidence (`work_hunter.db`):

```
distinct source hosts among 1366 stored jobs:
  716  jobs.ashbyhq.com
  203  job-boards.greenhouse.io
  146  www.coinbase.com
   99  stripe.com            (99 URLs contain "/search")
   65  cribl.io
   59  databricks.com        (59 URLs contain "/company")
   48  jobicy.com
   30  careers.airbnb.com
```

---

## 4. Root Causes (Ranked)

### CRITICAL

- **C1 — Query-string destruction in normalization.** `JobNormalizer._normalize_url` (`backend/services/normalizer.py:200-205`) removes `?...` entirely. For query-addressed jobs this yields a listing URL and a `source_job_id` from the wrong segment (`"search"`, `"jobs"`), breaking identity and the `(source_id, source_job_id)` uniqueness (`models/database.py:182`).
- **C2 — `application_url` is not an application URL.** `ingestion.py:254` sets `application_url = raw.get("application_url") or ""`; `_persist_job` (`ingestion.py:431`) uses `... or source_url`. `ListingItem.apply_hint` is never populated by any adapter, and `find_explicit_apply_url` (`urls.py:438`) is dead. Users and alert links (`routes/jobs.py:35`) point at the detail page, not the apply target; contradicts the KRA/PSC audit intent.
- **C3 — Validation results do not gate persistence.** `_process_listing` always calls `_persist_job`; `url_status` is merely recorded (`ingestion.py:240-278, 361-442`). INVALID/search/off-domain/anti-bot pages land in `jobs`.

### HIGH

- **H1 — Source-specific URL patterns disabled for all legacy sources.** `_LegacyAdapter.job_url_patterns=[]` / `allowed_domains=[]` (`factory.py:42-43`), so `identify_job_url` and `_classify_path` use generic heuristics; Ashby/Workable/Remotive are falsely rejected while careers pages are accepted.
- **H2 — Greenhouse `absolute_url` trusted.** `scrapers/greenhouse.py:47` (and `_LegacyAdapter` passthrough) stores whatever the API returns; embedded boards return company search/careers pages with `?gh_jid=` (DB evidence).
- **H3 — Domain/redirect validation effectively disabled for legacy sources.** `_fetch_and_validate` falls back to candidate host (`ingestion.py:312-316`) and `adapter.validate_page` passes `allowed_domains=None` when `self.allowed_domains` is empty (`adapter.py:142-148`), so `checks["expected_domain"]` is always True.
- **H4 — Redirect handling is captured, not enforced.** `resolve_redirects`/`request_with_redirect` are dead; the chain is only recorded (`ingestion.py:331,357`). `source_url`/`canonical_url` keep the pre-redirect value; no off-domain/tracking-hop/interstitial policy.
- **H5 — Updates can overwrite valid URLs with bad ones.** Same-source update unconditionally overwrites `source_url`, `canonical_url`, and `final_url` (`ingestion.py:387-392`); cross-source merge overwrites `dup.final_url` (`ingestion.py:406-408`).

### MEDIUM

- **M1 — Generic extraction contract not enforced.** `extract_candidate_urls`/`identify_job_url` (`urls.py:252,275`) are unused in production; each adapter hand-rolls anchor filtering, bypassing the "never trust the first anchor" design.
- **M2 — `classify_url` heuristics misfire both ways** (`urls.py:205-245, 70-78`): accepts `/company/careers/...` pages; rejects `/<board>/<slug>` (Ashby) and `/remote-jobs/<cat>/<slug>` (Remotive).
- **M3 — No canonical/JSON-LD URL extraction.** `rel="canonical"` and `JobPosting.url`/`identifier` are never read; JSON-LD is only used for fuzu fields.
- **M4 — `JobDeduplicator` is broken and unused** (`services/deduplicator.py:21` raw-string `execute`, `execute_one` at line 98 does not exist). Latent hazard if wired.
- **M5 — Legacy dedup keys on raw URL** (`src/database/models.py:115` `filter_by(url=...)`), so tracking-param churn creates duplicates.

### LOW

- **L1 — Tracking list incomplete** (`urls.py:24-32`): `gh_jid`, `ref`, `gh_src`, `trk` are preserved; unknown params survive canonicalization.
- **L2 — `normalize_url` forces `https://`** on scheme-less strings (`urls.py:139-140`).
- **L3 — `adapter.validate_page` allowed-domain mapping is convoluted** (`adapter.py:143-148`, `[0]` + `discard("")`).

---

## 5. False-Positive URL Types Currently Accepted

- Embedded-ATS company pages: `https://stripe.com/jobs/search?gh_jid=<id>` (rejected by SEARCH marker only if the path literally contains `search`).
- Company careers pages with identity query: `https://databricks.com/company/careers/open-positions/job?gh_jid=<id>` (accepted as `job_detail`).
- Company-hosted board paths: `https://www.coinbase.com/careers/positions/<id>`, `https://wellfound.com/company/<co>/jobs/<id>`.
- Generic `/anything/.../careers|jobs|roles/<slug>` paths (`_is_detail_path`, `urls.py:70-78`).
- Any resolved detail URL that **redirects** to a search/expired/unrelated page (validation is not gating).
- Anti-bot/interstitial pages returned with HTTP 200 (no captcha / "Just a moment" detection).
- URLs retaining unknown/tracking params after `strip_tracking_params` (allow-by-default behavior, `urls.py:176-181`).

---

## 6. Missing Controls

- Canonical link extraction (`<link rel="canonical">`) and JSON-LD `url`/`identifier` extraction.
- Redirect policy: final-URL reclassification, off-domain hop detection, tracking-hop removal, interstitial detection, chain bounds.
- Content-type check (HTML vs JSON/XML error bodies) in `_fetch_and_validate`.
- Expired/removed-job detection (404 body, "no longer accepting applications", "position filled").
- URL-status gating / quarantine before persistence.
- Real apply-link extraction (`find_explicit_apply_url` unused; `apply_hint` never set).
- Query/identity-param preservation in the normalizer (identity params must not be stripped).
- Enforced, non-empty `job_url_patterns`/`allowed_domains` per source adapter.
- `original_url` population and a `discovered_url` vs `canonical_url` vs `application_url` distinction.
- Post-redirect `source_url` correction (source currently stays pre-redirect).

---

## 7. Recommended Architecture

Keep the existing `backend/sources/urls.py` primitives; make them the only path and add gating.

```
Discovery            registry SourceConfig.url / adapter listing
   |
Candidate extraction  adapter returns raw hrefs + apply_hint  (adapter.py ListingItem)
   |
Normalization         normalize_url + strip_tracking_params, NEVER drop query (fix C1)
   |
Redirect resolution   resolve_redirects/request_with_redirect (wire in, record chain)
   |
Canonicalization      <link rel=canonical> + JSON-LD JobPosting.url  (new, urls.py)
   |
Job-page validation   validate_job_page + content-type + expired/interstitial  -> GATE
   |
Application extraction find_explicit_apply_url (wire in); application_url != source_url
   |
Deduplication         (source_id, source_job_id) + fingerprint on canonical_url
   |
Persistence           store discovered/source/canonical/final/application separately; quarantine non-VALID
```

Rule: **nothing with `url_status != VALID` is written as a normal job**; it goes to a review/quarantine record.

---

## 8. Files / Functions to Change

- `backend/services/normalizer.py` — `JobNormalizer._normalize_url` (stop stripping query), `_extract_source_job_id` (use identity params).
- `backend/services/ingestion.py` — `_fetch_and_validate` (content-type, redirect policy, domain set), `_process_listing` (gate on `validation.ok`), `_persist_job` (separate URL fields, no destructive overwrite), `_resolve_candidate_url` (use `extract_candidate_urls`).
- `backend/sources/urls.py` — wire `find_explicit_apply_url`; add canonical + JSON-LD extractor; broaden `_SEARCH_MARKERS`/`_is_detail_path`; extend `TRACKING_PARAMS`; add `classify_url` support for ATS patterns.
- `backend/scrapers/factory.py` — `_LegacyAdapter` (populate `job_url_patterns`, `allowed_domains`, real `parse_detail`).
- `backend/scrapers/greenhouse.py` — stop trusting `absolute_url`; derive board detail URL / prefer API job detail.
- `backend/scrapers/adapters/*.py` — set `apply_hint`; add source patterns/domains.
- `backend/models/database.py` — populate `original_url`; implement `url_status` gating/quarantine semantics.
- `backend/services/deduplicator.py` — repair or delete (currently broken/unused).
- `src/database/models.py` `add_job` and `src/scrapers/greenhouse.py` — legacy dedup/URL (if legacy remains supported).

---

## 9. Test Plan (write before changing)

1. **Query preservation:** `JobNormalizer.normalize` keeps `?job_id=42` and derives `source_job_id` from the id, not `"jobs"`.
2. **Greenhouse embedded board:** given `absolute_url = https://stripe.com/jobs/search?gh_jid=7993151`, the engine must not store it as a job (or must resolve to the canonical detail via API / `rel=canonical`).
3. **Accepted vs rejected URLs:** parametrized `classify_url`/`identify_job_url` cases for Ashby (`jobs.ashbyhq.com/<b>/<id>`), Workable, Remotive (accept) and `/company/careers/...`, `/search?...`, `/company-profile/...` (reject).
4. **Validation gating:** mock detail page returning 404, `text/plain`, off-domain redirect, and Cloudflare "Just a moment" (200) must produce no persisted `jobs` row (quarantine only).
5. **Redirect != source:** detail URL redirecting `a -> b` stores `final_url=b`; `source_url`/`canonical_url` reflect the resolved canonical, chain recorded.
6. **Application extraction:** page with an "Apply" `<a>` on an allowed ATS domain sets `application_url` to that link, not the detail URL; KRA/PSC fall back only when no portal link exists.
7. **Overwrite safety:** re-scrape with a worse/redirected URL must not clobber an existing VALID `canonical_url`.
8. **Registry coverage:** every registered crawlable source either has an adapter or is explicitly skipped (no `KeyError`).
9. **Normalizer idempotency:** canonicalization + normalization applied twice is stable (no param/segment drift).

---

## 10. Final Verdict

> "The wrong-link problem originates primarily from the URL pipeline being bypassed and from conflating three different URLs into one — the normalizer destroys query-based job identity (`JobNormalizer._normalize_url`), `application_url` silently falls back to the scraped detail URL while the real apply/canonical extractors are dead code, and page validation does not gate persistence — compounded by legacy adapters that disable source-specific patterns/domains and trust source API `absolute_url` values (Greenhouse embedded boards storing `stripe.com/jobs/search?gh_jid=…` and `databricks.com/company/careers/…?gh_jid=…`)."

Link extraction itself is secondary: it is source-local and mostly adequate; the incorrect URLs are introduced *after* extraction, in normalization, canonicalization, apply-URL resolution, and validation/persistence.

---

# Phase 1 — URL Identity and Regression Tests: Implementation Report

**Scope:** URL normalization, job identity extraction, URL classification, and regression tests only. No schema, ingestion, apply-URL, or adapter changes.
**Status:** Complete. All tests pass.

## 1. Confirmed baseline failures

`.venv/bin/python -m pytest tests/unit/test_url_identity.py -q` → **12 failed / 23 passed** before the fix:

- `JobNormalizer._normalize_url` stripped the entire query string, so `?gh_jid=7993151` and `?job_id=42` were lost.
- `_extract_source_job_id` derived the id from the wrong path segment (`search`, `jobs`).
- Valid ATS detail URLs (Ashby, Workable, Remotive) were classified `unknown` and rejected.
- `stripe.com/jobs/search?gh_jid=7993151` produced `source_job_id='search'`.

## 2. Files modified

- `backend/services/normalizer.py`
  - `_normalize_url`: no longer deletes the query string; delegates to `canonicalize_url` (explicit tracking-param policy, fragment/port/scheme normalization). Identity params survive.
  - `_extract_source_job_id(url, company, title, source="")`: source-specific query params (`gh_jid` for `greenhouse`) → generic identity params (`IDENTITY_PARAMS`) → non-generic path segment (skips `search`/`jobs`/`careers`/…) → hash fallback. Never returns a generic path word.
  - Added `_SOURCE_IDENTITY_PARAMS`, `_IDENTITY_QUERY_PARAMS`, `_NON_IDENTIFYING_PATH_SEGMENTS`.
- `backend/sources/urls.py`
  - Added explicit `_ATS_DETAIL_PATTERNS` (Ashby, Workable, Remotive, Lever) and `_is_ats_detail`, checked first in `_classify_path`. No change to validation or persistence.

## 3. Tests added

`tests/unit/test_url_identity.py` — 35 cases:

- **A. Query identity (7):** `gh_jid`/`job_id` preserved and extracted; source id beats path segment; no id from generic path segment; slug identity unchanged; tracking stripped while identity survives; unrelated params not treated as identity.
- **B. ATS classification (6 valid/invalid + 6 identify):** Ashby/Workable/Remotive accepted; search, company, careers-landing, category, pagination, and board-landing rejected.
- **C. Normalization stability (10):** idempotent `canonicalize_url` and normalizer URL, fragment removal, scheme/host normalization, distinct jobs do not collapse.
- **D. Greenhouse regression (1):** `stripe.com/jobs/search?gh_jid=7993151` keeps `7993151` while remaining non-`JOB_DETAIL` and unidentified.

## 4. Tests passing / failing

- `tests/unit/test_url_identity.py`: **35 passed**.
- `tests/unit`: **89 passed** (54 pre-existing + 35 new), 0 failures.
- `tests`: **89 passed**, 0 failures.
- Import sanity (`backend.services.normalizer`, `backend.sources.urls`, `backend.api.app`): ok, no import cycle.

## 5. Compatibility concerns

- `_extract_source_job_id` gained an optional fourth arg (`source=""`); existing 3-arg callers remain valid.
- `normalized["url"]` is now canonicalized and keeps identity params; ingestion's stored `source_url` comes from a separate `canonicalize_url` path and is unaffected.
- Sources that previously collapsed to `source_job_id="search"` now receive a hash fallback id instead of a bogus one.

## 6. Remaining known URL pipeline defects (deferred to Phase 2+)

- Validation results are not a persistence gate (`_persist_job` writes invalid candidates).
- No redirect enforcement or final-URL reclassification; `source_url` remains pre-redirect.
- Legacy `_LegacyAdapter` has empty `job_url_patterns`/`allowed_domains` (trusts candidate host).
- Greenhouse adapter trusts API `absolute_url`.
- `UrlStatus` has no `UNKNOWN`/quarantine state.
- Canonical/JSON-LD extraction and apply-URL extraction still absent.

## 7. Exact commands

```
.venv/bin/python -m pytest tests/unit/test_url_identity.py -q
.venv/bin/python -m pytest tests/unit -q
.venv/bin/python -m pytest tests -q
```

---

# Phase 2 — Validation Gating and Redirect Enforcement: Implementation Report

**Scope:** `ingestion.py`, `urls.py`, `adapter.py`, and validation/ingestion tests. No Phase 3 apply-URL extraction, no scraper rewrite, no schema change.
**Status:** Complete. All tests pass.

## 1. Confirmed baseline failures

`.venv/bin/python -m pytest tests/unit/test_validation_gating.py -q` → **17 failed / 2 passed** before the fix. The engine persisted every candidate regardless of `url_status`; 404/403/429 all returned `INVALID`; `text/plain` and CAPTCHA-200 pages were accepted; off-domain/SSRF/loop redirects were followed and persisted; missing `allowed_domains` silently trusted the candidate host.

## 2. Files changed

- `backend/sources/urls.py`
  - `validate_job_page` now implements an explicit status/content policy and returns `VALID` / `INVALID` / `NEEDS_REVIEW`.
  - Added `looks_like_html`, `is_safe_fetch_url`, `_is_anti_bot`, `_is_removed`, and marker regexes.
- `backend/scrapers/adapter.py`
  - Added `expected_domains()` (empty → fail closed) and `max_redirects = 5` (bounded client).
  - `validate_page` no longer auto-adds the candidate host to the domain allow-list and forwards `content_type` / `is_html`.
- `backend/services/ingestion.py`
  - `_process_listing` gates persistence on `validation.ok`; non-VALID candidates are counted as invalid/review and logged.
  - `_fetch_and_validate` enforces SSRF policy before and after redirects, bounds redirect loops, passes content type, and records final URL/chain.
  - `_persist_job` refuses to persist/overwrite non-VALID candidates and populates `original_url`.

## 3. Validation policy implemented

Status mapping (repository-native `UrlStatus`; `NEEDS_REVIEW` is the "UNKNOWN" bucket):

| Condition | Status |
|-----------|--------|
| `VALID`: 2xx, HTML, in-policy domain, not search/category, content + title/company match, no removed/anti-bot markers | persisted |
| 404 / 410, non-2xx (non-403/429/5xx), job-removed markers, search/category final URL, non-HTML body | `INVALID` |
| status 0 (timeout/network), 403 / 429, 5xx, anti-bot/CAPTCHA interstitial (incl. HTTP 200), unexpected/unconfigured domain, thin content, title/company mismatch | `NEEDS_REVIEW` (skipped) |

Only `VALID` enters normal storage.

## 4. Redirect policy implemented

- `httpx` follows redirects with `max_redirects = 5`; `TooManyRedirects` → `NEEDS_REVIEW`. Loops are bounded and never persisted.
- Final URL is re-fetched/reclassified (`classify_url`) and checked against the source domain policy.
- Domain policy comes from `adapter.expected_domains()`; an empty policy **fails closed** (`NEEDS_REVIEW`) instead of trusting the candidate host.
- Legitimate external ATS redirects are accepted only when the ATS host is declared in `allowed_domains`.
- SSRF: `is_safe_fetch_url` rejects non-HTTP(S) schemes and loopback/private/link-local/reserved/multicast addresses, applied to both the requested and final URL. DNS rebinding is noted as out of scope (host-literal checks only).

## 5. Tests passing / failing

- `tests/unit/test_validation_gating.py`: **19 passed**.
- `tests/unit`: **108 passed** (89 prior + 19 new), 0 failures.
- `tests`: **108 passed**, 0 failures.
- Import sanity (`backend.api.app`, `backend.services.ingestion`, `backend.scrapers.adapter`): ok. (`backend.workers.tasks` needs `celery`, not installed in `.venv` — pre-existing.)

Test commands:

```
.venv/bin/python -m pytest tests/unit/test_validation_gating.py -q
.venv/bin/python -m pytest tests/unit -q
.venv/bin/python -m pytest tests -q
```

## 6. Regressions / unresolved failures

None. Existing Phase 1 and pre-existing tests still pass. No schema, migration, or DB edits.

## 7. Handling of unknown candidates, quarantine, and Phase 3 work

- **Unknown candidates:** classified `NEEDS_REVIEW`, counted in `review_urls`, logged as "withheld", never persisted and never allowed to overwrite a valid record. No quarantine table is introduced (per constraint); candidates are safely skipped.
- **Both paths enforce the same rules:** direct `POST /sources/{name}/ingest` (`routes/sources.py`) and Celery `scrape_all_sources` / `ingest_source` (`workers/tasks.py`) both call `IngestionEngine.run_source`; the gate lives inside the engine.
- **Remaining Phase 3 work:**
  - Application-URL extraction (`find_explicit_apply_url`, `apply_hint`) — still dead; `application_url` falls back to the detail URL.
  - Canonical (`rel="canonical"`) and JSON-LD `JobPosting.url` extraction.
  - Populate explicit `job_url_patterns` / `allowed_domains` for `_LegacyAdapter` (greenhouse/ashby/jobicy/myjobskenya) and fix the Greenhouse `absolute_url` bug; until then these sources fail closed (`NEEDS_REVIEW`).
  - Optional quarantine record for review candidates.
  - DNS-level SSRF resolution (anti-rebinding).

---

# Phase 2 Security Review — Findings Resolution: Implementation Report

Resolution of the Phase 2 security review (findings C1, H1, H2, M1, M2, M3, L1–L3;
L4 left as-is). Read-only review had issued a conditional NO-GO for Phase 3 until
C1/H1/H2 (and M1) were resolved.

## 1. Findings addressed

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| C1 | Critical | SSRF checks were post-hoc; `client.get` followed redirects internally, so intermediate hops were requested before host checks | Redirects are now followed **manually** by `fetch_with_policy`; every hop is validated *before* its request is issued |
| H1 | High | Any non-IP-literal host was treated as safe (DNS → private unchecked) | `_url_is_safe_async` resolves hostnames (worker thread, 0.75s timeout, per-process cache) and rejects if any resolved address is private/loopback/link-local/reserved |
| H2 | High | Encoded IP literals and arbitrary ports bypassed the check | `_parse_host_ip` handles decimal/hex/octal/shorthand IPv4, IPv4-mapped IPv6; `_ALLOWED_PORTS = {80,443,8080,8443}` |
| M1 | Medium | A failed per-job flush poisoned the session / could lose the whole run | `run_source` wraps each `_process_listing` in `session.begin_nested()` (savepoint); failures roll back only that job |
| M2 | Medium | `not_search_listing` excluded only `SEARCH`/`CATEGORY` | Now also excludes `COMPANY`, and a dedicated `not_homepage` check rejects `/` (and empty path) |
| M3 | Medium | `_body_text` included `<script>`/`<style>` text → anti-bot false positives | `_body_text` decomposes `script`/`style`/`noscript`/`template`; bare `cloudflare` marker removed |
| L1 | Low | `looks_like_html` treated any `application/xml` as HTML | XML now accepted only when the body is clearly an HTML document |
| L2 | Low | Cross-source dedup overwrote `final_url` unconditionally | Overwrite only when the existing `final_url` is empty or not `VALID` |
| L3 | Low | `redirect_chain` stored raw `Location` headers | `fetch_with_policy` normalizes each hop via `urljoin` + `normalize_url` |
| L4 | Low | Dead `resolve_redirects`/`request_with_redirect` remain | Left in place (out of scope; no callers) |

## 2. Files modified

- `backend/sources/urls.py`
  - Added async helpers `_resolve_host_ips_cached` / `_url_is_safe_async`, `_skips_dns_check`, `_NON_RESOLVABLE_SUFFIXES`, `_DNS_CACHE`, `_DNS_TIMEOUT`.
  - Reworked `_parse_host_ip` (inet_aton shorthand + hex/octal), added `_ip_is_unsafe`, `_ALLOWED_PORTS`.
  - `is_safe_fetch_url(url, *, resolve_dns=False)` now enforces ports, `localhost`/`.local`/`.internal`, encoded IP literals, and optional DNS.
  - New `async def fetch_with_policy(client, url, *, max_redirects=5, resolve_dns=True) -> (response, final_url, chain, error)`.
  - `looks_like_html` narrowed for XML; `validate_job_page` adds `not_search_listing` (`COMPANY`) and `not_homepage` checks, both → `INVALID`.
  - `_ANTI_BOT_MARKERS` no longer contains bare `cloudflare`/`access denied`.
- `backend/services/ingestion.py`
  - `_fetch_and_validate` now uses `fetch_with_policy` (no internal redirect following); unsafe hops → `INVALID`, timeouts/loops → `NEEDS_REVIEW`.
  - `_body_text` strips non-content tags.
  - `run_source` savepoint per job.
  - Cross-source `final_url` overwrite guarded.
  - Removed now-unused `httpx` import.
- `tests/unit/test_validation_gating.py` — 10 new regression tests (section 15).

## 3. New regression coverage

`test_intermediate_redirect_hop_is_never_fetched`, `test_dns_resolving_to_private_is_blocked`,
`test_encoded_ip_literals_are_rejected`, `test_non_web_ports_rejected`,
`test_company_page_is_invalid`, `test_homepage_is_invalid`,
`test_script_noise_does_not_trigger_antibot`, `test_redirect_chain_and_original_url_recorded`,
`test_5xx_preserves_existing_valid_record`, `test_partial_failure_rolls_back_only_that_job`.

## 4. Tests passing / failing

- `tests/unit/test_validation_gating.py`: **29 passed** (19 prior + 10 new).
- `tests`: **118 passed**, 0 failures (was 108). Suite runtime ~4.7s.

```
.venv/bin/python -m pytest tests -q
```

## 5. Residual risk / deferred

- **DNS rebinding (TOCTOU):** resolution is validated but the connection re-resolves; a rebinding attacker who flips the record between check and connect is not fully defeated. Full mitigation needs connect-to-pinned-IP or a filtering egress proxy.
- **DNS timeout fail-open:** an unresolvable/slow host is treated as safe and left to fail naturally at request time (avoided fail-closed to keep per-request latency bounded).
- **L4:** dead `resolve_redirects` / `request_with_redirect` retained; Phase 3 should delete them.
- Phase 3 items from the Phase 2 report remain open (canonical/JSON-LD extraction, `_LegacyAdapter` allow-lists, Greenhouse `absolute_url`).

**Verdict:** C1/H1/H2/M1/M2/M3/L1–L3 resolved and regression-tested; Phase 3 may proceed.

---

# Phase 3 — URL Extraction and Identity Resolution: Implementation Report

## 1. Files changed and why

- `backend/sources/urls.py`
  - `find_explicit_apply_url` rewritten: returns only an apply link that passes
    the shared safety/domain policy; no longer falls back to the detail URL
    (that was fabricating an application URL).
  - New `extract_url_signals(html, base_url, *, allowed_domains, apply_hint, detail_url)`
    resolving canonical and application URLs for a fetched page, plus helpers:
    `_validated_web_url`, `_job_identity_key`/`_same_job_identity`,
    `_each_jsonld`, `_is_jobposting`, `_jsonld_job_urls`,
    `_jsonld_application_urls`, `extract_canonical_url`.
  - `_validated_web_url` applies the Phase 2 policy to extracted URLs: http(s)
    only, `is_safe_fetch_url` (SSRF), domain policy, not search/company/category,
    not a homepage. Extracted URLs are policy-checked but never fetched.
- `backend/services/ingestion.py`
  - `_fetch_and_validate` calls `extract_url_signals` on validated 200 pages and
    carries `_canonical_url` / `_application_url` / `_url_notes` into the detail.
  - `_process_listing` uses the validated extraction (not the raw, unvalidated
    adapter `apply_hint`) for `application_url` / `_canonical_url`.
  - `_persist_job`: new jobs store `canonical_url` from extraction (else the
    detail URL) and `application_url` only when extracted (else `NULL`); the
    re-scrape path no longer clobbers a prev-valid canonical/application URL
    when extraction does not find one.
- `tests/unit/test_url_extraction.py` — new (20 tests).

## 2. URL precedence and validation policy

Definitions (per phase spec): `source_url`=discovered detail page; `canonical_url`
=preferred identity URL; `application_url`=explicit destination for applying;
`source_job_id`=stable identifier; `original_url`=first discovered URL.

Canonical precedence: `link[rel="canonical"]` (first valid) > JSON-LD
`JobPosting.url` (first valid). A candidate is discarded if it fails safety,
domain, or destination checks, or if it points at a *different* job identity
(`_job_identity_key`: identity query param first, else last non-generic path
segment). A canonical equal to the detail URL adds nothing and is kept blank.

Application precedence: adapter `apply_hint` > explicit apply anchor > explicit
JSON-LD application field. Each candidate must pass the same policy, and a
candidate equal to the detail URL is rejected (detail URL is never an
application URL).

## 3. Handling of missing and conflicting URLs

- Missing canonical or application evidence -> `" "`; new jobs store
  `canonical_url = source_url` and `application_url = NULL`. Nothing is invented.
- Failed re-extraction on a later scrape never clears a previously valid
  canonical or application URL (`existing.canonical_url or ...` /
  `if application_url:`).
- Conflicting evidence is resolved by the documented precedence; a conflicting
  canonical that proves to be a different posting is rejected rather than used.

## 4. Tests passing / failing

- `tests/unit/test_url_extraction.py`: **20 passed**.
- `tests`: **138 passed** (118 prior + 20 new), 0 failures. Runtime ~4.3s.

```
.venv/bin/python -m pytest tests -q
```

Coverage mapping to the spec's cases: 1) absolute apply button,
2) relative apply resolution, 3) external ATS only when policy-allowed,
4) no fabrication on missing link, 5) failed extraction preserves existing app
URL, 6) canonical extraction+normalization, 7) canonical search page rejected,
8) multiple/malformed canonical tags, 9) valid JSON-LD `JobPosting.url`,
10) malformed + multiple JSON-LD, 11) conflicting canonical/JSON-LD/source,
12) tracking stripped identity kept, 13) `gh_jid` preserved,
14) search/company-careers/homepage never detail, 15) extracted URLs cannot
bypass Phase 2 gate, 16) API + Celery share the engine entry point (`run_source`)
— imported via source-text assertion because `backend.workers.tasks` needs
`celery`, which is not installed in `.venv` (pre-existing).

## 5. Schema limitations

None encountered. All required columns (`application_url`, `source_url`,
`canonical_url`, `original_url`, `final_url`, `redirect_chain`, `url_status`)
already exist; no migration was needed. No DB records were changed.

## 6. Remaining Phase 4 work

- Populate explicit `job_url_patterns` / `allowed_domains` for `_LegacyAdapter`
  (greenhouse/ashby/jobicy/myjobskenya); until then those sources fail closed.
- Fix Greenhouse `absolute_url` handling (search/careers URLs containing
  `gh_jid` must not become detail pages; construct detail from the board/id).
- Expand per-source allowed-application/ATS domains (external ATS links are
  currently accepted only when the host is in `allowed_domains`).
- Repair/rewrite `JobDeduplicator` (unused, raw-SQL, references columns that do
  not exist) and historical audit/repair.
- Remove dead `resolve_redirects` / `request_with_redirect` (L4 from Phase 2).
- Open security items deferred to Phase 5: DNS fail-open and rebinding/TOCTOU.

---

# Phase 4 — Source Configuration, ATS Reliability, Deduplication, Data Repair

**Status:** Implemented. No production records were modified; the historical
audit is strictly read-only. No schema migration.

## 1. Source-specific domain policies (`backend/scrapers/policy.py`)

New adapters declare `job_url_patterns` / `allowed_domains` on the class. The
legacy scrapers (`greenhouse`, `ashby`, `jobicy`, `myjobskenya`) now get an
explicit, evidence-based `SourcePolicy` applied by `_LegacyAdapter.__init__`:

| source | allowed domains | job-detail rule | identity param |
|---|---|---|---|
| greenhouse | `greenhouse.io` | `job-boards.greenhouse.io/<board>/jobs/<id>` | `gh_jid` |
| ashby | `ashbyhq.com` | `jobs.ashbyhq.com/<board>/<id>` | — |
| jobicy | `jobicy.com` | `/jobs/<id>-<slug>` | — |
| myjobskenya | `myjobskenya.com` | `/job/<slug>` | — |

`source_policy_report()` reports every registered source as
`adapter` / `legacy` / `unconfigured`; `unconfigured_sources()` surfaces the gap.
Current unconfigured sources: **`brightermonday`, `careerpointkenya`,
`wellfound`** (no adapter, no policy). An empty policy stays fail-closed.

## 2. ATS URL construction fixes (part 2)

- `greenhouse._fetch_board` now derives the detail URL from `board + id`
  (`job-boards.greenhouse.io/<board>/jobs/<id>`), sets `source_job_id`, and only
  falls back to `absolute_url` when it is verifiably an individual posting
  (`is_greenhouse_detail_url`). Search/careers URLs (`stripe.com/jobs/search`,
  `careers.airbnb.com/positions/...`) are rejected and the row is emitted with
  no URL rather than a wrong one; a warning is logged.
- `ashby._fetch_board` derives `jobs.ashbyhq.com/<board>/<id>`, sets
  `source_job_id`, and rejects non-posting `jobUrl`/`url` values.
- `jobicy` and `myjobskenya` now emit `source_job_id` (Jobicy `id`; MyJobsKenya
  derived from the `/job/<slug>` path).
- `build_adapter` raises typed `UnconfiguredSourceError` for unsupported
  sources. `IngestionEngine.run_source` catches adapter-construction failures,
  records an `ingestion_errors` row (`stage="adapter"`), and returns **without
  pausing** the source so it resumes once configuration is fixed.

## 3. Deduplication repair (part 3)

`JobDeduplicator` was rewritten against the current ORM (the previous version
issued raw SQL against an `AsyncSession`, called a missing `execute_one`, and
referenced non-existent columns; it was unused). Precedence now mirrors the
engine: (1) same source + `source_job_id`, (2) cross-source `fingerprint`,
(3) exact `canonical_url`/`original_url`. Fuzzy matching is only a fallback in
the pure `deduplicate_batch`, never a broadener in `find_duplicates`. Merging is
non-destructive (provenance union + blank-field fill; no row deleted).

Engine (`_persist_job`) additions: conservative exact-URL dedup step, and an
inner savepoint around the new-job flush that converts a unique-constraint
`IntegrityError` into a provenance merge on the winning `(source_id,
source_job_id)` row instead of failing the job.

## 4. Historical audit (part 4) — read-only

`scripts/audit_job_urls.py` opens SQLite in `mode=ro`, auto-detects the current
vs legacy schema, and emits a JSON report plus proposed (never applied) repair
actions with confidence/reason/rollback. Output goes to gitignored
`data/audit/`. Nothing is guessed: when the Greenhouse board slug was never
persisted, rows are `manual_review`, not auto-repaired.

| DB | schema | jobs | actions | notable issues |
|---|---|---|---|---|
| `work_bot_hunter.db` | current | 56 | 50 manual_review, 6 none | 50 greenhouse rows missing `source_url` (only `careers.airbnb.com/positions/<id>` in `application_url`; board slug absent) |
| `work_hunter.db` | legacy | 1366 | 1202 none, 164 manual_review | 164 rows with `gh_jid` but no board slug (99 at `stripe.com/jobs/search`, 65 `cribl.io`) |

No writes: DB mtime unchanged; connection is `file:...?mode=ro`.

## 5. Observability (part 5)

- Adapter construction failure -> `logger.error("[<src>] adapter unavailable: ...")`
  plus an `ingestion_errors` row.
- Legacy source without a policy -> `logger.warning(...)` and fail-closed.
- ATS scrapers warn when a URL is withheld.
- End-of-run summary: `seen/new/updated/dup/invalid/review/errors`.
- Rejections already logged via `withheld <url> (<status>): <reason>`; non-VALID
  persists are refused with a log.

## 6. Tests (part 6)

- `tests/unit/test_source_policies.py` — policy coverage, report shape,
  unconfigured surfacing, fail-closed, typed error.
- `tests/unit/test_ats_url_construction.py` — detail-URL recognisers,
  Greenhouse/Ashby construction, search/careers rejection, `source_job_id`
  propagation through `_LegacyAdapter`.
- `tests/unit/test_dedup.py` (extended) — identity precedence, batch dedup
  (exact + fuzzy + distinct), ORM `find_duplicates`.
- `tests/unit/test_url_audit.py` — schema detection, read-only guarantee,
  missing-`source_url` and `gh_jid` findings, no guessed URLs.
- `tests/unit/test_ingestion.py` (extended) — unconfigured source reported, not
  crashed.

```
.venv/bin/python -m pytest tests -q
```

Result: **164 passed** (138 prior + 26 new), 0 failures.

## 7. Deliberately not done

- No historical record was rewritten; the repair plan is a proposal only and
  requires explicit approval before any application.
- No guessed Greenhouse board slugs.
- DNS fail-open / rebinding (TOCTOU) and dead-code removal remain deferred to
  the security phase.

# Phase 5 — End-to-End Verification and Production Readiness: Implementation Report

Scope: verify the completed Phase 1–4 pipeline (correctness, security,
resilience, observability, deployment readiness) and apply only narrowly scoped
fixes for confirmed defects. No schema migration, no data rewrite, no production
record touched, no broad rewrite.

## 1. Baseline

- `git status` clean except unrelated local files (`frontend/package-lock.json`,
  `close`, `notes`) — excluded from commits.
- Entry point `backend/services/ingestion.py:IngestionEngine.run_source` is shared
  by the API (`POST /sources/{name}/ingest`), Celery (`backend/workers/tasks.py`)
  and the Telegram/periodic paths — one engine, asserted by test.
- Production path traced: registry → adapter (`factory.build_adapter`) →
  `fetch_listings` → per-listing candidate resolution → `fetch_with_policy`
  (per-hop SSRF/DNS) → `validate_job_page` gate → normalize → `_persist_job`
  (savepoint + dedup) → source metrics. Matches the Phase 1–4 design.

## 2. Findings (severity-rated)

| # | Severity | Finding | Evidence | Disposition |
|---|----------|---------|----------|-------------|
| F1 | Critical | Auth is non-functional. `get_current_user` accepts any non-empty Bearer token and returns a placeholder user; no route issues or verifies a JWT (`decode_access_token` is unused) and there is no login endpoint. | `backend/api/deps.py:33`; `backend/security/__init__.py:32` | **Not fixed** (needs a real auth service / user store — out of narrow-fix scope). **Release blocker.** All mutating routes now at least require *a* token. |
| F2 | High | Source-mutating endpoints (`POST /sources/{name}/ingest`, `/pause`, `/resume`) had **no** auth dependency. | `backend/api/routes/sources.py` | **Fixed**: added `Depends(get_current_user)`. |
| F3 | High | CV upload wrote to `/tmp/cvs/{client filename}` — path traversal + arbitrary unauthenticated file write (and delete via `cv_file_path`); no size or extension enforcement. | `backend/api/routes/candidates.py:117` (pre-fix) | **Fixed**: `os.path.basename`, UUID filename, extension allowlist, 10 MB cap, storage under `settings.cv_storage_path`. |
| F4 | High | DNS resolution failure was **fail-open**: an unresolvable host yielded an empty address set, which passed the SSRF check (`return True`). | `backend/sources/urls.py:_url_is_safe_async` (pre-fix) | **Fixed**: `_classify_url_safety` returns `safe`/`unsafe`/`unverified`; unverifiable destinations are refused. |
| F5 | Medium | Negative DNS results were cached for the process lifetime, so a transient failure would permanently lock a host out once fail-closed was introduced. | `backend/sources/urls.py:_resolve_host_ips_cached` (pre-fix) | **Fixed**: only non-empty resolutions are cached. |
| F6 | Medium | CORS `allow_origins=["*"]` with `allow_credentials=True` — invalid per spec and a misconfiguration. | `backend/api/app.py` (pre-fix) | **Fixed**: `allow_credentials=False` (auth is Bearer, not cookies). |
| F7 | Medium | Rate-limit detection was dead code: `RateLimiter.record_response` was never called, so `should_pause` could never fire and 429/5xx never throttled a source. | `backend/services/ingestion.py` | **Fixed**: detail fetches now call `limiter.record_response`; wired through `_process_listing`/`_fetch_and_validate`. |
| F8 | Medium | No application logging configuration: the run-summary `logger.info` lines were suppressed at the default root level. | `backend/api/app.py` | **Fixed**: `logging.basicConfig(level=INFO)` in `create_app`. |
| F9 | Medium | No `.dockerignore`; the `Dockerfile` does `COPY . .`, so `.env`, `*.db`, `venv/` and `frontend/node_modules` could be baked into the image. | repo root | **Fixed**: added `.dockerignore`. |
| F10 | Medium | Unbounded HTTP response body: `fetch_with_policy` uses `client.get` and buffers the whole body; no size limit (DoS via large page). | `backend/sources/urls.py:665` | **Documented**; streaming cap is a larger change than a narrow fix. Recommended pre-scale. |
| F11 | Low | Stale tracked runtime files `bot.pid`, `frontend.pid`; `bot.sh` hardcodes a wrong `BOT_DIR`. | `git ls-files`; `bot.sh` | **Documented** (untrack + fix path). |
| F12 | Low | `structlog`/`tenacity` in `requirements.txt` but unused; `celery` not installed in the current venv so `backend/workers/tasks.py` cannot be imported here. | `requirements.txt` | **Documented**. |

## 3. Residual security risk (explicitly NOT claimed as solved)

- **DNS rebinding / TOCTOU (F4 residual).** `fetch_with_policy` re-resolves and
  re-checks each hop, but the address can still change between the check and the
  socket connect. This is **not** eliminated. Mitigation: run egress through a
  proxy that enforces the same private-range policy. This was deferred in
  `notes` and is now resolved to the extent that *unverifiable* hosts fail
  closed; rebinding remains open by design.
- **SSRF policy is per-hop and fail-closed for private ranges** (loopback, RFC1918,
  link-local, reserved, multicast, unspecified) including encoded IPv4 forms and
  IPv4-mapped IPv6; non-web ports `{80,443,8080,8443}` only.
- **SQL injection:** none found. All queries use SQLAlchemy expressions; the only
  raw SQL is `ALTER TABLE {table} ADD COLUMN {name} {definition}` from a static
  internal dict, never user input.
- **Secrets in logs:** none found. `secret_key`/`encryption_key` default to
  `change-me` and **must** be overridden in `.env` before deployment.

## 4. End-to-end verification (new tests)

`tests/integration/test_e2e_ingestion.py` (12) — mocked HTTP + isolated temp DB:
valid posting persisted with distinct, validated canonical/application URLs;
search/category/company rejected as INVALID and a bare `/careers` withheld;
expired (410 / "removed") rejected; 429 withheld as NEEDS_REVIEW; a withheld
update never overwrites a valid record; ATS id survives normalization; redirect
to `10.0.0.5` is blocked and never requested; an unresolvable host is fail-closed
and never requested; re-ingestion creates no duplicate; distinct postings are not
merged; API and Celery share `IngestionEngine.run_source`; source mutations
require auth.

`tests/integration/test_api_security.py` (5) — CV filename sanitization stays in
storage, bad extension rejected, oversized rejected, missing/empty token → 401,
CORS credentials disabled under wildcard.

`tests/unit/test_validation_gating.py` (+2) — DNS failure is fail-closed, not
cached, and classified distinctly from "unsafe".

## 5. Tests passing / failing

```
.venv/bin/python -m pytest tests -q
```

Result: **183 passed** (164 prior + 19 new), 0 failures.

## 6. Release readiness / go-no-go

- **Go only after F1 is resolved.** The API currently authenticates nobody;
  everything except `get_current_user` being a stub. This is the single hard
  blocker.
- **Schema management:** Alembic `versions/` is empty; schema is created by
  `Base.metadata.create_all` plus idempotent additive `ALTER TABLE` on every
  startup. Reversible migrations are **not** available. `BOOLEAN DEFAULT 0` in
  `_ADDITIVE_COLUMNS` is SQLite-oriented and must be verified on PostgreSQL
  before a Postgres rollout. Backups: SQLite file copy; Postgres `pg_dump`.
- **Worker:** `POST /sources/{name}/ingest` runs the full scrape inline in the
  request; production should dispatch to Celery instead.
- **Repair tooling:** `scripts/audit_job_urls.py` is read-only and never
  auto-runs; no data was modified by this phase.
- **Config:** `SECRET_KEY`/`ENCRYPTION_KEY` must be set; `.env` is gitignored and
  now excluded from Docker builds.

## 7. Files changed (Phase 5)

- `backend/sources/urls.py` — fail-closed destination classification, no negative
  DNS caching, docstrings.
- `backend/services/ingestion.py` — rate-limit `record_response` wiring.
- `backend/api/routes/sources.py` — auth on ingest/pause/resume.
- `backend/api/routes/candidates.py` — CV upload traversal/size/type hardening.
- `backend/api/app.py` — CORS credentials + logging config.
- `.dockerignore` — new.
- `tests/integration/test_e2e_ingestion.py`, `tests/integration/test_api_security.py` — new.
- `tests/unit/test_validation_gating.py` — DNS fail-closed tests.

