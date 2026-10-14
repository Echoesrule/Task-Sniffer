# Task Sniffer — Job Source Directory

Updated: 14 October 2026

## Purpose

A consolidated list of job sources to evaluate for Task Sniffer. A source
being listed here does not mean its scraper/API integration has been
implemented or verified. Check each site's terms, available APIs, access
rules, and URL-validation requirements before integrating it.

---

## 1. Kenyan job boards

### BrighterMonday Kenya

- URL: https://www.brightermonday.co.ke/
- Potential coverage: Kenyan entry-level roles, graduate opportunities,
  internships, and software/data jobs.
- Integration note: Validate individual job-detail URLs and direct
  application URLs; measure relevance and duplicate rates.

### Fuzu

- URL: https://www.fuzu.com/
- Potential coverage: Kenyan and broader African opportunities, including
  technology roles.
- Integration note: Check current listing access and whether a supported
  public API or permitted feed is available.

### MyJobMag Kenya

- URL: https://www.myjobmag.co.ke/
- Potential coverage: Kenyan vacancies, including local employer and
  technology roles.
- Integration note: Prioritize junior, graduate, internship, Python, and
  full-stack matches.

---

## 2. Employer applicant-tracking system (ATS) job boards

### Greenhouse

- Public job-board URL pattern: https://job-boards.greenhouse.io/
- Potential coverage: Individual employers using Greenhouse.
- Integration note: Preserve job identity parameters such as `gh_jid`
  where required. Verify that each result is an individual vacancy, not a
  company careers/search page.

### Lever

- Public job-board URL pattern: https://jobs.lever.co/
- Potential coverage: Individual employers using Lever.
- Integration note: Validate employer/job paths and final redirect
  destinations.

### Ashby

- Public job-board URL pattern: https://jobs.ashbyhq.com/
- Potential coverage: Individual employers using Ashby.
- Integration note: Confirm the URL points to a specific published job and
  retain stable job identifiers.

### Workable

- Public job-board URL pattern: https://apply.workable.com/
- Potential coverage: Individual employers using Workable.
- Integration note: Validate detail and application destinations
  independently.

> **ATS implementation note:** These are platforms used by many employers,
> not single centralized job boards with identical listings. Discover
> supported employer boards, respect each platform's access rules, and
> avoid treating generic company pages as job records.

---

## 3. International / remote job boards

### Remote OK

- URL: https://remoteok.com/
- Potential coverage: Remote roles across technical and other job
  categories.
- Integration note: Filter for location eligibility, role level, posting
  freshness, and duplicate listings.

### We Work Remotely

- URL: https://weworkremotely.com/
- Potential coverage: Remote jobs, including software development roles.
- Integration note: Verify that roles accept applicants located in Kenya or
  otherwise match the user's eligible region.

---

## 4. Professional networks / social job platforms

### LinkedIn

- URL: https://www.linkedin.com/jobs/
- Status: **deferred** — not fetched for now. LinkedIn has no self-serve
  public Jobs API; access is partner/paid-gated. Revisit only if approved
  API access becomes available.
- Potential coverage: Global professional roles across all experience
  levels and industries; a large volume of technology and remote postings.
- Integration note: LinkedIn's Terms of Service prohibit automated
  scraping, and its public job pages are aggressively rate-limited and
  protected by anti-bot measures. Do not scrape the public site. Pursue an
  approved access method only — the official LinkedIn Jobs API or partner /
  "Apply with LinkedIn" programs, a permitted feed, or manual import — and
  otherwise keep the source **RESTRICTED**. Keep job-detail, canonical, and
  application URLs as separate fields; never fabricate or guess an
  application URL.

---

## 5. Recommended implementation order

**Batch 1 — Kenyan job boards:**

- BrighterMonday Kenya
- Fuzu
- MyJobMag Kenya

**Batch 2 — Direct employer/ATS listings:**

- Greenhouse
- Lever
- Ashby
- Workable

**Batch 3 — International remote job boards:**

- Remote OK
- We Work Remotely

**Batch 4 — Professional networks (approved access only):**

- LinkedIn (official API / partner access required; do not scrape)

---

## 6. Metrics to track per source

- Valid job-detail URL rate
- Valid application URL rate
- Relevance rate for target roles and experience level
- Unique job yield after deduplication
- Listing freshness / age
- Fetch failures, anti-bot responses, and validation outcomes
- Number of suitable listings that lead to actual applications and
  responses

---

## 7. Security and data-quality checklist

- Apply the same outbound-fetch and redirect security policy to every
  source.
- Do not automatically trust a URL merely because it came from a known job
  board.
- Keep job-detail, canonical, and application URLs as separate fields.
- Never fabricate an application URL or silently use a generic careers page
  as one.
- Preserve meaningful query parameters needed for job identity.
- Validate final redirect destinations and block unsafe hosts/IPs.
- Deduplicate conservatively and retain provenance/source information.
- Check site terms, robots rules where applicable, and API/feed
  availability before implementing a scraper.
- Test a source on a small sample before enabling scheduled ingestion.
- Keep credentials and bot/API tokens out of source code, logs, and version
  control.

---

## Important

This directory is a planning list, not a statement that all sources are
currently integrated, scrapeable, or available through public APIs. Confirm
current access methods and each site's rules before implementation.
