from wssh.email import normalize_email, short_username
from wssh.constants import WARPGATE_DOMAIN


def test_normalize_appends_domain() -> None:
    assert normalize_email("sam.neal") == f"sam.neal@{WARPGATE_DOMAIN}"


def test_normalize_keeps_full_email() -> None:
    full = f"sam.neal@{WARPGATE_DOMAIN}"
    assert normalize_email(full) == full


def test_short_username() -> None:
    assert short_username(f"sam.neal@{WARPGATE_DOMAIN}") == "sam.neal"
