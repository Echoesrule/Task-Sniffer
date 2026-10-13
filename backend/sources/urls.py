"""URL handling pipeline (spec §§7-11).

Extract candidate URLs -> normalize -> strip tracking params -> identify the
job-detail URL -> resolve redirects -> validate the page -> canonicalize.

The first `<a>`/first URL on a listing is NEVER trusted as the job URL.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx

from backend.sources.models import UrlStatus, UrlType

logger = logging.getLogger(__name__)

#: tracking / analytics params that are safe to strip (spec §10)
TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
        "utm_id", "utm_campaignid", "utm_adgroup", "utm_adid", "utm_network",
        "utm_pubreferrer",
        "fbclid", "gclid", "gclsrc", "dclid", "msclkid", "mc_cid", "mc_eid",
        "igshid", "srsltid",
    }
)

#: query params that are job identifiers and MUST NOT be stripped
IDENTITY_PARAMS: frozenset[str] = frozenset(
    {"job", "job_id", "jobid", "jid", "vacancy", "vac", "offer", "posting",
     "position", "id", "listing", "advert"}
)

_DEFAULT_PORTS: dict[str, str] = {"http": "80", "https": "443"}

#: generic indicators that a listed URL is a search/listing/category page
_SEARCH_MARKERS = re.compile(
    r"/(search|results|browse|category|categories|tag|directory|keywords?|"
    r"job-type|job-types|location|industry|company-profile|companies|"
    r"apply-now|login|signup|register|account|saved|alert|alerts)([./?#]|$)",
    re.IGNORECASE,
)
_JOB_KEYWORDS: frozenset[str] = frozenset(
    {
        "job", "jobboard", "joblisting", "jobslisting", "vacancy", "vacancies",
        "position", "positions", "posting", "postings", "listing", "listings",
        "detail", "details", "opportunity", "opportunities", "career", "careers",
        "role", "roles", "opening", "openings", "offer", "offers", "advert",
    }
)
_SLUG_SEGMENT = re.compile(r"^[a-z0-9][a-z0-9._-]{2,}$", re.IGNORECASE)
_URL_TITLE_PARAM = re.compile(r"(job-title|job_title|title|slug|name)=", re.IGNORECASE)

#: Explicit, source-aware job-detail URL shapes for third-party ATS providers.
#: Each entry pairs a host pattern with the path shape of a concrete posting.
#: These are intentionally narrow; a board landing page (fewer segments) is not
#: matched. They exist so valid jobs are not rejected merely because their path
#: lacks the generic words "job"/"jobs"/"careers".
_ATS_DETAIL_PATTERNS: tuple[tuple[re.Pattern[str], re.Pattern[str]], ...] = (
    # Ashby: https://jobs.ashbyhq.com/<board>/<posting-id>
    (re.compile(r"(?:^|\.)jobs\.ashbyhq\.com$", re.I), re.compile(r"^/[^/]+/[^/]+/?$")),
    # Workable: https://apply.workable.com/<company>/j/<posting-id>/
    (re.compile(r"(?:^|\.)apply\.workable\.com$", re.I), re.compile(r"^/[^/]+/j/[^/]+/?$")),
    # Remotive: https://remotive.com/remote-jobs/<category>/<slug>
    (re.compile(r"(?:^|\.)remotive\.com$", re.I), re.compile(r"^/remote-jobs/[^/]+/[^/]+/?$")),
    # Lever: https://jobs.lever.co/<company>/<posting-uuid>
    (re.compile(r"(?:^|\.)jobs\.lever\.co$", re.I), re.compile(r"^/[^/]+/[0-9a-f-]{8,}/?$")),
)


def _is_ats_detail(parsed) -> bool:
    """True when ``parsed`` matches a known ATS concrete-posting URL shape."""
    host = (parsed.hostname or "").lower()
    path = parsed.path or "/"
    return any(
        host_re.search(host) and path_re.match(path)
        for host_re, path_re in _ATS_DETAIL_PATTERNS
    )


def _keyword_of(segment: str) -> str:
    seg = segment.lower()
    if seg.endswith("s"):
        cand = seg[:-1]
        if cand in _JOB_KEYWORDS:
            return cand
    return seg


def _is_detail_path(path: str) -> bool:
    """True when the path is ``/<job-keyword>/<slug>`` i.e. a concrete job."""
    segments = [s for s in path.split("/") if s]
    if len(segments) < 2:
        return False
    leaf = segments[-1]
    if not _SLUG_SEGMENT.match(leaf):
        return False
    return any(_keyword_of(s) in _JOB_KEYWORDS for s in segments[:-1])


@dataclass
class CandidateLink:
    """A single extracted hyperlink from a listing."""

    url: str
    text: str = ""
    kind: UrlType = UrlType.UNKNOWN

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CandidateLink {self.kind.value}: {self.url}>"


@dataclass
class RedirectChain:
    """Record of a URL's redirect history (spec §11)."""

    original_url: str = ""
    final_url: str = ""
    chain: list[str] = field(default_factory=list)
    status: int = 0

    @property
    def redirected(self) -> bool:
        return self.original_url != self.final_url

    @property
    def as_dict(self) -> dict[str, Any]:
        return {
            "original_url": self.original_url,
            "final_url": self.final_url,
            "chain": self.chain,
            "status": self.status,
        }


@dataclass
class UrlValidation:
    """Result of validating a job URL against a fetched page (spec §8)."""

    ok: bool = False
    status: UrlStatus = UrlStatus.NEEDS_REVIEW
    reason: str = "not validated"
    checks: dict[str, bool] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "status": self.status.value, "reason": self.reason, "checks": self.checks}


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def normalize_url(url: str, *, strip_fragment: bool = True) -> str:
    """Syntactic normalization: scheme, host case, default port, trailing slash."""
    url = (url or "").strip()
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url

    parsed = urlparse(url)
    scheme = (parsed.scheme or "https").lower()
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if port and str(port) == _DEFAULT_PORTS.get(scheme):
        port = None

    path = parsed.path or "/"
    if len(path) > 1:
        path = path.rstrip("/")

    netloc = host
    if port:
        netloc = f"{host}:{port}"

    fragment = ""
    if not strip_fragment and parsed.fragment:
        fragment = f"#{parsed.fragment}"

    query = parsed.query
    return urlunparse((scheme, netloc, path, parsed.params, query, fragment))


def strip_tracking_params(url: str, *, keep: Iterable[str] | None = None) -> str:
    """Remove tracking params while preserving identity params (spec §10).

    Some sites encode the job id in a query param; those are kept.
    """
    parsed = urlparse(url)
    if not parsed.query:
        return url

    keep = set(keep or ()) | IDENTITY_PARAMS
    preserved: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_lower = key.lower()
        if key_lower in keep or key_lower not in TRACKING_PARAMS:
            preserved.append((key, value))

    new_query = urlencode(preserved, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def canonicalize_url(url: str, *, keep_params: Iterable[str] | None = None,
                     source: str | None = None) -> str:
    """Full canonicalization: normalize + strip tracking + keep identity params.

    ``keep_params`` may override the default identity-param allow-list per source.
    """
    normalized = normalize_url(url)
    if not normalized:
        return ""
    return strip_tracking_params(normalized, keep=keep_params)


def is_same_domain(url_a: str, url_b: str) -> bool:
    pa, pb = urlparse(url_a), urlparse(url_b)
    ha, hb = (pa.hostname or "").lower(), (pb.hostname or "").lower()
    if not ha or not hb:
        return False
    return ha == hb or ha.endswith("." + hb) or hb.endswith("." + ha)


def _classify_path(url: str) -> UrlType:
    parsed = urlparse(url)
    path = parsed.path or "/"

    if _is_ats_detail(parsed):
        return UrlType.JOB_DETAIL

    if _SEARCH_MARKERS.search(path):
        return UrlType.SEARCH

    if _is_detail_path(path):
        return UrlType.JOB_DETAIL

    if _URL_TITLE_PARAM.search(parsed.query or "") and any(
        _keyword_of(s) in _JOB_KEYWORDS for s in path.split("/") if s
    ):
        return UrlType.JOB_DETAIL

    return UrlType.UNKNOWN


def classify_url(url: str, *, text: str = "",
                 source_patterns: list[str] | None = None) -> UrlType:
    """Classify a candidate URL using path heuristics + source-specific patterns."""
    if source_patterns:
        parsed = urlparse(url)
        if any(re.search(p, parsed.path, re.IGNORECASE) for p in source_patterns):
            return UrlType.JOB_DETAIL

    kind = _classify_path(url)
    if kind == UrlType.JOB_DETAIL:
        return kind

    # company-profile / navigation links that surfaced as candidates
    parsed = urlparse(url)
    path = parsed.path or "/"
    if re.search(r"/(company|employer|recruiter|about|team|terms|privacy|help|faq)", path, re.I):
        return UrlType.COMPANY

    text_lower = (text or "").lower()
    if "category" in text_lower or "/category/" in path:
        return UrlType.CATEGORY
    return kind


# ---------------------------------------------------------------------------
# Extraction from listing HTML
# ---------------------------------------------------------------------------


def extract_candidate_urls(html: str, base_url: str) -> list[CandidateLink]:
    """Extract all anchor links from a listing page (spec §7)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    links: list[CandidateLink] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        full = urljoin(base_url, href)
        canonical = canonicalize_url(full)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        text = anchor.get_text(" ", strip=True)
        links.append(CandidateLink(url=canonical, text=text))

    return links


def identify_job_url(links: Iterable[CandidateLink], *, title_hint: str = "",
                     source_patterns: list[str] | None = None) -> CandidateLink | None:
    """Pick the job-detail URL from candidate links (spec §7).

    Priority:
      1. URL that matches source-specific job-detail patterns.
      2. URL classified as JOB_DETAIL whose anchor text resembles the job
         title (when provided).
      3. Any JOB_DETAIL-classified URL.
    """
    candidates = list(links)

    token = ""
    if title_hint:
        token = re.sub(r"[^a-z0-9]+", "-", title_hint.lower()).strip("-")[:40]

    best: CandidateLink | None = None
    best_score = -1

    for link in candidates:
        if source_patterns and any(
            re.search(p, urlparse(link.url).path, re.IGNORECASE) for p in source_patterns
        ):
            score = 100
        else:
            kind = classify_url(link.url, text=link.text, source_patterns=source_patterns)
            score = 60 if kind == UrlType.JOB_DETAIL else 0

        if token and link.text:
            link_token = re.sub(r"[^a-z0-9]+", "-", link.text.lower()).strip("-")
            if token in link_token or link_token[:10] and (token[:10] in link_token or link_token in token):
                score += 20
            elif any(word in link_token for word in token.split("-") if len(word) > 3):
                score += 10

        # prefer same-domain, non-tracking detail links
        if score and not urlparse(link.url).query and "apply" not in link.url.lower():
            score += 5
        if "utm" in link.url:
            score -= 10

        if score > best_score:
            best, best_score = link, score

    if best is not None and best_score >= 40:
        return best
    return None


# ---------------------------------------------------------------------------
# Redirect resolution
# ---------------------------------------------------------------------------


async def resolve_redirects(client: httpx.AsyncClient, url: str) -> RedirectChain:
    """Follow redirects and record the chain (spec §11).

    Relies on ``client.follow_redirects=True``; httpx exposes the final URL and
    history.
    """
    chain: list[str] = []
    try:
        response = await client.get(url)
        chain = [h.headers.get("location", "") for h in response.history if h.headers.get("location")]
        chain = [url] + [c for c in chain if c]
        final = str(response.url) if response.url else url
        return RedirectChain(
            original_url=url,
            final_url=final,
            chain=chain,
            status=response.status_code,
        )
    except httpx.HTTPStatusError as exc:
        return RedirectChain(original_url=url, final_url=url, status=exc.response.status_code)
    except (httpx.RequestError, httpx.TimeoutException) as exc:
        logger.debug("Redirect resolve failed for %s: %s", url, exc)
        return RedirectChain(original_url=url, final_url=url)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_job_page(
    *,
    url: str,
    status_code: int,
    page_title: str = "",
    body_text: str = "",
    expected_title: str = "",
    expected_company: str = "",
    allowed_domains: set[str] | None = None,
    has_job_markers: bool = False,
) -> UrlValidation:
    """Validate a fetched job page against the checklist in spec §8.

    Returns a UrlValidation with ``status`` one of VALID / INVALID / NEEDS_REVIEW.
    """
    checks: dict[str, bool] = {}

    checks["http_ok"] = 200 <= status_code < 300
    checks["expected_domain"] = _domain_allowed(url, allowed_domains) if allowed_domains else True
    checks["not_search_listing"] = classify_url(url) not in (UrlType.SEARCH, UrlType.CATEGORY)
    checks["has_title"] = _page_mentions(page_title, expected_title, bodies=(body_text,)) if expected_title else True
    checks["has_company"] = _page_mentions(page_title, expected_company, bodies=(body_text,)) if expected_company else True
    checks["has_job_content"] = (len(body_text) > 120) or has_job_markers

    if not checks["http_ok"]:
        return UrlValidation(
            ok=False, status=UrlStatus.INVALID,
            reason=f"HTTP {status_code}", checks=checks,
        )

    if not checks["expected_domain"]:
        return UrlValidation(
            ok=False, status=UrlStatus.NEEDS_REVIEW,
            reason="final URL is on an unexpected domain", checks=checks,
        )

    if not checks["not_search_listing"]:
        return UrlValidation(
            ok=False, status=UrlStatus.INVALID,
            reason="URL resolves to a search/listing/category page", checks=checks,
        )

    if not checks["has_job_content"]:
        return UrlValidation(
            ok=False, status=UrlStatus.NEEDS_REVIEW,
            reason="page does not appear to contain job-specific content", checks=checks,
        )

    if not checks["has_title"] or not checks["has_company"]:
        return UrlValidation(
            ok=False, status=UrlStatus.NEEDS_REVIEW,
            reason="page does not mention the job title/company", checks=checks,
        )

    return UrlValidation(ok=True, status=UrlStatus.VALID, reason="validated", checks=checks)


def _domain_allowed(url: str, allowed: set[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    for domain in allowed:
        domain = domain.lower().lstrip(".").lstrip("*")
        if host == domain or host.endswith("." + domain):
            return True
    return False


def _page_mentions(full_text: str, needle: str, *, bodies: tuple[str, ...] = ()) -> bool:
    """Fuzzy contains-check: every significant token of the needle should appear."""
    if not needle:
        return True
    haystack = " ".join([full_text, *bodies]).lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", needle.lower()) if len(t) > 2]
    if not tokens:
        return True
    # tolerate plausible-token-rate of 2/3
    matches = sum(1 for t in tokens if t in haystack)
    return matches >= max(1, int(len(tokens) * 2 / 3))


def find_explicit_apply_url(html: str, base_url: str, *, allowed_domains: set[str]) -> str:
    """Locate an explicit 'apply' target on a job page.

    Prefers a same/related-domain apply href over external ATS links; falls back
    to the job detail URL itself. Never invents a URL.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    apply_links: list[CandidateLink] = []
    for anchor in soup.find_all("a", href=True):
        text = anchor.get_text(" ", strip=True).lower()
        href = str(anchor.get("href", "")).strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        if "apply" in text or "submit" in text or re.search(r"apply", href, re.I):
            full = urljoin(base_url, href)
            apply_links.append(CandidateLink(url=full, text=text))

    if not apply_links:
        return base_url

    preferred = next((l.url for l in apply_links if _domain_allowed(l.url, allowed_domains)), None)
    return preferred or apply_links[0].url