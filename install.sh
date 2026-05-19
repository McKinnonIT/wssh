#!/usr/bin/env bash
# Install wssh and dependencies.
#
#   curl -fsSL https://raw.githubusercontent.com/McKinnonIT/wssh/main/install.sh | bash
#
# Override repo: WSSH_REPO=https://github.com/you/wssh.git bash install.sh

set -euo pipefail

WSSH_REPO="${WSSH_REPO:-https://github.com/McKinnonIT/wssh.git}"
WSSH_GIT_SPEC="git+${WSSH_REPO}"

err() {
    echo "wssh install: $*" >&2
    exit 1
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1
}

can_sudo() {
    need_cmd sudo && [ "$(id -u)" -ne 0 ]
}

install_system_packages() {
    if need_cmd ssh && need_cmd python3 && need_cmd pipx; then
        return 0
    fi

    case "$(uname -s)" in
        Darwin)
            if need_cmd brew; then
                echo "Installing Python, pipx, and OpenSSH via Homebrew…"
                brew install python pipx openssh 2>/dev/null || brew install python pipx openssh
            fi
            ;;
        Linux)
            if need_cmd apt-get && can_sudo; then
                echo "Installing Python, pipx, and OpenSSH via apt…"
                sudo apt-get update -qq
                sudo apt-get install -y python3 python3-pip pipx openssh-client
            elif need_cmd dnf && can_sudo; then
                echo "Installing Python, pipx, and OpenSSH via dnf…"
                sudo dnf install -y python3 python3-pip pipx openssh-clients
            fi
            ;;
    esac
}

ensure_python() {
    need_cmd python3 || err "python3 is required (Python 3.10+). Install it and re-run."
    python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
        || err "Python 3.10+ is required."
}

ensure_pipx() {
    if need_cmd pipx; then
        return 0
    fi
    echo "Installing pipx…"
    python3 -m pip install --user pipx
    python3 -m pipx ensurepath
    export PATH="${HOME}/.local/bin:${PATH}"
    need_cmd pipx || err "pipx not on PATH — open a new shell or run: export PATH=\"\${HOME}/.local/bin:\${PATH}\""
}

warn_legacy_shell_function() {
    if type wssh 2>/dev/null | grep -qE 'function|alias'; then
        echo ""
        echo "WARNING: A legacy wssh shell function is still loaded." >&2
        echo "  Remove the 'warpgate wssh wrapper' block from ~/.zshrc, then: source ~/.zshrc" >&2
        echo ""
    fi
}

main() {
    if [ "$(id -u)" -eq 0 ]; then
        err "Don't run as root. Run as your normal user."
    fi

    install_system_packages
    ensure_python
    ensure_pipx
    warn_legacy_shell_function

    echo "Installing wssh from ${WSSH_REPO}…"
    pipx install --force "$WSSH_GIT_SPEC"

    echo ""
    echo "Done. Next step:"
    echo "  wssh setup"
}

main "$@"
