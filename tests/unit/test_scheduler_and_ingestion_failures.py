"""Scheduled work must be real, and source errors must remain observable."""

from __future__ import annotations

import asyncio
import ast
from pathlib import Path

import pytest

from backend.scrapers.factory import _LegacyAdapter
from backend.scrapers.adapters.corporatestaffing import CorporateStaffingAdapter
from backend.scrapers.adapters.kra import KraAdapter
from backend.scrapers.adapters.psc import PscAdapter
from backend.sources.registry import default_registry


def test_placeholder_periodic_tasks_are_not_scheduled():
    source = Path("backend/workers/celery_app.py").read_text()
    tree = ast.parse(source)
    assignment = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Attribute) and target.attr == "beat_schedule" for target in node.targets)
    )
    scheduled_names = {
        key.value for key in assignment.value.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }
    assert scheduled_names == {"scrape-all-sources"}


def test_legacy_listing_failure_propagates_to_ingestion_engine():
    adapter = _LegacyAdapter(default_registry.get("greenhouse"), "GreenhouseScraper")

    class BrokenScraper:
        async def fetch_jobs(self):
            raise RuntimeError("upstream unavailable")

    adapter._legacy = BrokenScraper()
    with pytest.raises(RuntimeError, match="upstream unavailable"):
        asyncio.run(adapter.fetch_listings())


@pytest.mark.parametrize(
    ("name", "adapter_class"),
    [
        ("corporatestaffing", CorporateStaffingAdapter),
        ("kra", KraAdapter),
        ("psc", PscAdapter),
    ],
)
def test_html_source_listing_fetch_failures_propagate(name, adapter_class):
    adapter = adapter_class(default_registry.get(name))

    async def broken_fetch(_url):
        raise RuntimeError("upstream unavailable")

    adapter.fetch = broken_fetch

    async def exercise():
        try:
            with pytest.raises(RuntimeError, match="upstream unavailable"):
                await adapter.fetch_listings()
        finally:
            await adapter.close()

    asyncio.run(exercise())
