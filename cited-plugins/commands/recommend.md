---
name: recommend
description: Read the recommendations from a Cited audit and make the fixes
user_invocable: true
arguments:
  - name: audit_id
    description: Audit ID (optional, the newest finished audit is used if not provided)
    required: false
---

Read the recommendations from a finished Cited audit and turn them into fixes.

If `$ARGUMENTS` contains an audit ID, pass it as `audit_id`. Otherwise call `get_recommendations` without it to use the newest finished audit.

Follow the geo-recommend skill: present the open items highest risk first, generate fixes for the ones the user picks (ask before spending credits), show the files and steps, then mark them done and verify them on the live site.
