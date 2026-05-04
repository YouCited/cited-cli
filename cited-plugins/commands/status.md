---
name: status
description: Quick status check — auth, businesses, and recent activity
user_invocable: true
---

Perform a quick status check of the user's Cited account:

1. Call `ping`. Stash the `tools_fingerprint` and `server_version` from the response for the rest of this conversation.
   - **First run this conversation:** stash the values and proceed.
   - **Later run, fingerprint matches the stashed value:** nothing changed, proceed.
   - **Later run, fingerprint differs:** the server's tool surface changed mid-conversation (a Cited release landed). Call `whats_new(since_fingerprint=<previous_fingerprint>, since_version=<previous_version>)` — this is the primary path, not best-effort — and surface its response to the user before continuing. The response shape determines what to surface:
     - **Normal diff** — render `tools_added`, `tools_changed`, `tools_removed`. Each item carries `added_in_version` / `changed_in_version` / `removed_in_version`. If a top-level `_note` is present (e.g. the prior fingerprint predates the changelog), include it verbatim so the user knows the diff is unbounded.
     - **`{"no_changes": true}`** — say "tool surface unchanged since last check" and move on.
     - **`{"error": true, "error_type": "changelog_unavailable"}`** — surface the response's `message` field verbatim. The server is healthy but can't compute a diff right now; ping and the rest of the skill still work.
     - **`{"error": true, "error_type": "tool_unavailable"}`** — only fires against a pre-0.3.5 server where `whats_new` isn't registered. Fall back to: "The MCP tool surface has changed since you connected. Disconnect and reconnect the Cited connector in your Claude Desktop / Claude.ai connector settings to pick up the latest tools."
2. Call `check_auth_status` to verify authentication and show the logged-in user.
3. Call `list_businesses` to show all businesses.
4. Call `list_audits` to show recent audit activity.

Present a concise summary of the user's current state on the Cited platform.

For ad-hoc tool exploration beyond the standard audit flow — diagnostics, deltas, intel without re-running an audit, one-off probes — see `cited:explore`.
