from __future__ import annotations

import contextlib
import sys
from typing import Annotated

import typer

from cited_cli.api import endpoints
from cited_cli.api.client import CitedClient
from cited_cli.auth.store import TokenStore
from cited_cli.config.manager import ConfigManager
from cited_cli.output.formatter import OutputContext, print_error, print_result, print_success
from cited_cli.output.tables import render_kv
from cited_cli.utils.errors import CitedAPIError, ExitCode, handle_api_error

auth_app = typer.Typer(name="auth", help="Authentication commands.")


def _get_ctx(ctx: typer.Context) -> tuple[OutputContext, ConfigManager, str]:
    obj = ctx.obj or {}
    out = obj.get("output", OutputContext())
    cfg = obj.get("config", ConfigManager())
    env = cfg.get_environment(
        profile=obj.get("profile", "default"),
        override=obj.get("env_override"),
    )
    return out, cfg, env


@auth_app.command()
def login(
    ctx: typer.Context,
    email: Annotated[str | None, typer.Option(help="Email address")] = None,
    password: Annotated[str | None, typer.Option(help="Password", hide_input=True)] = None,
) -> None:
    """Log in with email and password."""
    out, cfg, env = _get_ctx(ctx)

    if not sys.stdin.isatty() and (email is None or password is None):
        print_error("Non-interactive mode requires --email and --password", out)
        raise typer.Exit(ExitCode.VALIDATION_ERROR)

    if email is None:
        email = typer.prompt("Email")
    if password is None:
        password = typer.prompt("Password", hide_input=True)

    api_url = cfg.get_api_url(
        profile=(ctx.obj or {}).get("profile", "default"),
        env_override=(ctx.obj or {}).get("env_override"),
    )

    client = CitedClient(base_url=api_url)
    try:
        response = client.post_raw(endpoints.LOGIN, json={"email": email, "password": password})
        if not response.is_success:
            body = {}
            with contextlib.suppress(Exception):
                body = response.json()
            msg = body.get("detail", f"Login failed ({response.status_code})")
            raise CitedAPIError(response.status_code, str(msg))

        # Extract JWT from cookie
        token = response.cookies.get("advgeo_session")
        if not token:
            # Fallback: check Set-Cookie header manually
            for header_val in response.headers.get_list("set-cookie"):
                if header_val.startswith("advgeo_session="):
                    token = header_val.split("=", 1)[1].split(";")[0]
                    break

        if not token:
            print_error("Login succeeded but no session token was returned.", out)
            raise typer.Exit(ExitCode.ERROR)

        store = TokenStore()
        store.save_token(env, token)
        print_success(f"Logged in to {env} as {email}", out)
    except CitedAPIError as e:
        handle_api_error(e, out.json_mode)
    finally:
        client.close()


@auth_app.command()
def logout(ctx: typer.Context) -> None:
    """Log out and clear stored credentials."""
    out, cfg, env = _get_ctx(ctx)
    store = TokenStore()

    if not store.has_token(env):
        print_error(f"Not logged in to {env}", out)
        raise typer.Exit(ExitCode.ERROR)

    store.delete_token(env)
    print_success(f"Logged out of {env}", out)


@auth_app.command()
def status(ctx: typer.Context) -> None:
    """Show current authentication status and user info."""
    out, cfg, env = _get_ctx(ctx)
    store = TokenStore()
    token = store.get_token(env)

    if not token:
        print_error(f"Not logged in to {env}. Run: cited auth login", out)
        raise typer.Exit(ExitCode.AUTH_ERROR)

    api_url = cfg.get_api_url(
        profile=(ctx.obj or {}).get("profile", "default"),
        env_override=(ctx.obj or {}).get("env_override"),
    )
    client = CitedClient(base_url=api_url, token=token)
    try:
        user = client.get(endpoints.ME)
        data = {
            "environment": env,
            "email": user.get("email", ""),
            "name": user.get("name", user.get("full_name", "")),
            "plan": user.get("plan", user.get("subscription_tier", "")),
        }
        print_result(
            data,
            out,
            human_formatter=lambda d, c: render_kv("Auth Status", d, c),
        )
    except CitedAPIError as e:
        if e.status_code in (401, 403):
            store.delete_token(env)
            print_error("Session expired. Run: cited auth login", out)
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
