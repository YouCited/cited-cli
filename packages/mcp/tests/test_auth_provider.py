"""Tests for the CitedOAuthProvider — specifically JWT expiry handling."""
from __future__ import annotations

import asyncio
import time

import jwt as pyjwt
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from cited_mcp.auth_provider import CitedOAuthProvider, _user_jwt_expired


def run(coro):
    return asyncio.run(coro)


def _make_jwt(exp_offset: int) -> str:
    """Create a JWT with exp = now + exp_offset seconds."""
    return pyjwt.encode(
        {"sub": "test@example.com", "exp": int(time.time()) + exp_offset},
        "test-secret-key-long-enough-for-hs256",
        algorithm="HS256",
    )


def _make_provider() -> CitedOAuthProvider:
    return CitedOAuthProvider(
        backend_url="https://api.youcited.com",
        mcp_url="https://mcp.youcited.com",
        jwt_secret="test-secret-key-long-enough-for-hs256",
    )


def _make_client(client_id: str = "client-123") -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id=client_id,
        client_id_issued_at=int(time.time()),
        redirect_uris=[AnyUrl("http://localhost:12345")],
        token_endpoint_auth_method="none",
    )


class TestUserJwtExpired:
    def test_valid_jwt(self):
        assert _user_jwt_expired(_make_jwt(3600)) is False

    def test_expired_jwt(self):
        assert _user_jwt_expired(_make_jwt(-60)) is True

    def test_malformed_token(self):
        assert _user_jwt_expired("not-a-jwt") is True

    def test_empty_token(self):
        assert _user_jwt_expired("") is True


class TestLoadAccessToken:
    def test_rejects_expired_user_jwt(self):
        provider = _make_provider()
        now = int(time.time())
        token = provider._encode_token({
            "typ": "access",
            "sub": "client-123",
            "scopes": ["cited"],
            "user_jwt": _make_jwt(-60),  # expired backend JWT
            "exp": now + 3600,
            "iat": now,
        })

        result = run(provider.load_access_token(token))
        assert result is None

    def test_accepts_valid_user_jwt(self):
        provider = _make_provider()
        valid_jwt = _make_jwt(3600)
        now = int(time.time())
        token = provider._encode_token({
            "typ": "access",
            "sub": "client-123",
            "scopes": ["cited"],
            "user_jwt": valid_jwt,
            "exp": now + 3600,
            "iat": now,
        })

        result = run(provider.load_access_token(token))
        assert result is not None
        assert result.user_jwt == valid_jwt


class TestLoadRefreshToken:
    def test_rejects_expired_user_jwt(self):
        provider = _make_provider()
        client = _make_client()
        now = int(time.time())
        token = provider._encode_token({
            "typ": "refresh",
            "sub": client.client_id,
            "scopes": ["cited"],
            "user_jwt": _make_jwt(-60),  # expired backend JWT
            "exp": now + 86400,
            "iat": now,
        })

        result = run(provider.load_refresh_token(client, token))
        assert result is None

    def test_accepts_valid_user_jwt(self):
        provider = _make_provider()
        client = _make_client()
        valid_jwt = _make_jwt(3600)
        now = int(time.time())
        token = provider._encode_token({
            "typ": "refresh",
            "sub": client.client_id,
            "scopes": ["cited"],
            "user_jwt": valid_jwt,
            "exp": now + 86400,
            "iat": now,
        })

        result = run(provider.load_refresh_token(client, token))
        assert result is not None
        assert result.user_jwt == valid_jwt
