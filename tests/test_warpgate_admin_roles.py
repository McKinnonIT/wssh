import pytest

from wssh.config import WsshConfig
from wssh.warpgate_admin import WarpgateAdminClient


@pytest.fixture
def config() -> WsshConfig:
    return WsshConfig(host="bastion.example.com", api_token="admin-token")


def test_ensure_target_role_assigns_admin(config: WsshConfig, httpx_mock) -> None:
    httpx_mock.add_response(
        url="https://bastion.example.com/@warpgate/admin/api/roles",
        json=[{"id": "role-admin-uuid", "name": "admin"}],
    )
    httpx_mock.add_response(
        url=(
            "https://bastion.example.com/@warpgate/admin/api/targets/"
            "target-uuid/roles"
        ),
        json=[],
    )
    httpx_mock.add_response(
        method="POST",
        url=(
            "https://bastion.example.com/@warpgate/admin/api/targets/"
            "target-uuid/roles/role-admin-uuid"
        ),
        status_code=201,
    )
    with WarpgateAdminClient(config) as admin:
        assert admin.ensure_target_role("target-uuid", "admin") is True


def test_ensure_target_role_skips_when_present(config: WsshConfig, httpx_mock) -> None:
    httpx_mock.add_response(
        url="https://bastion.example.com/@warpgate/admin/api/roles",
        json=[{"id": "role-admin-uuid", "name": "admin"}],
    )
    httpx_mock.add_response(
        url=(
            "https://bastion.example.com/@warpgate/admin/api/targets/"
            "target-uuid/roles"
        ),
        json=[{"id": "role-admin-uuid", "name": "admin"}],
    )
    with WarpgateAdminClient(config) as admin:
        assert admin.ensure_target_role("target-uuid", "admin") is False
