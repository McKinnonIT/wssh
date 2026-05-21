import json

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
_LINE_WITH_COMMENT = f"ssh-rsa {_SAMPLE_BLOB} user@workstation.local"
_LINE_WITHOUT_COMMENT = f"ssh-rsa {_SAMPLE_BLOB}"


@pytest.fixture
def config() -> WsshConfig:
    return WsshConfig(
        user="alice@example.com",
        host="bastion.example.com",
        api_token="test-token",
    )


def test_add_public_key_strips_comment(config: WsshConfig, httpx_mock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://bastion.example.com/@warpgate/api/profile/credentials/public-keys",
        json={"id": "key-1", "label": "wssh (test)", "abbreviated": "ssh-rsa AA..."},
    )
    with WarpgateClient(config) as client:
        client.add_public_key("wssh (test)", _LINE_WITH_COMMENT)
    request = httpx_mock.get_requests()[0]
    assert json.loads(request.content) == {
        "label": "wssh (test)",
        "openssh_public_key": _LINE_WITHOUT_COMMENT,
    }
