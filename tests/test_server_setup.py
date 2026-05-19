from wssh.constants import SERVER_DOMAIN
from wssh.server_setup import (
    _build_authorized_keys_remote_cmd,
    default_server_host,
)


def test_build_authorized_keys_remote_cmd() -> None:
    cmd = _build_authorized_keys_remote_cmd(["ssh-ed25519 AAA test"])
    assert "sudo chown" in cmd
    assert "mkdir -p ~/.ssh" in cmd
    assert "ssh-ed25519 AAA test" in cmd


def test_default_server_host_short_name() -> None:
    assert default_server_host("dns01", SERVER_DOMAIN) == f"dns01.{SERVER_DOMAIN}"


def test_default_server_host_fqdn_unchanged() -> None:
    fqdn = "dns01.example.com"
    assert default_server_host(fqdn, SERVER_DOMAIN) == fqdn
