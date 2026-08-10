from wssh.targets import suggest_targets

KNOWN = ["dns01", "dns02", "docker02", "docker03", "docker04", "pangolin01", "zabbix02"]

# The fleet shapes that made the old matcher too eager: a shared word across a
# family of hosts, a longer sibling, and targets registered by address.
FAMILY = [
    "zabbix02",
    "zabbix-east-nixos",
    "zabbix-mckrd-nixos",
    "zabbix-merc-nixos",
    "dockermgmt01",
    "docker03",
    "docker04",
    "stt-server",
    "10.128.16.12",
    "10.128.16.13",
]


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


def test_a_shared_word_does_not_drag_in_the_whole_family() -> None:
    """'zabbix' means zabbix02, not every zabbix-*-nixos box that shares the word."""
    assert suggest_targets("zabbix", FAMILY) == ["zabbix02"]
    assert suggest_targets("docker", FAMILY) == ["docker03", "docker04"]


def test_an_unambiguous_prefix_still_suggests_however_short() -> None:
    """Only one target can start with 'stt' — there is nothing to be wrong about."""
    assert suggest_targets("stt", FAMILY) == ["stt-server"]


def test_addresses_never_match() -> None:
    """One digit apart is a different machine, not a typo."""
    assert suggest_targets("10.128.16.14", FAMILY) == []
    assert suggest_targets("10.128.16.12", FAMILY) == [], "not even an exact address"
    assert suggest_targets("2001:db8::1", FAMILY) == []
    # An address in the fleet is never offered as the answer to a hostname either.
    assert suggest_targets("10.128.16.1x", FAMILY) == []


def test_too_short_to_be_a_typo() -> None:
    assert suggest_targets("do", FAMILY) == []


def test_a_near_miss_beats_the_noise_it_used_to_bring() -> None:
    """'dsn01' is one transposition from dns01; ssh01 and pbs01 are not typos of it."""
    assert suggest_targets("dsn01", [*KNOWN, "ssh01", "pbs01"]) == ["dns01"]
