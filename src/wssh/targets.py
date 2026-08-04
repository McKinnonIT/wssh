"""Cache Warpgate SSH target names for tab completion."""

from __future__ import annotations

import difflib
import json
import time
from pathlib import Path
from typing import Any

from wssh.config import WsshConfig, default_cache_dir
from wssh.warpgate import WarpgateClient

CACHE_TTL_SECONDS = 24 * 3600


def cache_path() -> Path:
    return default_cache_dir() / "targets.json"


def load_cache(path: Path | None = None) -> dict[str, Any] | None:
    p = path or cache_path()
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def cache_is_fresh(data: dict[str, Any] | None) -> bool:
    if not data:
        return False
    try:
        # Pre-0.2 caches stored an ISO string here; treat those as stale.
        return time.time() - float(data["fetched_at"]) < CACHE_TTL_SECONDS
    except (KeyError, TypeError, ValueError):
        return False


def save_cache(names: list[str], path: Path | None = None) -> Path:
    p = path or cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"fetched_at": time.time(), "names": sorted(set(names))}
    p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return p


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
    cached = load_cache()
    if not force_refresh and cache_is_fresh(cached):
        return list(cached.get("names", []))

    if cache_only:
        if cached:
            return list(cached.get("names", []))
        return []

    names = fetch_ssh_target_names(config)
    save_cache(names)
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
