from wssh.config import WsshConfig
from wssh.server_setup import maybe_offer_setup


def test_maybe_offer_setup_registered_target_offers_retry(monkeypatch) -> None:
    config = WsshConfig(admin_api_token="token")
    monkeypatch.setattr(
        "wssh.server_setup._target_registered_in_warpgate",
        lambda cfg, name: True,
    )
    monkeypatch.setattr(
        "wssh.server_setup.try_fix_target_role_access",
        lambda cfg, name: False,
    )
    asks: list[str] = []
    monkeypatch.setattr(
        "wssh.server_setup.Confirm.ask",
        lambda msg, **k: asks.append(msg) or True,
    )
    setup_called: list[str] = []
    monkeypatch.setattr(
        "wssh.server_setup.setup_server_interactive",
        lambda cfg, name, **k: setup_called.append(name),
    )

    assert maybe_offer_setup(config, "zabbix02", "auth_failure") is True
    assert setup_called == []
    assert any("Retry connection" in q for q in asks)
