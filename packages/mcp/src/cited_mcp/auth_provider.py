from __future__ import annotations

import secrets
import time
from urllib.parse import urlencode

import jwt
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl


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

    The MCP server acts as both the OAuth authorization server (for Claude Desktop)
    and as a relay to the Cited backend API. The flow:

    1. Claude Desktop -> MCP /authorize -> redirect to backend /auth/authorize-app
    2. Backend authenticates user -> redirects to MCP /oauth/callback with JWT
    3. MCP /oauth/callback -> generates auth code -> redirects to Claude Desktop
    4. Claude Desktop -> MCP /token -> exchanges code for access/refresh tokens
    5. Claude Desktop -> MCP /mcp with Bearer token -> MCP uses stored JWT for API calls
    """

    def __init__(self, backend_url: str, mcp_url: str, jwt_secret: str) -> None:
        self.backend_url = backend_url
        self.mcp_url = mcp_url
        self.jwt_secret = jwt_secret
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._auth_codes: dict[str, CitedAuthCode] = {}
        self._access_tokens: dict[str, CitedAccessToken] = {}
        self._refresh_tokens: dict[str, CitedRefreshToken] = {}

    # -- Client registration (RFC 7591) --

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if client_info.client_id is None:
            client_info.client_id = secrets.token_urlsafe(24)
        # Only generate a secret if the client expects one (not "none" auth method)
        if client_info.token_endpoint_auth_method != "none" and client_info.client_secret is None:
            client_info.client_secret = secrets.token_urlsafe(48)
        client_info.client_id_issued_at = int(time.time())
        self._clients[client_info.client_id] = client_info

    # -- Authorization --

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        """Redirect the user to the Cited backend for authentication.

        We encode the original OAuth params into a signed state JWT so the
        /oauth/callback handler can reconstruct the authorization code response.
        """
        state_payload = {
            "client_id": client.client_id,
            "code_challenge": params.code_challenge,
            "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "scopes": params.scopes or [],
            "original_state": params.state,
            "exp": int(time.time()) + 600,  # 10 minute expiry
        }
        if params.resource:
            state_payload["resource"] = params.resource
        signed_state = jwt.encode(state_payload, self.jwt_secret, algorithm="HS256")

        callback_url = f"{self.mcp_url}/oauth/callback"
        query = urlencode({
            "callback": callback_url,
            "state": signed_state,
            "app_name": "Cited MCP",
        })
        return f"{self.backend_url}/auth/authorize-app?{query}"

    # -- Authorization code handling --

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> CitedAuthCode | None:
        code = self._auth_codes.get(authorization_code)
        if code and code.client_id != client.client_id:
            return None
        return code

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: CitedAuthCode,
    ) -> OAuthToken:
        # Remove the auth code (single use)
        self._auth_codes.pop(authorization_code.code, None)

        user_jwt = authorization_code.user_jwt
        scopes = authorization_code.scopes

        access_token_str = secrets.token_urlsafe(32)
        refresh_token_str = secrets.token_urlsafe(32)
        now = int(time.time())

        self._access_tokens[access_token_str] = CitedAccessToken(
            token=access_token_str,
            client_id=client.client_id or "",
            scopes=scopes,
            expires_at=now + 3600,
            user_jwt=user_jwt,
            resource=authorization_code.resource,
        )

        self._refresh_tokens[refresh_token_str] = CitedRefreshToken(
            token=refresh_token_str,
            client_id=client.client_id or "",
            scopes=scopes,
            expires_at=now + 86400 * 30,  # 30 days
            user_jwt=user_jwt,
        )

        return OAuthToken(
            access_token=access_token_str,
            refresh_token=refresh_token_str,
            expires_in=3600,
        )

    # -- Refresh token handling --

    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> CitedRefreshToken | None:
        rt = self._refresh_tokens.get(refresh_token)
        if rt and rt.client_id != client.client_id:
            return None
        if rt and rt.expires_at and rt.expires_at < time.time():
            self._refresh_tokens.pop(refresh_token, None)
            return None
        return rt

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: CitedRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        # Rotate both tokens
        self._refresh_tokens.pop(refresh_token.token, None)
        # Revoke old access tokens for this client
        old_access_keys = [
            k for k, v in self._access_tokens.items()
            if v.client_id == client.client_id
        ]
        for k in old_access_keys:
            del self._access_tokens[k]

        user_jwt = refresh_token.user_jwt
        effective_scopes = scopes if scopes else refresh_token.scopes

        new_access = secrets.token_urlsafe(32)
        new_refresh = secrets.token_urlsafe(32)
        now = int(time.time())

        self._access_tokens[new_access] = CitedAccessToken(
            token=new_access,
            client_id=client.client_id or "",
            scopes=effective_scopes,
            expires_at=now + 3600,
            user_jwt=user_jwt,
        )

        self._refresh_tokens[new_refresh] = CitedRefreshToken(
            token=new_refresh,
            client_id=client.client_id or "",
            scopes=effective_scopes,
            expires_at=now + 86400 * 30,
            user_jwt=user_jwt,
        )

        return OAuthToken(
            access_token=new_access,
            refresh_token=new_refresh,
            expires_in=3600,
        )

    # -- Access token verification --

    async def load_access_token(self, token: str) -> CitedAccessToken | None:
        at = self._access_tokens.get(token)
        if at and at.expires_at and at.expires_at < time.time():
            self._access_tokens.pop(token, None)
            return None
        return at

    # -- Revocation --

    async def revoke_token(
        self,
        token: CitedAccessToken | CitedRefreshToken,
    ) -> None:
        if isinstance(token, CitedAccessToken):
            self._access_tokens.pop(token.token, None)
            # Also revoke refresh tokens for same client
            to_remove = [
                k for k, v in self._refresh_tokens.items()
                if v.client_id == token.client_id
            ]
            for k in to_remove:
                del self._refresh_tokens[k]
        elif isinstance(token, CitedRefreshToken):
            self._refresh_tokens.pop(token.token, None)
            # Also revoke access tokens for same client
            to_remove = [
                k for k, v in self._access_tokens.items()
                if v.client_id == token.client_id
            ]
            for k in to_remove:
                del self._access_tokens[k]

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
    ) -> None:
        """Store an authorization code generated by the /oauth/callback handler."""
        self._auth_codes[code] = CitedAuthCode(
            code=code,
            client_id=client_id,
            code_challenge=code_challenge,
            redirect_uri=AnyUrl(redirect_uri),
            redirect_uri_provided_explicitly=redirect_uri_provided_explicitly,
            scopes=scopes,
            expires_at=time.time() + 300,  # 5 minute expiry
            user_jwt=user_jwt,
            resource=resource,
        )
