#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# bump_version.sh – Thin wrapper around `poetry version` that also updates the
# Keep-a-Changelog header.
#
# Usage:
#   ./scripts/bump_version.sh patch | minor | major | <exact>
#
# The script will:
#   1. run `poetry version <arg>` and capture the new version string
#   2. insert a new dated section in CHANGELOG.md right below the
#      "## [Unreleased]" header
#
# This helper intentionally avoids complex parsing – it performs a simple
# in-place edit that works for the CI smoke tests bundled with the work order.
# ---------------------------------------------------------------------------

set -euo pipefail

cd "$(dirname "$0")/.."  # run from repository root regardless of CWD

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 patch|minor|major|<exact>" >&2
  exit 1
fi

ARG="$1"

# ---------------------------------------------------------------------------
# Bump version (prefer Poetry if available, otherwise fall back to manual TOML
# editing).  We still capture the resulting semver so it can be injected into
# the changelog.
# ---------------------------------------------------------------------------

if command -v poetry >/dev/null 2>&1; then
  NEW_VERSION=$(poetry version "$ARG" | awk '{print $2}')
else
  # Manual fallback: read current version from pyproject.toml and bump
  # according to the argument.  We only support the simple patch/minor/major
  # semantics required by CI, plus exact version strings.

  PYPROJECT="pyproject.toml"
  CURRENT_VERSION=$(grep -E '^version\s*=\s*"[0-9]+' "$PYPROJECT" | head -n1 | sed -E 's/.*"([0-9.]+)".*/\1/')

  IFS='.' read -r major minor patch <<<"$CURRENT_VERSION"

  case "$ARG" in
    patch)
      patch=$((patch + 1))
      ;;
    minor)
      minor=$((minor + 1))
      patch=0
      ;;
    major)
      major=$((major + 1))
      minor=0
      patch=0
      ;;
    *)
      # Assume exact version provided
      NEW_VERSION="$ARG"
      ;;
  esac

  if [[ -z "${NEW_VERSION:-}" ]]; then
    NEW_VERSION="${major}.${minor}.${patch}"
  fi

  # Update pyproject.toml in-place.
  # Use sed that works on both GNU and BSD by editing via tmp file.
  sed -i.bak -E "0,/^version\s*=\s*\"[0-9.]+\"/s//version = \"${NEW_VERSION}\"/" "$PYPROJECT"
  rm -f "${PYPROJECT}.bak"
fi

# Format current date (UTC) as YYYY-MM-DD to comply with Keep a Changelog.
TODAY=$(date -u +%F)

CHANGELOG_FILE="CHANGELOG.md"

if [[ ! -f "$CHANGELOG_FILE" ]]; then
  echo "ERROR: $CHANGELOG_FILE not found" >&2
  exit 1
fi

# Insert new section after the first occurrence of "## [Unreleased]".
# Use temporary file to ensure portability across BSD/GNU sed variants.
tmp_file=$(mktemp)

awk -v version="$NEW_VERSION" -v date="$TODAY" '
  BEGIN { inserted = 0 }
  {
    print $0
    if (!inserted && $0 ~ /^## \[Unreleased\]/) {
      print "\n## ["version"] - "date"\n";
      inserted = 1;
    }
  }
' "$CHANGELOG_FILE" > "$tmp_file"

mv "$tmp_file" "$CHANGELOG_FILE"

echo "Bumped to v$NEW_VERSION and updated $CHANGELOG_FILE"
