"""Tests for usage guards (§14, §20). No API key needed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from voice.usage_guard import UsageGuard, UsageGuardTripped


def test_allows_normal_use():
    g = UsageGuard()
    g.check_request("Hello there.")
    assert g.stats()["rpm_used"] == 1


def test_rate_limit_trips():
    g = UsageGuard(max_requests_per_minute=2)
    g.check_request("one")
    g.check_request("two")
    with pytest.raises(UsageGuardTripped):
        g.check_request("three")
    assert g.stats()["trips"] == 1


def test_oversize_response_rejected():
    g = UsageGuard(max_response_chars=10)
    with pytest.raises(UsageGuardTripped):
        g.check_request("this is way too long for the limit")


def test_byte_budget_enforced():
    g = UsageGuard(max_utf8_bytes_per_session=20)
    g.check_request("12345")
    with pytest.raises(UsageGuardTripped):
        g.check_request("123456789012345678901")


def test_single_stream_slot():
    g = UsageGuard(max_concurrent_streams=1)
    with g.acquire_stream():
        with pytest.raises(UsageGuardTripped):
            with g.acquire_stream():
                pass
    with g.acquire_stream():
        pass
