from wssh.connect import classify_ssh_failure


def test_unknown_target() -> None:
    assert classify_ssh_failure("Warpgate: unknown target dns01") == "unknown_target"


def test_auth_failure() -> None:
    assert classify_ssh_failure("Permission denied (publickey)") == "auth_failure"
