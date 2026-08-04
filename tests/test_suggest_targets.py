from wssh.targets import suggest_targets

KNOWN = ["dns01", "dns02", "docker02", "docker03", "docker04", "pangolin01", "zabbix02"]


def test_prefix_beats_similarity() -> None:
    """The reported case: a short real prefix must win, difflib scores it too low."""
    assert suggest_targets("pangolin", KNOWN) == ["pangolin01"]


def test_ranks_all_prefix_matches_up_to_limit() -> None:
    assert suggest_targets("docker", KNOWN) == ["docker02", "docker03", "docker04"]
    assert suggest_targets("docker", KNOWN, limit=1) == ["docker02"]


def test_catches_transposition_and_typo() -> None:
    assert suggest_targets("dsn01", KNOWN)[0] == "dns01"
    assert suggest_targets("zabix02", KNOWN)[0] == "zabbix02"


def test_case_insensitive() -> None:
    assert suggest_targets("DNS0", KNOWN) == ["dns01", "dns02"]


def test_no_match_returns_empty() -> None:
    assert suggest_targets("wildlyunrelated", KNOWN) == []
    assert suggest_targets("", KNOWN) == []
    assert suggest_targets("dns01", []) == []
