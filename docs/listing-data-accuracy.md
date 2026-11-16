# Listing Data Accuracy Baseline (Pre-LLM)

Date: 2026-11-15
Dataset: local `work_bot_hunter.db` (372 jobs, 4 sources)
Scope: accuracy and completeness of stored listing data, not candidate match quality.

This is a **deterministic extraction baseline**. It measures what the current
pipeline actually stores, spot-checks correctness against live pages, and
identifies the bugs that must be fixed before an LLM is introduced.

> "Accuracy" here is field completeness plus verified correctness. A rigorous
> precision/recall number requires the golden dataset described in the
> remediation plan.

## Headline

The dataset is **not ready to serve as an LLM baseline**.

- Only **126 / 372 jobs (33.9%)** come from a currently crawlable source
  (`jobicy`). The other **246 (66.1%)** come from sources that are disabled or
  not currently crawlable (`myjobmag` 169, `fuzu` 27, legacy `greenhouse` 50).
- **Salary amounts: 0 / 372.**
- **Posted dates: 0 / 372**, even though every source exposes one.
- **Application URLs: at most 24 / 372 (6.5%) usable**; 126 jobicy rows point
  to a site-wide "Submit a Guest Post" page.
- **Descriptions: 219 / 372 (58.9%) empty.**
- **Locations: 193 / 372 (51.9%) are a fabricated `Nairobi` default**, not
  source data.
- **Risk analysis: 50 / 372 (13.4%)**, all from manual API calls; ingestion
  never runs the risk engine.
- **Jobicy link rot: 20 / 30 sampled job URLs returned HTTP 410** (~70% expired).

## Phase 1 Implementation Status (2026-11-15)

The deterministic fixes below are implemented and covered by regression tests.
They affect **new and re-scraped rows**. The 372-row baseline was repaired on
2026-11-16 after taking a backup (`data/backups/`):

- 132 application URLs cleared (126 site-wide `submit-guest-post`, 6 equal to
  the detail page);
- 25 `salary_currency` values without an amount cleared;
- 246 rows from disabled sources quarantined (`myjobmag` 169, `greenhouse` 50,
  `fuzu` 27).

Post-repair the normal job views expose **126 rows, all `jobicy`**. The
remaining 67 application URLs belong to quarantined rows and were left intact
because they look like genuine per-posting links. Dates still need a re-scrape:
repair cannot invent them.

| Defect | Fix |
|---|---|
| `currency` vs `salary_currency` key mismatch | Adapters emit both; the normalizer reads either. Currency is dropped when no salary amount exists. |
| Fabricated `Nairobi` location | Empty locations stay empty; no default is invented. |
| Dates never persisted | `posted_at` / `closing_at` are parsed (ISO-8601, RFC-2822, date-only, year-less listing dates) and stored as UTC datetimes. |
| `remote_type` / `salary_period` never persisted | Both are normalized and written on insert and re-scrape. |
| Jobicy detail enrichment called JSON on HTML | Legacy adapter parses schema.org `JobPosting` from the fetched HTML first; the legacy fetcher is only a fallback. |
| Jobicy `jobIndustry` treated as skills | Industry is no longer mapped to skills; skills come from the description. |
| Jobicy pagination ignored | `nextCursor` / `hasMore` pagination replaces the rejected `page` parameter. |
| Jobicy `jobType` list | Employment type lists are flattened and normalized (`FULL_TIME` → `full-time`). |
| Navigation anchor chosen as apply URL | Apply-link selection ignores `nav`/`header`/`footer`, rejects site-wide paths, and rejects links back to the detail page. JSON-LD `applicationUrl` is the fallback. |
| Non-crawlable rows mixed into metrics | `scripts/repair_listing_data.py` can quarantine rows from disabled sources; `status='quarantined'` is excluded from job lists, search, and stats unless `include_quarantined=true` is passed. A validated re-scrape clears the quarantine. |

Measurement and repair tooling:

```bash
python scripts/data_quality_report.py --db work_bot_hunter.db
python scripts/repair_listing_data.py --db work_bot_hunter.db          # dry run
python scripts/repair_listing_data.py --db work_bot_hunter.db --apply  # write
```

## Field Scorecard (baseline snapshot, before Phase 1 fixes)


| Field | Non-empty | Estimated correct | Main issue |
|---|---:|---:|---|
| Title | 372 (100%) | ~315 (84.7%) | 57 myjobmag titles include ` at <Company>` |
| Company | 210 (56.5%) | ~206 (55.4%) | 162 empty; 4 myjobmag rows have company == title |
| Location | 372 (100%) | ~179 (48.1%) | 169 myjobmag + 24 fuzu rows use the `Nairobi` default |
| Description | 153 (41.1%) | 153 | 0 myjobmag, 0 greenhouse; jobicy/fuzu populated |
| Skills | 139 (37.4%) | partially | jobicy seeds skills from `jobIndustry` categories |
| Salary min/max | 0 (0%) | 0 | Never populated; jobicy API omits amounts |
| Salary currency | 25 (6.7%) | 0 verified | All 25 are fuzu `KES` inferred from location |
| Posted at | 0 (0%) | 0 | Available from every source, never persisted |
| Closing at | 0 (0%) | 0 | Available from jobicy/fuzu, never parsed or persisted |
| Remote type | 0 (0%) | 0 | `remote` boolean only (126 true, 246 default false) |
| Employment type | 0 (0%) | 0 | 322 `unknown`, 50 null |
| Application URL | 199 (53.5%) | ~24 (6.5%) | 126 wrong jobicy URLs, 33 greenhouse 404s |
| Canonical / final URL | 322 (86.6%) | 322 | 50 legacy greenhouse rows have null URLs |
| Risk score/level | 50 (13.4%) | 50 | `analyzed_at` is null for all 372 |
| Fingerprint | 372 (100%) | n/a | 0 duplicates today; inputs are unreliable |

## Source Breakdown

| Source | Rows | Status | Description | Skills | Company | Salary | Application URL |
|---|---:|---|---:|---:|---:|---:|---:|
| myjobmag | 169 | Disabled (permission REVIEW) | 0% | 2% | 4% | 0% | 12% |
| jobicy | 126 | Active, permitted | 100% | 95% | 100% | 0% | 100% (all wrong) |
| greenhouse | 50 | Disabled pending config; legacy seed | 0% | 10% | 100% | 0% | 100% (86% dead) |
| fuzu | 27 | Disabled (terms prohibit) | 100% | 37% | 100% | 0% | 11% |

### myjobmag (169 rows)

- All 169 locations are `Nairobi`, which is the normalizer's empty-value default.
- 162 / 169 companies are empty. 4 companies equal the title.
- 57 titles still contain ` at <Company>` (e.g. `Teacher of English - Primary
  School at Excelon Limited`).
- 0 descriptions: the adapter looks for `article`, `.job-content`, `.content`,
  and `.job-info`, but the live detail page uses `.job-details` and
  `.job-description`.
- The listing card's company/date text is not parsed. The card shows
  `Title at Company | description | 14 November`; the date regex requires a
  4-digit year, so no date is extracted.
- 17 application URLs are `/job-application/<id>` links; 10/10 sampled were
  live. 3 rows incorrectly use the detail URL as the application URL.

### jobicy (126 rows)

- 126 / 126 application URLs are `https://jobicy.com/submit-guest-post`.
  The live page contains a navigation/footer anchor `Submit a Guest Post`
  before the real `Apply for this job` / `Apply now` anchors.
- `find_explicit_apply_url` matches any anchor whose text contains `submit`,
  regardless of position or job context.
- Detail enrichment is broken. `_LegacyAdapter.parse_detail` calls
  `JobicyScraper.fetch_job_details(url)`, which calls `fetch()` expecting JSON
  on an HTML page. It logs `Expecting value: line 1 column 1` and returns `{}`.
- The detail page's JSON-LD `JobPosting` contains `description`, `datePosted`,
  `validThrough`, `baseSalary`, `employmentType`, and `hiringOrganization`,
  none of which are used.
- The API returns `salaryCurrency` for most jobs (37/50 in a live sample) but
  never `annualSalaryMin`/`annualSalaryMax` (0/50). The currency is dropped by
  the `currency` vs `salary_currency` key mismatch.
- `jobIndustry` is mapped into `skills`, so category labels such as `sales`,
  `customer support & success`, and `product & operations` pollute the skill
  list.
- 20 / 30 sampled job URLs returned HTTP 410 (expired) and 1 returned 404.

### greenhouse (50 rows, legacy seed from 2026-08-17)

- `source_url`, `canonical_url`, and `final_url` are null; `url_status` is
  `NEEDS_REVIEW`. These rows predate the current validation gate.
- Description and skills are empty.
- Application URLs point at `careers.airbnb.com`. Of 50 sampled:
  33 returned 404, 10 were unreachable, and 7 returned a 301. At most 7 are
  directly usable.
- The current legacy detail path is also wrong: it calls the Greenhouse
  boards API with a `job-boards.greenhouse.io` HTML URL.

### fuzu (27 rows)

- Listing company/location/date are empty because the adapter only looks for
  `.company` / `.job-location` classes; the live card is a styled-components
  block containing `Company | Title | Location | Posted: 12 Nov 2026`.
- Detail JSON-LD does populate company, description, and `posted_at`, but
  `posted_at` is dropped at persistence.
- 24 / 27 locations are the `Nairobi` default. 25 / 27 currencies are `KES`
  inferred from that default, with no salary amount.

## Confirmed Defects

### Extraction / normalization

1. **Currency key mismatch.**
   `ListingItem.as_raw()` emits `"currency"` (`backend/scrapers/adapter.py`),
   but `JobNormalizer._normalize_salary` reads `"salary_currency"`
   (`backend/services/normalizer.py`). Adapter-supplied currencies are always
   discarded.
2. **Currency inferred without an amount.**
   `_normalize_salary` calls `_detect_currency(location)` even when
   `salary_min` and `salary_max` are both null. This creates 25 fuzu `KES`
   values with no salary.
3. **Location default fabricates data.**
   `_normalize_location("")` returns `"Nairobi"`. This makes myjobmag and fuzu
   look 100% complete while 193 rows have no source location.
4. **Employment type never reaches the normalizer.**
   `ListingItem` has no `employment_type` field; jobicy `jobType` and fuzu
   JSON-LD `employmentType` are dropped.
5. **Jobicy industry used as skills.**
   `jobIndustry` is assigned to `skills` in `backend/scrapers/jobicy.py`.
6. **Myjobmag selectors and title/company split are stale.**
   Detail parsing targets selectors that no longer exist; listing titles keep
   ` at <Company>`; company/date are not extracted from the card text.
7. **Fuzu listing parser ignores card text.**
   Company/location/date are in the card, not in child elements with the
   expected class names.

### URL pipeline

8. **Application URL selection matches site chrome.**
   `find_explicit_apply_url` (`backend/sources/urls.py`) scans every anchor and
   accepts any text containing `submit` or `apply`. Jobicy's `Submit a Guest
   Post` navigation link wins before the job's real apply link.
9. **Jobicy application URL is not job-specific.**
   126 rows share one URL. A valid application URL must be distinct from the
   detail URL and must not be a site-wide navigation target.
10. **Greenhouse application URLs are mostly dead.**
    No link-health check is performed at ingestion or on a schedule.

### Persistence

11. **`posted_at`, `closing_at`, `remote_type`, and `salary_period` are not
    persisted.** The `Job` insert/update paths in
    `backend/services/ingestion.py` never set them. `closing_at` is also absent
    from the normalizer output.
12. **`requirements` and `responsibilities` stay at the `"[]"` default.**
13. **`raw_hash` is never populated** (0 / 372).

### Risk / scoring

14. **Risk analysis is not part of ingestion.**
    `RiskEngine` is only invoked from `POST /jobs/{id}/analyze`
    (`backend/api/routes/jobs.py`). 322 rows have `risk_score = 0` and all 372
    have `analyzed_at = null`.

### Provenance

15. **The dataset mixes permitted and non-permitted sources.**
    Among the sources present here, only jobicy is currently crawlable.
    myjobmag and fuzu are disabled by permission/terms; greenhouse is disabled
    pending configuration. Reporting on the combined 372 hides this.

## What This Means for an LLM

An LLM cannot recover facts that were never fetched or persisted. Feeding the
current dataset to an LLM would:

- train/evaluate on fabricated locations and currencies;
- see 59% empty descriptions and 0% salary data;
- treat industry categories as skills;
- send users to a guest-post page or dead links;
- mix data from sources that are no longer permitted to be crawled.

The correct order is: **fix deterministic extraction and persistence first,
then use the LLM only for enrichment that rules cannot handle.**

## Pre-LLM Remediation Plan

### Phase 0 — Quarantine and measurement (1–2 days)

1. Add a `scripts/data_quality_report.py` that computes, per source:
   completeness, distinct-value checks, application-URL equality, link health,
   duplicate rate, and field-level accuracy against a golden set.
2. Snapshot the current 372-row baseline before changing code.
3. Quarantine rows from non-crawlable sources (`myjobmag`, `fuzu`, legacy
   `greenhouse`) or mark them with a clear provenance status. Do not mix them
   into "current" metrics.
4. Add DB invariants:
   - `url_status = VALID` requires `source_url` and `canonical_url`;
   - `application_url` must not equal `source_url`;
   - `salary_currency` requires at least one salary amount;
   - `posted_at` / `closing_at` must be parseable timestamps;
   - `location` must be source-derived or explicitly marked inferred.

### Phase 1 — Deterministic fixes (3–5 days)

1. **Salary:** use one key (`salary_currency`) end-to-end; never infer currency
   without an amount; parse salary text only when a real amount is present.
2. **Location:** stop defaulting to `Nairobi`; store null/`unknown` and record
   whether the value was extracted or inferred.
3. **Persistence:** persist `posted_at`, `closing_at`, `remote_type`, and
   `salary_period`; parse source dates to timezone-aware datetimes.
4. **Jobicy:**
   - parse JSON-LD `JobPosting` on the detail page (description, salary,
     `datePosted`, `validThrough`, `employmentType`, location);
   - stop using `jobIndustry` as skills; store it separately or drop it;
   - map `jobType` to `employment_type`;
   - fix application URL selection (see next item).
5. **Application URLs:** require apply-specific context, exclude navigation and
   footer regions, reject site-wide links, and require a distinct job-specific
   target. Prefer explicit ATS/`applicationUrl` evidence over anchor text.
6. **Myjobmag (only if re-enabled):** split `Title at Company`, parse
   `.job-details` / `.job-description` / `.job-key-info`, parse `14 November`
   dates, and stop fabricating location.
7. **Fuzu (only if re-enabled):** parse the card text for company, location,
   posted date, and closing date.
8. **Greenhouse:** re-scrape through the boards API with a working detail path;
   purge or replace the 50 legacy rows; validate application URLs.
9. **Risk:** run `RiskEngine` during ingestion or in a scheduled batch, and set
   `analyzed_at`.
10. **Tests:** add HTML fixtures for one live page per source and regression
    assertions for title, company, location, description, salary, dates, and
    application URL.

### Phase 2 — Accuracy gates (2–3 days)

Build a manually labeled golden set of 100–200 listings, stratified by source,
and compute field-level precision/recall/exact-match. Suggested release gates
for approved sources:

| Field | Target |
|---|---:|
| Title exact match | ≥ 95% |
| Company exact match | ≥ 90% |
| Location exact match (where source provides it) | ≥ 90% |
| Description present | ≥ 90% |
| Posted date present (where source provides it) | ≥ 90% |
| Application URL precision | ≥ 95% |
| Dead-link rate at ingestion | < 5% |
| Duplicate rate | < 2% |
| Salary amount coverage | reported, not forced |

Do not start LLM work until these gates are met or explicitly waived.

### Phase 3 — LLM only for enrichment

Use the LLM for:

- summarizing long descriptions;
- normalizing skill synonyms and seniority language;
- classifying role family or remote/hybrid policy from free text.

Never use the LLM to invent company names, locations, salaries, dates, or
application URLs. Every LLM output should be validated against deterministic
rules and logged with model/version/confidence so it can be evaluated against
the golden set.

## Recommended Immediate Order

1. ~~Add the data-quality report script and snapshot the baseline.~~ Done:
   `scripts/data_quality_report.py`.
2. ~~Fix the `currency` / `salary_currency` mismatch and remove currency
   inference without an amount.~~ Done.
3. ~~Persist `posted_at` / `closing_at` / `remote_type` / `salary_period`.~~ Done.
4. ~~Fix jobicy JSON-LD enrichment and application URL selection.~~ Done.
5. ~~Quarantine non-crawlable source rows; purge or re-scrape the greenhouse
   seed.~~ Repair applied on 2026-11-16; greenhouse rows are quarantined, not
   purged. Decide later whether to re-scrape them via the boards API.
6. ~~Re-run the report and compare before touching any LLM integration.~~ Done;
   post-repair snapshot in `data/quality/`.
7. Re-scrape `jobicy` so dates, salary, and JSON-LD enrichment populate the
   currently visible rows, then re-run the report against the Phase 2 gates.
