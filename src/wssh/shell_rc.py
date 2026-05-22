"""Detect and update shell rc files."""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

from wssh.constants import COMPLETION_BEGIN, COMPLETION_END, LEGACY_WRAPPER_BEGIN, LEGACY_WRAPPER_END


def detect_rc_file() -> Path:
    shell_name = os.path.basename(os.environ.get("SHELL", "/bin/bash"))
    home = Path.home()
    if shell_name == "zsh":
        return home / ".zshrc"
    if shell_name == "bash":
        if os.uname().sysname == "Darwin" and (home / ".bash_profile").is_file():
            return home / ".bash_profile"
        return home / ".bashrc"
    return home / ".profile"


def detect_shell_name() -> str:
    return os.path.basename(os.environ.get("SHELL", "bash"))


def _remove_block(content: str, begin: str, end: str) -> str:
    lines = content.splitlines(keepends=True)
    out: list[str] = []
    skip = False
    for line in lines:
        if begin in line:
            skip = True
            continue
        if end in line:
            skip = False
            continue
        if not skip:
            out.append(line)
    return "".join(out)


def remove_marked_blocks(path: Path) -> bool:
    if not path.is_file():
        return False
    original = path.read_text(encoding="utf-8")
    updated = _remove_block(
        _remove_block(original, LEGACY_WRAPPER_BEGIN, LEGACY_WRAPPER_END),
        COMPLETION_BEGIN,
        COMPLETION_END,
    )
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def completion_block(shell: str) -> str:
    if shell == "zsh":
        return (
            f"\n{COMPLETION_BEGIN}\n"
            f"# Added by wssh — tab-complete Warpgate SSH targets\n"
            f"# Place this block after 'compinit' in .zshrc if completion fails.\n"
            f"if command -v wssh >/dev/null 2>&1; then\n"
            f'  eval "$(wssh completion zsh)"\n'
            f"fi\n"
            f"{COMPLETION_END}\n"
        )
    return (
        f"\n{COMPLETION_BEGIN}\n"
        f"# Added by wssh — tab-complete Warpgate SSH targets\n"
        f"if command -v wssh >/dev/null 2>&1; then\n"
        f'  eval "$(wssh completion bash)"\n'
        f"fi\n"
        f"{COMPLETION_END}\n"
    )


def install_completion(path: Path, shell: str, dry_run: bool = False) -> None:
    block = completion_block(shell)
    if path.is_file() and COMPLETION_BEGIN in path.read_text(encoding="utf-8"):
        if dry_run:
            return
        remove_marked_blocks(path)
    if dry_run:
        return
    if path.is_file():
        backup = path.with_suffix(path.suffix + f".bak.{datetime.now():%Y%m%d%H%M%S}")
        shutil.copy2(path, backup)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(block)
