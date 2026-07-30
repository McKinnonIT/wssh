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
        """Registered public keys that include full OpenSSH lines when available.

        The user API abbreviates key material, so prefer the admin API when a token
        allows it and fall back to the user's own credentials.
        """
        # Imported here: warpgate_admin imports WarpgateApiError from this module.
        from wssh.warpgate_admin import WarpgateAdminClient

        if self.config.effective_admin_token() and self.config.user.strip():
            with WarpgateAdminClient(self.config) as admin:
                admin_keys = admin.list_user_public_keys(self.config.user.strip())
            if admin_keys is not None:
                return admin_keys
        creds = self.get_credentials()
        return list(creds.get("public_keys") or creds.get("publicKeys") or [])

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
