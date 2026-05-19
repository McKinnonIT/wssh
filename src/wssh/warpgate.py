"""Warpgate user API client."""

from __future__ import annotations

from typing import Any

import httpx

from wssh.config import WsshConfig
from wssh.ssh_key import normalize_openssh_public_key, public_keys_match


class WarpgateApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class WarpgateClient:
    def __init__(
        self,
        config: WsshConfig,
        *,
        token: str | None = None,
        session_cookie: str | None = None,
    ) -> None:
        self.config = config
        self._token = token
        self._session_cookie = session_cookie
        self._client = httpx.Client(
            base_url=config.user_api_base,
            timeout=30.0,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> WarpgateClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _headers(self, *, use_token: bool = True) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if use_token:
            token = self._token or self.config.effective_api_token()
            if token:
                headers["X-Warpgate-Token"] = token
        if self._session_cookie:
            headers["Cookie"] = f"warpgate-http-session={self._session_cookie}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        use_token: bool = True,
        **kwargs: Any,
    ) -> httpx.Response:
        response = self._client.request(
            method,
            path,
            headers=self._headers(use_token=use_token),
            **kwargs,
        )
        if response.status_code >= 400:
            detail = response.text.strip() or response.reason_phrase
            raise WarpgateApiError(
                f"{method} {path} failed ({response.status_code}): {detail}",
                status_code=response.status_code,
            )
        return response

    def get_sso_providers(self) -> list[dict[str, Any]]:
        return self._request("GET", "/sso/providers", use_token=False).json()

    def start_sso(self, provider: str, next_url: str) -> str:
        response = self._request(
            "GET",
            f"/sso/providers/{provider}/start",
            use_token=False,
            params={"next": next_url},
        )
        return response.json()["url"]

    def get_credentials(self) -> dict[str, Any]:
        return self._request("GET", "/profile/credentials").json()

    def add_public_key(self, label: str, openssh_public_key: str) -> dict[str, Any]:
        key = normalize_openssh_public_key(openssh_public_key)
        return self._request(
            "POST",
            "/profile/credentials/public-keys",
            json={"label": label, "openssh_public_key": key},
        ).json()

    def create_api_token(self, label: str, expiry_iso: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/profile/api-tokens",
            use_token=False,
            json={"label": label, "expiry": expiry_iso},
        ).json()

    def get_targets(self, search: str = "") -> list[dict[str, Any]]:
        params = {"search": search} if search else None
        return self._request("GET", "/targets", params=params).json()

    def verify_token(self) -> bool:
        try:
            self.get_targets()
            return True
        except WarpgateApiError:
            return False

    def _list_public_keys_with_material(self) -> list[dict[str, Any]]:
        """Registered public keys that include full OpenSSH lines when available."""
        admin_keys = self._admin_list_public_keys()
        if admin_keys is not None:
            return admin_keys
        creds = self.get_credentials()
        return list(creds.get("public_keys") or creds.get("publicKeys") or [])

    def _admin_list_public_keys(self) -> list[dict[str, Any]] | None:
        """Fetch this user's public keys via admin API (includes full key material)."""
        token = self.config.effective_admin_token()
        username = self.config.user.strip()
        if not token or not username:
            return None
        try:
            with httpx.Client(
                base_url=self.config.admin_api_base,
                timeout=30.0,
                headers={
                    "Accept": "application/json",
                    "X-Warpgate-Token": token,
                },
            ) as admin:
                users_resp = admin.get("/users")
                if users_resp.status_code >= 400:
                    return None
                match = next(
                    (
                        u
                        for u in users_resp.json()
                        if u.get("username") == username
                    ),
                    None,
                )
                if not match:
                    return None
                keys_resp = admin.get(
                    f"/users/{match['id']}/credentials/public-keys"
                )
                if keys_resp.status_code >= 400:
                    return None
                return keys_resp.json()
        except httpx.HTTPError:
            return None

    def find_matching_public_key(self, openssh_line: str) -> dict[str, Any] | None:
        """Return an existing Warpgate key entry with the same key material, if any."""
        normalized = openssh_line.strip()
        for entry in self._list_public_keys_with_material():
            full = entry.get("openssh_public_key") or entry.get("opensshPublicKey")
            if not full:
                continue
            if public_keys_match(normalized, full.strip()):
                return entry
        return None

    def public_key_already_registered(self, openssh_line: str) -> bool:
        return self.find_matching_public_key(openssh_line) is not None
