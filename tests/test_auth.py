from urllib.parse import quote

from wssh.auth import _login_page_url


def test_login_page_url_encodes_callback() -> None:
    callback = "http://127.0.0.1:62157/done"
    url = _login_page_url(callback)
    assert "/@warpgate/#/login?next=" in url
    assert quote(callback, safe="") in url
    assert "/api/sso/" not in url
