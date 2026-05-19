import pytest

from wssh.config import WsshConfig
from wssh.warpgate import WarpgateClient

_SAMPLE_BLOB = (
    "AAAAB3NzaC1yc2EAAAADAQABAAABgQDB0Vip9nZtbrP75BDkyedsDoRytfF5UXw4VcSBdfHWOubIc"
    "DPjSsL4ptn78mj/0r1Z+eKubQxbxsGrLYcQrhkcevnrr4V2n45mYUt1ohdF5DpL0Gy1u0CYOHmbw8"
    "nabBHKdavgnlKTww0QYKaI782XSJeBlw3w+OvVyFLr68NjFMlafMEGHkjOTuRbUKmiQ+92Bo2Yl"
    "SICetBVujI4IOC8eqvUAW1qrS6lSkhXZuAxb4Zb06iT8VgaqIACwdMgj43qflNDrhA0FMGGDAGB"
    "+2lttoBhtBgDwkd4m6hpjELZqm83lRB7Myy0PA4XlElTWoIOjHl2ReG7mk63awSYijRTmrCSgAp"
    "aJPQNcrnP1WjQzdYcgJMvSJ1+l9oxSBqwh2oOJ/sj/q3tbSx1iRhTS4IiGWUTD1U1isxyS3su6"
    "bPEzCUmGe2Zc0JO+di/0fAofcxBuU3b/nbMP3Tiez0J3unuNF5fq5cwlDX8Ymwl0YNjjLZ8Thqe0"
    "Af/MURD2LbvemU="
)
_LOCAL_LINE = f"ssh-rsa {_SAMPLE_BLOB} local@host"
_STORED_LINE = f"ssh-rsa {_SAMPLE_BLOB}"


@pytest.fixture
def config() -> WsshConfig:
    return WsshConfig(
        user="sam.neal@mckinnonsc.vic.edu.au",
        api_token="test-token",
    )


def test_find_matching_public_key_via_admin_api(config: WsshConfig, httpx_mock) -> None:
    httpx_mock.add_response(
        url="https://ssh.mckinnon.tech/@warpgate/admin/api/users",
        json=[
            {
                "id": "user-uuid",
                "username": "sam.neal@mckinnonsc.vic.edu.au",
            }
        ],
    )
    httpx_mock.add_response(
        url=(
            "https://ssh.mckinnon.tech/@warpgate/admin/api/users/"
            "user-uuid/credentials/public-keys"
        ),
        json=[
            {
                "id": "key-1",
                "label": "sam@Sams-MacBook-Pro.local",
                "openssh_public_key": _STORED_LINE,
            }
        ],
    )
    with WarpgateClient(config) as client:
        match = client.find_matching_public_key(_LOCAL_LINE)
    assert match is not None
    assert match["label"] == "sam@Sams-MacBook-Pro.local"


def test_find_matching_public_key_returns_none_when_new(config: WsshConfig, httpx_mock) -> None:
    httpx_mock.add_response(
        url="https://ssh.mckinnon.tech/@warpgate/admin/api/users",
        json=[
            {
                "id": "user-uuid",
                "username": "sam.neal@mckinnonsc.vic.edu.au",
            }
        ],
    )
    httpx_mock.add_response(
        url=(
            "https://ssh.mckinnon.tech/@warpgate/admin/api/users/"
            "user-uuid/credentials/public-keys"
        ),
        json=[],
    )
    with WarpgateClient(config) as client:
        match = client.find_matching_public_key(_LOCAL_LINE)
    assert match is None
