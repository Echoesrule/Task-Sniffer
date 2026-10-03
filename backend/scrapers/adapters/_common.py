"""Shared helpers for HTML source adapters."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from backend.scrapers.adapter import ListingItem
from backend.sources.urls import canonicalize_url

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return WS_RE.sub(" ", TAG_RE.sub(" ", value)).strip()


def is_http(url: str) -> bool:
    return url.startswith(("http://", "https://"))


def absolute(base: str, href: str) -> str:
    if not href:
        return ""
    if href.startswith(("javascript:", "mailto:", "tel:", "#")):
        return ""
    return canonicalize_url(urljoin(base, href))


def rss_items(xml_text: str) -> list[dict[str, str]]:
    """Parse RSS 2.0 / Atom XML into item dicts using stdlib ElementTree."""
    items: list[dict[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        return [{"_error": str(exc)}]

    for item in root.iter():
        tag = _local(item.tag)
        if tag not in ("item", "entry"):
            continue
        entry: dict[str, str] = {}
        link_candidates: list[tuple[str, str]] = []  # (rel, href)
        for child in item.iter():
            if child is item:
                continue
            ctag = _local(child.tag)
            if ctag not in entry:
                entry[ctag] = child.text or ""
            if ctag == "link":
                href = child.get("href") or (child.text or "")
                if href:
                    link_candidates.append((child.get("rel") or "", href))
        for _rel, href in link_candidates:
            if _rel in ("alternate", "", None):
                entry["href"] = href
                break
        if "href" not in entry and link_candidates:
            entry["href"] = link_candidates[0][1]
        if clean_text(entry.get("title", "")):
            items.append(entry)
    return items


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def job_title_from_container(node: Tag) -> str:
    """Best-effort title from heading elements inside a card node."""
    for el in node.select("h1,h2,h3,h4,h5"):
        text = clean_text(el.get_text(" ", strip=True))
        if text:
            return text
    title_attr = node.get("title") or node.get("aria-label")
    if title_attr:
        return clean_text(title_attr)
    return ""


def dedupe_by_url(items: Iterable[ListingItem]) -> list[ListingItem]:
    """Collapse listing items to one per candidate detail URL."""
    seen: set[str] = set()
    out: list[ListingItem] = []
    for item in items:
        key = next((c for c in item.url_candidates if c), item.source_url or item.raw_url or item.title)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out