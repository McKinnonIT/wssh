"""Reinstall wssh from GitHub, and notice when a newer commit is available.

Commits are the only usable signal here: the repo has no tags or releases, and
``__version__`` has been ``0.1.0`` across every commit, so comparing versions
would report "up to date" forever. pip records the exact commit a VCS install
came from (PEP 610 ``direct_url.json``), and ``git ls-remote`` reads the tip of
the default branch without cloning or authenticating.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

from rich.console import Console

from wssh.config import default_cache_dir

DEFAULT_REPO = "https://github.com/McKinnonIT/wssh.git"
CHECK_INTERVAL_SECONDS = 24 * 3600
LS_REMOTE_TIMEOUT = 5

console = Console()
# The notice is decoration around the real output. stdout belongs to the command
# (`wssh targets list | xargs` must stay clean), so it goes to stderr.
err_console = Console(stderr=True)


# --------------------------------------------------------------------------- #
# Where this copy came from
# --------------------------------------------------------------------------- #


def _direct_url() -> dict:
    """pip's record of the install source (PEP 610). Empty when unavailable."""
    try:
        raw = distribution("wssh").read_text("direct_url.json")
    except (PackageNotFoundError, OSError):
        return {}
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}


def installed_commit() -> str | None:
    """Commit this copy was built from, or None when not installed from git.

    None is the honest answer for an editable checkout or a PyPI-style install:
    there is no commit to compare, so no update can be claimed.
    """
    return (_direct_url().get("vcs_info") or {}).get("commit_id")


def version_line() -> str:
    """``0.1.0 (e0a0d9d)`` — the commit is what actually identifies a build.

    Version first, so ``wssh version | cut -d' ' -f1`` still works.
    """
    from wssh import __version__

    commit = installed_commit()
    return f"{__version__} ({commit[:7]})" if commit else __version__


def repo_url() -> str:
    """Repo to update from: WSSH_REPO, else where this copy came from, else default.

    The recorded URL is only trusted for a VCS install — a local-directory
    install records a ``file://`` path that is not necessarily a git repo.
    """
    override = os.environ.get("WSSH_REPO", "").strip()
    if override:
        return override
    data = _direct_url()
    if data.get("vcs_info"):
        return data.get("url") or DEFAULT_REPO
    return DEFAULT_REPO


def repo_spec() -> str:
    """pip requirement for the wssh repo."""
    return f"git+{repo_url()}"


# --------------------------------------------------------------------------- #
# What is on the remote
# --------------------------------------------------------------------------- #


def remote_commit(url: str | None = None) -> str | None:
    """Commit at the tip of the remote's default branch. None if unreachable.

    Both prompt-suppressing variables are load-bearing: a repo that turns
    private, or an SSH remote with a passphrase-protected key, would otherwise
    stop and ask for input — hanging a check the user never asked for.
    """
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_SSH_COMMAND": "ssh -oBatchMode=yes",
    }
    try:
        result = subprocess.run(
            ["git", "ls-remote", url or repo_url(), "HEAD"],
            capture_output=True,
            text=True,
            timeout=LS_REMOTE_TIMEOUT,
            env=env,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    fields = result.stdout.split()
    return fields[0] if fields else None


# --------------------------------------------------------------------------- #
# Cached check
# --------------------------------------------------------------------------- #


def cache_path() -> Path:
    return default_cache_dir() / "update.json"


def _load_cache() -> dict:
    try:
        return json.loads(cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_cache(remote: str | None) -> None:
    """Record the attempt, successful or not, so an outage is not retried every run."""
    path = cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"checked_at": time.time(), "remote_commit": remote}) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass  # a read-only cache dir must not break the command


def clear_cache() -> None:
    """Drop the cached result so the next run re-checks (used after updating)."""
    try:
        cache_path().unlink(missing_ok=True)
    except OSError:
        pass


def _cache_is_fresh(cached: dict) -> bool:
    try:
        return time.time() - float(cached["checked_at"]) < CHECK_INTERVAL_SECONDS
    except (KeyError, TypeError, ValueError):
        return False


def check_disabled() -> bool:
    """WSSH_NO_UPDATE_CHECK — for air-gapped machines and CI.

    Suppresses the checks nobody asked for. ``wssh update --check`` ignores it:
    checking is the entire point of that command.
    """
    return bool(os.environ.get("WSSH_NO_UPDATE_CHECK", "").strip())


def check_for_update(*, force: bool = False) -> str | None:
    """Remote commit when it differs from the installed one, else None.

    Result is cached for a day, so the network is touched once regardless of how
    often wssh runs.
    """
    if check_disabled():
        return None
    local = installed_commit()
    if not local:
        return None

    cached = _load_cache()
    if not force and _cache_is_fresh(cached):
        remote = cached.get("remote_commit")
    else:
        remote = remote_commit()
        _save_cache(remote)

    if not remote or remote == local:
        return None
    # ponytail: commit inequality, not ordering — two commits cannot be ranked
    # without a local clone, so a copy installed from a branch ahead of main
    # also reports "available". Both shas are printed so the notice stays true.
    # Tag releases and compare versions if that ever matters.
    return remote


def maybe_notify_update() -> None:
    """Print a one-line update notice. Never raises, never touches stdout."""
    if not sys.stderr.isatty():
        return  # piped or scripted: nobody is reading a banner
    try:
        remote = check_for_update()
        if not remote:
            return
        local = installed_commit() or "?"
        err_console.print(
            f"\n[yellow]Update available[/yellow] "
            f"[dim]({local[:7]} → {remote[:7]})[/dim] — run [bold]wssh update[/bold]"
        )
    except Exception:
        # A cosmetic version check must never be the reason a connection fails.
        return


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def report_update_status() -> int:
    """`wssh update --check`: say where this copy stands, and how to move it."""
    local = installed_commit()
    if not local:
        console.print(
            "[yellow]This copy was not installed from git, so there is nothing to "
            "compare against.[/yellow]\n"
            f"[dim]Install from the repo to enable update checks:[/dim] "
            f"pipx install --force {repo_spec()}"
        )
        return 0

    remote = remote_commit()
    if not remote:
        console.print(
            f"[yellow]Could not reach {repo_url()}[/yellow] "
            "[dim]— offline, or no access to the repo[/dim]"
        )
        return 0

    _save_cache(remote)
    if remote == local:
        console.print(f"[green]Up to date[/green] [dim]({local[:7]})[/dim]")
        return 0
    console.print(
        f"[yellow]Update available[/yellow] [dim]({local[:7]} → {remote[:7]})[/dim]\n"
        "Run [bold]wssh update[/bold] to install it."
    )
    return 0


def update_command() -> list[str]:
    """pipx when it is on PATH (how install.sh installs), else pip into this interpreter.

    ``--force`` / ``--force-reinstall`` are not optional: the version in
    pyproject rarely changes between commits, so pip would otherwise decide the
    requirement is already satisfied and install nothing.
    """
    spec = repo_spec()
    if shutil.which("pipx"):
        return ["pipx", "install", "--force", spec]
    return [sys.executable, "-m", "pip", "install", "--force-reinstall", spec]


def run_update() -> int:
    cmd = update_command()
    console.print(f"[dim]$ {' '.join(cmd)}[/dim]")
    code = subprocess.call(cmd)
    if code != 0:
        console.print("[red]Update failed[/red]")
        return code
    # This process still reports the pre-update commit, so a stale cached result
    # would keep nagging about an update that just landed.
    clear_cache()
    console.print("[green]wssh updated[/green] [dim]— open a new shell to reload completion[/dim]")
    return 0
