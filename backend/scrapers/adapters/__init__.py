"""Approved Milestone-1 source adapters.

Each adapter implements :class:`backend.scrapers.adapter.JobSourceAdapter`.
Adapters only *parse*; all URL resolution/validation/canonicalization is owned
by the ingestion engine.
"""

from backend.scrapers.adapters.fuzu import FuzuAdapter
from backend.scrapers.adapters.myjobmag import MyJobMagAdapter
from backend.scrapers.adapters.corporatestaffing import CorporateStaffingAdapter
from backend.scrapers.adapters.kra import KraAdapter
from backend.scrapers.adapters.psc import PscAdapter

ADAPTER_CLASSES = {
    FuzuAdapter.name: FuzuAdapter,
    MyJobMagAdapter.name: MyJobMagAdapter,
    CorporateStaffingAdapter.name: CorporateStaffingAdapter,
    KraAdapter.name: KraAdapter,
    PscAdapter.name: PscAdapter,
}

__all__ = [
    "FuzuAdapter",
    "MyJobMagAdapter",
    "CorporateStaffingAdapter",
    "KraAdapter",
    "PscAdapter",
    "ADAPTER_CLASSES",
]