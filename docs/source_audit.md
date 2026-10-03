# Task Sniffer — Milestone 1: Source Access Audit

Audit date: 2026-08-30
Scope: the eight priority sources from the ingest spec, section 4.
Method: robots.txt inspection, live checks for published sitemaps/feeds/APIs,
public documentation. Nothing was crawled beyond these signals.

Verdict values: `permission_status` in {APPROVED, API, REVIEW, RESTRICTED, DISABLED}.

---

## Verdicts

| # | Source | Domain | robots.txt | Access method | permission_status | notes |
|---|--------|--------|------------|---------------|-------------------|-------|
| 1 | MyJobMag Kenya | myjobmag.co.ke | Partial | `html` (rss optional) | **APPROVED** | Robots disallows all query-string URLs (`/*?`), `/search/jobs?*`, `/apply-now/`, `/job-application/`. `/jobs` listing + detail pages `/job/<slug>` are allowed. Feed endpoint unverified (`/feeds/` is a widget page, not an RSS file) → use HTML by default; a verified feed URL can be set via `feed_url`. |
| 2 | BrighterMonday Kenya | brightermonday.co.ke | Unclear/NA | `html` | **REVIEW** | No public API found. robots.txt at the real `.co.ke` domain did not resolve; existing adapter pointed at the wrong domain (`.com`). Confirm robots/terms and polite HTML access before enabling. Detail pages embed JSON-LD `JobPosting`. |
| 3 | Fuzu | fuzu.com | Allowed | `html` (+ sitemap) | **APPROVED** | robots.txt only excludes apply-tracking params. Publishes `kenya/sitemap-job-listings.xml.gz`. Strong candidate for first adapter. |
| 4 | Career Point Kenya | careerpointkenya.co.ke | Allowed | `html` | **APPROVED** | WordPress + Yoast, full disallow block empty, sitemap published. Crawl with delay. |
| 5 | Corporate Staffing Services | corporatestaffing.co.ke | Allowed | `html` | **APPROVED** | robots.txt allows all UAs (Bingbot crawl-delay 30). WordPress job board. |
| 6 | Public Service Commission | publicservice.go.ke + psckjobs.go.ke | Allowed | `html` | **APPROVED** | Government, very high provenance. Vacancy adverts public on `/jobs/`; applications go through the psckjobs.go.ke portal (account). `requires_auth=True` for *applying* only; listing public. Never charge-related fraud signals note: PSC publicly states no fees. |
| 7 | KRA Careers | kra.go.ke | Absent (404) | `html` | **APPROVED** | No robots.txt (no explicit restriction). Careers list + detail pages public; application through erecruitment.kra.go.ke (account). Very high provenance. |
| 8 | Wellfound | wellfound.com | Blocked (403) | none identified | **RESTRICTED** | Cloudflare returns 403 even for `/robots.txt` and the public `/api/v1/jobs` endpoint. Automated access not permitted/blocked. Do not scrape. Requires official API/partnership → keep RESTRICTED. |

---

## Access method priority (per spec §1)

1. Official API
2. Official RSS/Atom feed
3. Permitted public HTML
4. Partner/affiliate feed
5. Manual/import

## Approved to implement now (Milestone 2 core)

- **Fuzu** — `html` / sitemap, APPROVED
- **MyJobMag Kenya** — `html` primary (robots-compliant: `/jobs` + `/job/<slug>` only, no query URLs), OPTIONAL rss via `feed_url`, APPROVED
- **Corporate Staffing Services** — `html`, APPROVED
- **KRA Careers** — `html`, APPROVED (government; applying is auth-gated — store `application_url` = portal, never invent it)
- **PSC** — `html`, APPROVED (same rule as KRA)
- **Career Point Kenya** — `html`, APPROVED

## Restricted / hold

- **BrighterMonday** — REVIEW. Domain/assets and robots/terms must be re-verified; existing adapter's `.com` URL is stale.
- **Wellfound** — RESTRICTED. No automated access path identified; requires official API or partnership.

## First implementation group (spec §4)

`Fuzu`, `MyJobMag`, `Corporate Staffing`, `KRA` — these four cover approved HTML and RSS access methods and produce the correct URLs the Milestone 2 pipeline must prove out before adding more.