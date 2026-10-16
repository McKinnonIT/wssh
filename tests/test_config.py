import yaml

from wssh.config import WsshConfig, apply_env_overrides, default_config_path, load_config


def test_apply_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("WSSH_HOST", "bastion.example.com")
    monkeypatch.setenv("WSSH_PORT", "2223")
    monkeypatch.setenv("WSSH_DOMAIN", "example.com")
    monkeypatch.setenv("WSSH_SERVER_DOMAIN", "internal.example.com")
    config = apply_env_overrides(WsshConfig())
    assert config.host == "bastion.example.com"
    assert config.port == 2223
    assert config.domain == "example.com"
    assert config.server_domain == "internal.example.com"


def test_config_urls() -> None:
    config = WsshConfig(host="bastion.example.com")
    assert config.login_url == "https://bastion.example.com/@warpgate/#/login"
    assert config.credentials_url.endswith("/profile/credentials")
    assert config.api_tokens_url.endswith("/profile/api-tokens")


def test_bastion_ssh_host_falls_back_to_host() -> None:
    assert WsshConfig(host="web.example.com").bastion_ssh_host == "web.example.com"
    config = WsshConfig(host="web.example.com", ssh_host="ssh.example.com")
    assert config.bastion_ssh_host == "ssh.example.com"
    assert config.login_url.startswith("https://web.example.com/")


def test_default_config_path() -> None:
    assert default_config_path().name == "config.yaml"
    assert default_config_path().parent.name == ".wssh"


def test_load_config_migrates_ssh_host(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("WSSH_SSH_HOST", raising=False)
    path = tmp_path / "config.yaml"
    path.write_text("user: a@b.c\nhost: ssh.mckinnon.tech\n")
    assert load_config(path).bastion_ssh_host == "wssh.mckinnon.tech"
    assert yaml.safe_load(path.read_text())["ssh_host"] == "wssh.mckinnon.tech"
    # Other hosts, and an explicit ssh_host, are left alone.
    path.write_text("host: ssh.mckinnon.tech\nssh_host: custom.example.com\n")
    assert load_config(path).ssh_host == "custom.example.com"
    path.write_text("host: bastion.example.com\n")
    assert load_config(path).ssh_host == ""
