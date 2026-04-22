from __future__ import annotations

import logging
import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import jwt
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import construct_redirect_uri
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from cited_core.api.client import CitedClient
from cited_mcp.auth_provider import CitedAccessToken, CitedOAuthProvider
from cited_mcp.context import CitedContext

logger = logging.getLogger(__name__)


class _PatchRegistrationMiddleware:
    """ASGI middleware that patches OAuth client registration requests.

    The MCP SDK (v1.27) requires grant_types to include both
    "authorization_code" and "refresh_token". Some clients (e.g. Claude's
    Custom Connectors) only send "authorization_code". This middleware
    adds "refresh_token" to grant_types before the SDK's validation runs.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] != "/register":
            await self.app(scope, receive, send)
            return

        import json as _json

        body_parts: list[bytes] = []
        patched = False

        async def patching_receive() -> dict:
            nonlocal patched
            message = await receive()
            if message["type"] == "http.request" and not patched:
                raw = message.get("body", b"")
                body_parts.append(raw)
                if message.get("more_body", False):
                    return message
                full_body = b"".join(body_parts)
                try:
                    data = _json.loads(full_body)
                    grant_types = data.get("grant_types", [])
                    if "refresh_token" not in grant_types:
                        data["grant_types"] = list(grant_types) + ["refresh_token"]
                        full_body = _json.dumps(data).encode()
                        logger.debug("Patched registration: added refresh_token to grant_types")
                except (ValueError, KeyError):
                    pass
                patched = True
                message = {**message, "body": full_body}
            return message

        await self.app(scope, patching_receive, send)


@asynccontextmanager
async def cited_remote_lifespan(server: FastMCP) -> AsyncIterator[CitedContext]:
    """Lifespan for the remote MCP server.

    Unlike the stdio lifespan, the remote server doesn't have a pre-configured
    token. The per-user JWT comes from the OAuth access token at request time
    via get_access_token(). The lifespan provides a base context with no token.
    """
    api_url = os.environ.get("CITED_API_URL", "https://api.youcited.com")
    env = os.environ.get("CITED_ENV", "prod")

    client = CitedClient(base_url=api_url, token=None)
    try:
        yield CitedContext(client=client, env=env, api_url=api_url)
    finally:
        client.close()


def get_user_client(api_url: str) -> CitedClient | None:
    """Create a CitedClient using the authenticated user's JWT from OAuth context.

    Tools can call this to get a client authenticated as the current user.
    """
    access_token = get_access_token()
    if not access_token or not isinstance(access_token, CitedAccessToken):
        return None
    return CitedClient(base_url=api_url, token=access_token.user_jwt)


def create_remote_server() -> FastMCP:
    """Create and configure the remote MCP server with OAuth auth."""
    import cited_mcp.server as server_module

    backend_url = os.environ.get("CITED_API_URL", "https://api.youcited.com")
    mcp_url = os.environ.get("MCP_URL", "https://mcp.youcited.com")
    jwt_secret = os.environ["JWT_SECRET"]
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))

    auth_provider = CitedOAuthProvider(
        backend_url=backend_url,
        mcp_url=mcp_url,
        jwt_secret=jwt_secret,
    )

    remote_mcp = FastMCP(
        "cited",
        instructions="Cited GEO platform — audit, optimize, and monitor AI search presence",
        host=host,
        port=port,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            allowed_origins=[
                "https://claude.ai",
                "https://api.anthropic.com",
                mcp_url,
            ],
        ),
        lifespan=cited_remote_lifespan,
        auth_server_provider=auth_provider,
        auth=AuthSettings(
            issuer_url=mcp_url,  # type: ignore[arg-type]
            resource_server_url=mcp_url,  # type: ignore[arg-type]
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                valid_scopes=["cited"],
                default_scopes=["cited"],
            ),
            revocation_options=RevocationOptions(enabled=True),
        ),
    )

    # Set the module-level mcp instance so tool modules register on it
    server_module.mcp = remote_mcp

    # Register the OAuth callback route (handles redirect from backend)
    @remote_mcp.custom_route("/oauth/callback", methods=["GET"])  # type: ignore[untyped-decorator]
    async def oauth_callback(request: Request) -> Response:
        """Handle callback from the Cited backend after user authentication."""
        user_token = request.query_params.get("token")
        state_jwt = request.query_params.get("state")

        if not user_token or not state_jwt:
            return JSONResponse(
                {"error": "Missing token or state parameter"},
                status_code=400,
            )

        # Validate user_token is a well-formed, non-expired JWT from the backend.
        # We can't verify the signature (different secret), but we can reject
        # malformed tokens, expired tokens, and tokens missing required claims.
        try:
            user_claims = jwt.decode(
                user_token,
                options={"verify_signature": False, "verify_exp": True},
            )
            if "sub" not in user_claims or "email" not in user_claims:
                return JSONResponse(
                    {"error": "Invalid user token: missing required claims"},
                    status_code=400,
                )
        except jwt.ExpiredSignatureError:
            return JSONResponse(
                {"error": "User token has expired. Please log in again."},
                status_code=400,
            )
        except jwt.InvalidTokenError:
            return JSONResponse(
                {"error": "Invalid user token format."},
                status_code=400,
            )

        try:
            state = jwt.decode(state_jwt, jwt_secret, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return JSONResponse(
                {"error": "Authorization state expired. Please try again."},
                status_code=400,
            )
        except jwt.InvalidTokenError:
            return JSONResponse(
                {"error": "Invalid authorization state."},
                status_code=400,
            )

        # Generate authorization code and store it
        code = secrets.token_urlsafe(32)
        auth_provider.store_auth_code(
            code=code,
            user_jwt=user_token,
            client_id=state["client_id"],
            code_challenge=state["code_challenge"],
            redirect_uri=state["redirect_uri"],
            redirect_uri_provided_explicitly=state.get(
                "redirect_uri_provided_explicitly", True
            ),
            scopes=state.get("scopes", []),
            resource=state.get("resource"),
        )

        # Redirect to Claude Desktop's redirect URI with the auth code
        redirect_uri = construct_redirect_uri(
            state["redirect_uri"],
            code=code,
            state=state.get("original_state"),
        )
        return RedirectResponse(url=redirect_uri, status_code=302)

    @remote_mcp.custom_route("/health", methods=["GET"])  # type: ignore[untyped-decorator]
    async def health_check(request: Request) -> Response:
        return JSONResponse({"status": "ok"})

    @remote_mcp.custom_route("/robots.txt", methods=["GET"])  # type: ignore[untyped-decorator]
    async def robots_txt(request: Request) -> Response:
        return Response(
            content=(
                "User-agent: *\n"
                "Disallow: /oauth/\n"
                "Allow: /health\n"
                "Allow: /robots.txt\n"
            ),
            media_type="text/plain",
        )

    # Now import tools — they'll register on remote_mcp via server_module.mcp
    server_module.register_tools()

    return remote_mcp


def run_remote_server() -> None:
    """Start the remote MCP server with Streamable HTTP transport and OAuth."""
    import uvicorn

    if "JWT_SECRET" not in os.environ:
        raise SystemExit("JWT_SECRET environment variable is required")
    server = create_remote_server()

    # Wrap the Starlette app with the registration-patching middleware
    # so Custom Connectors that omit refresh_token in grant_types still work.
    starlette_app = server.streamable_http_app()
    patched_app = _PatchRegistrationMiddleware(starlette_app)

    config = uvicorn.Config(
        patched_app,
        host=server.settings.host,
        port=server.settings.port,
        log_level=server.settings.log_level.lower(),
    )
    uvicorn_server = uvicorn.Server(config)

    import anyio
    anyio.run(uvicorn_server.serve)


if __name__ == "__main__":
    run_remote_server()
