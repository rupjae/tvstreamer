#!/usr/bin/env bash
# file: pr.sh
#
# Usage examples:
#   ./pr.sh "Fix typo in README"
#   ./pr.sh "Add CSV import" -b develop -t "CSV import" -d  # draft PR

set -euo pipefail

# --- defaults ---------------------------------------------------------------
BASE_BRANCH="main"
TITLE=""
DRAFT=false

# --- parse flags ------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case $1 in
    -b|--base)   BASE_BRANCH="$2"; shift 2 ;;
    -t|--title)  TITLE="$2";       shift 2 ;;
    -d|--draft)  DRAFT=true;       shift   ;;
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

# --- generate a branch name -------------------------------------------------
SLUG=$(echo "$COMMIT_MSG" | tr '[:upper:]' '[:lower:]' \
                          | tr -cs 'a-z0-9' '-' | sed 's/^-//;s/-$//')
BRANCH="feature/$SLUG"

# make sure we’re up to date
git switch "$BASE_BRANCH"
git pull --ff-only

# create & switch
git switch -c "$BRANCH"

# stage, commit, push
git add -A
git commit -m "$COMMIT_MSG"
git push -u origin "$BRANCH"

# --- create the PR ----------------------------------------------------------
ARGS=(--base "$BASE_BRANCH" --head "$BRANCH" --body "")
[[ -n $TITLE ]] && ARGS+=(--title "$TITLE") || ARGS+=(--title "$COMMIT_MSG")
$DRAFT && ARGS+=(--draft)

gh pr create "${ARGS[@]}"

echo "✅ PR created for $BRANCH → $BASE_BRANCH"