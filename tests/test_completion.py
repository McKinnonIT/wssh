from wssh.completion import zsh_completion


def test_zsh_completion_registers_compdef_not_invoke() -> None:
    script = zsh_completion()
    assert "compdef _wssh wssh" in script
    assert '_wssh "$@"' not in script
    assert "#compdef wssh" in script
