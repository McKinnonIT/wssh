#!/usr/bin/env bash
# wssh-setup.sh — Bootstrap the wssh Python CLI and run first-time setup.
#
# Safe to re-run. Prefer: pipx install . && wssh setup

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRY_RUN=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [--dry-run] [--help]

Installs the wssh Python package and runs interactive setup.

Options:
  -n, --dry-run    Pass --dry-run to wssh setup
  -h, --help       Show this help
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        -n|--dry-run) DRY_RUN=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
    esac
done

if [ "$(id -u)" -eq 0 ]; then
    echo "Don't run this script as root." >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required. Install Python 3.10+ and re-run." >&2
    exit 1
fi

warn_legacy_function() {
    if type wssh 2>/dev/null | grep -qE 'function|alias'; then
        echo "" >&2
        echo "WARNING: A legacy wssh shell function is still loaded." >&2
        echo "  'wssh setup' will try to SSH to a host named 'setup' until you remove it." >&2
        echo "" >&2
        echo "  Remove the block marked 'warpgate wssh wrapper' from ~/.zshrc, then:" >&2
        echo "    source ~/.zshrc" >&2
        echo "" >&2
        echo "  This script will use the pipx binary directly." >&2
        echo "" >&2
    fi
}

install_wssh() {
    if command -v pipx >/dev/null 2>&1; then
        pipx install --force "$SCRIPT_DIR"
        return
    fi
    python3 -m pip install --user "$SCRIPT_DIR"
}

resolve_wssh_bin() {
    # Prefer pipx venv binary — avoids shell function shadowing `wssh`
    if command -v pipx >/dev/null 2>&1; then
        local venv
        venv="$(pipx environment --value PIPX_HOME 2>/dev/null)/venvs/wssh/bin/wssh"
        if [ -x "$venv" ]; then
            echo "$venv"
            return
        fi
    fi
    if [ -x "${HOME}/.local/bin/wssh" ]; then
        echo "${HOME}/.local/bin/wssh"
        return
    fi
    command -v wssh
}

echo "Installing wssh…"
install_wssh
warn_legacy_function

WSSH_BIN="$(resolve_wssh_bin)"
if [ -z "$WSSH_BIN" ] || [ ! -x "$WSSH_BIN" ]; then
    echo "wssh binary not found after install." >&2
    exit 1
fi

SETUP_ARGS=()
if $DRY_RUN; then
    SETUP_ARGS+=(--dry-run)
fi

echo "Running: $WSSH_BIN setup"
exec "$WSSH_BIN" setup "${SETUP_ARGS[@]}"
