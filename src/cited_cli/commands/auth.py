from __future__ import annotations

import sys
from typing import Annotated

import typer

from cited_cli.output.formatter import OutputContext, print_error, print_result, print_success
from cited_cli.output.tables import render_kv
from cited_cli.utils.errors import CitedAPIError, ExitCode, handle_api_error
from cited_cli.utils.interactive import is_interactive
from cited_core.api import endpoints
from cited_core.api.client import CitedClient
from cited_core.auth.store import TokenStore
from cited_core.config.constants import DEFAULT_ENV, FRONTEND_URLS
from cited_core.config.manager import ConfigManager

auth_app = typer.Typer(name="auth", help="Authentication commands.")

_VALID_PROVIDERS = ("google", "microsoft", "github")


def _get_ctx(ctx: typer.Context) -> tuple[OutputContext, ConfigManager, str]:
    obj = ctx.obj or {}
    out = obj.get("output", OutputContext())
    cfg = obj.get("config", ConfigManager())
    env = cfg.get_environment(
        profile=obj.get("profile", "default"),
        override=obj.get("env_override"),
    )
    return out, cfg, env


def _get_api_url(ctx: typer.Context, cfg: ConfigManager) -> str:
    obj = ctx.obj or {}
    return cfg.get_api_url(
        profile=obj.get("profile", "default"),
        env_override=obj.get("env_override"),
    )


def _password_login(out: OutputContext, api_url: str, env: str, email: str, password: str) -> None:
    client = CitedClient(base_url=api_url)
    try:
        response = client.post(endpoints.CLI_LOGIN, json={"email": email, "password": password})
        token = response["token"]

        store = TokenStore()
        store.save_token(env, token)
        print_success(f"Logged in to {env} as {email}", out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


def _browser_auth(
    out: OutputContext, api_url: str, env: str, provider: str | None = None,
    *, mode: str = "login",
) -> None:
    import webbrowser
    from urllib.parse import urlencode

    from cited_core.auth.oauth_server import OAuthCallbackServer

    callback_server = OAuthCallbackServer(timeout=120)
    callback_server.start()

    try:
        # Build the authorize-app URL — the backend handles login/consent/redirect
        params: dict[str, str] = {
            "callback": callback_server.redirect_uri,
            "app_name": "cited-cli",
        }
        if provider:
            params["provider"] = provider
        if mode == "register":
            params["mode"] = "register"

        auth_url = f"{api_url}{endpoints.AUTHORIZE_APP}?{urlencode(params)}"

        action = "registration" if mode == "register" else "login"
        label = f"{provider} {action}" if provider else action
        out.console.print(f"Opening browser for {label}...")
        if not webbrowser.open(auth_url):
            out.console.print(
                f"\nCould not open browser. Visit this URL manually:\n{auth_url}"
            )
        out.console.print("[dim]Waiting for authentication...[/dim]")

        token = callback_server.wait_for_token()
        if not token:
            # Paste fallback for environments where localhost callback fails
            if is_interactive():
                out.console.print(
                    "\n[yellow]Browser callback timed out.[/yellow]\n"
                    "If you completed login in the browser, copy the token shown\n"
                    "on the success page and paste it below.\n"
                )
                pasted = typer.prompt("Paste token (or press Enter to cancel)", default="")
                if pasted.strip():
                    token = pasted.strip()
                else:
                    print_error("Authentication cancelled.", out)
                    raise typer.Exit(ExitCode.AUTH_ERROR)
            else:
                print_error("Authentication timed out. Please try again.", out)
                raise typer.Exit(ExitCode.AUTH_ERROR)

        store = TokenStore()
        store.save_token(env, token)
        via = f" via {provider}" if provider else ""
        success_msg = "Registered" if mode == "register" else "Logged in"
        print_success(f"{success_msg} on {env}{via}", out)
    finally:
        callback_server.shutdown()


def _password_register(
    out: OutputContext, api_url: str, env: str, name: str, email: str, password: str,
) -> None:
    from urllib.parse import parse_qs, urlparse

    client = CitedClient(base_url=api_url)
    try:
        response = client.post(
            endpoints.CLI_REGISTER,
            json={"name": name, "email": email, "password": password},
        )
        msg = response["message"]
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
        return
    finally:
        client.close()

    print_success(f"Account created for {email} on {env}", out)
    out.console.print(f"[dim]{msg}[/dim]")

    out.console.print("\n[bold]Paste your verification link from the email:[/bold]")
    verify_url = typer.prompt("Verification URL").strip()

    parsed = urlparse(verify_url)
    params = parse_qs(parsed.query)
    token = params.get("token", [None])[0]
    if not token:
        print_error(
            "Could not find token in URL. Run `cited login` after verifying in browser.",
            out,
        )
        raise typer.Exit(1)

    client = CitedClient(base_url=api_url)
    try:
        verify_response = client.post(
            endpoints.CLI_VERIFY_EMAIL,
            json={"token": token},
        )
        jwt = verify_response["token"]
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
        return
    finally:
        client.close()

    store = TokenStore()
    store.save_token(env, jwt)
    print_success(f"Email verified! Logged in as {email}", out)

    frontend_url = FRONTEND_URLS.get(env, FRONTEND_URLS[DEFAULT_ENV])
    out.console.print(f"[dim]→ Complete your account setup at {frontend_url}/onboarding[/dim]")


def do_login(
    ctx: typer.Context,
    email: str | None = None,
    password: str | None = None,
    provider: str | None = None,
) -> None:
    """Shared login logic for both `cited login` and `cited auth login`."""
    out, cfg, env = _get_ctx(ctx)
    api_url = _get_api_url(ctx, cfg)

    if provider and provider not in _VALID_PROVIDERS:
        print_error(
            f"Invalid provider '{provider}'. "
            f"Must be one of: {', '.join(_VALID_PROVIDERS)}",
            out,
        )
        raise typer.Exit(ExitCode.VALIDATION_ERROR)

    if email:
        if password is None:
            if not is_interactive():
                print_error(
                    "Non-interactive mode requires --email and --password", out
                )
                raise typer.Exit(ExitCode.VALIDATION_ERROR)
            password = typer.prompt("Password", hide_input=True)
        _password_login(out, api_url, env, email, password)
    else:
        # Browser login — works in both TTY and non-TTY contexts.
        # The browser opens independently and the localhost callback
        # server receives the token without needing stdin.
        _browser_auth(out, api_url, env, provider, mode="login")


def do_logout(ctx: typer.Context) -> None:
    """Shared logout logic for both `cited logout` and `cited auth logout`."""
    out, cfg, env = _get_ctx(ctx)
    store = TokenStore()

    if not store.has_token(env):
        print_error(f"Not logged in to {env}", out)
        raise typer.Exit(ExitCode.ERROR)

    store.delete_token(env)
    print_success(f"Logged out of {env}", out)


def do_register(
    ctx: typer.Context,
    email: str | None = None,
    name: str | None = None,
    password: str | None = None,
    provider: str | None = None,
) -> None:
    """Shared register logic for both `cited register` and `cited auth register`."""
    out, cfg, env = _get_ctx(ctx)
    api_url = _get_api_url(ctx, cfg)

    if provider and provider not in _VALID_PROVIDERS:
        print_error(
            f"Invalid provider '{provider}'. "
            f"Must be one of: {', '.join(_VALID_PROVIDERS)}",
            out,
        )
        raise typer.Exit(ExitCode.VALIDATION_ERROR)

    if email:
        if name is None:
            if not is_interactive():
                print_error("Non-interactive mode requires --name", out)
                raise typer.Exit(ExitCode.VALIDATION_ERROR)
            name = typer.prompt("Full name")
        if password is None:
            if not is_interactive():
                print_error("Non-interactive mode requires --password", out)
                raise typer.Exit(ExitCode.VALIDATION_ERROR)
            password = typer.prompt("Password", hide_input=True)
            confirm = typer.prompt("Confirm password", hide_input=True)
            if password != confirm:
                print_error("Passwords do not match.", out)
                raise typer.Exit(ExitCode.VALIDATION_ERROR)
        _password_register(out, api_url, env, name, email, password)
    else:
        _browser_auth(out, api_url, env, provider, mode="register")


@auth_app.command()
def login(
    ctx: typer.Context,
    email: Annotated[str | None, typer.Option(help="Email address")] = None,
    password: Annotated[
        str | None, typer.Option(help="Password", hide_input=True)
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option(help="OAuth provider: google, microsoft, github"),
    ] = None,
) -> None:
    """Log in to Cited. Opens browser by default, or use --email for password login."""
    do_login(ctx, email, password, provider)


@auth_app.command()
def logout(ctx: typer.Context) -> None:
    """Log out and clear stored credentials."""
    do_logout(ctx)


@auth_app.command()
def register(
    ctx: typer.Context,
    email: Annotated[str | None, typer.Option(help="Email address")] = None,
    name: Annotated[str | None, typer.Option(help="Full name")] = None,
    password: Annotated[
        str | None, typer.Option(help="Password", hide_input=True)
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option(help="OAuth provider: google, microsoft, github"),
    ] = None,
) -> None:
    """Register a new Cited account. Opens browser or use --email."""
    do_register(ctx, email, name, password, provider)


@auth_app.command()
def status(ctx: typer.Context) -> None:
    """Show current authentication status and user info."""
    out, cfg, env = _get_ctx(ctx)
    store = TokenStore()
    token = store.get_token(env)

    if not token:
        print_error(f"Not logged in to {env}. Run: cited login", out)
        raise typer.Exit(ExitCode.AUTH_ERROR)

    api_url = _get_api_url(ctx, cfg)
    client = CitedClient(base_url=api_url, token=token)
    try:
        user = client.get(endpoints.ME)
        onboarding_completed = user.get("onboarding_completed", False)
        data = {
            "environment": env,
            "email": user.get("email", ""),
            "name": user.get("name", user.get("full_name", "")),
            "plan": user.get("plan", user.get("subscription_tier", "")),
            "onboarding_completed": onboarding_completed,
        }
        print_result(
            data,
            out,
            human_formatter=lambda d, c: render_kv("Auth Status", d, c),
        )
        if not onboarding_completed and not out.json_mode:
            frontend_url = FRONTEND_URLS.get(env, FRONTEND_URLS[DEFAULT_ENV])
            out.console.print(
                f"[yellow]→ Account setup incomplete. "
                f"Visit {frontend_url}/onboarding to finish.[/yellow]"
            )
    except CitedAPIError as e:
        if e.status_code in (401, 403):
            store.delete_token(env)
            print_error("Session expired. Run: cited login", out)
            raise typer.Exit(ExitCode.AUTH_ERROR) from e
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@auth_app.command()
def token(ctx: typer.Context) -> None:
    """Print the raw JWT token (for piping to other tools)."""
    out, cfg, env = _get_ctx(ctx)
    store = TokenStore()
    t = store.get_token(env)

    if not t:
        print_error(f"Not logged in to {env}", out)
        raise typer.Exit(ExitCode.AUTH_ERROR)

    # Always print raw token to stdout, even in JSON mode
    sys.stdout.write(t + "\n")
