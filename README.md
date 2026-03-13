# Cited CLI

Command-line interface for the [Cited](https://youcited.com) GEO (Generative Engine Optimization) platform.

## Installation

### From source (development)

```bash
git clone https://github.com/AdvantageGEOadmin/homebrew-cited.git
cd homebrew-cited
pip install -e ".[dev]"
```

### Homebrew (coming soon)

```bash
brew tap cited/tap
brew install cited
```

## Quick Start

```bash
# Log in
cited auth login

# Check connection
cited status

# List businesses
cited business list

# Run an audit
cited audit start <business-id>

# Watch job progress
cited job watch <job-id>

# Get results
cited audit result <job-id>
```

## Global Flags

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | JSON output (agent-friendly) |
| `--env` | `-e` | Target environment: dev, prod, local |
| `--profile` | `-p` | Config profile |
| `--verbose` | `-v` | Debug logging |
| `--quiet` | `-q` | Minimal output |
| `--no-color` | | Disable colors |

## Commands

```
cited auth login|logout|status|token
cited config set|get|show|environments
cited business list|get|create|update|delete|health|crawl
cited audit start|status|result|list|export
cited recommend start|status|result|list
cited solution start|status|result|list
cited hq <business_id> [--full] [--personas] [--products]
cited analytics compare|trends|summary
cited agent facts|claims|comparison|semantic-health|buyer-fit
cited job watch|cancel
cited status
cited version
```

## Configuration

Config is stored in `~/.cited/config.toml`:

```bash
# Set default environment
cited config set environment dev

# Set default business
cited config set default_business_id <uuid>

# Set agent API key
cited config set agent_api_key <key>
```

## JSON Output

All commands support `--json` for structured output:

```bash
cited --json business list | jq '.[].name'
cited --json audit result <id> > audit.json
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Authentication error |
| 3 | Not found |
| 4 | Validation error |
| 5 | Rate limited |

## Development

```bash
pip install -e ".[dev]"
pytest -v
ruff check src/
mypy src/cited_cli/
```
