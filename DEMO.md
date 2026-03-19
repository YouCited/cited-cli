# Cited CLI — Demo Walkthrough

Copy-paste each block into a terminal, one at a time. Each step captures IDs into shell variables that feed into the next step.

**Prerequisites:** `cited` CLI installed, `jq` installed, logged out (or ready to re-login).

---

## Setup

```bash
cited config set environment dev
cited --env dev status
cited login
cited auth status
```

## Step 1: Create business

```bash
BUSINESS_ID=$(cited --env dev --json business create \
  --name        "CLI Demo $(date +%H%M%S)" \
  --website     "https://anthropic.com" \
  --description "Demo business for validating the full Cited GEO pipeline via CLI." \
  --industry    "technology" \
  | jq -r '.id')
echo "BUSINESS_ID=$BUSINESS_ID"

cited --env dev business get $BUSINESS_ID
```

## Step 2: Crawl the website

```bash
CRAWL_JOB=$(cited --env dev --json business crawl $BUSINESS_ID | jq -r '.job_id')
echo "CRAWL_JOB=$CRAWL_JOB"

cited --env dev job watch $CRAWL_JOB

cited --env dev business health $BUSINESS_ID
```

## Step 3: Create audit template

```bash
TEMPLATE_ID=$(cited --env dev --json audit template create \
  --name        "Demo GEO Audit" \
  --business    $BUSINESS_ID \
  --description "Checks citation presence across key AI and technology queries" \
  --question    "Are we cited when people ask about AI safety?" \
  --question    "Does our product appear in AI assistant recommendations?" \
  --question    "Are we mentioned when users research responsible AI?" \
  | jq -r '.id')
echo "TEMPLATE_ID=$TEMPLATE_ID"

cited --env dev audit template get $TEMPLATE_ID
```

## Step 4: Refine template questions

```bash
cited --env dev audit template update $TEMPLATE_ID \
  --question "Are we cited when enterprise buyers ask about AI safety?" \
  --question "Does Anthropic appear in responsible AI tool recommendations?" \
  --question "Are we mentioned when developers compare AI platforms?"

cited --env dev audit template get $TEMPLATE_ID
```

## Step 5: Run the audit

```bash
AUDIT_JOB=$(cited --env dev --json audit start $TEMPLATE_ID --business $BUSINESS_ID \
  | jq -r '.job_id')
echo "AUDIT_JOB=$AUDIT_JOB"

cited --env dev job watch $AUDIT_JOB

cited --env dev audit result $AUDIT_JOB
```

## Step 6: Generate recommendations

```bash
RECO_JOB=$(cited --env dev --json recommend start $AUDIT_JOB | jq -r '.job_id')
echo "RECO_JOB=$RECO_JOB"

cited --env dev job watch $RECO_JOB

cited --env dev recommend result $RECO_JOB
```

## Step 7: View insights

```bash
cited --env dev recommend insights $RECO_JOB

SOURCE_ID=$(cited --env dev --json recommend insights $RECO_JOB \
  | jq -r '.question_insights[0].question_id')
echo "SOURCE_ID=$SOURCE_ID"
```

## Step 8: Start a solution

```bash
cited --env dev solution start $RECO_JOB \
  --type   question_insight \
  --source $SOURCE_ID
```

## Step 9: HQ dashboard

```bash
cited --env dev hq $BUSINESS_ID
cited --env dev hq $BUSINESS_ID --full
```

## Step 10: Analytics

```bash
cited --env dev analytics trends $BUSINESS_ID
cited --env dev analytics summary $BUSINESS_ID
```

## Cleanup

```bash
cited --env dev audit template delete $TEMPLATE_ID --yes
cited --env dev business delete $BUSINESS_ID --yes
cited logout
cited auth status   # should fail with exit code 2
```
