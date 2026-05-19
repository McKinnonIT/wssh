"""Generate bash/zsh completion scripts."""

from __future__ import annotations

from wssh.config import load_config
from wssh.targets import get_target_names
from wssh.warpgate import WarpgateApiError


def _target_names() -> list[str]:
    try:
        return get_target_names(load_config(), cache_only=True)
    except WarpgateApiError:
        return []


def bash_completion() -> str:
    names = _target_names()
    names_str = " ".join(names)
    return f"""# wssh bash completion
_wssh() {{
    local cur prev words cword
    _init_completion || return
    local commands="setup setup-server auth targets completion credentials"
    if [[ $cword -eq 1 ]]; then
        local targets="{names_str}"
        COMPREPLY=($(compgen -W "$commands $targets" -- "$cur"))
        return
    fi
    case "${{words[1]}}" in
        auth)
            COMPREPLY=($(compgen -W "login logout" -- "$cur"))
            ;;
        targets)
            COMPREPLY=($(compgen -W "list refresh" -- "$cur"))
            ;;
        completion)
            COMPREPLY=($(compgen -W "bash zsh" -- "$cur"))
            ;;
        credentials)
            COMPREPLY=($(compgen -W "add-key" -- "$cur"))
            ;;
    esac
}}
complete -F _wssh wssh
"""


def _zsh_quote(word: str) -> str:
    escaped = word.replace("'", "'\\''")
    return f"'{escaped}'"


def zsh_completion() -> str:
    names = _target_names()
    targets_literal = " ".join(_zsh_quote(n) for n in names)
    return f"""#compdef wssh

_wssh() {{
    local -a commands targets
    commands=(
        'setup:Configure wssh and Warpgate access'
        'setup-server:Bootstrap a server in Warpgate'
        'auth:Authentication commands'
        'targets:List Warpgate targets'
        'completion:Shell completion scripts'
        'credentials:Manage credentials'
        'doctor:Check install issues'
        'version:Show version'
    )
    targets=({targets_literal})
    _arguments -C \\
        '1: :->cmd' \\
        '*::arg:->args'
    case $state in
        cmd)
            _describe 'command' commands
            _describe 'target' targets
            ;;
        args)
            case $words[1] in
                auth)
                    _values 'auth command' login logout
                    ;;
                targets)
                    _values 'targets command' list refresh
                    ;;
                completion)
                    _values 'shell' bash zsh
                    ;;
                credentials)
                    _values 'credentials command' add-key
                    ;;
            esac
            ;;
    esac
}}

compdef _wssh wssh
"""
