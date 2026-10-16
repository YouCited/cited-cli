"""Agent identity: self-serve agent signup and per-user agent API keys.

An agent with no Cited account calls ``agent_signup`` to get its own key
(sent as ``X-Agent-API-Key``) on an unclaimed account, then hands its human a
claim link and code so the account moves into theirs.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from cited_core.api import endpoints
from cited_core.auth.store import TokenStore
from cited_core.errors import CitedAPIError
from cited_mcp.context import CitedContext
from cited_mcp.server import mcp
from cited_mcp.tools._helpers import (
    _api_error_response,
    _auth_check,
    _get_ctx,
    _has_agent_key,
    log_tool_call,
)


def _has_remote_session() -> bool:
    """True when this call is authenticated through the hosted MCP's OAuth."""
    try:
        from mcp.server.auth.middleware.auth_context import get_access_token
    except ImportError:
        return False
    try:
        return get_access_token() is not None
    except Exception:
        return False


@mcp.tool(
    title="Agent Signup",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),  # noqa: E501
)
@log_tool_call
async def agent_signup(
    ctx: Context[Any, CitedContext, Any],
    agent_name: str | None = None,
    owner_email: str | None = None,
) -> Any:
    """Create a Cited account for this agent and start using its own API key. No login needed.

    Use this when you have no Cited credentials and the human has not signed
    in. The new account is unclaimed: 1 business and 1 audit, paid per audit
    with buy_audit ($15), and deleted 7 days after signup unless a person
    claims it. The API key is saved on this machine and used for every
    following call, now and in later sessions.

    You MUST show the human ``claim.url`` and the 6-digit ``claim.code``
    and ask them to open the link, sign in or create an account, and enter
    the code. Claiming moves everything into their account. If you pass
    owner_email the link is emailed to them too, but the code is not, so
    still give them the code.

    Returns ``claim`` {url, code, expires_at}, ``account`` {unclaimed,
    expires_at, limits}, ``key_prefix``, ``oauth`` and ``next_steps``.

    Args:
        ctx: MCP context
        agent_name: Optional name for this agent, shown to the human when claiming
        owner_email: Optional email of the human who will claim the account
    """
    lc: CitedContext = ctx.request_context.lifespan_context
    if lc.client.token or _has_remote_session():
        return {
            "error": True,
            "error_type": "already_authenticated",
            "message": (
                "Already signed in as a person, so no agent key is needed. Agent signup "
                "is for agents without an account."
            ),
        }
    if _has_agent_key(lc):
        return {
            "error": True,
            "error_type": "already_has_agent_key",
            "message": "This server already uses an agent key. Call key_status to see it.",
        }

    payload: dict[str, str] = {}
    if agent_name:
        payload["agent_name"] = agent_name
    if owner_email:
        payload["owner_email"] = owner_email
    try:
        data = lc.client.post(endpoints.AGENT_SIGNUP, json=payload)
    except CitedAPIError as e:
        return _api_error_response(e)

    if not isinstance(data, dict) or not data.get("api_key"):
        return {"error": True, "message": "Signup response had no api_key.", "response": data}

    api_key = str(data.pop("api_key"))
    lc.client.set_agent_api_key(api_key)
    result: dict[str, Any] = dict(data)
    try:
        TokenStore().save_agent_key(lc.env, api_key)
        result["api_key_saved"] = True
    except Exception:
        # Could not persist (no keychain and no writable home): hand the key
        # over so it isn't lost. It works for the rest of this session anyway.
        result["api_key_saved"] = False
        result["api_key"] = api_key
        result["warning"] = (
            "The key could not be saved on this machine. Ask the human to store it "
            "(e.g. CITED_AGENT_API_KEY); it is shown only once."
        )

    claim = data.get("claim") or {}
    result["instructions"] = (
        f"Show the human this claim link: {claim.get('url', '')} and this code: "
        f"{claim.get('code', '')}. Ask them to open the link, sign in or create an "
        f"account, and enter the code before {claim.get('expires_at', 'it expires')}. "
        "Until then the account can hold 1 business and run 1 audit, paid with buy_audit."
    )
    return result


@mcp.tool(
    title="Agent Key Status",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def key_status(ctx: Context[Any, CitedContext, Any]) -> Any:
    """Show the state of the agent API key this server uses.

    Returns ``key_prefix``, ``unclaimed``, ``account_expires_at`` (when an
    unclaimed account is deleted), ``key_expires_at`` (keys expire 90 days
    after the account is claimed), ``days_left``, ``notice`` and ``oauth``
    {mcp_url, instructions}. When a key has an expiry, tell the human and
    suggest connecting the hosted MCP with OAuth, which does not expire.
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.get(endpoints.AGENT_KEY_STATUS)
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="List API Keys",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def list_api_keys(ctx: Context[Any, CitedContext, Any]) -> Any:
    """List the account's agent API keys.

    Returns ``keys`` [{id, key_prefix, label, created_at, last_used_at,
    expires_at, revoked_at, status: active|expired|revoked}]. Full keys are
    never shown again after signup.
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.get(endpoints.AGENT_KEYS)
    except CitedAPIError as e:
        return _api_error_response(e)


@mcp.tool(
    title="Revoke API Key",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False),  # noqa: E501
)
@log_tool_call
async def revoke_api_key(ctx: Context[Any, CitedContext, Any], key_id: str) -> Any:
    """Revoke an agent API key. Any agent using it loses access immediately.

    Only call this when the human asked to revoke that key. Revoking the key
    this server itself uses ends its access.

    Args:
        ctx: MCP context
        key_id: Key ID from list_api_keys
    """
    cited_ctx = _get_ctx(ctx)
    if err := _auth_check(cited_ctx):
        return err
    try:
        return cited_ctx.client.delete(endpoints.AGENT_KEY.format(key_id=key_id))
    except CitedAPIError as e:
        return _api_error_response(e)
