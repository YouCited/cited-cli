# Future Enhancements

## v2 Auth: Dedicated CLI Login Endpoints

The current CLI extracts the JWT from the `Set-Cookie: advgeo_session` header on `POST /auth/login`. This works but is fragile — it depends on cookie parsing and breaks if the backend changes cookie settings. These enhancements require backend changes in the `cited` monorepo (`backend/routes/auth.py`).

### 1. `POST /auth/cli-login`

A new endpoint that returns the JWT directly in the response body instead of as a cookie.

**Backend (new route in `backend/routes/auth.py`):**
```python
@router.post("/auth/cli-login")
async def cli_login(credentials: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login endpoint for CLI clients. Returns JWT in response body."""
    user = await auth_service.authenticate(db, credentials.email, credentials.password)
    token = auth_service.create_token(user)
    return {"token": token, "user": {"email": user.email, "name": user.name}}
```

**CLI changes (`src/cited_cli/commands/auth.py`):**
- Try `POST /auth/cli-login` first
- Extract token from `response.json()["token"]` — no cookie parsing needed
- Fall back to `POST /auth/login` + cookie extraction for older backends

**Add endpoint constant (`src/cited_cli/api/endpoints.py`):**
```python
CLI_LOGIN = "/auth/cli-login"
```

### 2. `POST /auth/cli-oauth-start` (browser-based login)

Enables `cited auth login --browser` which opens the user's browser for Google/Microsoft/GitHub OAuth, with a localhost callback to receive the token.

**Flow:**
1. CLI starts a temporary HTTP server on `http://localhost:<port>/callback`
2. CLI calls `POST /auth/cli-oauth-start` with `{"redirect_uri": "http://localhost:<port>/callback", "provider": "google"}`
3. Backend returns `{"auth_url": "https://accounts.google.com/o/oauth2/..."}`
4. CLI opens `auth_url` in the user's default browser
5. User completes OAuth in browser
6. Backend redirects to `http://localhost:<port>/callback?token=<jwt>`
7. CLI's local server receives the token, stores it, shuts down

**Backend (new route in `backend/routes/auth.py`):**
```python
@router.post("/auth/cli-oauth-start")
async def cli_oauth_start(request: CLIOAuthRequest):
    """Start OAuth flow for CLI. Returns auth URL with localhost redirect."""
    # Validate redirect_uri starts with http://localhost
    if not request.redirect_uri.startswith("http://localhost"):
        raise HTTPException(400, "redirect_uri must be localhost")
    auth_url = oauth_service.get_auth_url(
        provider=request.provider,
        redirect_uri=request.redirect_uri,
    )
    return {"auth_url": auth_url}
```

**Backend: OAuth callback modification (`backend/routes/auth.py`):**
The existing OAuth callbacks (`/auth/callback`, `/auth/microsoft/callback`, `/auth/github/callback`) need to detect localhost redirect URIs and append the JWT as a query parameter instead of setting a cookie:
```python
if redirect_uri.startswith("http://localhost"):
    return RedirectResponse(f"{redirect_uri}?token={jwt}")
```

**Backend: Allow localhost redirect URIs:**
Update OAuth provider configurations (Google, Microsoft, GitHub) to permit `http://localhost:*` as valid redirect URIs. Google's OAuth already allows localhost for "Desktop" app types. Microsoft and GitHub may need explicit configuration in their respective app registrations.

**CLI changes (`src/cited_cli/commands/auth.py`):**
```python
@auth_app.command()
def login(ctx, ..., browser: bool = False, provider: str = "google"):
    if browser:
        _browser_login(ctx, provider)
    else:
        _password_login(ctx, email, password)

def _browser_login(ctx, provider):
    # 1. Find free port, start local HTTP server
    # 2. POST /auth/cli-oauth-start with redirect_uri
    # 3. webbrowser.open(auth_url)
    # 4. Wait for callback with token
    # 5. Store token
```

**Dependencies to add:** None — Python stdlib has `http.server`, `webbrowser`, and `socket` for finding free ports.

---

## MCP Integration: `cited mcp serve`

Expose CLI commands as [Model Context Protocol](https://modelcontextprotocol.io/) tools, making the Cited platform directly callable from Claude Code, Cursor, Windsurf, and other MCP-compatible agents.

### What it does

`cited mcp serve` starts a stdio-based MCP server that exposes each CLI command as a tool. An AI agent can then call tools like `cited_business_list`, `cited_audit_start`, `cited_hq` directly without shelling out.

### Implementation

**New command (`src/cited_cli/commands/mcp.py`):**
```python
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server

mcp_app = typer.Typer(name="mcp", help="MCP server for AI agent integration.")

@mcp_app.command("serve")
def mcp_serve(ctx: typer.Context):
    """Start MCP server exposing CLI commands as tools."""
    server = Server("cited-cli")

    @server.list_tools()
    async def list_tools():
        return [
            Tool(name="cited_status", description="Check API health", inputSchema={...}),
            Tool(name="cited_business_list", description="List businesses", inputSchema={...}),
            Tool(name="cited_audit_start", description="Start audit", inputSchema={...}),
            # ... one tool per CLI command
        ]

    @server.call_tool()
    async def call_tool(name, arguments):
        # Route to the appropriate API client call
        # Always return JSON (same as --json mode)
        ...

    asyncio.run(stdio_server(server))
```

**New dependency:**
```toml
# pyproject.toml
dependencies = [
    ...,
    "mcp>=1.0.0",
]
```

**Register in app.py:**
```python
from cited_cli.commands.mcp import mcp_app
app.add_typer(mcp_app, name="mcp")
```

### User configuration

Users add the server to their MCP client config. For Claude Code (`.claude/settings.json`):
```json
{
  "mcpServers": {
    "cited": {
      "command": "cited",
      "args": ["mcp", "serve", "--env", "dev"]
    }
  }
}
```

### Tools to expose

Priority tools for agent use (all return JSON):

| Tool | Maps to | Description |
|------|---------|-------------|
| `cited_status` | `cited status` | API health check |
| `cited_business_list` | `cited business list` | List businesses |
| `cited_business_get` | `cited business get` | Business details |
| `cited_business_health` | `cited business health` | Health scores |
| `cited_business_crawl` | `cited business crawl` | Trigger crawl |
| `cited_audit_start` | `cited audit start` | Start audit |
| `cited_audit_status` | `cited audit status` | Job status |
| `cited_audit_result` | `cited audit result` | Audit results |
| `cited_recommend_start` | `cited recommend start` | Generate recommendations |
| `cited_recommend_result` | `cited recommend result` | Recommendation results |
| `cited_solution_start` | `cited solution start` | Generate solution |
| `cited_solution_result` | `cited solution result` | Solution results |
| `cited_hq` | `cited hq` | Business HQ dashboard |
| `cited_analytics_trends` | `cited analytics trends` | KPI trends |
| `cited_agent_facts` | `cited agent facts` | Business facts |
| `cited_agent_claims` | `cited agent claims` | Verifiable claims |
| `cited_agent_buyer_fit` | `cited agent buyer-fit` | Buyer-fit simulation |

### Design notes

- The MCP server reuses the same `CitedClient` and auth from the CLI — no separate auth flow needed
- All tool responses are JSON (equivalent to `--json` mode)
- The server inherits `--env` and `--profile` from the `cited mcp serve` invocation
- Long-running operations (audit, recommend, solution) should return the job ID immediately, letting the agent poll status separately
