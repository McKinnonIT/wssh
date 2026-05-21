"""Normalize Warpgate usernames and email addresses."""

from __future__ import annotations

import re
import subprocess


def git_default_email(domain: str) -> str:
    """Return a git-configured email when it matches the configured domain."""
    if not domain:
        return ""
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
        local, _, addr_domain = email.partition("@")
        if addr_domain == domain:
            return email
        if addr_domain and local:
            return f"{local}@{domain}"
    return ""


def normalize_email(raw: str, domain: str) -> str:
    """Append @domain when the user omits it (e.g. alice -> alice@domain)."""
    value = raw.strip()
    if not value:
        return ""
    if "@" not in value:
        if not domain:
            return value
        return f"{value}@{domain}"
    return value


def is_org_email(email: str, domain: str) -> bool:
    if not domain:
        return True
    return email.endswith(f"@{domain}")


def short_username(email: str, domain: str) -> str:
    if domain and email.endswith(f"@{domain}"):
        return email[: -len(domain) - 1]
    return email.split("@", 1)[0]


def looks_like_local_part(value: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9._+-]+$", value))
