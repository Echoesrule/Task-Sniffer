"""URL handling pipeline (spec §§7-11).

Extract candidate URLs -> normalize -> strip tracking params -> identify the
job-detail URL -> resolve redirects -> validate the page -> canonicalize.

The first `<a>`/first URL on a listing is NEVER trusted as the job URL.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import re
import socket
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


#: anti-bot / interstitial markers: HTTP 200 pages that are not real content.
_ANTI_BOT_MARKERS = re.compile(
    r"(just a moment|checking your browser|enable javascript and cookies|"
    r"attention required|cf-browser-verification|"
    r"verify you are human|are you a robot|captcha|ddos protection|"
    r"unusual traffic)",
    re.IGNORECASE,
)

#: explicit removed/expired job indicators.
_REMOVED_MARKERS = re.compile(
    r"(no longer accepting applications|this job has expired|"
    r"position has been filled|this posting is closed|"
    r"job (?:is )?no longer available|the job you are looking for|"
    r"this (?:position|role|job) is (?:now )?closed|"
    r"applications? (?:are )?closed)",
    re.IGNORECASE,
)


def _is_anti_bot(page_title: str, body_text: str) -> bool:
    return bool(_ANTI_BOT_MARKERS.search(f"{page_title} {body_text[:5000]}"))


def _is_removed(page_title: str, body_text: str) -> bool:
    return bool(_REMOVED_MARKERS.search(f"{page_title} {body_text[:5000]}"))


def looks_like_html(content_type: str, body: str = "") -> bool:
    """Whether a response should be treated as an HTML job page.

    An unknown/empty content type is treated permissively (many servers omit
    it); an explicit non-HTML type is only accepted when the body is clearly an
    HTML document (some servers mislabel HTML as ``text/plain``).
    """
    content_type = (content_type or "").strip().lower()
    if not content_type:
        return True
    if "html" in content_type:
        return True
    if "xml" in content_type:
        head = (body or "").lstrip()[:200].lower()
        return head.startswith("<!doctype") or head.startswith("<html") or "<html" in head
    if content_type.startswith(("text/plain", "application/json", "application/octet-stream")):
        head = (body or "").lstrip()[:200].lower()
        return head.startswith("<!doctype") or head.startswith("<html") or "<html" in head
    return True


#: ports a job fetch is permitted to use; everything else is refused to avoid
#: turning the fetcher into an internal port scanner.
_ALLOWED_PORTS: frozenset[int] = frozenset({80, 443, 8080, 8443})


def _parse_host_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse a host into an IP, tolerating legacy decimal/hex/octal literals."""
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    lowered = host.lower()
    # shorthand dotted forms ("127.1", "10.1", "2130706433") accepted by inet_aton
    if re.fullmatch(r"\d+(\.\d+){0,3}", host):
        try:
            return ipaddress.ip_address(socket.inet_aton(host))
        except (OSError, ValueError, OverflowError):
            return None
    try:
        if lowered.startswith("0x"):
            return ipaddress.ip_address(int(lowered, 16))
        if lowered.isdigit():
            return ipaddress.ip_address(int(lowered, 8) if lowered.startswith("0") else int(lowered))
    except (ValueError, OverflowError):
        return None
    return None


def _ip_is_unsafe(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _resolve_host_ips(host: str) -> set[str]:
    """Resolve a hostname to its IP literals (best-effort; empty on failure)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, OSError, ValueError):
        return set()
    ips: set[str] = set()
    for info in infos:
        addr = info[4][0]
        if isinstance(addr, str):
            ips.add(addr.split("%", 1)[0])
    return ips


#: hosts under these special-use domains can never resolve publicly, so the
#: DNS safety check is skipped for them (also keeps tests fast/deterministic).
_NON_RESOLVABLE_SUFFIXES = (
    ".example",
    ".example.com",
    ".example.net",
    ".example.org",
    ".invalid",
    ".test",
    ".localhost",
)

_DNS_CACHE: dict[str, frozenset[str]] = {}
_DNS_TIMEOUT = 0.75


def _skips_dns_check(host: str) -> bool:
    return host.endswith(_NON_RESOLVABLE_SUFFIXES)


async def _resolve_host_ips_cached(host: str) -> frozenset[str]:
    """Resolve via a worker thread with a timeout, caching results per process.

    Only successful, non-empty resolutions are cached. A failed, timed-out, or
    empty lookup is intentionally *not* cached so a transient DNS failure does
    not permanently lock a host out; it is also treated as unverifiable by the
    caller (fail-closed), never as safe.
    """
    if host in _DNS_CACHE:
        return _DNS_CACHE[host]
    try:
        ips = await asyncio.wait_for(asyncio.to_thread(_resolve_host_ips, host), timeout=_DNS_TIMEOUT)
        result = frozenset(ips)
    except Exception:  # noqa: BLE001 - timeout/failure => unverifiable
        result = frozenset()
    if result:
        _DNS_CACHE[host] = result
    return result


#: outbound destination safety verdicts
SAFETY_SAFE = "safe"
SAFETY_UNSAFE = "unsafe"
SAFETY_UNVERIFIED = "unverified"


async def _classify_url_safety(url: str) -> str:
    """Classify a fetch destination as safe / unsafe / unverifiable.

    Static checks (scheme, port, literal IP ranges) run first. Hostnames are
    then resolved and *every* resolved address must be public. A lookup that
    fails, times out, or yields no addresses is ``unverified`` and treated as
    fail-closed: the request must not be issued, but the outcome is recorded as
    inconclusive (NEEDS_REVIEW) rather than proven-malicious.
    """
    if not is_safe_fetch_url(url, resolve_dns=False):
        return SAFETY_UNSAFE
    host = (urlparse(url).hostname or "").strip().lower()
    if _parse_host_ip(host) is not None or _skips_dns_check(host):
        return SAFETY_SAFE
    ips = await _resolve_host_ips_cached(host)
    if not ips:
        return SAFETY_UNVERIFIED
    for literal in ips:
        try:
            resolved = ipaddress.ip_address(literal)
        except ValueError:
            continue
        if _ip_is_unsafe(resolved):
            return SAFETY_UNSAFE
    return SAFETY_SAFE


async def _url_is_safe_async(url: str) -> bool:
    """Boolean form of :func:`_classify_url_safety` (fail-closed).

    An unverifiable destination returns ``False``.
    """
    return await _classify_url_safety(url) == SAFETY_SAFE


def is_safe_fetch_url(url: str, *, resolve_dns: bool = False) -> bool:
    """Reject unsafe fetch destinations (scheme, port, private IP ranges).

    Checks are applied to IP literals directly (including legacy decimal, hex
    and octal encodings and IPv4-mapped IPv6). When ``resolve_dns`` is set,
    hostnames are also resolved and rejected if *any* resolved address is
    private/loopback/link-local/reserved. When resolution fails, times out, or
    returns no addresses the destination is refused (fail-closed) rather than
    allowed. DNS rebinding (the address changing between this check and the
    actual connect) remains a residual TOCTOU risk; see
    :func:`fetch_with_policy`.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme.lower() not in ("http", "https"):
        return False

    try:
        port = parsed.port
    except ValueError:
        return False
    if port is not None and port not in _ALLOWED_PORTS:
        return False

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False
    if (
        host == "localhost"
        or host.endswith(".localhost")
        or host.endswith(".local")
        or host.endswith(".internal")
    ):
        return False

    ip = _parse_host_ip(host)
    if ip is not None:
        return not _ip_is_unsafe(ip)

    if resolve_dns:
        for literal in _resolve_host_ips(host):
            try:
                resolved = ipaddress.ip_address(literal)
            except ValueError:
                continue
            if _ip_is_unsafe(resolved):
                return False
    return True


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


async def fetch_with_policy(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_redirects: int = 5,
    resolve_dns: bool = True,
) -> tuple[httpx.Response | None, str, list[str], str]:
    """Fetch a URL, following redirects manually with a per-hop SSRF check.

    Each redirect target is validated *before* the next request is issued, so
    no request is ever sent to a loopback/private/link-local/reserved host,
    a non-HTTP(S) scheme, or a non-web port, even as an intermediate hop.

    Destination safety is fail-closed: a host that cannot be resolved (DNS
    failure or timeout) is refused and reported as unverifiable. DNS rebinding
    between this check and the connect is a residual TOCTOU risk and is *not*
    eliminated here (mitigate with an outbound egress proxy that enforces the
    same policy).

    Returns ``(response, final_url, chain, error)``. ``response`` is ``None``
    when a hop was refused, a loop/limit was hit, or the request failed; the
    ``error`` string distinguishes unsafe destinations ("unsafe") from
    merely-unverifiable ones ("could not be verified") and inconclusive
    outcomes.
    """
    start = normalize_url(url) or url
    chain = [start]
    current = start

    for _ in range(max_redirects + 1):
        if resolve_dns:
            verdict = await _classify_url_safety(current)
            if verdict == SAFETY_UNSAFE:
                return None, current, chain, "unsafe destination (SSRF policy)"
            if verdict == SAFETY_UNVERIFIED:
                return None, current, chain, "destination could not be verified (DNS)"
        elif not is_safe_fetch_url(current):
            return None, current, chain, "unsafe destination (SSRF policy)"

        try:
            response = await client.get(current, follow_redirects=False)
        except Exception as exc:  # noqa: BLE001 - surfaced as inconclusive
            logger.debug("fetch failed %s: %s", current, exc)
            return None, current, chain, f"fetch error: {exc}"

        if response.is_redirect:
            location = response.headers.get("location")
            if not location:
                return response, current, chain, ""
            target = normalize_url(urljoin(current, location)) or urljoin(current, location)
            if target in chain:
                return None, current, chain, "redirect loop"
            chain.append(target)
            current = target
            continue

        return response, current, chain, ""

    return None, current, chain, "too many redirects"


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
    content_type: str = "",
    is_html: bool | None = None,
) -> UrlValidation:
    """Validate a fetched job page against the checklist in spec §8.

    Returns a UrlValidation whose ``status`` is one of:

    * ``VALID`` - sufficient evidence the destination is a job-detail page.
    * ``INVALID`` - affirmative evidence it is not (removed job, search page,
      non-HTML body, ...).
    * ``NEEDS_REVIEW`` - the repository's "unknown" bucket: inconclusive
      evidence (timeout, 403/429, anti-bot interstitial, unexpected domain,
      missing domain policy). Unknown candidates must not be persisted.
    """
    checks: dict[str, bool] = {}

    checks["http_status"] = status_code
    checks["expected_domain"] = _domain_allowed(url, allowed_domains) if allowed_domains else False
    checks["not_search_listing"] = classify_url(url) not in (UrlType.SEARCH, UrlType.CATEGORY, UrlType.COMPANY)
    checks["not_homepage"] = (urlparse(url).path or "/") not in ("", "/")
    checks["has_title"] = _page_mentions(page_title, expected_title, bodies=(body_text,)) if expected_title else True
    checks["has_company"] = _page_mentions(page_title, expected_company, bodies=(body_text,)) if expected_company else True
    checks["has_job_content"] = (len(body_text) > 120) or has_job_markers
    checks["anti_bot"] = not _is_anti_bot(page_title, body_text)
    checks["removed"] = not _is_removed(page_title, body_text)
    checks["is_html"] = looks_like_html(content_type) if is_html is None else is_html

    # --- status-code policy -------------------------------------------------
    if status_code == 0:
        return UrlValidation(
            ok=False, status=UrlStatus.NEEDS_REVIEW,
            reason="no HTTP response (network error/timeout)", checks=checks,
        )

    if status_code in (404, 410):
        return UrlValidation(
            ok=False, status=UrlStatus.INVALID,
            reason=f"job removed (HTTP {status_code})", checks=checks,
        )

    if status_code in (403, 429) or 500 <= status_code <= 599:
        return UrlValidation(
            ok=False, status=UrlStatus.NEEDS_REVIEW,
            reason=f"inconclusive HTTP {status_code}", checks=checks,
        )

    if not 200 <= status_code < 300:
        return UrlValidation(
            ok=False, status=UrlStatus.INVALID,
            reason=f"HTTP {status_code}", checks=checks,
        )

    # --- 2xx content policy -------------------------------------------------
    if not checks["is_html"]:
        return UrlValidation(
            ok=False, status=UrlStatus.INVALID,
            reason="response is not an HTML job page", checks=checks,
        )

    if not checks["anti_bot"]:
        return UrlValidation(
            ok=False, status=UrlStatus.NEEDS_REVIEW,
            reason="anti-bot/interstitial page (not conclusive)", checks=checks,
        )

    if not checks["removed"]:
        return UrlValidation(
            ok=False, status=UrlStatus.INVALID,
            reason="job posting removed/expired", checks=checks,
        )

    if not checks["expected_domain"]:
        return UrlValidation(
            ok=False, status=UrlStatus.NEEDS_REVIEW,
            reason="final URL is on an unexpected/unconfigured domain", checks=checks,
        )

    if not checks["not_search_listing"]:
        return UrlValidation(
            ok=False, status=UrlStatus.INVALID,
            reason="URL resolves to a search/listing/company/category page", checks=checks,
        )

    if not checks["not_homepage"]:
        return UrlValidation(
            ok=False, status=UrlStatus.INVALID,
            reason="URL resolves to a site homepage/landing page", checks=checks,
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


#: query params that, when present, pin a URL to a specific posting.
_CANDIDATE_IDENTITY_PARAMS: tuple[str, ...] = (
    "gh_jid", "job_id", "jobid", "jid", "vacancy", "vac", "offer", "posting",
    "position", "id", "listing", "advert",
)

#: path segments that never identify a concrete posting on their own.
_CANDIDATE_NON_JOB_SEGMENTS: frozenset[str] = frozenset(
    {
        "search", "results", "browse", "jobs", "job", "jobsearch",
        "careers", "career", "positions", "openings", "apply", "apply-now",
        "view", "details", "listing", "listings", "vacancies", "category",
        "categories", "company", "companies", "profile", "about", "index",
    }
)


def _job_identity_key(url: str) -> str:
    """A conservative identity key for comparing two URLs of the same posting."""
    parsed = urlparse(url or "")
    query = {k.lower(): v for k, v in parse_qsl(parsed.query, keep_blank_values=False)}
    for key in _CANDIDATE_IDENTITY_PARAMS:
        if query.get(key):
            return f"{key}={query[key]}"
    segments = [
        s.lower()
        for s in (parsed.path or "").split("/")
        if s and s.lower() not in _CANDIDATE_NON_JOB_SEGMENTS
    ]
    return segments[-1] if segments else ""


def _same_job_identity(a: str, b: str) -> bool:
    ka, kb = _job_identity_key(a), _job_identity_key(b)
    if ka and kb:
        return ka == kb
    return True  # identity of one side unknown -> do not reject


def _validated_web_url(candidate: str, base_url: str, allowed_domains: set[str]) -> str:
    """Resolve + canonicalize + policy-check an in-page URL. '' when rejected.

    Applies the same safety/domain/destination rules used for fetched pages so
    URLs from canonical tags, JSON-LD, or apply anchors cannot bypass Phase 2
    controls (SSRF, domain policy, search/-homepage/company-page rejection).
    """
    if not candidate:
        return ""
    resolved = urljoin(base_url, (candidate or "").strip())
    if urlparse(resolved).scheme.lower() not in ("http", "https"):
        return ""
    url = canonicalize_url(resolved)
    if not url:
        return ""
    if not is_safe_fetch_url(url):
        return ""
    if not allowed_domains or not _domain_allowed(url, allowed_domains):
        return ""
    if classify_url(url) in (UrlType.SEARCH, UrlType.CATEGORY, UrlType.COMPANY):
        return ""
    if (urlparse(url).path or "/") in ("", "/"):
        return ""
    return url


def _each_jsonld(html: str) -> Iterable[dict[str, Any]]:
    """Yield every JSON-LD object (dicts nested in lists / @graph / arrays)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    def walk(node: Any) -> Iterable[dict[str, Any]]:
        if isinstance(node, dict):
            graph = node.get("@graph")
            if isinstance(graph, list):
                for item in graph:
                    yield from walk(item)
            yield node
        elif isinstance(node, list):
            for item in node:
                yield from walk(item)

    for tag in soup.find_all("script"):
        typ = (tag.get("type") or "").lower().strip()
        if "ld+json" not in typ:
            continue
        raw = (tag.string or tag.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.debug("malformed JSON-LD block skipped")
            continue
        yield from walk(data)


def _is_jobposting(obj: dict[str, Any]) -> bool:
    typ = obj.get("@type")
    if isinstance(typ, str):
        return typ.lower() == "jobposting"
    if isinstance(typ, list):
        return any(isinstance(t, str) and t.lower() == "jobposting" for t in typ)
    return False


def _jsonld_job_urls(html: str, base_url: str) -> list[str]:
    """URL candidates from JobPosting.url nodes, in document order."""
    urls: list[str] = []
    for obj in _each_jsonld(html):
        if not _is_jobposting(obj):
            continue
        u = obj.get("url")
        if isinstance(u, str) and u.strip():
            urls.append(u.strip())
    return urls


def _jsonld_application_urls(html: str, base_url: str) -> list[str]:
    """Explicit application URLs from JSON-LD where the meaning is explicit."""
    urls: list[str] = []
    for obj in _each_jsonld(html):
        for key in ("applicationUrl", "application_url", "applyUrl", "apply_url"):
            u = obj.get(key)
            if isinstance(u, str) and u.strip():
                urls.append(u.strip())
    return urls


def extract_canonical_url(html: str, base_url: str, *, allowed_domains: set[str],
                          detail_url: str = "") -> str:
    """Canonical identity URL: link[rel=canonical] then JSON-LD JobPosting.url.

    Candidates are validated against safety/domain/destination policy and must
    not point at a different posting's identity, or they are discarded.
    """
    from bs4 import BeautifulSoup

    detail = canonicalize_url(detail_url or base_url)
    candidates: list[str] = []

    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("link", href=True):
        rels = link.get("rel") or []
        rels = rels if isinstance(rels, list) else [rels]
        if any(str(r).lower() == "canonical" for r in rels):
            href = str(link.get("href", "")).strip()
            if href:
                candidates.append(href)

    candidates.extend(_jsonld_job_urls(html, base_url))

    if not candidates:
        return ""

    seen: set[str] = set()
    for cand in candidates:
        url = _validated_web_url(cand, base_url, allowed_domains)
        if not url or url in seen:
            continue
        seen.add(url)
        if url == detail:
            continue  # adds no information
        if not _same_job_identity(detail, url):
            logger.info("canonical candidate rejected (different job identity): %s", url)
            continue
        return url
    return ""


def find_explicit_apply_url(html: str, base_url: str, *, allowed_domains: set[str]) -> str:
    """Locate an explicit 'apply' target on a job page.

    Returns the first apply link that passes the shared safety/domain policy or
    ``""`` when none is trustworthy. Never invents a URL.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        text = anchor.get_text(" ", strip=True).lower()
        href = str(anchor.get("href", "")).strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        if "apply" in text or "submit" in text or re.search(r"apply", href, re.I):
            full = urljoin(base_url, href)
            url = _validated_web_url(full, base_url, allowed_domains)
            if url:
                return url
    return ""


@dataclass
class UrlSignals:
    """Validated URLs extracted from a fetched job page (Phase 3)."""

    canonical_url: str = ""
    application_url: str = ""
    notes: list[str] = field(default_factory=list)


def extract_url_signals(html: str, base_url: str, *, allowed_domains: set[str],
                        apply_hint: str = "", detail_url: str = "") -> UrlSignals:
    """Resolve detail/canonical/application semantics for one fetched page.

    - ``canonical_url``: preferred identity URL when reliably established.
    - ``application_url``: explicit application destination when one is found;
      otherwise left empty. Never fabricated and never set to the detail URL.
    Precedence for application evidence: adapter ``apply_hint`` > explicit apply
    anchor > explicit JSON-LD application field. Every candidate must pass the
    shared safety/domain/destination policy.
    """
    detail = canonicalize_url(detail_url or base_url) or base_url
    notes: list[str] = []

    canonical_url = extract_canonical_url(
        html, base_url, allowed_domains=allowed_domains, detail_url=detail,
    )

    application_url = ""
    if apply_hint:
        candidate = _validated_web_url(apply_hint, base_url, allowed_domains)
        if candidate:
            application_url = candidate
        else:
            notes.append("adapter apply_hint rejected by safety/domain policy")

    if not application_url:
        candidate = find_explicit_apply_url(html, base_url, allowed_domains=allowed_domains)
        if candidate:
            application_url = candidate

    if not application_url:
        for candidate in _jsonld_application_urls(html, base_url):
            application_url = _validated_web_url(candidate, base_url, allowed_domains)
            if application_url:
                break

    if application_url and application_url == detail:
        application_url = ""

    return UrlSignals(
        canonical_url=canonical_url,
        application_url=application_url,
        notes=notes,
    )