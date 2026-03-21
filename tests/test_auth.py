from __future__ import annotations

import json
import threading
import urllib.request

import httpx
import respx


def _setup_tmp_config(tmp_path, monkeypatch):
    config_dir = tmp_path / ".cited"
    config_file = config_dir / "config.toml"
    creds_file = config_dir / "credentials.json"
    monkeypatch.setattr("cited_core.config.constants.CONFIG_DIR", config_dir)
    monkeypatch.setattr("cited_core.config.constants.CONFIG_FILE", config_file)
    monkeypatch.setattr("cited_core.config.constants.CREDENTIALS_FILE", creds_file)
    # Also patch the already-imported references in store.py
    monkeypatch.setattr("cited_core.auth.store.CONFIG_DIR", config_dir)
    monkeypatch.setattr("cited_core.auth.store.CREDENTIALS_FILE", creds_file)
    # Force file-based credential storage (no keyring) so we can verify
    monkeypatch.setattr("cited_core.auth.store.TokenStore._has_keyring", lambda self: False)
    return config_dir, creds_file


def test_auth_status_not_logged_in(runner, cli_app, tmp_path, monkeypatch):
    _setup_tmp_config(tmp_path, monkeypatch)
    result = runner.invoke(cli_app, ["auth", "status"])
    assert result.exit_code != 0


def test_auth_logout_not_logged_in(runner, cli_app, tmp_path, monkeypatch):
    _setup_tmp_config(tmp_path, monkeypatch)
    result = runner.invoke(cli_app, ["auth", "logout"])
    assert result.exit_code != 0


def test_auth_token_not_logged_in(runner, cli_app, tmp_path, monkeypatch):
    _setup_tmp_config(tmp_path, monkeypatch)
    result = runner.invoke(cli_app, ["auth", "token"])
    assert result.exit_code != 0


@respx.mock
def test_login_password_flow(runner, cli_app, tmp_path, monkeypatch):
    """Password login via --email/--password calls /auth/cli-login and stores token."""
    _, creds_file = _setup_tmp_config(tmp_path, monkeypatch)

    respx.post("https://api.youcited.com/auth/cli-login").mock(
        return_value=httpx.Response(200, json={"token": "fake-jwt-token"})
    )

    result = runner.invoke(
        cli_app,
        ["--env", "prod", "auth", "login", "--email", "user@example.com", "--password", "secret"],
    )
    assert result.exit_code == 0
    assert "Logged in" in result.output

    # Verify token was stored
    creds = json.loads(creds_file.read_text())
    assert creds["prod"] == "fake-jwt-token"


@respx.mock
def test_login_browser_flow(runner, cli_app, tmp_path, monkeypatch):
    """Browser login starts OAuth server, opens browser, receives token via callback."""
    _, creds_file = _setup_tmp_config(tmp_path, monkeypatch)

    # Capture the redirect_uri from the request so we can send a token to it
    captured_redirect_uri = {}

    def mock_oauth_start(request):
        body = json.loads(request.content)
        captured_redirect_uri["uri"] = body["redirect_uri"]
        return httpx.Response(200, json={"auth_url": "https://accounts.google.com/auth"})

    respx.post("https://api.youcited.com/auth/cli-oauth-start").mock(
        side_effect=mock_oauth_start
    )

    # Mock webbrowser.open to instead send a token to the callback server
    def fake_browser_open(url):
        # Give the server a moment, then send the token callback
        def send_callback():
            uri = captured_redirect_uri["uri"]
            callback_url = f"{uri}?token=browser-jwt-token"
            urllib.request.urlopen(callback_url, timeout=5)  # noqa: S310

        threading.Thread(target=send_callback, daemon=True).start()
        return True

    monkeypatch.setattr("webbrowser.open", fake_browser_open)

    result = runner.invoke(
        cli_app,
        ["--env", "prod", "auth", "login", "--provider", "google"],
        input=None,
    )
    assert result.exit_code == 0
    assert "Logged in" in result.output
    assert "google" in result.output

    creds = json.loads(creds_file.read_text())
    assert creds["prod"] == "browser-jwt-token"


def test_login_invalid_provider(runner, cli_app, tmp_path, monkeypatch):
    """Invalid provider name should exit with validation error."""
    _setup_tmp_config(tmp_path, monkeypatch)

    result = runner.invoke(
        cli_app,
        ["auth", "login", "--provider", "facebook"],
    )
    assert result.exit_code != 0
    assert "Invalid provider" in result.output


def test_login_non_interactive_email_requires_password(runner, cli_app, tmp_path, monkeypatch):
    """Non-TTY with --email but no --password should fail with a helpful error."""
    _setup_tmp_config(tmp_path, monkeypatch)
    monkeypatch.setattr("cited_cli.commands.auth.is_interactive", lambda: False)

    result = runner.invoke(cli_app, ["auth", "login", "--email", "user@example.com"])
    assert result.exit_code != 0
    assert "Non-interactive" in result.output


# --- Top-level login/logout tests ---


@respx.mock
def test_top_level_login_password(runner, cli_app, tmp_path, monkeypatch):
    """Top-level `cited login --email ...` should work identically to `cited auth login`."""
    _, creds_file = _setup_tmp_config(tmp_path, monkeypatch)

    respx.post("https://api.youcited.com/auth/cli-login").mock(
        return_value=httpx.Response(200, json={"token": "top-level-jwt"})
    )

    result = runner.invoke(
        cli_app,
        ["--env", "prod", "login", "--email", "user@example.com", "--password", "secret"],
    )
    assert result.exit_code == 0
    assert "Logged in" in result.output

    creds = json.loads(creds_file.read_text())
    assert creds["prod"] == "top-level-jwt"


@respx.mock
def test_top_level_logout(runner, cli_app, tmp_path, monkeypatch):
    """Top-level `cited logout` clears stored token."""
    config_dir, creds_file = _setup_tmp_config(tmp_path, monkeypatch)

    # Pre-store a token
    config_dir.mkdir(parents=True, exist_ok=True)
    creds_file.write_text(json.dumps({"prod": "some-token"}))

    result = runner.invoke(cli_app, ["--env", "prod", "logout"])
    assert result.exit_code == 0
    assert "Logged out" in result.output

    creds = json.loads(creds_file.read_text())
    assert "prod" not in creds


# --- Register tests ---


_FAKE_USER = {
    "id": "user-123",
    "name": "Test User",
    "email": "new@example.com",
    "auth_provider": "email",
    "email_verified": True,
    "has_password": True,
    "created_at": "2026-01-01T00:00:00Z",
    "avatar_url": None,
    "business_name": None,
    "business_website": None,
    "industry": None,
    "business_description": None,
    "onboarding_completed": False,
    "subscription_tier": "growth",
    "subscription_status": None,
    "cancel_at_period_end": None,
    "subscription_period_end": None,
    "subscription_canceled_at": None,
    "plan_limits": None,
    "role": "user",
    "agency_owner_id": None,
    "is_agency_owner": False,
    "active_agency_context_id": None,
    "active_agency_permission": None,
    "available_agencies": None,
    "owner_subscription_status": None,
    "is_impersonating": False,
    "impersonating_user_id": None,
    "impersonating_user_email": None,
    "impersonating_user_name": None,
    "real_admin_id": None,
    "pending_invitations_count": 0,
}


@respx.mock
def test_register_password_flow(runner, cli_app, tmp_path, monkeypatch):
    """Password registration calls /auth/cli-register (no token), prompts for verification URL, then calls /auth/cli-verify-email and stores token."""
    _, creds_file = _setup_tmp_config(tmp_path, monkeypatch)

    respx.post("https://api.youcited.com/auth/cli-register").mock(
        return_value=httpx.Response(
            201, json={"message": "Verification email sent. Check your inbox to complete registration."}
        )
    )
    respx.post("https://api.youcited.com/auth/cli-verify-email").mock(
        return_value=httpx.Response(
            200, json={"token": "register-jwt-token", "user": _FAKE_USER}
        )
    )

    fake_verify_url = "https://app.youcited.com/complete-registration?token=fake-verification-token-abc123xyz"

    result = runner.invoke(
        cli_app,
        [
            "--env", "prod", "auth", "register",
            "--email", "new@example.com",
            "--name", "Test User",
            "--password", "Secret1234",
        ],
        input=f"{fake_verify_url}\n",
    )
    assert result.exit_code == 0, result.output
    assert "Account created" in result.output
    assert "Email verified" in result.output

    creds = json.loads(creds_file.read_text())
    assert creds["prod"] == "register-jwt-token"


@respx.mock
def test_top_level_register(runner, cli_app, tmp_path, monkeypatch):
    """Top-level `cited register --email ...` should work identically to `cited auth register`."""
    _, creds_file = _setup_tmp_config(tmp_path, monkeypatch)

    respx.post("https://api.youcited.com/auth/cli-register").mock(
        return_value=httpx.Response(
            201, json={"message": "Verification email sent. Check your inbox to complete registration."}
        )
    )
    respx.post("https://api.youcited.com/auth/cli-verify-email").mock(
        return_value=httpx.Response(
            200, json={"token": "top-register-jwt", "user": _FAKE_USER}
        )
    )

    fake_verify_url = "https://app.youcited.com/complete-registration?token=fake-verification-token-abc123xyz"

    result = runner.invoke(
        cli_app,
        [
            "--env", "prod", "register",
            "--email", "new@example.com",
            "--name", "Test User",
            "--password", "Secret1234",
        ],
        input=f"{fake_verify_url}\n",
    )
    assert result.exit_code == 0, result.output
    assert "Account created" in result.output
    assert "Email verified" in result.output

    creds = json.loads(creds_file.read_text())
    assert creds["prod"] == "top-register-jwt"


@respx.mock
def test_register_browser_flow(runner, cli_app, tmp_path, monkeypatch):
    """Browser registration sends mode=register in cli-oauth-start payload."""
    _, creds_file = _setup_tmp_config(tmp_path, monkeypatch)

    captured_payload = {}

    def mock_oauth_start(request):
        body = json.loads(request.content)
        captured_payload.update(body)
        return httpx.Response(200, json={"auth_url": "https://accounts.google.com/auth"})

    respx.post("https://api.youcited.com/auth/cli-oauth-start").mock(
        side_effect=mock_oauth_start
    )

    def fake_browser_open(url):
        def send_callback():
            uri = captured_payload["redirect_uri"]
            callback_url = f"{uri}?token=register-browser-jwt"
            urllib.request.urlopen(callback_url, timeout=5)  # noqa: S310

        threading.Thread(target=send_callback, daemon=True).start()
        return True

    monkeypatch.setattr("webbrowser.open", fake_browser_open)

    result = runner.invoke(
        cli_app,
        ["--env", "prod", "auth", "register", "--provider", "google"],
        input=None,
    )
    assert result.exit_code == 0
    assert "Registered" in result.output
    assert captured_payload.get("mode") == "register"

    creds = json.loads(creds_file.read_text())
    assert creds["prod"] == "register-browser-jwt"


def test_register_invalid_provider(runner, cli_app, tmp_path, monkeypatch):
    """Invalid provider name should exit with validation error."""
    _setup_tmp_config(tmp_path, monkeypatch)

    result = runner.invoke(
        cli_app,
        ["auth", "register", "--provider", "facebook"],
    )
    assert result.exit_code != 0
    assert "Invalid provider" in result.output


def test_register_password_mismatch(runner, cli_app, tmp_path, monkeypatch):
    """Interactive prompt with mismatched passwords should exit with validation error."""
    _setup_tmp_config(tmp_path, monkeypatch)
    monkeypatch.setattr("cited_cli.commands.auth.is_interactive", lambda: True)

    result = runner.invoke(
        cli_app,
        ["auth", "register", "--email", "new@example.com", "--name", "Test User"],
        input="Secret1234\nDifferent1234\n",
    )
    assert result.exit_code != 0
    assert "do not match" in result.output.lower() or "Passwords" in result.output


@respx.mock
def test_paste_fallback(runner, cli_app, tmp_path, monkeypatch):
    """When browser callback times out, user can paste token manually."""
    _, creds_file = _setup_tmp_config(tmp_path, monkeypatch)

    respx.post("https://api.youcited.com/auth/cli-oauth-start").mock(
        return_value=httpx.Response(200, json={"auth_url": "https://example.com/auth"})
    )

    # Mock webbrowser.open to do nothing (simulates browser opening but no callback)
    monkeypatch.setattr("webbrowser.open", lambda url: True)

    # Mock OAuthCallbackServer.wait_for_token to return None (timeout)
    monkeypatch.setattr(
        "cited_cli.auth.oauth_server.OAuthCallbackServer.wait_for_token",
        lambda self: None,
    )

    # CliRunner replaces sys.stdin, so patch the helper used by auth.py
    monkeypatch.setattr("cited_cli.commands.auth.is_interactive", lambda: True)

    result = runner.invoke(
        cli_app,
        ["--env", "prod", "login", "--provider", "google"],
        input="pasted-jwt-token\n",
    )
    assert result.exit_code == 0
    assert "Logged in" in result.output

    creds = json.loads(creds_file.read_text())
    assert creds["prod"] == "pasted-jwt-token"
