from wssh.email import normalize_email, short_username

EXAMPLE_DOMAIN = "example.com"


def test_normalize_appends_domain() -> None:
    assert normalize_email("alice", EXAMPLE_DOMAIN) == f"alice@{EXAMPLE_DOMAIN}"


def test_normalize_keeps_full_email() -> None:
    full = f"alice@{EXAMPLE_DOMAIN}"
    assert normalize_email(full, EXAMPLE_DOMAIN) == full


def test_normalize_without_domain() -> None:
    assert normalize_email("alice@corp.test", "") == "alice@corp.test"


def test_short_username() -> None:
    assert short_username(f"alice@{EXAMPLE_DOMAIN}", EXAMPLE_DOMAIN) == "alice"
