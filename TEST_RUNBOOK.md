# Cited CLI — Test Runbook

Comprehensive test commands organized by workflow stage. Each section builds on the previous one. Replace placeholder IDs with actual values as you go.

## 1. System & Config

```bash
# Verify CLI is installed
cited version
cited --json version

# Check API health (both environments)
cited --env dev status
cited --env prod status
cited --json --env dev status

# Configure default environment
cited config set environment dev
cited config get environment
cited config show
cited config environments
cited --json config environments
```

## 2. Authentication

```bash
# Login (interactive — will prompt for password)
cited auth login --email <your-email>

# Login (non-interactive — scriptable)
cited auth login --email <your-email> --password <your-password>

# Verify session
cited auth status
cited --json auth status

# Extract token (for piping to other tools)
cited auth token
cited auth token | head -c 50   # Verify it's a JWT

# Test wrong credentials (should exit code 2)
cited auth login --email fake@example.com --password wrong; echo "Exit: $?"
```

## 3. Business CRUD

```bash
# List existing businesses
cited business list
cited --json business list

# Create a test business
cited business create --name "CLI Test Corp" --website "https://example.com" --industry "Technology"
# ^^^ Save the returned business ID as $BIZ_ID

# Get business details
cited business get <BIZ_ID>
cited --json business get <BIZ_ID>

# Update business
cited business update <BIZ_ID> --name "CLI Test Corp Updated"
cited business update <BIZ_ID> --website "https://example.org"

# Health scores
cited business health <BIZ_ID>
cited --json business health <BIZ_ID>

# Trigger crawl
cited business crawl <BIZ_ID>
```

## 4. Audit Workflow (full pipeline)

```bash
# Start an audit (use a business that has crawl data)
cited audit start <BIZ_ID>
# ^^^ Save the returned job_id as $AUDIT_JOB

# Watch it run (live progress bar)
cited job watch <AUDIT_JOB>

# Or poll status manually
cited audit status <AUDIT_JOB>
cited --json audit status <AUDIT_JOB>

# Get results when complete
cited audit result <AUDIT_JOB>
cited --json audit result <AUDIT_JOB>

# List audit history
cited audit list
cited audit list --business <BIZ_ID>
cited --json audit list --business <BIZ_ID>

# Export PDF
cited audit export <AUDIT_JOB>
cited audit export <AUDIT_JOB> --output my-audit.pdf
ls -la *.pdf
```

## 5. Recommendations (requires completed audit)

```bash
# Generate recommendations from audit
cited recommend start <AUDIT_JOB>
# ^^^ Save the returned job_id as $RECO_JOB

# Watch progress
cited job watch <RECO_JOB>

# Check status / results
cited recommend status <RECO_JOB>
cited recommend result <RECO_JOB>
cited --json recommend result <RECO_JOB>

# List recommendation history
cited recommend list
cited recommend list --audit <AUDIT_JOB>
```

## 6. Solutions (requires completed recommendation)

```bash
# Generate solution from a recommendation
cited solution start <RECOMMENDATION_ID>
# ^^^ Save the returned job_id as $SOL_JOB

# Watch progress
cited job watch <SOL_JOB>

# Check status / results
cited solution status <SOL_JOB>
cited solution result <SOL_JOB>
cited --json solution result <SOL_JOB>

# List solution history
cited solution list
cited solution list --business <BIZ_ID>
```

## 7. Business HQ Dashboard

```bash
# Basic dashboard
cited hq <BIZ_ID>

# With additional sections
cited hq <BIZ_ID> --personas
cited hq <BIZ_ID> --products
cited hq <BIZ_ID> --actions
cited hq <BIZ_ID> --personas --products --intents --actions

# Full heavy load (all data)
cited hq <BIZ_ID> --full

# JSON output (great for piping to jq)
cited --json hq <BIZ_ID> --full
cited --json hq <BIZ_ID> --full | jq '.health_scores'
```

## 8. Analytics

```bash
# KPI trends over time
cited analytics trends <BIZ_ID>
cited --json analytics trends <BIZ_ID>

# Business summary
cited analytics summary <BIZ_ID>
cited --json analytics summary <BIZ_ID>

# Compare audit against baseline
cited analytics compare <AUDIT_JOB>
```

## 9. Agent API (requires API key)

```bash
# Set agent API key
cited config set agent_api_key <your-agent-api-key>

# Business facts
cited agent facts <BIZ_ID>
cited --json agent facts <BIZ_ID>

# Verifiable claims
cited agent claims <BIZ_ID>

# Competitive comparison
cited agent comparison <BIZ_ID>

# Semantic health
cited agent semantic-health <BIZ_ID>

# Buyer-fit simulation
cited agent buyer-fit --query "best GEO platform for e-commerce"
cited agent buyer-fit --query "enterprise SEO tool" --business <BIZ_ID>
cited --json agent buyer-fit --query "best GEO platform" --business <BIZ_ID>
```

## 10. Job Management

```bash
# Start a long-running job and cancel it
cited audit start <BIZ_ID>
# ^^^ Note the job_id
cited job cancel <JOB_ID>

# Watch with custom poll interval
cited job watch <JOB_ID> --interval 5

# Specify job type explicitly (skips auto-detection probe)
cited job watch <JOB_ID> --type audit
cited job cancel <JOB_ID> --type recommendations
```

## 11. Global Flags & Edge Cases

```bash
# JSON mode on everything
cited --json version
cited --json status
cited --json auth status
cited --json business list
cited --json audit list

# Quiet mode
cited --quiet auth status
cited --quiet business list

# No color (for CI/log capture)
cited --no-color business list
cited --no-color status

# Pipe-friendly (auto-detects non-TTY)
cited business list | cat
cited --json business list | jq '.[0].name'

# Environment switching inline
cited --env dev status
cited --env prod status
cited --env dev business list
cited --env prod business list

# Error handling (verify exit codes)
cited business get nonexistent-id; echo "Exit: $?"           # Should be 3 (not found)
cited --env dev auth login --email bad --password bad; echo "Exit: $?"  # Should be 2 (auth)
cited business update <BIZ_ID>; echo "Exit: $?"              # Should be 4 (validation - no fields)
```

## 12. Cleanup

```bash
# Delete test business
cited business delete <BIZ_ID> --yes

# Logout
cited auth logout
cited auth status   # Should fail with exit code 2
```

---

## End-to-End Pipeline

The single deepest-path test — exercises auth, CRUD, async jobs, polling, PDF generation, and cleanup:

```bash
cited config set environment dev
cited auth login --email <your-email> --password <your-password>
cited business create --name "E2E Test" --website "https://example.com" --industry "Technology"
# ^^^ capture BIZ_ID

cited business crawl <BIZ_ID>
# wait for crawl to complete

cited audit start <BIZ_ID>
# ^^^ capture AUDIT_JOB
cited job watch <AUDIT_JOB>

cited recommend start <AUDIT_JOB>
# ^^^ capture RECO_JOB
cited job watch <RECO_JOB>
cited --json recommend result <RECO_JOB>
# ^^^ extract a RECOMMENDATION_ID from the results

cited solution start <RECOMMENDATION_ID>
# ^^^ capture SOL_JOB
cited job watch <SOL_JOB>

cited hq <BIZ_ID> --full
cited analytics trends <BIZ_ID>
cited audit export <AUDIT_JOB> --output e2e-test.pdf

cited business delete <BIZ_ID> --yes
cited auth logout
```
