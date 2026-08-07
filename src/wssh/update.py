"""Reinstall wssh from GitHub, and notice when a newer commit is available.

Commits are the signal, not versions. The distribution version is derived from
git (``0.0.1.dev31+ga0e2b10``), so it does identify a build — but reading it back
tells you only what you already have, never what the remote has. pip records the
exact commit a VCS install came from (PEP 610 ``direct_url.json``), and
``git ls-remote`` reads the tip of the default branch without cloning or
authenticating.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, distribution, version

from rich.console import Console

from wssh.cache import drop_cache, is_fresh, read_cache, write_cache

DEFAULT_REPO = "https://github.com/McKinnonIT/wssh.git"
CACHE_NAME = "update.json"
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
    """What ``wssh version`` prints: the commit, which is the only real build id.

    The distribution version is git-derived and carries this same commit, so
    printing both would just say it twice, more verbosely.
    """
    commit = installed_commit()
    if commit:
        return commit[:7]
    # A local-directory install records no commit, but its git-derived version
    # still names one (0.0.1.dev31+g6d9ac2de4) — better than nothing.
    try:
        return version("wssh")
    except PackageNotFoundError:
        return "unknown"


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


def check_disabled() -> bool:
    """WSSH_NO_UPDATE_CHECK — for air-gapped machines and CI.

    Suppresses the checks nobody asked for. ``wssh update --check`` ignores it:
    checking is the entire point of that command.
    """
    return bool(os.environ.get("WSSH_NO_UPDATE_CHECK", "").strip())


def check_for_update() -> str | None:
    """Remote commit when it differs from the installed one, else None.

    Result is cached for a day, so the network is touched once regardless of how
    often wssh runs.
    """
    if check_disabled():
        return None
    local = installed_commit()
    if not local:
        return None

    cached = read_cache(CACHE_NAME)
    if is_fresh(cached, CHECK_INTERVAL_SECONDS):
        remote = cached.get("remote_commit")
    else:
        remote = remote_commit()
        # Recorded even when None: an outage must not be retried on every run.
        write_cache(CACHE_NAME, {"remote_commit": remote})

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


def report_update_status(*, brief: bool = False) -> int:
    """Say where this copy stands, and how to move it.

    ``brief`` drops the current commit from the up-to-date line, for callers
    like ``wssh version`` that have just printed it.
    """
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

    write_cache(CACHE_NAME, {"remote_commit": remote})
    if remote == local:
        suffix = "" if brief else f" [dim]({local[:7]})[/dim]"
        console.print(f"[green]Up to date[/green]{suffix}")
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


def run_update(*, force: bool = False) -> int:
    """Install the latest commit, skipping the reinstall when already on it."""
    local = installed_commit()
    remote = remote_commit() if local else None
    if remote:
        write_cache(CACHE_NAME, {"remote_commit": remote})

    if remote and remote == local:
        if not force:
            console.print(
                f"[green]Already up to date[/green] [dim]({local[:7]})[/dim]\n"
                "[dim]Nothing to install — use --force to reinstall anyway.[/dim]"
            )
            return 0
        console.print(f"[dim]Reinstalling {local[:7]}[/dim]")
    elif remote:
        console.print(f"[bold]Updating[/bold] [dim]{local[:7]} → {remote[:7]}[/dim]")
    # Either side unknown — not a git install, or the remote is unreachable —
    # means there is nothing to compare. Defer to the user and install: they
    # asked, and ls-remote's short timeout can fail on a link a clone survives.

    cmd = update_command()
    console.print(f"[dim]$ {' '.join(cmd)}[/dim]")
    code = subprocess.call(cmd)
    if code != 0:
        console.print("[red]Update failed[/red]")
        return code
    # This process still reports the pre-update commit, so a stale cached result
    # would keep nagging about an update that just landed.
    drop_cache(CACHE_NAME)
    console.print("[green]wssh updated[/green] [dim]— open a new shell to reload completion[/dim]")
    return 0
