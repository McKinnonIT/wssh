"""Cache Warpgate SSH target names for tab completion."""

from __future__ import annotations

import difflib

from wssh.cache import is_fresh, read_cache, write_cache
from wssh.config import WsshConfig
from wssh.warpgate import WarpgateClient

CACHE_NAME = "targets.json"
CACHE_TTL_SECONDS = 24 * 3600


def fetch_ssh_target_names(config: WsshConfig) -> list[str]:
    with WarpgateClient(config) as client:
        targets = client.get_targets()
    return sorted(t["name"] for t in targets if (t.get("kind") or "").lower() == "ssh")


def get_target_names(
    config: WsshConfig,
    *,
    force_refresh: bool = False,
    cache_only: bool = False,
) -> list[str]:
    cached = read_cache(CACHE_NAME)
    if cache_only or (not force_refresh and is_fresh(cached, CACHE_TTL_SECONDS)):
        return list(cached.get("names", []))

    names = fetch_ssh_target_names(config)
    write_cache(CACHE_NAME, {"names": sorted(set(names))})
    return names


def suggest_targets(name: str, known: list[str], limit: int = 3) -> list[str]:
    """Known targets a typo'd name probably meant, best first. Empty if nothing is close.

    Prefix hits come first and skip difflib entirely: "pangolin" -> "pangolin01"
    is obvious to a human but scores below any useful similarity cutoff once the
    typed name is much shorter than the real one.
    """
    lowered = name.strip().lower()
    if not lowered:
        return []
    prefix = [n for n in known if n.lower().startswith(lowered)]
    if prefix:
        return prefix[:limit]
    return difflib.get_close_matches(lowered, known, n=limit, cutoff=0.6)
