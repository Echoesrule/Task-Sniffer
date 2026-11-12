"""Shared test fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_local_rate_limiter():
    """Keep authentication throttling state isolated between tests.

    The limiter normally uses Redis; the test environment has no Redis module,
    so it falls back to a process-local bucket dict. Clearing it prevents one
    test's login/link attempts from causing another test to receive HTTP 429.
    """
    from backend.security.rate_limit import limiter

    limiter._local.clear()
    try:
        yield
    finally:
        limiter._local.clear()
