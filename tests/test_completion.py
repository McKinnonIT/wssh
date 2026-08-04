from wssh.completion import bash_completion, command_tree, zsh_completion


def test_zsh_completion_registers_compdef_not_invoke() -> None:
    script = zsh_completion()
    assert "compdef _wssh wssh" in script
    assert '_wssh "$@"' not in script
    assert "#compdef wssh" in script


def test_command_tree_matches_registered_cli_commands() -> None:
    """The tree is derived from Typer, so completion cannot drift from the CLI."""
    tree = command_tree()
    assert set(tree) == {
        "setup",
        "setup-server",
        "auth",
        "targets",
        "credentials",
        "completion",
        "update",
        "version",
        "config-path",
    }
    assert tree["auth"][1] == ["login", "logout"]
    assert tree["targets"][1] == ["list", "refresh"]
    assert tree["credentials"][1] == ["add-key"]
    assert all(help_text for help_text, _ in tree.values()), "every command needs a description"


def test_every_command_appears_in_both_scripts() -> None:
    bash, zsh = bash_completion(), zsh_completion()
    for name in command_tree():
        assert name in bash
        assert f"'{name}:" in zsh
