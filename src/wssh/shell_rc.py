"""Detect and update shell rc files."""

from __future__ import annotations

import os
from pathlib import Path

COMPLETION_BEGIN = "# >>> wssh completion >>>"
COMPLETION_END = "# <<< wssh completion <<<"


def detect_shell_name() -> str:
    return os.path.basename(os.environ.get("SHELL", "bash"))


def detect_rc_file() -> Path:
    home = Path.home()
    shell_name = detect_shell_name()
    if shell_name == "zsh":
        return home / ".zshrc"
    if shell_name == "bash":
        if os.uname().sysname == "Darwin" and (home / ".bash_profile").is_file():
            return home / ".bash_profile"
        return home / ".bashrc"
    return home / ".profile"


def remove_completion_block(path: Path) -> bool:
    """Strip a previously installed wssh completion block. True if the file changed."""
    if not path.is_file():
        return False
    original = path.read_text(encoding="utf-8")
    out: list[str] = []
    skip = False
    for line in original.splitlines(keepends=True):
        if COMPLETION_BEGIN in line:
            skip = True
        elif COMPLETION_END in line:
            skip = False
        elif not skip:
            out.append(line)
    updated = "".join(out)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def completion_block(shell: str) -> str:
    # Only two scripts exist; anything else (fish, sh) gets the bash one, as before.
    shell = "zsh" if shell == "zsh" else "bash"
    # zsh only: compinit must already have run, and it usually has not by the time
    # a block appended to the end of .zshrc is read.
    ordering_note = (
        "# Place this block after 'compinit' in .zshrc if completion fails.\n"
        if shell == "zsh"
        else ""
    )
    return (
        f"\n{COMPLETION_BEGIN}\n"
        f"# Added by wssh — tab-complete Warpgate SSH targets\n"
        f"{ordering_note}"
        f"if command -v wssh >/dev/null 2>&1; then\n"
        f'  eval "$(wssh completion {shell})"\n'
        f"fi\n"
        f"{COMPLETION_END}\n"
    )


def install_completion(path: Path, shell: str, dry_run: bool = False) -> None:
    if dry_run:
        return
    remove_completion_block(path)  # idempotent: never stack duplicate blocks
    with path.open("a", encoding="utf-8") as fh:
        fh.write(completion_block(shell))
