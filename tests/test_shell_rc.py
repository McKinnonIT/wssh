from wssh.shell_rc import completion_block


def test_completion_block_guards_when_wssh_missing() -> None:
    zsh = completion_block("zsh")
    assert "if command -v wssh >/dev/null 2>&1; then" in zsh
    assert 'eval "$(wssh completion zsh)"' in zsh
    bash = completion_block("bash")
    assert "if command -v wssh >/dev/null 2>&1; then" in bash
