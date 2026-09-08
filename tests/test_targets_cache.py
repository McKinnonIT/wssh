import json
import time

import pytest

from wssh import targets
from wssh.config import WsshConfig
from wssh.targets import CACHE_TTL_SECONDS, get_target_names


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    """Never touch the real cache, and never reach the network by accident."""
    monkeypatch.setattr("wssh.targets.default_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(
        targets,
        "fetch_ssh_target_names",
        lambda config: pytest.fail("unexpected API call"),
    )
    return tmp_path


def write_raw(tmp_path, payload: object) -> None:
    (tmp_path / "targets.json").write_text(json.dumps(payload), encoding="utf-8")


def test_fresh_cache_is_served_without_an_api_call(isolate) -> None:
    targets._write_cache(["dns01"])
    assert get_target_names(WsshConfig()) == ["dns01"]


def test_stale_cache_refetches_and_restamps(monkeypatch, isolate) -> None:
    write_raw(isolate, {"names": ["old"], "fetched_at": time.time() - CACHE_TTL_SECONDS - 1})
    monkeypatch.setattr(targets, "fetch_ssh_target_names", lambda config: ["dns01", "dns01"])
    assert get_target_names(WsshConfig()) == ["dns01", "dns01"]
    assert get_target_names(WsshConfig()) == ["dns01"]  # deduped on the way in


def test_cache_only_serves_a_stale_cache_rather_than_fetching(isolate) -> None:
    # Completion hooks take whatever is on disk — a legacy ISO stamp reads as
    # stale, but the names it holds are still the best answer available.
    write_raw(isolate, {"names": ["dns01"], "fetched_at": "2026-07-30T00:00:00Z"})
    assert get_target_names(WsshConfig(), cache_only=True) == ["dns01"]


def test_unreadable_cache_is_a_miss_not_an_error(monkeypatch, isolate) -> None:
    (isolate / "targets.json").write_text("{not json")
    assert get_target_names(WsshConfig(), cache_only=True) == []
    monkeypatch.setattr(targets, "fetch_ssh_target_names", lambda config: ["dns01"])
    assert get_target_names(WsshConfig()) == ["dns01"]


def test_unwritable_cache_dir_does_not_break_the_command(monkeypatch, isolate) -> None:
    # mkdir under a regular file raises NotADirectoryError — stands in for any
    # cache dir we cannot write to.
    (isolate / "blocker").write_text("")
    monkeypatch.setattr("wssh.targets.default_cache_dir", lambda: isolate / "blocker" / "cache")
    monkeypatch.setattr(targets, "fetch_ssh_target_names", lambda config: ["dns01"])
    assert get_target_names(WsshConfig()) == ["dns01"]
