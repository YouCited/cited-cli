---
name: status
description: Quick status check — auth, businesses, and recent activity
user_invocable: true
---

Perform a quick status check of the user's Cited account:

1. Call `ping` first. Note the `tools_fingerprint` and `server_version` in the response — keep them in mind for the rest of this conversation.
   - **If you ran this skill earlier in this conversation** and the new `tools_fingerprint` differs from the value you stashed, the server's tool surface has changed since the user connected (likely a Cited release). Call `whats_new(since_fingerprint=<previous>)` and surface the additions, removals, and changed tools to the user before continuing. If `whats_new` returns a `tool_unavailable` error, fall back to telling the user: "The MCP tool surface has changed. Disconnect and reconnect the Cited connector in your Claude Desktop / Claude.ai connector settings to pick up the latest tools."
   - **If this is your first run in the conversation,** just stash the fingerprint and proceed.
2. Call `check_auth_status` to verify authentication and show the logged-in user.
3. Call `list_businesses` to show all businesses.
4. Call `list_audits` to show recent audit activity.

Present a concise summary of the user's current state on the Cited platform.
