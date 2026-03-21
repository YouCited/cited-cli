# Setting Up Cited for Claude Desktop

This guide walks you through connecting Claude Desktop to the Cited GEO platform. Once set up, you can ask Claude to audit your business's AI search presence, generate recommendations, and create solutions — all through conversation.

## What You Need

- **Claude Desktop** app installed
- **A Cited account** at [youcited.com](https://youcited.com)
- **Node.js** installed (download from [nodejs.org](https://nodejs.org))

## Step 1: Configure Claude Desktop

1. Open Claude Desktop
2. Click the **Claude** menu (top-left on Mac, top bar on Windows)
3. Click **Settings**
4. Click **Developer** in the left sidebar
5. Click **Edit Config**

This opens `claude_desktop_config.json`. Add the `mcpServers` section:

```json
{
  "mcpServers": {
    "cited": {
      "command": "npx",
      "args": ["mcp-remote", "https://mcp.youcited.com"]
    }
  }
}
```

Save the file and close the text editor.

## Step 2: Restart Claude Desktop

Quit Claude Desktop completely (Cmd+Q on Mac, or close fully on Windows), then reopen it.

## Step 3: Try It Out

Start a new conversation in Claude Desktop and try any of these:

- **"List my businesses"** — shows all your businesses on Cited
- **"Run a GEO audit on [business name]"** — audits your AI search presence
- **"Check my Cited account status"** — verifies you're connected

On first use, your browser will open to log in to your Cited account. After logging in, you'll be redirected back automatically. This only happens once.

## Troubleshooting

**Browser login popup doesn't appear:**
- Make sure Node.js is installed: open a terminal and type `node --version`
- Make sure you saved the config file correctly
- Restart Claude Desktop fully (not just close the window)

**"npx not found" error:**
- Install Node.js from [nodejs.org](https://nodejs.org) (LTS version recommended)
- Restart Claude Desktop after installing Node.js

## What Can Claude Do With Cited?

Once connected, Claude can:

- **List and manage your businesses** — view, create, update, or delete businesses
- **Run GEO audits** — check how your business appears in AI search results (ChatGPT, Perplexity, Gemini, etc.)
- **Generate recommendations** — get actionable insights to improve your AI search visibility
- **Create solutions** — detailed implementation steps for each recommendation
- **Check health scores** — see your overall GEO health at a glance

Just ask Claude in plain English — no commands to memorize.
