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

---

## 8. Registered source configuration (reviewed 23 October 2026)

Registration does not mean ingestion is enabled. The shared runner only
considers sources whose registry policy permits crawling and whose runtime
status is active. New sources below remain disabled unless the table says an
existing reviewed adapter is already in use.

| Source | Discovery/access | Adapter | Current activation |
|---|---|---|---|
| Fuzu | HTML is technically available, but the current Service Terms prohibit automated scraping/extraction | Existing FuzuAdapter | Disabled, RESTRICTED pending written authorization or an approved feed |
| MyJobMag Kenya | HTML /jobs and query-free /job/<slug> detail pages; current robots blocks all query-string URLs; terms do not clearly authorize automated extraction | Existing MyJobMagAdapter | Disabled, REVIEW pending permission review; config corrected from RSS to HTML |
| Corporate Staffing Services | HTML job archive, subject to the existing repository audit | Existing CorporateStaffingAdapter | Existing approved configuration retained; current terms/robots could not be independently reverified |
| BrighterMonday Kenya | HTML/sitemap discovery is visible, but current robots disallows /job/ detail paths; no permitted end-to-end detail method or terms approval established | Legacy scraper is stale and is not factory-registered | Disabled, REVIEW |
| Career Point Kenya | HTML is a candidate method; current robots/terms were not verifiable in this review | No adapter | Disabled, REVIEW |
| JobWeb Kenya | No current permitted discovery method verified | No adapter | Disabled, REVIEW |
| Greenhouse | Official public Job Board API GET; requires each employer's board token | Existing API adapter | Disabled by default; requires a known board token and GREENHOUSE_ENABLED=true |
| Ashby | Official public posting API; requires each employer's job-board name | Existing API adapter | Disabled by default; requires a known board name and ASHBY_ENABLED=true |
| Workable | Documented public published-jobs endpoint; the authenticated SPI API is separate and requires an employer-issued r_jobs token | WorkableAdapter parses the public endpoint | Disabled, REVIEW until downstream third-party display/redistribution is approved |
| Remotive | Public API and RSS exist | No active adapter | Restricted pending written permission: current Terms prohibit automated extraction/redistribution without it |
| LinkedIn | No permitted public job retrieval method established | No adapter | Restricted; never scrape |
| Fiverr | Freelance-gig marketplace, not a job-board adapter; no general public gig API established | No adapter | Restricted; never scrape without authorized access |

### ATS board configuration

Greenhouse and Ashby board identifiers are public routing identifiers, not
secrets. Configure only employer boards that have been individually selected:

~~~dotenv
GREENHOUSE_ENABLED=false
GREENHOUSE_BOARD_TOKENS=
ASHBY_ENABLED=false
ASHBY_BOARD_NAMES=
~~~

The values are comma-separated. Both a non-empty identifier list and the
matching explicit enable flag are required. Do not place Workable employer SPI
tokens in these fields. WORKABLE_ACCOUNT_SUBDOMAINS configures the documented
public account endpoint for tests or a future reviewed activation; it does not
grant third-party redistribution permission and cannot enable the current
REVIEW source.

No universal Greenhouse or Ashby endpoint enumerates all employers. Discover
and configure employer board identifiers individually; never guess slugs.

### Evidence and limitations

- Greenhouse's official Job Board documentation says GET data is public without
  authentication and exposes jobs per board token:
  https://developers.greenhouse.io/job-board.html
- Ashby's official posting API requires a job-board name in its path:
  https://developers.ashbyhq.com/docs/public-job-posting-api
- Workable documents a public published-jobs endpoint for custom careers pages
  and documents SPI /jobs separately with the r_jobs scope:
  https://help.workable.com/hc/en-us/articles/115012771647-Using-the-Workable-API-to-create-a-careers-page
- Fuzu's current Global Service Terms prohibit automated scraping/extraction
  without authorization:
  https://www.fuzu.com/legal/terms
- MyJobMag's robots file permits only selected path patterns, while its terms
  page (revised 2012) does not clearly address automated job-data extraction;
  the registry therefore keeps it disabled pending permission review:
  https://www.myjobmag.co.ke/robots.txt and https://www.myjobmag.co.ke/terms
- Remotive's current Terms of Use prohibit automated access and redistribution
  without written permission. Its API page additionally requires attribution
  and a backlink and restricts some third-party listing and signup uses:
  https://remotive.com/terms-of-use and https://remotive.com/remote-jobs/api
- LinkedIn's current User Agreement explicitly prohibits scraping/copying with
  crawlers and bots. Developer portal access by itself is not permission for
  this use:
  https://www.linkedin.com/legal/user-agreement
- Fiverr's Community Standards state that scraping data from the platform is
  prohibited:
  https://help.fiverr.com/hc/en-us/articles/37554441398929-Our-Community-Standards

The current BrighterMonday robots file disallows /job/ and publishes listing
sitemaps; this does not by itself authorize fetching those job pages. Current
robots or terms for Career Point, JobWeb and Corporate Staffing were not
independently confirmed by the available documentation fetch. Existing
Corporate Staffing activation was retained from the repository's prior source
audit; reverify before changing its configuration.
