# Future Enhancements

## Shell Completions: `cited completions`

Generate shell completion scripts for bash, zsh, and fish. Typer has built-in support for this but it needs to be exposed as a command.

```bash
# Generate and install completions
cited completions zsh > ~/.zfunc/_cited
cited completions bash > /etc/bash_completion.d/cited
cited completions fish > ~/.config/fish/completions/cited.fish
```

Typer provides this via `typer.main.get_command(app).get_help()` and Click's shell completion utilities.

---

## Batch Operations

### `cited audit batch`

Run multiple audit templates in sequence or parallel, collecting results into a single report.

```bash
# Run all templates for a business
cited audit batch --business $BID --all

# Run specific templates
cited audit batch --business $BID --template $T1 --template $T2

# Export combined results
cited audit batch --business $BID --all --export results.json
```

### `cited business import`

Bulk-create businesses from a CSV or JSON file for agencies managing multiple clients.

```bash
cited business import clients.csv
cited business import --format json clients.json
```

---

## Diff and History

### `cited audit diff`

Compare two audit runs side-by-side to show citation changes over time.

```bash
cited audit diff $JOB_ID_1 $JOB_ID_2
```

Output would show per-question citation deltas (gained/lost citations, score changes) in a Rich table.

### `cited analytics export`

Export historical analytics data to CSV/JSON for external analysis or dashboarding.

```bash
cited analytics export --business $BID --from 2026-01-01 --to 2026-03-20 --format csv > trends.csv
```

---

## Interactive Mode: `cited interactive`

A REPL-style session that keeps auth and business context loaded, reducing repetitive flags:

```bash
$ cited interactive --business $BID --env dev
cited> audit template list
cited> audit start $TEMPLATE_ID
cited> job watch $JOB_ID
cited> recommend start $JOB_ID
```

Would use `prompt_toolkit` for readline-style history, tab completion, and inline help.

---

## Webhooks: `cited webhook`

Register webhook URLs to get notified when jobs complete, instead of polling with `job watch`.

```bash
cited webhook create --event job.completed --url https://example.com/hook
cited webhook list
cited webhook delete $WEBHOOK_ID
```

Requires backend support for webhook delivery.

---

## MCP Server Card (SEP-2127)

Publish a server card at `/.well-known/mcp/server-card.json` to support automatic MCP server discovery. This would advertise the server's capabilities, authentication requirements, and tool catalog to MCP clients.

---

## MCP Code Mode

Inspired by [Cloudflare's Code Mode pattern](https://blog.cloudflare.com/enterprise-mcp/), reduce token consumption by exposing just two tools (`search` and `execute`) instead of all 30 tool definitions. The model discovers available tools via search and executes them by name. Could reduce initial token overhead by ~90% for clients that support it.
