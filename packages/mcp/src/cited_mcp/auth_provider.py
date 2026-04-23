from __future__ import annotations

import logging
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import jwt as pyjwt
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl

logger = logging.getLogger(__name__)


def _user_jwt_expired(user_jwt: str) -> bool:
    """Check if the backend user JWT has expired.

    Decodes WITHOUT signature verification (we don't have the backend's secret).
    Only inspects the ``exp`` claim to detect expiry.
    """
    try:
        pyjwt.decode(
            user_jwt,
            options={"verify_signature": False, "verify_exp": True},
        )
        return False  # decode succeeded → not expired
    except pyjwt.ExpiredSignatureError:
        return True
    except pyjwt.InvalidTokenError:
        # Malformed token — treat as expired to force re-auth
        return True


# Allowed redirect URI prefixes for OAuth clients.
# localhost: mcp-remote and local development
# claude.ai: Claude Desktop Custom Connectors
# youcited.com: our own frontend/MCP server callbacks
_ALLOWED_REDIRECT_PREFIXES = (
    "http://localhost",
    "http://127.0.0.1",
    "https://claude.ai/",
    "https://youcited.com/",
    "https://app.youcited.com/",
    "https://mcp.youcited.com/",
)


class _AllowlistedRedirectClient(OAuthClientInformationFull):
    """Client that validates redirect URIs against a whitelist.

    Accepts localhost (any port) for mcp-remote/Cursor and specific
    HTTPS domains for Claude Custom Connectors and Cited services.
    """

    def validate_redirect_uri(self, redirect_uri: AnyUrl | None) -> AnyUrl:
        if redirect_uri is not None:
            uri = str(redirect_uri)
            if any(uri.startswith(prefix) for prefix in _ALLOWED_REDIRECT_PREFIXES):
                return redirect_uri
        return super().validate_redirect_uri(redirect_uri)

# Token lifetimes
ACCESS_TOKEN_TTL = 86400 * 7  # 7 days — matches backend JWT TTL
REFRESH_TOKEN_TTL = 86400 * 7  # 7 days (matches backend JWT TTL)


class CitedAuthCode(AuthorizationCode):
    """Extended authorization code that carries the user's backend JWT."""

    user_jwt: str


class CitedAccessToken(AccessToken):
    """Extended access token that carries the user's backend JWT."""

    user_jwt: str


class CitedRefreshToken(RefreshToken):
    """Extended refresh token that carries the user's backend JWT."""

    user_jwt: str


class CitedOAuthProvider(
    OAuthAuthorizationServerProvider[CitedAuthCode, CitedRefreshToken, CitedAccessToken],
):
    """OAuth provider that delegates user authentication to the Cited backend.

    Access and refresh tokens are **stateless signed JWTs**, so they survive
    server restarts, deploys, and Fargate Spot reclaims without triggering
    re-authentication in Claude Desktop.

    Auth codes remain in-memory (short-lived, single-use, exchanged in seconds).
    Client registrations are also in-memory — Claude Desktop re-registers each session.
    """

    def __init__(self, backend_url: str, mcp_url: str, jwt_secret: str) -> None:
        self.backend_url = backend_url
        self.mcp_url = mcp_url
        self.jwt_secret = jwt_secret
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._auth_codes: dict[str, CitedAuthCode] = {}

    # -- Stateless token helpers --

    def _encode_token(self, payload: dict[str, Any]) -> str:
        return pyjwt.encode(payload, self.jwt_secret, algorithm="HS256")

    def _decode_token(self, token: str) -> dict[str, Any] | None:
        try:
            return pyjwt.decode(token, self.jwt_secret, algorithms=["HS256"])
        except pyjwt.ExpiredSignatureError:
            return None
        except pyjwt.InvalidTokenError:
            return None

    def _issue_tokens(
        self,
        user_jwt: str,
        client_id: str,
        scopes: list[str],
        resource: str | None = None,
    ) -> OAuthToken:
        now = int(time.time())

        access_payload = {
            "typ": "access",
            "sub": client_id,
            "scopes": scopes,
            "user_jwt": user_jwt,
            "exp": now + ACCESS_TOKEN_TTL,
            "iat": now,
        }
        if resource:
            access_payload["resource"] = resource

        refresh_payload = {
            "typ": "refresh",
            "sub": client_id,
            "scopes": scopes,
            "user_jwt": user_jwt,
            "exp": now + REFRESH_TOKEN_TTL,
            "iat": now,
        }

        return OAuthToken(
            access_token=self._encode_token(access_payload),
            refresh_token=self._encode_token(refresh_payload),
            expires_in=ACCESS_TOKEN_TTL,
        )

    # -- Client registration (RFC 7591) --
    # Client info is stored in-memory AND encoded into a signed client_id JWT.
    # On get_client, if the in-memory lookup misses (post-restart), we decode
    # the client_id JWT to reconstruct the registration — making it survive restarts.

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        # Try in-memory first
        client = self._clients.get(client_id)
        if client:
            return client

        # Try to reconstruct from signed client_id JWT (post-restart recovery)
        payload = self._decode_token(client_id)
        if payload and payload.get("typ") == "client":
            client_info = OAuthClientInformationFull(
                client_id=client_id,
                client_secret=payload.get("client_secret"),
                client_id_issued_at=payload.get("iat", int(time.time())),
                redirect_uris=[AnyUrl(u) for u in payload.get("redirect_uris", [])],
                scope=payload.get("scope"),
                token_endpoint_auth_method=payload.get("token_endpoint_auth_method", "none"),
            )
            self._clients[client_id] = client_info
            return client_info

        # Accept unknown client IDs (e.g. old UUID-format registrations lost on restart).
        # Security relies on PKCE, not client identity — this avoids forcing re-registration
        # on every deploy. The permissive redirect client accepts localhost (mcp-remote)
        # and any HTTPS URI (Claude Custom Connectors).
        logger.info("Auto-accepting unknown client_id: %s", client_id[:12])
        client_info = _AllowlistedRedirectClient(
            client_id=client_id,
            client_id_issued_at=int(time.time()),
            redirect_uris=[AnyUrl("http://localhost")],
            scope="cited",
            token_endpoint_auth_method="none",
        )
        self._clients[client_id] = client_info
        return client_info

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        # Generate a client_secret if needed
        if client_info.token_endpoint_auth_method != "none" and client_info.client_secret is None:
            client_info.client_secret = secrets.token_urlsafe(48)

        now = int(time.time())
        # Encode client registration into a signed JWT as the client_id
        client_payload = {
            "typ": "client",
            "redirect_uris": [str(u) for u in (client_info.redirect_uris or [])],
            "token_endpoint_auth_method": client_info.token_endpoint_auth_method or "none",
            "scope": client_info.scope,
            "iat": now,
        }
        if client_info.client_secret:
            client_payload["client_secret"] = client_info.client_secret

        client_info.client_id = self._encode_token(client_payload)
        client_info.client_id_issued_at = now
        self._clients[client_info.client_id] = client_info

    # -- Authorization --

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        """Redirect the user to the Cited backend for authentication."""
        state_payload = {
            "client_id": client.client_id,
            "code_challenge": params.code_challenge,
            "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "scopes": params.scopes or [],
            "original_state": params.state,
            "exp": int(time.time()) + 600,
        }
        if params.resource:
            state_payload["resource"] = params.resource
        signed_state = pyjwt.encode(state_payload, self.jwt_secret, algorithm="HS256")

        callback_url = f"{self.mcp_url}/oauth/callback"
        query = urlencode({
            "callback": callback_url,
            "state": signed_state,
            "app_name": "Cited MCP",
        })
        return f"{self.backend_url}/auth/authorize-app?{query}"

    # -- Authorization code handling (stateless signed JWT) --
    # Auth codes are encoded as signed JWTs so they survive container
    # restarts and deploy rollovers. The in-memory dict is kept as a
    # replay-prevention set (codes are single-use).

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> CitedAuthCode | None:
        # Check replay prevention
        if authorization_code in self._auth_codes:
            return None  # Already exchanged

        # Decode the stateless auth code JWT
        payload = self._decode_token(authorization_code)
        if not payload or payload.get("typ") != "authcode":
            # Fallback: try legacy in-memory lookup
            code = self._auth_codes.get(authorization_code)
            if code and code.client_id != client.client_id:
                return None
            return code

        if payload.get("client_id") != client.client_id:
            return None

        return CitedAuthCode(
            code=authorization_code,
            client_id=payload["client_id"],
            code_challenge=payload["code_challenge"],
            redirect_uri=AnyUrl(payload["redirect_uri"]),
            redirect_uri_provided_explicitly=payload.get(
                "redirect_uri_provided_explicitly", True
            ),
            scopes=payload.get("scopes", []),
            expires_at=payload.get("exp"),
            user_jwt=payload["user_jwt"],
            resource=payload.get("resource"),
        )

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: CitedAuthCode,
    ) -> OAuthToken:
        # Mark as used (replay prevention)
        self._auth_codes[authorization_code.code] = None  # type: ignore
        return self._issue_tokens(
            user_jwt=authorization_code.user_jwt,
            client_id=client.client_id or "",
            scopes=authorization_code.scopes,
            resource=authorization_code.resource,
        )

    # -- Refresh token handling (stateless JWT) --

    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> CitedRefreshToken | None:
        payload = self._decode_token(refresh_token)
        if not payload or payload.get("typ") != "refresh":
            return None
        if payload.get("sub") != client.client_id:
            return None

        user_jwt = payload.get("user_jwt", "")
        if _user_jwt_expired(user_jwt):
            logger.info(
                "Refresh token rejected: embedded user JWT has expired — "
                "client must re-authenticate"
            )
            return None

        return CitedRefreshToken(
            token=refresh_token,
            client_id=payload["sub"],
            scopes=payload.get("scopes", []),
            expires_at=payload.get("exp"),
            user_jwt=user_jwt,
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: CitedRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        effective_scopes = scopes if scopes else refresh_token.scopes
        return self._issue_tokens(
            user_jwt=refresh_token.user_jwt,
            client_id=client.client_id or "",
            scopes=effective_scopes,
        )

    # -- Access token verification (stateless JWT) --

    async def load_access_token(self, token: str) -> CitedAccessToken | None:
        payload = self._decode_token(token)
        if not payload or payload.get("typ") != "access":
            return None

        user_jwt = payload.get("user_jwt", "")
        if _user_jwt_expired(user_jwt):
            logger.info("Access token rejected: embedded user JWT has expired")
            return None

        return CitedAccessToken(
            token=token,
            client_id=payload["sub"],
            scopes=payload.get("scopes", []),
            expires_at=payload.get("exp"),
            user_jwt=user_jwt,
            resource=payload.get("resource"),
        )

    # -- Revocation (best-effort, no-op for stateless tokens) --

    async def revoke_token(
        self,
        token: CitedAccessToken | CitedRefreshToken,
    ) -> None:
        # Stateless JWTs can't be revoked server-side without a blocklist.
        # For this use case (Claude Desktop), explicit revocation is rare
        # and tokens expire naturally.
        logger.debug("Token revocation requested (no-op for stateless tokens)")

    # -- Helper: store auth code from callback --

    def store_auth_code(
        self,
        code: str,
        user_jwt: str,
        client_id: str,
        code_challenge: str,
        redirect_uri: str,
        redirect_uri_provided_explicitly: bool,
        scopes: list[str],
        resource: str | None = None,
    ) -> str:
        """Generate a stateless auth code as a signed JWT.

        The ``code`` parameter (random string) is ignored — we generate
        a self-contained signed JWT that survives container restarts.
        Returns the JWT auth code string.
        """
        now = int(time.time())
        auth_code_jwt = self._encode_token({
            "typ": "authcode",
            "client_id": client_id,
            "code_challenge": code_challenge,
            "redirect_uri": redirect_uri,
            "redirect_uri_provided_explicitly": redirect_uri_provided_explicitly,
            "scopes": scopes,
            "user_jwt": user_jwt,
            "resource": resource,
            "exp": now + 300,
            "iat": now,
        })
        return auth_code_jwt
