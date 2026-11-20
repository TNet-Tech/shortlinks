"""
Tests for the shortlinks module (no running server needed).

Run with:  pytest shortlinks_src/tests -v   (from the module folder)
"""
import asyncio
import re
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from .. import service
from ..models import CODE_PATTERN, LinkCreate


def _event(code="abc123"):
    return service.VisitEvent(
        link_id=1, code=code, target_url="https://example.com", user_agent="curl/8",
        referer=None, client_ip="127.0.0.1", visited_at=datetime.now(timezone.utc),
    )


def test_generated_codes_are_valid_and_varied():
    codes = {service.generate_code() for _ in range(200)}
    assert len(codes) > 190
    assert all(re.fullmatch(CODE_PATTERN, c) and len(c) == service.CODE_LENGTH for c in codes)


def test_create_schema_validates_url_and_code():
    assert LinkCreate(url="https://example.com/a?b=c").code is None
    assert LinkCreate(url="https://example.com", code="summer-sale").code == "summer-sale"
    for bad in ({"url": "not a url"}, {"url": "https://x.com", "code": "a b"}, {"url": "https://x.com", "code": "ab"}):
        with pytest.raises(ValidationError):
            LinkCreate(**bad)


def test_listeners_called_and_failures_isolated():
    seen = []

    async def async_listener(e):
        seen.append(("async", e.code))

    def broken(e):
        raise RuntimeError("boom")

    service.add_visit_listener("t-async", async_listener)
    service.add_visit_listener("t-broken", broken)
    service.add_visit_listener("t-sync", lambda e: seen.append(("sync", e.code)))
    try:
        asyncio.run(service.notify_visit(_event("xyz")))
        assert ("async", "xyz") in seen and ("sync", "xyz") in seen
    finally:
        for n in ("t-async", "t-broken", "t-sync"):
            service.remove_visit_listener(n)


def test_registering_same_listener_name_replaces_it():
    calls = []
    service.add_visit_listener("t-dup", lambda e: calls.append(1))
    service.add_visit_listener("t-dup", lambda e: calls.append(2))
    try:
        asyncio.run(service.notify_visit(_event()))
        assert calls == [2]
    finally:
        service.remove_visit_listener("t-dup")


async def run_module_tests():
    """Entry point used by the ChaCC backbone (test_entry_point in module_meta.json)."""
    test_generated_codes_are_valid_and_varied()
    test_create_schema_validates_url_and_code()
