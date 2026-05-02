#!/usr/bin/env python3
"""End-to-end MCP test harness — exercises the deployed Cited MCP server.

Usage:
    ./scripts/mcp_test_harness.py --env dev
    ./scripts/mcp_test_harness.py --env prod

On first run per env, runs a full OAuth flow (DCR + PKCE + browser callback).
Tokens are cached in the OS keychain (service "cited-mcp-test-harness",
account = env name) so subsequent runs skip the browser click as long as
the JWT exp claim is still valid (7-day TTL by default). If keyring isn't
available (headless Linux without DBus, etc.), the harness falls back to
prompting OAuth on every run rather than writing the token to disk in
clear text.

Test categories (counted independently in the summary):

  [PR1] tools_fingerprint on `ping` (PR #4 / db91191)
  [PR2] whats_new + tool_changelog.yaml convention (PR #7 / 766af8f)
  [PR3] upgrade_plan response wrap (PR #8 / 1bc2305)
  [PR4] structured tool_unavailable on unknown tool calls (PR #10 / 5c3b257)
  [+]   additions beyond the original PR test plans

Additions ([+] tag):
  * /health 200
  * OAuth metadata advertises expected endpoints
  * tools/list contains canonical tool names
  * deployed fingerprint matches the local checked-in changelog
    (catches deploy/source drift in either direction)
  * Bearer invalid token → 401 invalid_token + non-empty error_description
    (auth provider regression detector)
  * POST with bogus Host header → rejected (non-2xx)
    (catches DNS-rebound / host-header-injection misconfig)
  * Rate limiter triggers within 70 sequential check_auth_status calls
    (catches "rate limiter accidentally disabled")
  * Cross-env token rejection — the OTHER env's token presented to THIS env
    returns 401 (catches OAuth issuer-confusion regressions). Skipped if
    the other env hasn't been authenticated yet (run --env <other> first).
  * /robots.txt returns the expected disallow rules
    (catches accidentally-public OAuth paths)

Side effects:
  * Each run creates one OAuth client registration (DCR) — these are stored
    in-memory on the server and expire when the Fargate task restarts.
  * The rate-limiter test fills the user's per-token request window for ~1
    minute, so any other tooling targeting the same env from the same user
    might see rate-limited responses for a minute after.
  * The upgrade_plan test calls upgrade_plan with the user's CURRENT tier,
    which is a no-op (already_on_plan branch) — no Stripe state change.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import http.server
import json
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any

import httpx
import jwt
import yaml

try:
    import keyring  # OS keychain (Keychain on macOS, Secret Service on Linux)
except ImportError:  # pragma: no cover
    keyring = None  # type: ignore[assignment]

KEYRING_SERVICE = "cited-mcp-test-harness"

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG_PATH = (
    REPO_ROOT / "packages" / "mcp" / "src" / "cited_mcp" / "tool_changelog.yaml"
)

ENVS = {
    "dev":  {"base": "https://mcpdev.youcited.com", "label": "dev"},
    "prod": {"base": "https://mcp.youcited.com",    "label": "prod"},
}

CALLBACK_PORT = 31415
CALLBACK_URI = f"http://localhost:{CALLBACK_PORT}/callback"

# Bogus business_id for the resource-not-found regression case.
BOGUS_BUSINESS_ID = "00000000-0000-0000-0000-000000000000"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"


# ---------------------------------------------------------------------------
# OAuth (cached per-env)
# ---------------------------------------------------------------------------

def _load_cached_token(env: str) -> str | None:
    """Load the cached MCP access token for *env* from the OS keychain.

    Returns None if keyring is unavailable, the token isn't stored, or it has
    expired (per its embedded JWT exp claim — signature is not verified
    locally since we don't have the JWT_SECRET).
    """
    if keyring is None:
        return None
    try:
        tok = keyring.get_password(KEYRING_SERVICE, env)
        if not tok:
            return None
        claims = jwt.decode(tok, options={"verify_signature": False})
        if claims.get("exp", 0) < time.time() + 60:
            return None
        return str(tok)
    except Exception:
        return None


def _save_cached_token(env: str, access_token: str) -> None:
    """Cache the MCP access token in the OS keychain (silent no-op if absent)."""
    if keyring is None:
        return
    with contextlib.suppress(Exception):
        keyring.set_password(KEYRING_SERVICE, env, access_token)


def oauth_flow(mcp_base: str) -> str:
    """Run DCR + PKCE + browser callback. Returns access token."""
    reg_resp = httpx.post(
        f"{mcp_base}/register",
        json={
            "client_name": "Cited MCP test harness",
            "redirect_uris": [CALLBACK_URI],
            "grant_types": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_method": "client_secret_post",
        },
        timeout=30,
    )
    reg_resp.raise_for_status()
    reg = reg_resp.json()
    client_id = reg["client_id"]
    client_secret = reg.get("client_secret", "")

    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    state = secrets.token_urlsafe(16)

    authz_url = f"{mcp_base}/authorize?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": CALLBACK_URI,
        "scope": "cited",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })

    captured: dict[str, str] = {}

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            url = urllib.parse.urlparse(self.path)
            captured.update(dict(urllib.parse.parse_qsl(url.query)))
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Authorized</h1><p>Return to terminal.</p>")

        def log_message(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
            pass

    srv = http.server.HTTPServer(("127.0.0.1", CALLBACK_PORT), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    print(f"\n  Open this URL in your browser to authenticate:\n\n    {authz_url}\n")
    with contextlib.suppress(Exception):
        webbrowser.open(authz_url)
    print("  Waiting up to 5 minutes for callback...")

    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        if "code" in captured:
            break
        time.sleep(0.5)
    else:
        srv.shutdown()
        raise SystemExit("Timed out waiting for OAuth callback.")
    srv.shutdown()

    if captured.get("state") != state:
        raise SystemExit("State mismatch — possible CSRF.")

    tok_resp = httpx.post(
        f"{mcp_base}/token",
        data={
            "grant_type": "authorization_code",
            "code": captured["code"],
            "redirect_uri": CALLBACK_URI,
            "client_id": client_id,
            "client_secret": client_secret,
            "code_verifier": verifier,
        },
        timeout=30,
    )
    tok_resp.raise_for_status()
    return str(tok_resp.json()["access_token"])


# ---------------------------------------------------------------------------
# MCP request helper (streamable HTTP, stateless)
# ---------------------------------------------------------------------------

class MCP:
    def __init__(self, base: str, token: str) -> None:
        self.base = base
        self.token = token
        self._id = 0

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        body = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": self._next_id(),
        }
        r = httpx.post(
            f"{self.base}/mcp",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            json=body,
            timeout=120,
        )
        r.raise_for_status()
        last: Any = None
        for line in r.text.splitlines():
            if line.startswith("data: "):
                with contextlib.suppress(json.JSONDecodeError):
                    last = json.loads(line[6:])
        return last if last is not None else r.text

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        return self.call("tools/call", {"name": name, "arguments": arguments or {}})

    @staticmethod
    def structured(envelope: Any) -> Any:
        if not isinstance(envelope, dict):
            return None
        result = envelope.get("result", {})
        sc = result.get("structuredContent")
        if sc is not None:
            return sc
        for block in result.get("content", []):
            if block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except (KeyError, json.JSONDecodeError):
                    pass
        return None


# ---------------------------------------------------------------------------
# Test results
# ---------------------------------------------------------------------------

class Results:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str, str]] = []

    def record(self, tag: str, name: str, ok: bool, msg: str = "") -> None:
        status = PASS if ok else FAIL
        self.rows.append((tag, name, status, msg))
        print(f"  {tag:6s} {status} {name}  {msg}".rstrip())

    def skip(self, tag: str, name: str, msg: str) -> None:
        self.rows.append((tag, name, SKIP, msg))
        print(f"  {tag:6s} {SKIP} {name}  {msg}")

    def summary(self) -> int:
        passed = sum(1 for r in self.rows if r[2] == PASS)
        failed = sum(1 for r in self.rows if r[2] == FAIL)
        skipped = sum(1 for r in self.rows if r[2] == SKIP)
        print(f"\nTotal: {passed} pass / {failed} fail / {skipped} skip")
        return 0 if failed == 0 else 1


def load_local_changelog_fingerprint() -> str:
    with CHANGELOG_PATH.open() as f:
        data = yaml.safe_load(f)
    return str(data["versions"][0]["fingerprint"])


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def run_tests(env: str) -> int:
    cfg = ENVS[env]
    base = cfg["base"]
    print(f"=== Testing {cfg['label']} ({base}) ===\n")
    results = Results()

    # ------------------------------------------------------------- [+] /health
    try:
        r = httpx.get(f"{base}/health", timeout=10)
        results.record("[+]", "/health returns 200", r.status_code == 200,
                       f"got {r.status_code}")
    except Exception as e:
        results.record("[+]", "/health returns 200", False, str(e))

    # ------------------------------------------------------------- [+] OAuth metadata
    try:
        r = httpx.get(f"{base}/.well-known/oauth-authorization-server", timeout=10)
        meta = r.json()
        ok = (
            meta.get("issuer", "").startswith(base)
            and meta.get("authorization_endpoint", "").endswith("/authorize")
            and meta.get("token_endpoint", "").endswith("/token")
            and "S256" in meta.get("code_challenge_methods_supported", [])
        )
        results.record("[+]", "OAuth metadata advertises expected endpoints", ok)
    except Exception as e:
        results.record("[+]", "OAuth metadata advertises expected endpoints", False, str(e))

    # ------------------------------------------------------------- [+] /robots.txt
    try:
        r = httpx.get(f"{base}/robots.txt", timeout=10)
        expected = (
            "User-agent: *\n"
            "Disallow: /oauth/\n"
            "Allow: /health\n"
            "Allow: /robots.txt\n"
        )
        results.record(
            "[+]",
            "/robots.txt returns expected disallow rules",
            r.status_code == 200 and r.text == expected,
            f"status={r.status_code}, content match={r.text == expected}",
        )
    except Exception as e:
        results.record("[+]", "/robots.txt returns expected disallow rules", False, str(e))

    # ------------------------------------------------------------- [+] Bearer invalid token → 401
    try:
        r = httpx.post(
            f"{base}/mcp",
            headers={
                "Authorization": "Bearer this.is.not.a.real.token",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json={"jsonrpc": "2.0", "method": "tools/list", "id": 999},
            timeout=15,
        )
        body = r.json() if "json" in r.headers.get("content-type", "") else {}
        ok = (
            r.status_code == 401
            and body.get("error") == "invalid_token"
            and bool(body.get("error_description"))
        )
        results.record(
            "[+]",
            "Bearer invalid token -> 401 invalid_token + non-empty error_description",
            ok,
            f"status={r.status_code}, error={body.get('error')!r}, "
            f"desc={(body.get('error_description') or '')[:60]!r}",
        )
    except Exception as e:
        results.record(
            "[+]",
            "Bearer invalid token -> 401 invalid_token + non-empty error_description",
            False, str(e),
        )

    # ------------------------------------------------------------- [+] Bogus Host header → rejected
    try:
        r = httpx.post(
            f"{base}/mcp",
            headers={
                "Host": "evil.example.com",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json={"jsonrpc": "2.0", "method": "tools/list", "id": 998},
            timeout=15,
        )
        rejected = not (200 <= r.status_code < 300)
        results.record(
            "[+]",
            "POST with bogus Host header -> rejected (non-2xx)",
            rejected,
            f"status={r.status_code}",
        )
    except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError) as e:
        # Connection-level rejection (Cloudflare TLS error / disconnect) is also a pass.
        results.record(
            "[+]",
            "POST with bogus Host header -> rejected (non-2xx)",
            True,
            f"connection-level rejection (acceptable): {type(e).__name__}",
        )
    except Exception as e:
        results.record(
            "[+]",
            "POST with bogus Host header -> rejected (non-2xx)",
            False, str(e),
        )

    # ------------------------------------------------------------- OAuth (cached)
    token = _load_cached_token(env)
    if not token:
        print("\n  No cached token; running OAuth flow...")
        token = oauth_flow(base)
        _save_cached_token(env, token)
    else:
        print("\n  Using cached OAuth token (still valid).")

    mcp = MCP(base, token)

    # ------------------------------------------------------------- [+] tools/list sanity
    try:
        envelope = mcp.call("tools/list")
        tool_names = {t["name"] for t in envelope["result"]["tools"]}
        canonical = {
            "ping", "whats_new", "upgrade_plan", "check_auth_status",
            "list_businesses", "start_audit",
        }
        missing = canonical - tool_names
        results.record(
            "[+]",
            "tools/list contains canonical tool names",
            not missing,
            f"missing: {missing}" if missing else f"({len(tool_names)} tools)",
        )
    except Exception as e:
        results.record("[+]", "tools/list contains canonical tool names", False, str(e))
        return results.summary()

    # ------------------------------------------------------------- [PR1] ping
    ping1 = MCP.structured(mcp.call_tool("ping"))
    ping2 = MCP.structured(mcp.call_tool("ping"))
    fp1 = (ping1 or {}).get("tools_fingerprint")
    results.record(
        "[PR1]",
        "ping has server_version, tools_fingerprint (12-hex), tools_count",
        bool(
            isinstance(ping1, dict)
            and ping1.get("server_version")
            and isinstance(fp1, str)
            and len(fp1) == 12
            and all(c in "0123456789abcdef" for c in fp1)
            and isinstance(ping1.get("tools_count"), int)
        ),
        f"version={ping1.get('server_version')!r}, fp={fp1!r}, "
        f"count={ping1.get('tools_count')!r}",
    )
    results.record(
        "[PR1]",
        "tools_fingerprint deterministic across two consecutive calls",
        fp1 == (ping2 or {}).get("tools_fingerprint"),
    )
    results.record(
        "[PR1]",
        "tools_count > 0",
        isinstance((ping1 or {}).get("tools_count"), int) and ping1["tools_count"] > 0,
    )

    # ----------------------------------------------------- [+] deploy-vs-source fingerprint match
    try:
        local_fp = load_local_changelog_fingerprint()
        results.record(
            "[+]",
            "deployed fingerprint matches local checked-in changelog",
            local_fp == fp1,
            f"local={local_fp!r}, deployed={fp1!r}",
        )
    except Exception as e:
        results.record(
            "[+]", "deployed fingerprint matches local checked-in changelog", False, str(e),
        )

    # ------------------------------------------------------------- [PR2] whats_new
    wn_none = MCP.structured(mcp.call_tool("whats_new"))
    results.record(
        "[PR2]",
        "whats_new no-args returns most recent changelog entry",
        bool(
            isinstance(wn_none, dict)
            and "current_version" in wn_none
            and "current_fingerprint" in wn_none
            and not wn_none.get("no_changes")
            and "_note" not in wn_none
        ),
        f"current_version={wn_none.get('current_version')!r}",
    )

    wn_current = MCP.structured(mcp.call_tool("whats_new", {"since_fingerprint": fp1}))
    results.record(
        "[PR2]",
        "whats_new with current fingerprint returns no_changes: true",
        bool(isinstance(wn_current, dict) and wn_current.get("no_changes") is True),
    )

    wn_bogus = MCP.structured(
        mcp.call_tool("whats_new", {"since_fingerprint": "000000000000"})
    )
    results.record(
        "[PR2]",
        "whats_new with bogus fingerprint returns full history with _note",
        bool(isinstance(wn_bogus, dict) and wn_bogus.get("_note")),
        f"_note: {((wn_bogus or {}).get('_note') or '')[:60]!r}",
    )

    # --------------------------------------------- [PR3] upgrade_plan (no-op safe path only)
    auth = MCP.structured(mcp.call_tool("check_auth_status"))
    current_tier = (auth or {}).get("subscription_tier")
    if not current_tier:
        results.skip(
            "[PR3]",
            "upgrade_plan with current tier -> already_on_plan",
            "could not read current tier from check_auth_status",
        )
    else:
        upgrade = MCP.structured(
            mcp.call_tool("upgrade_plan", {"target_tier": current_tier})
        )
        results.record(
            "[PR3]",
            f"upgrade_plan(target_tier={current_tier!r}) -> already_on_plan, "
            "tools_unlocked=[], pending_action=null",
            bool(
                isinstance(upgrade, dict)
                and upgrade.get("action") == "already_on_plan"
                and upgrade.get("tools_unlocked") == []
                and upgrade.get("pending_action") is None
            ),
            f"action={upgrade.get('action')!r}, "
            f"pending_action={upgrade.get('pending_action')!r}",
        )

    # ------------------------------------------------------------- [PR4] tool_unavailable
    bogus = MCP.structured(mcp.call_tool("this_tool_does_not_exist_xyz"))
    msg = (bogus or {}).get("message", "")
    results.record(
        "[PR4]",
        "tools/call bogus_name -> error_type=tool_unavailable, message refs "
        "whats_new + ping",
        bool(
            isinstance(bogus, dict)
            and bogus.get("error") is True
            and bogus.get("error_type") == "tool_unavailable"
            and "whats_new" in msg
            and "ping" in msg
        ),
        f"error_type={bogus.get('error_type')!r}",
    )

    results.record(
        "[PR4]",
        "tools/call ping -> normal response (regression)",
        bool(isinstance(ping1, dict) and ping1.get("status") == "ok"),
    )

    not_found = MCP.structured(
        mcp.call_tool("get_business", {"business_id": BOGUS_BUSINESS_ID})
    )
    results.record(
        "[PR4]",
        "get_business with bogus id -> CitedAPIError shape (NOT tool_unavailable)",
        bool(
            isinstance(not_found, dict)
            and not_found.get("error_type") != "tool_unavailable"
            and (not_found.get("error") is True or "status_code" in not_found)
        ),
        f"error_type={not_found.get('error_type')!r}, "
        f"status_code={not_found.get('status_code')!r}",
    )

    # ------------------------------------------------------------- [+] Cross-env token rejection
    other_env = "prod" if env == "dev" else "dev"
    other_token = _load_cached_token(other_env)
    if not other_token:
        results.skip(
            "[+]",
            f"{other_env} token presented to {env} -> 401",
            f"no cached {other_env} token (run --env {other_env} first)",
        )
    else:
        try:
            r = httpx.post(
                f"{base}/mcp",
                headers={
                    "Authorization": f"Bearer {other_token}",
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                },
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 997},
                timeout=15,
            )
            body = r.json() if "json" in r.headers.get("content-type", "") else {}
            results.record(
                "[+]",
                f"{other_env} token presented to {env} -> 401",
                r.status_code == 401,
                f"status={r.status_code}, error={body.get('error')!r}",
            )
        except Exception as e:
            results.record(
                "[+]",
                f"{other_env} token presented to {env} -> 401",
                False, str(e),
            )

    # --------------------------------------------- [+] Rate limiter (LAST: pollutes window ~60s)
    # _check_rate_limit returns {"error": True, "message": "Rate limited...",
    # "retry_after_seconds": N} — match on `retry_after_seconds` (specific to
    # the rate-limit branch) rather than the message text (which could change).
    print("\n  [+] Running rate-limiter test (~70 sequential calls, ~30s)...")
    try:
        rate_limited = 0
        for _ in range(70):
            envelope = mcp.call_tool("check_auth_status")
            sc = MCP.structured(envelope)
            if isinstance(sc, dict) and "retry_after_seconds" in sc and sc.get("error") is True:
                rate_limited += 1
        results.record(
            "[+]",
            "Rate limiter triggers within 70 sequential check_auth_status calls",
            rate_limited > 0,
            f"rate-limited responses: {rate_limited}/70",
        )
    except Exception as e:
        results.record(
            "[+]",
            "Rate limiter triggers within 70 sequential check_auth_status calls",
            False, str(e),
        )

    return results.summary()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=list(ENVS.keys()), required=True)
    args = parser.parse_args()
    return run_tests(args.env)


if __name__ == "__main__":
    sys.exit(main())
