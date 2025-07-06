#!/usr/bin/env bash
# file: pr.sh
#
# Usage examples:
#   ./pr.sh "Fix typo in README"
#   ./pr.sh "Add CSV import" -b develop -t "CSV import" -m "Adds CSV parser and docs" -d  # draft PR
#   ./pr.sh "Hot‑fix" -u                          # reuse current branch

set -euo pipefail

# --- defaults ---------------------------------------------------------------
BASE_BRANCH="main"
TITLE=""
DRAFT=false
DESCRIPTION=""
USE_CURRENT=false      # if true, operate on the current branch instead of making a new one

# --- parse flags ------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case $1 in
    -b|--base)   BASE_BRANCH="$2"; shift 2 ;;
    -t|--title)  TITLE="$2";       shift 2 ;;
    -m|--message|--body)
      DESCRIPTION="$2"; shift 2 ;;
    -d|--draft)  DRAFT=true;       shift   ;;
    -u|--use-current)
      USE_CURRENT=true; shift ;;
    *)           COMMIT_MSG="$1";  shift   ;;
  esac
done

if [[ -z "${COMMIT_MSG:-}" ]]; then
  echo "Error: commit message required"
  exit 1
fi

# --- sanity checks ----------------------------------------------------------
command -v gh >/dev/null 2>&1 || { echo "Install GitHub CLI (gh) first."; exit 1; }
# abort early if the working tree is clean (tracked + untracked)
if [[ -z $(git status --porcelain) ]]; then
  echo "No changes to commit."
  exit 0
fi

# --- determine branch & checkout --------------------------------------------
if $USE_CURRENT; then
  # stay on whatever branch we’re currently on
  BRANCH=$(git rev-parse --abbrev-ref HEAD)
  echo "ℹ️  Reusing current branch: $BRANCH"
else
  # slugify commit msg -> feature/<slug>
  SLUG=$(echo "$COMMIT_MSG" | tr '[:upper:]' '[:lower:]' \
                            | tr -cs 'a-z0-9' '-' | sed 's/^-//;s/-$//')
  BRANCH="feature/$SLUG"

  # ensure we start from the up‑to‑date base branch
  git switch "$BASE_BRANCH"

  # pull only if clean; skip to avoid clobbering local edits
  if [[ -z $(git status --porcelain) ]]; then
    git pull --ff-only
  else
    echo "⚠️  Uncommitted changes detected — skipping 'git pull'."
  fi

  # create & switch, bringing pending edits along
  git switch -c "$BRANCH"
fi

# stage, commit, push
git add -A
git commit -m "$COMMIT_MSG"
git push -u origin "$BRANCH"

# --- create the PR ----------------------------------------------------------
ARGS=(--base "$BASE_BRANCH" --head "$BRANCH")
[[ -n $TITLE ]] && ARGS+=(--title "$TITLE") || ARGS+=(--title "$COMMIT_MSG")
[[ -n $DESCRIPTION ]] && ARGS+=(--body "$DESCRIPTION") || ARGS+=(--body "")
$DRAFT && ARGS+=(--draft)

gh pr create "${ARGS[@]}"

echo "✅ PR created for $BRANCH → $BASE_BRANCH"