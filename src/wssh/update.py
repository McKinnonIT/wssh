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
import re
import shutil
import subprocess
import sys
import time
from importlib.metadata import PackageNotFoundError, distribution, version
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.text import Text

from wssh.config import default_cache_dir

DEFAULT_REPO = "https://github.com/McKinnonIT/wssh.git"
LS_REMOTE_TIMEOUT = 5
UNREACHABLE_WARN_INTERVAL = 24 * 3600
# The URL that last answered, which is not always the one pip recorded.
_reachable_url: str | None = None

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


# --------------------------------------------------------------------------- #
# What is on the remote
# --------------------------------------------------------------------------- #


def alternate_urls(url: str) -> list[str]:
    """The same GitHub repo addressed the other way round: https <-> ssh.

    pip records the URL a copy was installed from, and that URL stops working
    when the repo turns private and the machine's credential is the other kind.
    The repo did not move — only the transport that can reach it did.
    """
    https = re.match(r"https://github\.com/(.+?)(?:\.git)?$", url)
    if https:
        return [f"ssh://git@github.com/{https.group(1)}.git"]
    ssh = re.match(r"(?:ssh://)?git@github\.com[:/](.+?)(?:\.git)?$", url)
    if ssh:
        return [f"https://github.com/{ssh.group(1)}.git"]
    return []


def _ls_remote(url: str) -> str | None:
    """Commit at the tip of ``url``'s default branch. None if unreachable.

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
            ["git", "ls-remote", url, "HEAD"],
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


def remote_commit(url: str | None = None) -> str | None:
    """Commit at the tip of the remote, over whichever transport can reach it.

    Remembers the URL that answered, so an update installs from the same place
    the check read — not from the recorded one that just failed.
    """
    global _reachable_url
    for candidate in [url or repo_url()] if url else [repo_url(), *alternate_urls(repo_url())]:
        commit = _ls_remote(candidate)
        if commit:
            _reachable_url = candidate
            return commit
    return None


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

    Asked live, every run. A day-long cache meant a commit pushed after the last
    check stayed invisible for a day — exactly when you want to hear about it.
    The caller has already established that someone is watching, and pays one
    ls-remote (5s ceiling) for the answer.
    """
    if check_disabled():
        return None
    local = installed_commit()
    if not local:
        return None

    remote = remote_commit()
    if not remote or remote == local:
        return None
    # ponytail: commit inequality, not ordering — two commits cannot be ranked
    # without a local clone, so a copy installed from a branch ahead of main
    # also reports "available". Both shas are printed so the notice stays true.
    # Tag releases and compare versions if that ever matters.
    return remote


# --------------------------------------------------------------------------- #
# The notice itself
# --------------------------------------------------------------------------- #

# A glint drawn along the line four times, each pass at the same unhurried pace —
# a blade turning in the light, not one being yanked out. Costs ~2.8s, which is
# why it only ever runs when there is something to say and someone to see it.
SHIMMER_SECONDS = 0.62
SHIMMER_PASSES = (SHIMMER_SECONDS,) * 4
SHIMMER_PAUSE = 0.07
SHIMMER_FPS = 60
_CORE, _HOT, _WARM = 3, 4, 8  # glint width, then the trail behind it


def animation_disabled() -> bool:
    """WSSH_NO_ANIMATION — for anyone who wants the notice without the wait."""
    return bool(os.environ.get("WSSH_NO_ANIMATION", "").strip())


def _notice_parts(local: str, remote: str) -> list[tuple[str, str]]:
    """The notice as (text, base style) runs, so one line serves both renderers."""
    return [
        ("Update available ", "yellow"),
        (f"({local} → {remote})", "dim"),
        (" — run ", "yellow"),
        ("wssh update", "bold yellow"),
    ]


def _ease(t: float) -> float:
    """Ease-in-out cubic: slow at both ends, quick through the middle."""
    return 4 * t**3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def _shimmer_frame(parts: list[tuple[str, str]], pos: float, *, flash: bool = False) -> Text:
    """One frame: the line with the glint and its trail centred on ``pos``."""
    out = Text("\n")
    index = 0
    for text, base in parts:
        for char in text:
            offset = index - pos
            if flash:
                style = "bold yellow" if base == "dim" else "bold white"
            elif 0 <= offset < _CORE:
                style = "bold white"
            elif -_HOT <= offset < 0:
                style = "bold yellow"
            elif -_WARM <= offset < -_HOT:
                style = "yellow"
            else:
                style = base
            out.append(char, style=style)
            index += 1
    return out


def _shimmer(parts: list[tuple[str, str]]) -> None:
    """Draw the glint across the notice, then leave the line sitting there."""
    width = sum(len(text) for text, _ in parts)
    span = width + _WARM + _CORE
    rest = _shimmer_frame(parts, -span)  # glint offscreen: the plain line
    with Live(rest, console=err_console, refresh_per_second=SHIMMER_FPS) as live:
        for seconds in SHIMMER_PASSES:
            started = time.monotonic()
            while (elapsed := time.monotonic() - started) < seconds:
                live.update(_shimmer_frame(parts, -_WARM + _ease(elapsed / seconds) * span))
                time.sleep(1 / SHIMMER_FPS)
            time.sleep(SHIMMER_PAUSE)
        live.update(_shimmer_frame(parts, 0, flash=True))  # the blade catches the light
        time.sleep(SHIMMER_PAUSE)
        live.update(rest)


def _unreachable_stamp() -> Path:
    return default_cache_dir() / "update-unreachable"


def _warn_unreachable_once_a_day() -> None:
    """Silence is how a broken update check hid for weeks. Say it, but not hourly."""
    stamp = _unreachable_stamp()
    try:
        if time.time() - stamp.stat().st_mtime < UNREACHABLE_WARN_INTERVAL:
            return
    except OSError:
        pass  # never warned, or the cache is unreadable: warn now
    try:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.touch()
    except OSError:
        pass  # a read-only cache must not cost the warning
    err_console.print(
        f"\n[yellow]Cannot check for wssh updates[/yellow] [dim]({repo_url()})[/dim]\n"
        "[dim]The repo is private and this machine has no credential for it. Fix with "
        "[bold]gh auth login && gh auth setup-git[/bold], or add an SSH key to GitHub.[/dim]"
    )


def maybe_notify_update() -> None:
    """Print a one-line update notice. Never raises, never touches stdout."""
    if not (sys.stderr.isatty() and sys.stdout.isatty()):
        # Both, not just the stream it prints on. `eval "$(wssh completion zsh)"`
        # in an rc file has a terminal on stderr and a pipe on stdout — a banner
        # there greets every new shell, from a command the user never typed.
        return  # piped, captured, or scripted: nobody is reading a banner
    try:
        if check_disabled() or not installed_commit():
            return
        remote = check_for_update()
        if not remote:
            if not remote_commit():
                _warn_unreachable_once_a_day()
            return
        local = installed_commit() or "?"
        parts = _notice_parts(local[:7], remote[:7])
        if animation_disabled():
            line = Text("\n")
            for text, style in parts:
                line.append(text, style=style)
            err_console.print(line)
        else:
            _shimmer(parts)
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
            f"pipx install --force git+{repo_url()}"
        )
        return 0

    remote = remote_commit()
    if not remote:
        console.print(
            f"[yellow]Could not reach {repo_url()}[/yellow] "
            "[dim]— offline, or no access to the repo[/dim]"
        )
        return 0

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
    spec = f"git+{_reachable_url or repo_url()}"
    if shutil.which("pipx"):
        return ["pipx", "install", "--force", spec]
    return [sys.executable, "-m", "pip", "install", "--force-reinstall", spec]


def run_update(*, force: bool = False) -> int:
    """Install the latest commit, skipping the reinstall when already on it."""
    local = installed_commit()
    remote = remote_commit() if local else None

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
    console.print("[green]wssh updated[/green] [dim]— open a new shell to reload completion[/dim]")
    return 0
