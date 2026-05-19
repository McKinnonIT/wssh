"""Browser SSO and API token management."""

from __future__ import annotations

import socket
import threading
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import quote

from rich.console import Console

from wssh.config import WsshConfig, save_config
from wssh.constants import API_TOKEN_LABEL, API_TOKENS_URL, LOGIN_URL
from wssh.warpgate import WarpgateApiError, WarpgateClient

console = Console()

CALLBACK_TIMEOUT_SECONDS = 300


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _login_page_url(callback_url: str) -> str:
    """Warpgate web UI login — calls startSso in-browser and redirects to Google."""
    return f"{LOGIN_URL}?next={quote(callback_url, safe='')}"


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


def _wait_for_callback(port: int, path: str = "/done") -> bool:
    """Block until the browser hits the local callback URL. Returns False on timeout."""
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path.split("?", 1)[0] == path:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    b"<html><body><h2>Warpgate sign-in complete</h2>"
                    b"<p>You can close this tab and return to the terminal.</p></body></html>"
                )
                done.set()
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = 1
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    timed_out = not done.wait(timeout=CALLBACK_TIMEOUT_SECONDS)
    server.shutdown()
    return not timed_out


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
    provider: str = "google",
    token: str | None = None,
    use_browser_cookies: bool = True,
) -> str:
    """Return API token (existing, pasted, or newly created)."""
    del provider  # SSO provider is chosen on the Warpgate login page

    if token:
        config.api_token = token.strip()
        save_config(config)
        return config.api_token

    existing = config.effective_api_token()
    if existing and WarpgateClient(config).verify_token():
        console.print("[green]Using existing API token[/green]")
        return existing

    host = config.host
    callback_port = _free_port()
    callback_url = f"http://127.0.0.1:{callback_port}/done"
    login_url = _login_page_url(callback_url)

    console.print("\n[bold]Sign in with Google[/bold]")
    console.print("1. Your browser will open the Warpgate login page")
    console.print("2. Click [bold]Sign in with Google[/bold]")
    console.print("3. After Google sign-in you should return here automatically\n")
    console.print(f"If the browser did not open: {login_url}\n")
    webbrowser.open(login_url)

    try:
        if _wait_for_callback(callback_port):
            console.print("[green]Sign-in complete[/green]")
        else:
            console.print(
                "[yellow]Timed out waiting for redirect — if you finished sign-in, "
                "press Enter to continue[/yellow]"
            )
            console.input()
    except KeyboardInterrupt:
        raise SystemExit("Sign-in cancelled") from None

    secret: str | None = None
    if use_browser_cookies:
        session_cookie = _try_browser_session_cookie(host)
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
            f"  {API_TOKENS_URL}\n"
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
