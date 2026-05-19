from wssh.ssh_key import (
    normalize_openssh_public_key,
    public_key_blob,
    public_key_fingerprint,
    public_key_stored_correctly,
    public_keys_match,
)

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
_LINE_WITH_COMMENT = f"ssh-rsa {_SAMPLE_BLOB} sam@Sams-MacBook-Pro.local"
_LINE_WITHOUT_COMMENT = f"ssh-rsa {_SAMPLE_BLOB}"


def test_public_key_blob_ignores_comment() -> None:
    assert public_key_blob(_LINE_WITH_COMMENT) == _SAMPLE_BLOB
    assert public_key_blob(_LINE_WITHOUT_COMMENT) == _SAMPLE_BLOB


def test_public_keys_match_ignores_comment() -> None:
    assert public_keys_match(_LINE_WITH_COMMENT, _LINE_WITHOUT_COMMENT)


def test_public_key_fingerprint_same_for_comment_variants() -> None:
    assert public_key_fingerprint(_LINE_WITH_COMMENT) == public_key_fingerprint(
        _LINE_WITHOUT_COMMENT
    )


def test_normalize_openssh_public_key_strips_comment() -> None:
    assert normalize_openssh_public_key(_LINE_WITH_COMMENT) == _LINE_WITHOUT_COMMENT


def test_public_key_stored_correctly() -> None:
    assert public_key_stored_correctly(_LINE_WITHOUT_COMMENT)
    assert not public_key_stored_correctly(_LINE_WITH_COMMENT)
