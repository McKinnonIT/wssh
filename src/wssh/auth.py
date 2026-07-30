"""Browser SSO and API token management."""

from __future__ import annotations

import webbrowser
from datetime import datetime, timedelta, timezone

from rich.console import Console

from wssh.config import WsshConfig, save_config
from wssh.warpgate import WarpgateApiError, WarpgateClient

console = Console()

API_TOKEN_LABEL = "wssh-cli"


def _try_browser_session_cookie(host: str) -> str | None:
    try:
        import browser_cookie3  # type: ignore[import-untyped]
    except ImportError:
        return None
    for loader in (browser_cookie3.chrome, browser_cookie3.firefox, browser_cookie3.safari):
        try:
            jar = loader(domain_name=host)
        except Exception:
            continue
        for cookie in jar:
            if cookie.name == "warpgate-http-session" and cookie.value:
                return cookie.value
    return None


def create_api_token_with_session(
    config: WsshConfig, session_cookie: str, label: str = API_TOKEN_LABEL
) -> str:
    expiry = (datetime.now(timezone.utc) + timedelta(days=365)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    with WarpgateClient(config, session_cookie=session_cookie) as client:
        result = client.create_api_token(label, expiry)
    return result["secret"]


def login_interactive(
    config: WsshConfig,
    *,
    token: str | None = None,
    use_browser_cookies: bool = True,
) -> str:
    """Return API token (existing, pasted, or newly created)."""

    if token:
        config.api_token = token.strip()
        save_config(config)
        return config.api_token

    existing = config.effective_api_token()
    if existing and WarpgateClient(config).verify_token():
        console.print("[green]Using existing API token[/green]")
        return existing

    console.print("\n[bold]Sign in to Warpgate[/bold]")
    console.print("1. Your browser will open the Warpgate login page")
    console.print("2. Complete sign-in (SSO or local account, per your Warpgate setup)")
    console.print("3. Return here when finished\n")
    console.print(f"If the browser did not open: {config.login_url}\n")
    webbrowser.open(config.login_url)

    try:
        console.input("[bold]Press Enter once sign-in is complete[/bold]: ")
    except KeyboardInterrupt:
        raise SystemExit("Sign-in cancelled") from None

    secret: str | None = None
    if use_browser_cookies:
        session_cookie = _try_browser_session_cookie(config.host)
        if session_cookie:
            try:
                secret = create_api_token_with_session(config, session_cookie)
                console.print("[green]Created API token automatically[/green]")
            except WarpgateApiError as exc:
                console.print(f"[yellow]Could not create token via session: {exc}[/yellow]")
        else:
            console.print(
                "[dim]Tip: pip install 'wssh[cookies]' for automatic token creation "
                "after browser sign-in[/dim]"
            )

    if not secret:
        console.print(
            "\nCreate an API token in Warpgate, then paste it here.\n"
            f"  {config.api_tokens_url}\n"
            "  Profile → API Tokens → Add token (label: wssh-cli)\n"
        )
        pasted = console.input("[bold]API token[/bold]: ").strip()
        if not pasted:
            raise SystemExit("API token is required")
        secret = pasted

    config.api_token = secret
    save_config(config)

    if not WarpgateClient(config).verify_token():
        raise SystemExit("Token verification failed — check the token and try again")

    return secret


def logout(config: WsshConfig) -> None:
    config.api_token = ""
    save_config(config)
    console.print("[green]Removed API token from config[/green]")
