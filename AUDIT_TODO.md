# Task Sniffer - Frontend/API Audit Findings (TODO)

**Audit Date:** 2026-10-21  
**Status:** Ready for Implementation  
**Priority Order:** High → Medium → Low

## HIGH PRIORITY (Critical User Impact)

### F-01: Dashboard uses mock data instead of real API data
- **Severity:** HIGH
- **Area:** Frontend/Dashboard
- **Impact:** Misleads users with fabricated counts, matches, and activity
- **Root Cause:** `frontend/src/app/dashboard/page.tsx` imports only from `@/data/mock.ts`, no API calls
- **Evidence:**
  - `frontend/src/app/dashboard/page.tsx:11-21, 71-76` - imports mocks, shows "12 strong opportunities found today", "Retro" greeting
  - No calls to `jobsService` or `analyticsService`
- **Files to Change:**
  - `frontend/src/app/dashboard/page.tsx`
- **Smallest Safe Fix:**
  1. Replace mock imports with `jobsService.stats()` and `jobsService.list({page_size:"5"})`
  2. Add loading/error states
  3. Fallback gracefully on error
  4. Remove dependency on mock data for live counts
- **Regression Tests:** Add test verifying dashboard fetches from API or handles errors correctly
- **Acceptance Criteria:**
  - [ ] Dashboard shows real job counts from DB (372 total)
  - [ ] Top matches pulled from real API
  - [ ] No mock data imported for live dashboard stats
  - [ ] Loading and error states implemented
- **Risks/Deps:** None - read-only API calls

### F-02: Data freshness not surfaced (stale ~7 days)
- **Severity:** HIGH
- **Area:** Data/UX
- **Impact:** Users think jobs are current when latest is 2026-10-14 19:39:37
- **Root Cause:** No ingestion timestamp exposed to UI
- **Evidence:**
  - DB: `SELECT MAX(created_at) FROM jobs` = `2026-10-14 19:39:37`
  - Scheduler not running
- **Files to Change:**
  - `backend/api/routes/jobs.py` (extend `/jobs/stats` or add endpoint)
  - `frontend/src/app/dashboard/page.tsx`
  - `frontend/src/app/jobs/page.tsx`
  - `frontend/src/services/api.ts` (if adding new endpoint)
- **Smallest Safe Fix:**
  1. Extend `JobStatsResponse` to include `latest_created_at` and/or `last_ingested_at`
  2. Add query to get max created_at in `/jobs/stats`
  3. Display "Last updated: X ago" on dashboard and jobs header
  4. Update copy to reflect actual status
- **Regression Tests:** API test for new stats fields
- **Acceptance Criteria:**
  - [ ] API returns latest job timestamp
  - [ ] UI displays last update time
  - [ ] Stale data is clearly communicated
- **Risks/Deps:** May need schema change if tracking separate ingestion timestamp

## MEDIUM PRIORITY

### F-03: No pagination in Jobs UI (fetches only 100)
- **Severity:** MEDIUM
- **Area:** Frontend/Jobs
- **Impact:** Can't access jobs beyond first 100; API supports pagination but UI doesn't use it
- **Root Cause:** `jobs/page.tsx` hardcodes `page_size: "100"` with no page controls
- **Evidence:**
  - `frontend/src/app/jobs/page.tsx:40-66` - calls `jobsService.list({page_size:"100"})` with no pagination state
  - API supports `page`, `page_size` (max 100)
- **Files to Change:**
  - `frontend/src/app/jobs/page.tsx`
  - `frontend/src/services/api.ts` (update if needed)
- **Smallest Safe Fix:**
  1. Add `page`, `total` state
  2. Add pagination controls (Previous/Next or page numbers)
  3. Update API call to include page
  4. Handle page changes
- **Regression Tests:** Test pagination navigation doesn't repeat/skip jobs
- **Acceptance Criteria:**
  - [ ] Can navigate through all job pages
  - [ ] Total count displayed correctly
  - [ ] No duplicate jobs across pages
- **Risks/Deps:** Backend pagination already implemented

### F-04: Search is client-side only, server search unused
- **Severity:** MEDIUM
- **Area:** Frontend/Jobs/Search
- **Impact:** Search only works on loaded results (first 100); server has `POST /jobs/search` unused
- **Root Cause:** UI does in-memory filtering
- **Evidence:**
  - `frontend/src/app/jobs/page.tsx:68-76` - client-side filter
  - `backend/api/routes/jobs.py:154-177` - `POST /jobs/search` exists
- **Files to Change:**
  - `frontend/src/app/jobs/page.tsx`
- **Smallest Safe Fix:**
  1. Either use `jobsService.search()` for server-side search
  2. Or clearly label "Search in loaded results"
  3. Prefer server search for better UX
- **Regression Tests:** Test search behavior
- **Acceptance Criteria:**
  - [ ] Search works correctly (server or clearly labeled client-side)
  - [ ] No confusion about search scope
- **Risks/Deps:** None

### F-05: Dummy auth token sent everywhere, no login flow
- **Severity:** MEDIUM
- **Area:** Auth/Frontend
- **Impact:** Protected routes will fail with 401; confusing auth state
- **Root Cause:** `fetchAPI` hardcodes `Authorization: "Bearer test-token"`
- **Evidence:**
  - `frontend/src/services/api.ts:5` - hardcoded token
  - Backend enforces real JWT validation
- **Files to Change:**
  - `frontend/src/services/api.ts`
  - Possibly add auth UI/routes
- **Smallest Safe Fix:**
  1. Read token from localStorage or env
  2. Only send auth header if token exists
  3. Handle 401s gracefully
  4. Or gate protected routes
- **Regression Tests:** Test auth header behavior
- **Acceptance Criteria:**
  - [ ] No hardcoded tokens
  - [ ] Auth handled properly
  - [ ] 401s handled gracefully
- **Risks/Deps:** May need auth UI implementation

### F-06: 50 jobs with NEEDS_REVIEW URL status not flagged
- **Severity:** MEDIUM
- **Area:** Frontend/Jobs/Links
- **Impact:** Users may click unvalidated links
- **Root Cause:** UI doesn't check `url_status`
- **Evidence:**
  - DB: `url_status` shows `NEEDS_REVIEW: 50, VALID: 322`
  - URL policy hardened but UI doesn't reflect it
- **Files to Change:**
  - `frontend/src/app/jobs/page.tsx`
  - `frontend/src/app/jobs/[id]/page.tsx`
  - `frontend/src/components/jobs/job-card.tsx` (if exists)
- **Smallest Safe Fix:**
  1. Add badge "Link needs review" for non-VALID status
  2. Warn before opening external links
  3. Prefer canonical only if VALID
- **Regression Tests:** UI test for badge display
- **Acceptance Criteria:**
  - [ ] NEEDS_REVIEW jobs clearly flagged
  - [ ] Users warned about unvalidated links
- **Risks/Deps:** URL fields already in API response

## LOW PRIORITY

### F-07: Generic error messages
- **Severity:** LOW
- **Area:** Frontend/API
- **Impact:** Harder to debug UX issues
- **Root Cause:** `fetchAPI` throws generic "API error: N"
- **Evidence:**
  - `frontend/src/services/api.ts:8`
- **Files to Change:**
  - `frontend/src/services/api.ts`
- **Smallest Safe Fix:**
  1. Parse response body for error detail
  2. Show user-friendly messages
- **Regression Tests:** Test error parsing
- **Acceptance Criteria:**
  - [ ] Errors show meaningful messages when available
- **Risks/Deps:** None

### F-08: Copy doesn't reflect reality (stale/mocked data)
- **Severity:** LOW
- **Area:** Frontend/Dashboard
- **Impact:** Misleading copy
- **Root Cause:** Hardcoded text
- **Evidence:**
  - `frontend/src/app/dashboard/page.tsx:71-76` - "12 strong opportunities found today", "The Hunter is active"
- **Files to Change:**
  - `frontend/src/app/dashboard/page.tsx`
- **Smallest Safe Fix:**
  1. Update copy to be factual or tie to real data
  2. Remove misleading claims
- **Regression Tests:** None needed
- **Acceptance Criteria:**
  - [ ] Copy matches actual state
- **Risks/Deps:** Should be done with F-01/F-02

## Notes
- Backend API is working well with real data for jobs
- URL safety has been hardened (recent phases)
- Auth system is properly implemented server-side
- Main issues are frontend not using available APIs correctly
- No critical security vulnerabilities found
