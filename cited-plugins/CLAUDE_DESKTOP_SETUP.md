# Setting Up Cited for Claude Desktop

This guide walks you through connecting Claude Desktop to the Cited GEO platform. Once set up, you can ask Claude to audit your business's AI search presence, generate recommendations, and create solutions — all through conversation.

## What You Need

- **Claude Desktop** app installed on your Mac
- **A Cited account** at [youcited.com](https://youcited.com)
- **uv** (a Python tool runner) — we'll install this in step 1

## Step 1: Install uv

Open the **Terminal** app (search for "Terminal" in Spotlight, or find it in Applications > Utilities).

Copy and paste this command, then press Enter:

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close and reopen Terminal after it finishes.

## Step 2: Get Your Auth Token

You need a session token from the Cited web app. The easiest way is to use the Cited CLI:

```
uvx cited-cli login --env dev
```

This opens your browser. Log in with your Cited account (Google, Microsoft, GitHub, or email). Once you see "Authentication successful", you can close the browser tab.

## Step 3: Configure Claude Desktop

1. Open Claude Desktop
2. Click the **Claude** menu in the top-left corner of your screen
3. Click **Settings**
4. Click **Developer** in the left sidebar
5. Click **Edit Config**

This opens a file called `claude_desktop_config.json`. Replace its entire contents with:

```json
{
  "mcpServers": {
    "cited": {
      "command": "PATH_TO_UVX",
      "args": ["cited-mcp"],
      "env": {
        "CITED_ENV": "dev"
      }
    }
  }
}
```

**Important:** Replace `PATH_TO_UVX` with the actual path to uvx on your machine. To find it, open Terminal and run:

```
which uvx
```

It's usually one of these:
- `/Users/YOUR_USERNAME/.local/bin/uvx` (most common)
- `/opt/homebrew/bin/uvx` (if installed via Homebrew)

Save the file (Command + S) and close the text editor.

## Step 4: Restart Claude Desktop

Quit Claude Desktop completely (Command + Q), then reopen it.

You may see a macOS popup asking to allow Python to access your keychain — click **Always Allow** and enter your Mac password. This lets Claude read your Cited login token.

## Step 5: Try It Out

Start a new conversation in Claude Desktop and try any of these:

- **"List my businesses"** — shows all your businesses on Cited
- **"Run a GEO audit on [business name]"** — audits your AI search presence
- **"Check my Cited account status"** — verifies you're connected

## Troubleshooting

**Claude says "Not authenticated":**
- Open Terminal and run `uvx cited-cli login --env dev` again
- Restart Claude Desktop

**Claude doesn't show Cited tools:**
- Make sure you saved the config file correctly
- Make sure you fully quit and reopened Claude Desktop (not just closed the window)
- Check that uv is installed: open Terminal and type `uvx --version`

**Keychain popup keeps appearing:**
- Click "Always Allow" instead of just "Allow" so it doesn't ask again

## What Can Claude Do With Cited?

Once connected, Claude can:

- **List and manage your businesses** — view, create, update, or delete businesses
- **Run GEO audits** — check how your business appears in AI search results (ChatGPT, Perplexity, Gemini, etc.)
- **Generate recommendations** — get actionable insights to improve your AI search visibility
- **Create solutions** — detailed implementation steps for each recommendation
- **Check health scores** — see your overall GEO health at a glance

Just ask Claude in plain English — no commands to memorize.
