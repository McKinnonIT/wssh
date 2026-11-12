#!/usr/bin/env bash
# Install wssh and dependencies.
#
#   git clone git@github.com:McKinnonIT/wssh.git && bash wssh/install.sh
#   gh repo clone McKinnonIT/wssh -- --depth 1 && bash wssh/install.sh
#
# The repo is private, so the install needs a GitHub credential. Either an SSH
# key or an authenticated `gh` works — whichever this machine has is picked.
#
# Override repo: WSSH_REPO=https://github.com/you/wssh.git bash install.sh

set -euo pipefail

WSSH_REPO="${WSSH_REPO:-}"
WSSH_SSH_URL="ssh://git@github.com/McKinnonIT/wssh.git"
WSSH_HTTPS_URL="https://github.com/McKinnonIT/wssh.git"

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
            elif need_cmd pacman && can_sudo; then
                echo "Installing Python, pipx, and OpenSSH via pacman…"
                sudo pacman -Sy --needed --noconfirm python python-pipx openssh
            fi
            ;;
    esac
}

ensure_python() {
    need_cmd python3 || err "python3 is required (Python 3.10+). Install it and re-run."
    python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
        || err "Python 3.10+ is required."
}

can_read_repo() {
    # Never prompt: a missing credential must fail fast, not stop on a password
    # nobody can see when this runs from a pipe.
    GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND="ssh -oBatchMode=yes" \
        git ls-remote "$1" HEAD >/dev/null 2>&1
}

resolve_repo() {
    # The repo is private, so the URL that works depends on the credential this
    # machine has: an SSH key, or a gh token. Try SSH first — it needs no setup
    # step — then gh. An explicit WSSH_REPO wins: pointing at a fork means it.
    if [ -n "$WSSH_REPO" ]; then
        return 0
    fi
    need_cmd git || err "git is required to install from the repo. Install it and re-run."

    if can_read_repo "$WSSH_SSH_URL"; then
        WSSH_REPO="$WSSH_SSH_URL"
        return 0
    fi
    if need_cmd gh && gh auth status >/dev/null 2>&1; then
        # Teaches git to use the gh token for github.com, so `wssh update` keeps
        # working later from a plain HTTPS URL.
        gh auth setup-git >/dev/null 2>&1 || true
        if can_read_repo "$WSSH_HTTPS_URL"; then
            WSSH_REPO="$WSSH_HTTPS_URL"
            return 0
        fi
    fi

    err "no GitHub credential can reach McKinnonIT/wssh (it is private).
  Set up ONE of these, then re-run:
    SSH key:  https://github.com/settings/keys  (test: ssh -T git@github.com)
    gh CLI:   gh auth login                     (test: gh auth status)"
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

main() {
    if [ "$(id -u)" -eq 0 ]; then
        err "Don't run as root. Run as your normal user."
    fi

    install_system_packages
    ensure_python
    ensure_pipx
    resolve_repo

    echo "Installing wssh from ${WSSH_REPO}…"
    pipx install --force "git+${WSSH_REPO}"

    echo ""
    echo "Done. Next step:"
    echo "  wssh setup"
}

main "$@"
