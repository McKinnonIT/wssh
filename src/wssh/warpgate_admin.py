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
from wssh.constants import DEFAULT_TARGET_ROLE
from wssh.warpgate import WarpgateApiError


def ssh_key_to_openssh(kind: str, public_key_base64: str) -> str:
    """Convert admin API key record to OpenSSH authorized_keys line."""
    kind_map = {
        "ssh-ed25519": "ssh-ed25519",
        "ed25519": "ssh-ed25519",
        "rsa": "ssh-rsa",
        "ssh-rsa": "ssh-rsa",
        "ecdsa": "ecdsa-sha2-nistp256",
    }
    key_type = kind_map.get(kind.lower(), kind)
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


class WarpgateAdminClient:
    def __init__(self, config: WsshConfig, *, token: str | None = None) -> None:
        self.config = config
        self._token = token or config.effective_admin_token()
        self._client = httpx.Client(
            base_url=config.admin_api_base,
            timeout=30.0,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> WarpgateAdminClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        if not self._token:
            raise WarpgateApiError("No API token configured (set api_token or WSSH_API_TOKEN)")
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Warpgate-Token": self._token,
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = self._client.request(method, path, headers=self._headers(), **kwargs)
        if response.status_code == 403:
            raise WarpgateApiError(
                "Admin API access denied — your token may lack admin permissions",
                status_code=403,
            )
        if response.status_code >= 400:
            detail = response.text.strip() or response.reason_phrase
            raise WarpgateApiError(
                f"{method} {path} failed ({response.status_code}): {detail}",
                status_code=response.status_code,
            )
        return response

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

    def target_exists(self, name: str) -> bool:
        return self.find_target_by_name(name) is not None

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
        tid, rid = str(target_id), str(role_id)
        response = self._client.request(
            "POST",
            f"/targets/{tid}/roles/{rid}",
            headers=self._headers(),
        )
        if response.status_code in (201, 409):
            return
        if response.status_code >= 400:
            detail = response.text.strip() or response.reason_phrase
            raise WarpgateApiError(
                f"POST /targets/{tid}/roles/{rid} failed ({response.status_code}): {detail}",
                status_code=response.status_code,
            )

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
        if existing:
            opts = dict(_parse_ssh_options(existing) or existing.get("options") or {})
            if opts.get("kind", "").lower() == "ssh" or opts.get("kind") == "Ssh":
                opts["kind"] = "Ssh"
                opts["host"] = host
                opts["port"] = port
                opts["username"] = username
                if "auth" not in opts or not opts["auth"]:
                    opts["auth"] = {"kind": "PublicKey"}
                return opts
        return {
            "kind": "Ssh",
            "host": host,
            "port": port,
            "username": username,
            "auth": {"kind": "PublicKey"},
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
        desc = description
        if existing and not desc:
            desc = existing.get("description") or ""
        body: dict[str, Any] = {
            "name": name,
            "description": desc,
            "options": self._ssh_options(host, port, username, existing),
        }
        if existing:
            for field in (
                "rate_limit_bytes_per_second",
                "group_id",
                "ticket_max_duration_seconds",
                "ticket_requests_disabled",
                "ticket_require_approval",
                "ticket_max_uses",
            ):
                if field in existing and existing[field] is not None:
                    body[field] = existing[field]
        return body

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
