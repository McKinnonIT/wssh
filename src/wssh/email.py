"""Normalize McKinnon Google Workspace usernames."""

from __future__ import annotations

import re
import subprocess

from wssh.constants import WARPGATE_DOMAIN


def git_default_email() -> str:
    try:
        result = subprocess.run(
            ["git", "config", "--global", "user.email"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    email = (result.stdout or "").strip()
    if not email:
        return ""
    if "@" in email:
        local, _, domain = email.partition("@")
        if domain == WARPGATE_DOMAIN:
            return email
        if domain and local:
            return f"{local}@{WARPGATE_DOMAIN}"
    return ""


def normalize_email(raw: str, domain: str = WARPGATE_DOMAIN) -> str:
    """Append @domain when the user omits it (e.g. sam.neal -> sam.neal@domain)."""
    value = raw.strip()
    if not value:
        return ""
    if "@" not in value:
        return f"{value}@{domain}"
    return value


def is_org_email(email: str, domain: str = WARPGATE_DOMAIN) -> bool:
    return email.endswith(f"@{domain}")


def short_username(email: str, domain: str = WARPGATE_DOMAIN) -> str:
    if email.endswith(f"@{domain}"):
        return email[: -len(domain) - 1]
    return email.split("@", 1)[0]


def looks_like_local_part(value: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9._+-]+$", value))
