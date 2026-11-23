#!/usr/bin/env bash
# Sets up the Cited test account for the weekly Paid audit check and saves its
# agent key as the CITED_SMOKE_AGENT_KEY secret in YouCited/cited-cli.
#
#   bash scripts/setup_smoke_key.sh start             # agent signup; prints the claim link and code
#   (John claims it in a private browser window, signed in as the TEST login)
#   bash scripts/setup_smoke_key.sh finish [VOUCHER]  # checks the claim, saves the key to GitHub,
#                                             # readies the youcited.com business, redeems VOUCHER
#
# Version 3 (2026-11-23): two non-interactive steps, so a session on John's Mac
# can run it. The key is never printed. Between the steps it sits in
# ~/.cited-smoke-setup (only this user can read it); finish deletes that folder
# once the key is in GitHub. John's own Cited login and keychain are not touched.
set -euo pipefail

REPO="YouCited/cited-cli"
SITE="youcited.com"
WORK="$HOME/.cited-smoke-setup"
CREDS="$WORK/.cited/credentials.json"

command -v cited >/dev/null || { echo "Install the cited CLI first: brew install youcited/cited/cited"; exit 1; }
command -v python3 >/dev/null || { echo "python3 is needed"; exit 1; }

# cited, run as a fresh user: its own config and credentials file, no keychain.
c() {
  env -u CITED_TOKEN -u CITED_AGENT_API_KEY HOME="$WORK" \
    PYTHON_KEYRING_BACKEND=keyring.backends.fail.Keyring cited --env prod "$@"
}
# One field of a JSON reply; empty when the reply isn't JSON (an error).
field() { python3 -c 'import json,sys
try: d=json.load(sys.stdin)
except ValueError: d={}
for k in sys.argv[1].split("."): d=(d or {}).get(k) if isinstance(d, dict) else None
print("" if d is None else d)' "$1"; }
site_business() { c --json business get 2>/dev/null | python3 -c 'import json,sys
try: items=json.load(sys.stdin).get("businesses") or []
except ValueError: items=[]
print(next((b["id"] for b in items if sys.argv[1] in (b.get("website") or "")), ""))' "$SITE"; }

case "${1:-}" in
start)
  if [[ -f "$CREDS" ]]; then
    echo "A signup is already waiting in $WORK. Claim it and run 'finish', or delete that folder to start over."
    exit 1
  fi
  mkdir -p "$WORK" && chmod 700 "$WORK"
  SIGNUP="$(c --json agent signup --name "Cited CI paid check")"
  [[ "$(echo "$SIGNUP" | field api_key_saved)" == "True" ]] || { echo "Signup failed:"; echo "$SIGNUP"; exit 1; }
  echo "CLAIM_URL=$(echo "$SIGNUP" | field claim.url)"
  echo "CLAIM_CODE=$(echo "$SIGNUP" | field claim.code)"
  echo "Next: claim it in a private window signed in as the TEST login (Log in, enter the code,"
  echo "leave 'keep using my account for 90 days' ticked), then run: $0 finish VOUCHER"
  ;;
finish)
  VOUCHER="${2:-}"
  [[ -f "$CREDS" ]] || { echo "No signup waiting. Run '$0 start' first."; exit 1; }
  command -v gh >/dev/null && gh auth status >/dev/null 2>&1 || { echo "gh isn't signed in: run 'gh auth login', then finish again."; exit 1; }
  if [[ "$(c --json status 2>/dev/null | field account.unclaimed)" != "False" ]]; then
    echo "Not claimed yet (or the status check failed). Claim it, then run finish again."
    exit 1
  fi
  echo "Claimed. Saving the key as $REPO secret CITED_SMOKE_AGENT_KEY..."
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["agent_key:prod"], end="")' "$CREDS" \
    | gh secret set CITED_SMOKE_AGENT_KEY -R "$REPO"
  echo "Saved."
  # From here on a failure can't lose the key: it's in GitHub.
  trap 'rm -rf "$WORK"' EXIT
  BUSINESS="$(site_business)"
  if [[ -z "$BUSINESS" ]]; then
    c business setup --website "$SITE"
    BUSINESS="$(site_business)"
  fi
  [[ -n "$BUSINESS" ]] || { echo "Couldn't find the $SITE business."; exit 1; }
  echo "Business $BUSINESS. Drafting questions (a few minutes)..."
  c audit questions --business "$BUSINESS"
  if [[ -n "$VOUCHER" ]]; then c credits buy --voucher "$VOUCHER"; else echo "No voucher given: credits not added."; fi
  c audit quote --business "$BUSINESS"
  echo "Done. The key is now only in GitHub; $WORK is deleted."
  ;;
*)
  sed -n '2,8p' "$0"; exit 1 ;;
esac
