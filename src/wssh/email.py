"""Normalize Warpgate usernames and email addresses."""

from __future__ import annotations

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
