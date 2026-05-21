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
            "host": "dns01.internal.example.com",
            "port": 22,
            "username": "deploy",
        },
    }
    assert ssh_target_summary(target) == "deploy@dns01.internal.example.com:22"


def test_ssh_options_api_format() -> None:
    client = WarpgateAdminClient(WsshConfig(host="bastion.example.com"))
    opts = client._ssh_options("dns01.internal.example", 22, "deploy")
    assert opts["kind"] == "Ssh"
    assert opts["auth"] == {"kind": "PublicKey"}
