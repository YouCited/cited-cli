# Cited plugin for ChatGPT

Submission package for the ChatGPT plugin directory: `plugin.json` (listing, review test cases, publication), `mcp.json` (the hosted server at `https://mcp.youcited.com/mcp`, OAuth through discovery and dynamic client registration), the onboarding skill and the icons.

Build the ZIP from this folder, then upload it at https://platform.openai.com/plugins:

```bash
cd chatgpt-plugin && zip -r ../cited-chatgpt-plugin.zip . -x README.md
```

Before submitting, add `"demo_recording_url": "<video URL>"` under `review` in `plugin.json` and enter the reviewer test account in the portal (never in this package).

`get_audit` and `free_audit` results show as a report card in ChatGPT (the MCP Apps standard). The card is served by the hosted server (`backend/services/mcp_apps/` in YouCited/cited), so nothing in this package changes when the card does.
