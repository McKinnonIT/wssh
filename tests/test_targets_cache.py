import time

from wssh.cache import is_fresh, read_cache, write_cache
from wssh.targets import CACHE_TTL_SECONDS


def test_cache_is_fresh() -> None:
    assert is_fresh({"fetched_at": time.time()}, CACHE_TTL_SECONDS)


def test_cache_is_stale() -> None:
    assert not is_fresh({"fetched_at": time.time() - CACHE_TTL_SECONDS - 1}, CACHE_TTL_SECONDS)


def test_cache_missing_or_legacy_iso_timestamp_is_stale() -> None:
    assert not is_fresh(None, CACHE_TTL_SECONDS)
    assert not is_fresh({}, CACHE_TTL_SECONDS)
    assert not is_fresh({"fetched_at": "2026-07-30T00:00:00Z"}, CACHE_TTL_SECONDS)


def test_round_trip_stamps_the_payload(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("wssh.cache.default_cache_dir", lambda: tmp_path)
    write_cache("targets.json", {"names": ["dns01"]})
    cached = read_cache("targets.json")
    assert cached["names"] == ["dns01"]
    assert is_fresh(cached, CACHE_TTL_SECONDS)


def test_unreadable_cache_is_a_miss_not_an_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("wssh.cache.default_cache_dir", lambda: tmp_path)
    (tmp_path / "targets.json").write_text("{not json")
    assert read_cache("targets.json") == {}
