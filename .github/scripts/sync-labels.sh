#!/usr/bin/env bash
# Idempotent label sync for the-show.
# Re-runs are safe: existing labels are updated, new ones created.
# Requires gh CLI authenticated against the target repo.
set -euo pipefail

REPO="${REPO:-markscleary/the-show}"

sync() {
  local name="$1" color="$2" desc="$3"
  if gh label create "$name" --color "$color" --description "$desc" --repo "$REPO" >/dev/null 2>&1; then
    echo "created: $name"
  else
    gh label edit "$name" --color "$color" --description "$desc" --repo "$REPO" >/dev/null
    echo "updated: $name"
  fi
}

# Type
sync "bug"           "d73a4a" "Something isn't working"
sync "enhancement"   "a2eeef" "New feature or improvement"
sync "documentation" "0075ca" "Documentation work"
sync "question"      "d876e3" "Further information requested"

# Area
sync "area: runtime"    "c5def5" "Core runtime code"
sync "area: adapters"   "c5def5" "Adapter contracts and implementations"
sync "area: cli"        "c5def5" "Operator-facing CLI"
sync "area: docs"       "c5def5" "Operator guide, quickstart, examples"
sync "area: dispatcher" "c5def5" "the-show-dispatcher-* packages"

# Priority
sync "priority: high"   "b60205" "Blocking real operators"
sync "priority: medium" "fbca04" "Meaningful but not blocking"
sync "priority: low"    "0e8a16" "Nice to have"

# Status
sync "triage"      "fef2c0" "Newly opened, needs review"
sync "accepted"    "0e8a16" "Confirmed and on the roadmap"
sync "in progress" "1d76db" "Actively being worked"
sync "blocked"     "b60205" "Waiting on something external"
sync "wontfix"     "ffffff" "Declined with reason"

# Special
sync "good first issue" "7057ff" "Good for newcomers"
sync "dog-food"         "5319e7" "Found by The Show running on itself"
sync "v1.2"             "ededed" "Targeted for v1.2"
sync "v1.3"             "ededed" "Targeted for v1.3"
