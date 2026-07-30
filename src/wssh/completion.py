"""Generate bash/zsh completion scripts."""

from __future__ import annotations

from wssh.config import load_config
from wssh.targets import get_target_names
from wssh.warpgate import WarpgateApiError

# Subcommands Typer cannot report: `completion`'s argument is a plain string.
_ARGUMENT_CHOICES = {"completion": ["bash", "zsh"]}


def _target_names() -> list[str]:
    try:
        return get_target_names(load_config(), cache_only=True)
    except WarpgateApiError:
        return []


def _command_help(command: object) -> str:
    doc = (getattr(command, "callback", None).__doc__ or "") if command else ""
    return getattr(command, "help", None) or doc.strip().split("\n")[0]


def command_tree() -> dict[str, tuple[str, list[str]]]:
    """Map command name -> (help, subcommands), read off the Typer app itself.

    Derived rather than duplicated: a hand-kept list drifts the moment a
    command is added.
    """
    from wssh.cli import app  # local import: cli imports this module

    tree: dict[str, tuple[str, list[str]]] = {}
    for cmd in app.registered_commands:
        name = cmd.name or (cmd.callback.__name__.replace("_", "-") if cmd.callback else "")
        if name:
            tree[name] = (_command_help(cmd), _ARGUMENT_CHOICES.get(name, []))
    for group in app.registered_groups:
        sub = group.typer_instance
        if not group.name or sub is None:
            continue
        subcommands = sorted(
            c.name or (c.callback.__name__.replace("_", "-") if c.callback else "")
            for c in sub.registered_commands
        )
        tree[group.name] = (sub.info.help or "", [s for s in subcommands if s])
    return tree


def bash_completion() -> str:
    tree = command_tree()
    commands = " ".join(sorted(tree))
    cases = "\n".join(
        f"""        {name})
            COMPREPLY=($(compgen -W "{' '.join(subs)}" -- "$cur"))
            ;;"""
        for name, (_, subs) in sorted(tree.items())
        if subs
    )
    return f"""# wssh bash completion
_wssh() {{
    local cur prev words cword
    _init_completion || return
    local commands="{commands}"
    if [[ $cword -eq 1 ]]; then
        local targets="{' '.join(_target_names())}"
        COMPREPLY=($(compgen -W "$commands $targets" -- "$cur"))
        return
    fi
    case "${{words[1]}}" in
{cases}
    esac
}}
complete -F _wssh wssh
"""


def _zsh_quote(word: str) -> str:
    escaped = word.replace("'", "'\\''")
    return f"'{escaped}'"


def zsh_completion() -> str:
    tree = command_tree()
    targets_literal = " ".join(_zsh_quote(n) for n in _target_names())
    commands_literal = "\n".join(
        f"        {_zsh_quote(f'{name}:{help_text}')}" for name, (help_text, _) in sorted(tree.items())
    )
    cases = "\n".join(
        f"""                {name})
                    _values '{name} argument' {' '.join(subs)}
                    ;;"""
        for name, (_, subs) in sorted(tree.items())
        if subs
    )
    return f"""#compdef wssh

_wssh() {{
    local -a commands targets
    commands=(
{commands_literal}
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
{cases}
            esac
            ;;
    esac
}}

compdef _wssh wssh
"""
