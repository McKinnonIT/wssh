"""Cache Warpgate SSH target names for tab completion."""

from __future__ import annotations

import difflib
import ipaddress

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


MIN_TYPO_LENGTH = 3
# A prefix must be most of the name it completes: "zabbix" means zabbix02, not
# every zabbix-*-nixos host that happens to share the word.
PREFIX_COVERAGE = 0.7
# Tight enough that only a slip of one or two characters gets through.
SIMILARITY_CUTOFF = 0.75


def _is_ip(name: str) -> bool:
    try:
        ipaddress.ip_address(name)
    except ValueError:
        return False
    return True


def suggest_targets(name: str, known: list[str], limit: int = 3) -> list[str]:
    """Known targets a typo'd name probably meant, best first. Empty if nothing is close.

    Deliberately narrow. The suggestion is offered at a y/n prompt that defaults to
    yes, so a loose match opens a session on a machine the user never asked for —
    saying nothing is the better failure.

    Prefix hits come first and skip difflib entirely: "pangolin" -> "pangolin01"
    is obvious to a human but scores below any useful similarity cutoff once the
    typed name is much shorter than the real one. They must still cover most of
    the candidate, or one shared word drags in the whole family.

    IP addresses never match, on either side: one digit apart is a different
    machine, not a typo, and nothing in the string tells you which.
    """
    typed = name.strip().lower()
    if len(typed) < MIN_TYPO_LENGTH or _is_ip(typed):
        return []
    candidates = {n.lower(): n for n in known if not _is_ip(n.strip())}

    prefix = [original for low, original in candidates.items() if low.startswith(typed)]
    if len(prefix) == 1:
        # Nothing to be ambiguous about: "stt" can only be stt-server.
        return prefix
    covering = [n for n in prefix if len(typed) >= len(n) * PREFIX_COVERAGE]
    if covering:
        return sorted(covering, key=len)[:limit]  # closest completion first
    close = difflib.get_close_matches(typed, candidates, n=limit, cutoff=SIMILARITY_CUTOFF)
    return [candidates[match] for match in close]
