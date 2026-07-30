"""Warpgate admin API client.

Admin base: https://{host}/@warpgate/admin/api

Endpoints (from warp-tech/warpgate warpgate-admin):
  GET  /ssh/own-keys          — Warpgate client public keys for authorized_keys
  GET  /targets               — list all targets (admin)
  POST /targets               — create target (requires targets_create permission)
  PUT  /targets/:id           — update target (requires targets_edit permission)
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx

from wssh.config import WsshConfig
from wssh.warpgate import ApiClient, WarpgateApiError

# Role granted on targets created/updated by wssh setup-server
# (Warpgate "Allow access for roles")
DEFAULT_TARGET_ROLE = "admin"


def ssh_key_to_openssh(kind: str, public_key_base64: str) -> str:
    """Convert admin API key record to OpenSSH authorized_keys line."""
    # Self-mapping entries dropped — anything already in OpenSSH form passes through.
    key_type = {
        "ed25519": "ssh-ed25519",
        "rsa": "ssh-rsa",
        "ecdsa": "ecdsa-sha2-nistp256",
    }.get(kind.lower(), kind)
    return f"{key_type} {public_key_base64} warpgate"


def _parse_ssh_options(target: dict[str, Any]) -> dict[str, Any]:
    opts = target.get("options") or {}
    kind = str(opts.get("kind", "")).lower()
    if kind == "ssh" and "host" in opts:
        return opts
    return {}


def ssh_target_summary(target: dict[str, Any]) -> str:
    opts = _parse_ssh_options(target)
    host = opts.get("host", "?")
    port = opts.get("port", 22)
    user = opts.get("username", "?")
    return f"{user}@{host}:{port}"


class WarpgateAdminClient(ApiClient):
    forbidden_message = "Admin API access denied — your token may lack admin permissions"

    def __init__(self, config: WsshConfig, *, token: str | None = None) -> None:
        super().__init__(config.admin_api_base)
        self.config = config
        self._token = token or config.effective_admin_token()

    def _headers(self) -> dict[str, str]:
        if not self._token:
            raise WarpgateApiError("No API token configured (set api_token or WSSH_API_TOKEN)")
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Warpgate-Token": self._token,
        }

    def get_ssh_client_keys(self) -> list[str]:
        data = self._request("GET", "/ssh/own-keys").json()
        lines: list[str] = []
        for item in data:
            lines.append(
                ssh_key_to_openssh(item["kind"], item["public_key_base64"])
            )
        return lines

    def list_targets(self) -> list[dict[str, Any]]:
        return self._request("GET", "/targets").json()

    def find_target_by_name(self, name: str) -> dict[str, Any] | None:
        for target in self.list_targets():
            if target.get("name") == name:
                return target
        return None

    def list_user_public_keys(self, username: str) -> list[dict[str, Any]] | None:
        """A user's public keys with full key material. None when unavailable."""
        try:
            users = self._request("GET", "/users").json()
            match = next((u for u in users if u.get("username") == username), None)
            if not match:
                return None
            return self._request(
                "GET", f"/users/{match['id']}/credentials/public-keys"
            ).json()
        except (WarpgateApiError, httpx.HTTPError):
            return None

    def list_roles(self) -> list[dict[str, Any]]:
        return self._request("GET", "/roles").json()

    def find_role_by_name(self, name: str) -> dict[str, Any] | None:
        for role in self.list_roles():
            if role.get("name") == name:
                return role
        return None

    def list_target_roles(self, target_id: str | UUID) -> list[dict[str, Any]]:
        tid = str(target_id)
        return self._request("GET", f"/targets/{tid}/roles").json()

    def target_has_role(self, target_id: str | UUID, role_id: str | UUID) -> bool:
        rid = str(role_id).lower()
        return any(str(r.get("id", "")).lower() == rid for r in self.list_target_roles(target_id))

    def assign_target_role(self, target_id: str | UUID, role_id: str | UUID) -> None:
        try:
            self._request("POST", f"/targets/{target_id}/roles/{role_id}")
        except WarpgateApiError as exc:
            if exc.status_code != 409:  # 409 = already assigned
                raise

    def ensure_target_role(
        self,
        target_id: str | UUID,
        role_name: str = DEFAULT_TARGET_ROLE,
    ) -> bool:
        """Grant role access on a target. Returns True if the role was newly assigned."""
        role = self.find_role_by_name(role_name)
        if not role or not role.get("id"):
            raise WarpgateApiError(f"Warpgate role '{role_name}' not found")
        if self.target_has_role(target_id, role["id"]):
            return False
        self.assign_target_role(target_id, role["id"])
        return True

    def _ssh_options(
        self,
        host: str,
        port: int,
        username: str,
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build TargetOptions for SSH (admin API uses kind Ssh / PublicKey)."""
        opts = dict(_parse_ssh_options(existing or {}))
        return {
            **opts,
            "kind": "Ssh",
            "host": host,
            "port": port,
            "username": username,
            "auth": opts.get("auth") or {"kind": "PublicKey"},
        }

    def _target_body(
        self,
        name: str,
        host: str,
        port: int,
        username: str,
        description: str = "",
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "name": name,
            "description": description or (existing or {}).get("description") or "",
            "options": self._ssh_options(host, port, username, existing),
        }

    def create_ssh_target(
        self,
        name: str,
        host: str,
        port: int,
        username: str,
        description: str = "",
    ) -> dict[str, Any]:
        body = self._target_body(name, host, port, username, description)
        return self._request("POST", "/targets", json=body).json()

    def update_ssh_target(
        self,
        target_id: str | UUID,
        name: str,
        host: str,
        port: int,
        username: str,
        *,
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = self._target_body(name, host, port, username, existing=existing)
        tid = str(target_id)
        return self._request("PUT", f"/targets/{tid}", json=body).json()

    def ensure_target_access(self, name: str, role_name: str = DEFAULT_TARGET_ROLE) -> bool:
        """Ensure an existing target grants ``role_name``. Returns True if newly assigned."""
        target = self.find_target_by_name(name)
        if not target or not target.get("id"):
            return False
        return self.ensure_target_role(target["id"], role_name)
