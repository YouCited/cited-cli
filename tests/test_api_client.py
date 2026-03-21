from __future__ import annotations

import json

import httpx
import pytest
import respx

from cited_core.api.client import CitedClient
from cited_core.errors import CitedAPIError


@respx.mock
def test_get_success():
    respx.get("https://api.example.com/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )
    client = CitedClient(base_url="https://api.example.com")
    result = client.get("/health")
    assert result == {"status": "ok"}
    client.close()


@respx.mock
def test_get_404():
    respx.get("https://api.example.com/missing").mock(
        return_value=httpx.Response(404, json={"detail": "Not found"})
    )
    client = CitedClient(base_url="https://api.example.com")
    with pytest.raises(CitedAPIError) as exc_info:
        client.get("/missing")
    assert exc_info.value.status_code == 404
    assert "Not found" in exc_info.value.message
    client.close()


@respx.mock
def test_post_with_json():
    respx.post("https://api.example.com/data").mock(
        return_value=httpx.Response(200, json={"id": "abc"})
    )
    client = CitedClient(base_url="https://api.example.com")
    result = client.post("/data", json={"name": "test"})
    assert result == {"id": "abc"}
    client.close()


@respx.mock
def test_auth_cookie_sent():
    route = respx.get("https://api.example.com/auth/me").mock(
        return_value=httpx.Response(200, json={"email": "test@example.com"})
    )
    client = CitedClient(base_url="https://api.example.com", token="my-jwt-token")
    client.get("/auth/me")
    assert route.called
    request = route.calls[0].request
    assert "advgeo_session=my-jwt-token" in request.headers.get("cookie", "")
    client.close()


@respx.mock
def test_agent_api_key_header():
    route = respx.get("https://api.example.com/agent/v1/business/123/facts").mock(
        return_value=httpx.Response(200, json={"facts": []})
    )
    client = CitedClient(base_url="https://api.example.com", agent_api_key="test-key")
    client.get("/agent/v1/business/123/facts")
    assert route.called
    request = route.calls[0].request
    assert request.headers["x-agent-api-key"] == "test-key"
    client.close()


@respx.mock
def test_context_manager():
    respx.get("https://api.example.com/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )
    with CitedClient(base_url="https://api.example.com") as client:
        result = client.get("/health")
        assert result["status"] == "ok"
