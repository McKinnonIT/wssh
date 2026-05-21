from wssh.config import WsshConfig, apply_env_overrides, default_config_path


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


def test_default_config_path() -> None:
    assert default_config_path().name == "config.yaml"
    assert default_config_path().parent.name == ".wssh"
