from datetime import datetime, timedelta, timezone

from wssh.targets import cache_is_fresh


def test_cache_is_fresh() -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert cache_is_fresh({"fetched_at": now}, ttl_hours=24)


def test_cache_is_stale() -> None:
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert not cache_is_fresh({"fetched_at": old}, ttl_hours=24)
