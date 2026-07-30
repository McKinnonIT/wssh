from datetime import datetime, timedelta, timezone

from wssh.config import WsshConfig
from wssh.targets import cache_is_fresh

CONFIG = WsshConfig(targets_cache_ttl_hours=24)


def test_cache_is_fresh() -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert cache_is_fresh({"fetched_at": now}, CONFIG)


def test_cache_is_stale() -> None:
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert not cache_is_fresh({"fetched_at": old}, CONFIG)
