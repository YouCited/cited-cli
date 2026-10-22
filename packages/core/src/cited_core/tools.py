"""Cited's agent tools, called over the API.

The tools are defined once, in the Cited API: ``GET /agent/tools`` lists them
(names, schemas, annotations) and ``POST /agent/tools/{name}`` runs one. The
hosted MCP server at mcp.youcited.com serves the same tools. The ``cited`` CLI
and the ``cited-mcp`` server are thin clients of these endpoints, so a tool
behaves the same everywhere.

``tools.json`` next to this file is a snapshot of the manifest, used when the
API can't be reached at startup. ``scripts/sync_tools_manifest.py`` refreshes
it from the API.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

import httpx

from cited_core.api.client import CitedClient
from cited_core.auth.store import TokenStore

TOOLS_PATH = "/agent/tools"
# Long enough for the slowest tool call (a free audit start waits on the
# site check), which the API caps below a minute.
TOOL_TIMEOUT = 120.0
MANIFEST_TIMEOUT = 5.0


def bundled_manifest() -> dict[str, Any]:
    """The manifest snapshot shipped with this package."""
    text = resources.files("cited_core").joinpath("tools.json").read_text("utf-8")
    data: dict[str, Any] = json.loads(text)
    return data


def fetch_manifest(client: CitedClient) -> dict[str, Any]:
    """The API's current manifest, or the bundled snapshot when it can't be fetched."""
    try:
        data = client.get(TOOLS_PATH, timeout=MANIFEST_TIMEOUT)
    except Exception:
        return bundled_manifest()
    if isinstance(data, dict) and isinstance(data.get("tools"), list) and data["tools"]:
        return data
    return bundled_manifest()


def tool_names(manifest: dict[str, Any] | None = None) -> list[str]:
    return [t["name"] for t in (manifest or bundled_manifest())["tools"]]


def _error_body(response: httpx.Response) -> dict[str, Any]:
    """A tool error in the tools' own shape: ``{"error", "status_code", ...}``.

    Tool failures already come that way; errors from the API before the tool
    ran (a bad key, the rate limiter) are turned into it.
    """
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and "error" in body and isinstance(body["error"], str):
        return {**body, "status_code": response.status_code}
    message = f"Request failed (HTTP {response.status_code})"
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, str):
        message = detail
    elif isinstance(detail, dict):
        message = str(detail.get("message") or detail.get("error") or message)
    elif isinstance(body, dict) and body.get("message"):
        message = str(body["message"])
    result: dict[str, Any] = {"error": message, "status_code": response.status_code}
    if response.status_code == 401:
        result["error_type"] = "login_required"
    return result


def call_tool(
    client: CitedClient, name: str, arguments: dict[str, Any] | None = None
) -> tuple[dict[str, Any], int]:
    """Run one tool. Returns ``(result, http_status)``; never raises for API errors."""
    try:
        response = client.post_raw(
            f"{TOOLS_PATH}/{name}", json=arguments or {}, timeout=TOOL_TIMEOUT
        )
    except httpx.HTTPError as e:
        return {"error": f"Could not reach the Cited API: {e}", "status_code": 503}, 503
    client._record_notice(response)
    if not response.is_success:
        body = _error_body(response)
        return body, response.status_code
    try:
        data = response.json()
    except ValueError:
        data = {"text": response.text}
    return (data if isinstance(data, dict) else {"result": data}), response.status_code


def keep_agent_key(
    client: CitedClient, env: str, result: dict[str, Any], store: TokenStore | None = None
) -> dict[str, Any]:
    """After agent_signup: save the new key, use it, and drop it from the result.

    The key is shown once and only this machine needs it, so it is stored with
    the other credentials and never printed or handed to the model.
    """
    api_key = result.get("api_key")
    if not api_key:
        return result
    (store or TokenStore()).save_agent_key(env, str(api_key))
    client.set_agent_api_key(str(api_key))
    out = {k: v for k, v in result.items() if k != "api_key"}
    out["api_key_saved"] = True
    steps = out.get("next_steps")
    if isinstance(steps, list) and steps and "api_key" in str(steps[0]):
        out["next_steps"] = [
            "The API key is saved on this machine and used for every call.",
            *steps[1:],
        ]
    return out


def run_tool(
    client: CitedClient,
    env: str,
    name: str,
    arguments: dict[str, Any] | None = None,
    store: TokenStore | None = None,
) -> tuple[dict[str, Any], int]:
    """``call_tool`` plus what a local client does with the result."""
    result, status = call_tool(client, name, arguments)
    if name == "agent_signup" and status < 400:
        result = keep_agent_key(client, env, result, store)
    return result, status
