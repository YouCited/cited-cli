from __future__ import annotations

import html
import socket
import threading
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

_SUCCESS_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Cited CLI</title>
<style>body{{font-family:system-ui,sans-serif;display:flex;justify-content:center;
align-items:center;height:100vh;margin:0;background:#f8f9fa;}}
.card{{text-align:center;padding:2rem;max-width:600px;}}
.token-section{{margin-top:1.5rem;text-align:left;}}
.token-box{{background:#f1f5f9;border:1px solid #cbd5e1;border-radius:6px;
padding:0.75rem;font-family:monospace;font-size:0.8rem;word-break:break-all;
max-height:4rem;overflow-y:auto;}}
.copy-btn{{margin-top:0.5rem;padding:0.4rem 1rem;background:#3b82f6;color:#fff;
border:none;border-radius:4px;cursor:pointer;font-size:0.85rem;}}
.copy-btn:hover{{background:#2563eb;}}
summary{{cursor:pointer;color:#64748b;font-size:0.9rem;}}</style></head>
<body><div class="card">
<h1 style="color:#22c55e;">&#10003; Authentication successful</h1>
<p>You can close this tab and return to your terminal.</p>
<details class="token-section">
<summary>Terminal not responding? Copy your token manually</summary>
<p style="font-size:0.85rem;color:#475569;">
If the CLI didn't detect the login, copy this token and paste it in your terminal.</p>
<div class="token-box" id="token-text">{token}</div>
<button class="copy-btn" onclick="
var t=document.getElementById('token-text').textContent;
navigator.clipboard.writeText(t).then(function(){{this.textContent='Copied!'}}.bind(this))
">Copy token</button>
</details>
</div></body></html>
"""

_ERROR_HTML = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Cited CLI</title>
<style>body{font-family:system-ui,sans-serif;display:flex;justify-content:center;
align-items:center;height:100vh;margin:0;background:#f8f9fa;}
.card{text-align:center;padding:2rem;}</style></head>
<body><div class="card">
<h1 style="color:#ef4444;">Authentication failed</h1>
<p>No token was received. Please try again.</p>
</div></body></html>
"""


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _CallbackHandler(BaseHTTPRequestHandler):
    def __init__(
        self, token_event: threading.Event, server_ref: OAuthCallbackServer, *args, **kwargs,
    ):
        self._token_event = token_event
        self._server_ref = server_ref
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self.send_error(404)
            return

        params = parse_qs(parsed.query)
        token = params.get("token", [None])[0]

        if token:
            self._server_ref.token = token
            success_html = _SUCCESS_HTML_TEMPLATE.format(token=html.escape(token))
            self._send_html(200, success_html)
            self._token_event.set()
        else:
            self._send_html(400, _ERROR_HTML)

    def _send_html(self, code: int, html: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # Suppress request logging


class OAuthCallbackServer:
    """Temporary localhost server to receive OAuth callback with token."""

    def __init__(self, timeout: float = 120.0) -> None:
        self.token: str | None = None
        self.port: int = _find_free_port()
        self.redirect_uri = f"http://localhost:{self.port}/callback"
        self._timeout = timeout
        self._token_event = threading.Event()
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        handler = partial(_CallbackHandler, self._token_event, self)
        self._server = HTTPServer(("127.0.0.1", self.port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def wait_for_token(self) -> str | None:
        self._token_event.wait(timeout=self._timeout)
        return self.token

    def shutdown(self) -> None:
        if self._server:
            self._server.shutdown()
        if self._thread:
            self._thread.join(timeout=5)
