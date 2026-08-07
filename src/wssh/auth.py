"""Browser SSO and API token management."""

from __future__ import annotations

import webbrowser

from rich.console import Console

from wssh.config import WsshConfig, save_config
from wssh.warpgate import WarpgateClient

console = Console()

API_TOKEN_LABEL = "wssh-cli"


def login_interactive(config: WsshConfig, *, token: str | None = None) -> str:
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

    console.print("\n[bold]Create an API token in Warpgate[/bold]")
    console.print(
        f"  1. Open [bold]{config.api_tokens_url}[/bold]\n"
        "     [dim]Sign in if prompted — the page stays empty until you do.[/dim]\n"
        "  2. Go to [bold]Profile → API Tokens[/bold] and click [bold]Add token[/bold]\n"
        f"  3. Label: [bold]{API_TOKEN_LABEL}[/bold], then save\n"
        "  4. Copy the token it shows you — it is only displayed once\n"
    )
    webbrowser.open(config.api_tokens_url)
    secret = console.input("[bold]Paste the API token here[/bold]: ").strip()
    if not secret:
        raise SystemExit("API token is required")

    config.api_token = secret
    save_config(config)

    if not WarpgateClient(config).verify_token():
        raise SystemExit("Token verification failed — check the token and try again")

    return secret


def logout(config: WsshConfig) -> None:
    config.api_token = ""
    save_config(config)
    console.print("[green]Removed API token from config[/green]")
