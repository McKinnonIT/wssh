from urllib.parse import quote

from wssh.auth import _login_page_url
from wssh.config import WsshConfig


def test_login_page_url_encodes_callback() -> None:
    config = WsshConfig(host="bastion.example.com")
    callback = "http://127.0.0.1:62157/done"
    url = _login_page_url(config, callback)
    assert "https://bastion.example.com/@warpgate/#/login?next=" in url
    assert quote(callback, safe="") in url
    assert "/api/sso/" not in url
