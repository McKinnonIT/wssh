from wssh.setup_flow import normalize_email

EXAMPLE_DOMAIN = "example.com"


def test_normalize_appends_domain() -> None:
    assert normalize_email("alice", EXAMPLE_DOMAIN) == f"alice@{EXAMPLE_DOMAIN}"


def test_normalize_keeps_full_email() -> None:
    full = f"alice@{EXAMPLE_DOMAIN}"
    assert normalize_email(full, EXAMPLE_DOMAIN) == full


def test_normalize_without_domain() -> None:
    assert normalize_email("alice@corp.test", "") == "alice@corp.test"
    assert normalize_email("alice", "") == "alice"


def test_normalize_empty() -> None:
    assert normalize_email("  ", EXAMPLE_DOMAIN) == ""
