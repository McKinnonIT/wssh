"""JSON caches under ~/.wssh/cache, stamped with a fetch time.

Everything cached here is a convenience copy of something Warpgate or GitHub can
be asked for again, so an unreadable or unwritable cache is never an error — it
is a miss.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from wssh.config import default_cache_dir


def cache_path(name: str) -> Path:
    return default_cache_dir() / name


def read_cache(name: str) -> dict[str, Any]:
    """Cached payload, or empty when missing, unreadable, or malformed."""
    try:
        data = json.loads(cache_path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_cache(name: str, payload: dict[str, Any]) -> None:
    """Stamp and store. A read-only cache dir must not break the command."""
    path = cache_path(name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({**payload, "fetched_at": time.time()}, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def drop_cache(name: str) -> None:
    """Forget the cached result so the next read goes back to the source."""
    try:
        cache_path(name).unlink(missing_ok=True)
    except OSError:
        pass


def is_fresh(data: dict[str, Any] | None, ttl_seconds: int) -> bool:
    """Pre-0.2 caches stored an ISO string in ``fetched_at`` — those read as stale."""
    try:
        return time.time() - float(data["fetched_at"]) < ttl_seconds
    except (KeyError, TypeError, ValueError):
        return False
