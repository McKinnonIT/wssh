"""Load and save ~/.config/wssh/config.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from wssh.constants import (
    DEFAULT_TARGETS_CACHE_TTL_HOURS,
    SERVER_DOMAIN,
    WARPGATE_DOMAIN,
    WARPGATE_HOST,
    WARPGATE_PORT,
)


@dataclass
class WsshConfig:
    user: str = ""
    host: str = WARPGATE_HOST
    port: int = WARPGATE_PORT
    domain: str = WARPGATE_DOMAIN
    server_domain: str = SERVER_DOMAIN
    api_token: str = ""
    admin_api_token: str = ""
    warpgate_client_keys: list[str] = field(default_factory=list)
    targets_cache_ttl_hours: int = DEFAULT_TARGETS_CACHE_TTL_HOURS
    default_ssh_user: str = "sysadmin"
    default_ssh_port: int = 22

    @property
    def user_api_base(self) -> str:
        return f"https://{self.host}/@warpgate/api"

    @property
    def admin_api_base(self) -> str:
        return f"https://{self.host}/@warpgate/admin/api"

    def effective_api_token(self) -> str:
        return os.environ.get("WSSH_API_TOKEN", "").strip() or self.api_token.strip()

    def effective_admin_token(self) -> str:
        token = os.environ.get("WSSH_ADMIN_API_TOKEN", "").strip()
        if token:
            return token
        if self.admin_api_token.strip():
            return self.admin_api_token.strip()
        return self.effective_api_token()

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "user": self.user,
            "host": self.host,
            "port": self.port,
            "domain": self.domain,
            "server_domain": self.server_domain,
            "targets_cache_ttl_hours": self.targets_cache_ttl_hours,
            "default_ssh_user": self.default_ssh_user,
            "default_ssh_port": self.default_ssh_port,
        }
        if self.api_token:
            data["api_token"] = self.api_token
        if self.admin_api_token:
            data["admin_api_token"] = self.admin_api_token
        if self.warpgate_client_keys:
            data["warpgate_client_keys"] = self.warpgate_client_keys
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WsshConfig:
        return cls(
            user=str(data.get("user", "")),
            host=str(data.get("host", WARPGATE_HOST)),
            port=int(data.get("port", WARPGATE_PORT)),
            domain=str(data.get("domain", WARPGATE_DOMAIN)),
            server_domain=str(data.get("server_domain", SERVER_DOMAIN)),
            api_token=str(data.get("api_token", "")),
            admin_api_token=str(data.get("admin_api_token", "")),
            warpgate_client_keys=list(data.get("warpgate_client_keys") or []),
            targets_cache_ttl_hours=int(
                data.get("targets_cache_ttl_hours", DEFAULT_TARGETS_CACHE_TTL_HOURS)
            ),
            default_ssh_user=str(data.get("default_ssh_user", "root")),
            default_ssh_port=int(data.get("default_ssh_port", 22)),
        )


def default_config_path() -> Path:
    override = os.environ.get("WSSH_CONFIG")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "wssh" / "config.yaml"


def default_cache_dir() -> Path:
    return Path.home() / ".cache" / "wssh"


def load_config(path: Path | None = None) -> WsshConfig:
    config_path = path or default_config_path()
    if not config_path.is_file():
        return WsshConfig()
    with config_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid config format in {config_path}")
    return WsshConfig.from_dict(data)


def save_config(config: WsshConfig, path: Path | None = None) -> Path:
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(config.to_dict(), fh, default_flow_style=False, sort_keys=False)
    config_path.chmod(0o600)
    return config_path
