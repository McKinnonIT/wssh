from wssh.warpgate_admin import WarpgateAdminClient, ssh_key_to_openssh, ssh_target_summary
from wssh.config import WsshConfig


def test_ssh_key_to_openssh() -> None:
    line = ssh_key_to_openssh("ssh-ed25519", "AAAAC3NzaC1lZDI1NTE5AAAAI")
    assert line.startswith("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI")
    assert line.endswith(" warpgate")


def test_ssh_target_summary() -> None:
    target = {
        "name": "dns01",
        "options": {
            "kind": "Ssh",
            "host": "dns01.noddy.mckinnonsc.vic.edu.au",
            "port": 22,
            "username": "sysadmin",
        },
    }
    assert ssh_target_summary(target) == "sysadmin@dns01.noddy.mckinnonsc.vic.edu.au:22"


def test_ssh_options_api_format() -> None:
    client = WarpgateAdminClient(WsshConfig())
    opts = client._ssh_options("dns01.noddy.example", 22, "sysadmin")
    assert opts["kind"] == "Ssh"
    assert opts["auth"] == {"kind": "PublicKey"}
