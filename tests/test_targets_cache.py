import time

from wssh.targets import CACHE_TTL_SECONDS, cache_is_fresh


def test_cache_is_fresh() -> None:
    assert cache_is_fresh({"fetched_at": time.time()})


def test_cache_is_stale() -> None:
    assert not cache_is_fresh({"fetched_at": time.time() - CACHE_TTL_SECONDS - 1})


def test_cache_missing_or_legacy_iso_timestamp_is_stale() -> None:
    assert not cache_is_fresh(None)
    assert not cache_is_fresh({})
    assert not cache_is_fresh({"fetched_at": "2026-07-30T00:00:00Z"})
