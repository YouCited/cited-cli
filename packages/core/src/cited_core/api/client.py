from __future__ import annotations

import contextvars
import os
from typing import Any

import httpx

from cited_core import __version__
from cited_core.errors import CitedAPIError

DEFAULT_TIMEOUT = 30.0
LONG_TIMEOUT = 120.0

AGENT_KEY_HEADER = "X-Agent-API-Key"
NOTICE_HEADER = "X-Cited-Notice"
# Appended to the User-Agent; the live tests set it to "cited-ci" so their
# traffic can be told apart from real use.
USER_AGENT_TAG_ENV_VAR = "CITED_USER_AGENT_TAG"

# The most recent X-Cited-Notice the API sent in the current context (task or
# thread). The MCP tool wrapper clears it before each tool call and copies it
# into the tool result afterwards, so every tool surfaces it without per-tool
# code. A ContextVar (not only an attribute) because the remote MCP server
# builds a fresh client per request.
_last_notice: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "cited_last_notice", default=None
)


def get_notice() -> str | None:
    """Return the last X-Cited-Notice seen in this context, if any."""
    return _last_notice.get()


def clear_notice() -> None:
    """Forget any X-Cited-Notice seen in this context."""
    _last_notice.set(None)


def _origin(url: httpx.URL) -> tuple[str, str, int | None]:
    return (url.scheme, url.host, url.port)


class CitedClient:
    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        agent_api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.agent_api_key = agent_api_key
        self.last_notice: str | None = None
        user_agent = f"cited/{__version__}"
        if tag := os.environ.get(USER_AGENT_TAG_ENV_VAR):
            user_agent = f"{user_agent} {tag}"
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": user_agent,
        }
        cookies: dict[str, str] = {}
        if token:
            cookies["advgeo_session"] = token
        # A per-user agent key authenticates every request. A signed-in
        # session cookie takes precedence: the key is only sent when there is
        # no token.
        if agent_api_key and not token:
            headers[AGENT_KEY_HEADER] = agent_api_key
        self._origin = _origin(httpx.URL(self.base_url))
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            cookies=cookies,
            timeout=timeout,
            follow_redirects=True,
            event_hooks={"request": [self._strip_credentials_off_origin]},
        )

    def _strip_credentials_off_origin(self, request: httpx.Request) -> None:
        """A redirect to another host must not carry the session or agent key."""
        if _origin(request.url) != self._origin:
            request.headers.pop("Cookie", None)
            request.headers.pop(AGENT_KEY_HEADER, None)

    def close(self) -> None:
        self._client.close()

    @property
    def auth_method(self) -> str | None:
        """``"token"`` (session cookie), ``"agent_key"``, or None."""
        if self.token:
            return "token"
        if self.agent_api_key:
            return "agent_key"
        return None

    def set_token(self, token: str | None) -> None:
        """Use (or clear) a session token; a token overrides any agent key."""
        self.token = token
        if token:
            self._client.cookies.set("advgeo_session", token)
            self._client.headers.pop(AGENT_KEY_HEADER, None)
        else:
            self._client.cookies.delete("advgeo_session")
            if self.agent_api_key:
                self._client.headers[AGENT_KEY_HEADER] = self.agent_api_key

    def set_agent_api_key(self, agent_api_key: str | None) -> None:
        """Use (or clear) a per-user agent key. Ignored on the wire while a token is set."""
        self.agent_api_key = agent_api_key
        if agent_api_key and not self.token:
            self._client.headers[AGENT_KEY_HEADER] = agent_api_key
        else:
            self._client.headers.pop(AGENT_KEY_HEADER, None)

    def set_request_id(self, request_id: str | None) -> None:
        """Stamp X-Request-ID on subsequent outgoing requests so the cited
        backend can echo it in its access logs and produce end-to-end traces.
        Pass None to clear."""
        if request_id:
            self._client.headers["X-Request-ID"] = request_id
        else:
            self._client.headers.pop("X-Request-ID", None)

    def __enter__(self) -> CitedClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _record_notice(self, response: httpx.Response) -> None:
        notice = response.headers.get(NOTICE_HEADER)
        if notice:
            self.last_notice = notice
            _last_notice.set(notice)

    def _handle_response(self, response: httpx.Response) -> Any:
        self._record_notice(response)
        if response.is_success:
            if response.headers.get("content-type", "").startswith("application/json"):
                return response.json()
            return response.text
        # Try to extract error message from JSON body
        message = f"HTTP {response.status_code}"
        error_code = None
        detail_obj: dict[str, Any] | None = None
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = body.get("detail", body.get("message", message))
                if isinstance(detail, dict):
                    # Structured error, e.g. {"error": "insufficient_credits",
                    # "message": ..., "credits_needed": ..., "buy_url": ...}
                    detail_obj = detail
                    message = str(detail.get("message") or detail.get("error") or message)
                    error_code = detail.get("error") or body.get("error_code")
                else:
                    message = str(detail)
                    error_code = body.get("error_code")
        except Exception:
            message = response.text or message
        raise CitedAPIError(response.status_code, str(message), error_code, detail_obj)

    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        kwargs: dict[str, Any] = {"params": params}
        if timeout is not None:
            kwargs["timeout"] = timeout
        response = self._client.get(path, **kwargs)
        return self._handle_response(response)

    def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        kwargs: dict[str, Any] = {}
        if json is not None:
            kwargs["json"] = json
        if data is not None:
            kwargs["data"] = data
        if timeout is not None:
            kwargs["timeout"] = timeout
        response = self._client.post(path, **kwargs)
        return self._handle_response(response)

    def put(self, path: str, json: dict[str, Any] | None = None) -> Any:
        response = self._client.put(path, json=json or {})
        return self._handle_response(response)

    def patch(self, path: str, json: dict[str, Any] | None = None) -> Any:
        response = self._client.patch(path, json=json or {})
        return self._handle_response(response)

    def delete(self, path: str) -> Any:
        response = self._client.delete(path)
        return self._handle_response(response)

    def post_raw(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """POST that returns the raw httpx.Response (for cookie extraction, etc.)."""
        kwargs: dict[str, Any] = {}
        if json is not None:
            kwargs["json"] = json
        if timeout is not None:
            kwargs["timeout"] = timeout
        return self._client.post(path, **kwargs)
