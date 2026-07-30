"""Load and save ~/.wssh/config.yaml."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

DEFAULT_WARPGATE_PORT = 2222


@dataclass
class WsshConfig:
    user: str = ""
    host: str = ""
    port: int = DEFAULT_WARPGATE_PORT
    domain: str = ""
    server_domain: str = ""
    api_token: str = ""
    admin_api_token: str = ""
    warpgate_client_keys: list[str] = field(default_factory=list)
    default_ssh_user: str = "root"
    default_ssh_port: int = 22

    @property
    def user_api_base(self) -> str:
        return f"https://{self.host}/@warpgate/api"

    @property
    def admin_api_base(self) -> str:
        return f"https://{self.host}/@warpgate/admin/api"

    @property
    def credentials_url(self) -> str:
        return f"https://{self.host}/@warpgate/#/profile/credentials"

    @property
    def api_tokens_url(self) -> str:
        return f"https://{self.host}/@warpgate/#/profile/api-tokens"

    @property
    def login_url(self) -> str:
        return f"https://{self.host}/@warpgate/#/login"

    def effective_api_token(self) -> str:
        return os.environ.get("WSSH_API_TOKEN", "").strip() or self.api_token.strip()

    def effective_admin_token(self) -> str:
        token = os.environ.get("WSSH_ADMIN_API_TOKEN", "").strip()
        if token:
            return token
        if self.admin_api_token.strip():
            return self.admin_api_token.strip()
        return self.effective_api_token()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WsshConfig:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


def apply_env_overrides(config: WsshConfig) -> WsshConfig:
    """Apply WSSH_* environment variables over file-backed settings."""
    if host := os.environ.get("WSSH_HOST", "").strip():
        config.host = host
    if port := os.environ.get("WSSH_PORT", "").strip():
        config.port = int(port)
    if domain := os.environ.get("WSSH_DOMAIN", "").strip():
        config.domain = domain
    if server_domain := os.environ.get("WSSH_SERVER_DOMAIN", "").strip():
        config.server_domain = server_domain
    return config


def default_config_path() -> Path:
    override = os.environ.get("WSSH_CONFIG")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".wssh" / "config.yaml"


def default_cache_dir() -> Path:
    return Path.home() / ".wssh" / "cache"


def load_config(path: Path | None = None) -> WsshConfig:
    config_path = path or default_config_path()
    if not config_path.is_file():
        return apply_env_overrides(WsshConfig())
    with config_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid config format in {config_path}")
    return apply_env_overrides(WsshConfig.from_dict(data))


def save_config(config: WsshConfig, path: Path | None = None) -> Path:
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(asdict(config), fh, default_flow_style=False, sort_keys=False)
    config_path.chmod(0o600)
    return config_path
