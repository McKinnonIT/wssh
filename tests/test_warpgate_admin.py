from wssh.config import WsshConfig
from wssh.warpgate_admin import WarpgateAdminClient, ssh_key_to_openssh, ssh_target_summary


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
    assert opts["allow_insecure_algos"] is False


def test_target_body_sends_every_required_boolean() -> None:
    """Warpgate 400s on a null boolean, so each one must be present on every write."""
    client = WarpgateAdminClient(WsshConfig(host="bastion.example.com"))

    body = client._target_body("dns01", "dns01.internal.example", 22, "deploy")
    for field in ("ticket_requests_disabled", "ticket_require_approval", "require_approval"):
        assert body[field] is False, field
    assert body["options"]["allow_insecure_algos"] is False

    existing = {
        "description": "kept",
        "require_approval": True,
        "options": {"kind": "Ssh", "host": "old", "allow_insecure_algos": True},
    }
    kept = client._target_body("dns01", "dns01.internal.example", 22, "deploy", existing=existing)
    assert kept["require_approval"] is True
    assert kept["options"]["allow_insecure_algos"] is True
    assert kept["description"] == "kept"
