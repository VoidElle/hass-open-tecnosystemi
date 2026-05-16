#!/usr/bin/env bash
# Bump the integration version in all relevant files.
#
# Usage:
#   ./bump_version.sh <major|minor|patch>   # auto-increment a component
#   ./bump_version.sh <x.y.z>              # set an explicit version

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

MANIFEST="$ROOT_DIR/manifest.json"
README="$ROOT_DIR/README.md"

usage() {
  echo "Usage: $0 <major|minor|patch|x.y.z>"
  exit 1
}

# --- read current version from manifest.json ---
CURRENT=$(grep -E '"version"' "$MANIFEST" | sed 's/.*"\([0-9]*\.[0-9]*\.[0-9]*\)".*/\1/')
if [[ -z "$CURRENT" ]]; then
  echo "Error: could not find version in $MANIFEST" >&2
  exit 1
fi

IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT"

# --- resolve argument or prompt interactively ---
if [[ $# -eq 1 ]]; then
  ARG="$1"
else
  echo "Current version: $CURRENT"
  echo ""
  echo "  1) patch  →  ${MAJOR}.${MINOR}.$((PATCH + 1))"
  echo "  2) minor  →  ${MAJOR}.$((MINOR + 1)).0"
  echo "  3) major  →  $((MAJOR + 1)).0.0"
  echo "  4) custom"
  echo ""
  read -rp "Choose [1-4]: " CHOICE
  case "$CHOICE" in
    1) ARG="patch" ;;
    2) ARG="minor" ;;
    3) ARG="major" ;;
    4) read -rp "Enter version (x.y.z): " ARG ;;
    *) echo "Invalid choice." >&2; exit 1 ;;
  esac
fi

# --- determine new version ---
case "$ARG" in
  major) NEW="$((MAJOR + 1)).0.0" ;;
  minor) NEW="${MAJOR}.$((MINOR + 1)).0" ;;
  patch) NEW="${MAJOR}.${MINOR}.$((PATCH + 1))" ;;
  *)
    if [[ "$ARG" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      NEW="$ARG"
    else
      echo "Error: invalid version '$ARG'" >&2
      usage
    fi
    ;;
esac

if [[ "$NEW" == "$CURRENT" ]]; then
  echo "Version is already $CURRENT, nothing to do."
  exit 0
fi

echo "Bumping version: $CURRENT → $NEW"

# --- update manifest.json ---
sed -i '' "s/\"version\": \"${CURRENT}\"/\"version\": \"${NEW}\"/" "$MANIFEST"
echo "  manifest.json   $CURRENT → $NEW"

# --- update README.md version badge (if present) ---
if grep -q "/badge/version-${CURRENT}-orange" "$README" 2>/dev/null; then
  sed -i '' "s|/badge/version-${CURRENT}-orange|/badge/version-${NEW}-orange|" "$README"
  echo "  README.md badge  $CURRENT → $NEW"
fi

echo "Done. Remember to:"
echo "  git add manifest.json README.md"
echo "  git commit -m \"chore: bump version to v${NEW}\""
echo "  git tag v${NEW}"
echo "  git push && git push --tags"
