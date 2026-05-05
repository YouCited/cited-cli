from __future__ import annotations

from typing import Any

import httpx

from cited_core.errors import CitedAPIError

DEFAULT_TIMEOUT = 30.0
LONG_TIMEOUT = 120.0


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
        headers: dict[str, str] = {
            "Accept": "application/json",
        }
        cookies: dict[str, str] = {}
        if token:
            cookies["advgeo_session"] = token
        if agent_api_key:
            headers["X-Agent-API-Key"] = agent_api_key
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            cookies=cookies,
            timeout=timeout,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

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

    def _handle_response(self, response: httpx.Response) -> Any:
        if response.is_success:
            if response.headers.get("content-type", "").startswith("application/json"):
                return response.json()
            return response.text
        # Try to extract error message from JSON body
        message = f"HTTP {response.status_code}"
        error_code = None
        try:
            body = response.json()
            if isinstance(body, dict):
                message = str(body.get("detail", body.get("message", message)))
                error_code = body.get("error_code")
        except Exception:
            message = response.text or message
        raise CitedAPIError(response.status_code, str(message), error_code)

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = self._client.get(path, params=params)
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
