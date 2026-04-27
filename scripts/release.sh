#!/usr/bin/env bash
# Release a new version of querri.
#
# Usage: ./scripts/release.sh X.Y.Z
#
# What it does:
#   1. Pre-flight: must be on main, in sync with origin, tag must not exist.
#   2. Stashes any uncommitted work (so the release runs against a clean tree).
#   3. Edits querri/_version.py — the single source of truth. pyproject.toml
#      reads from it via [tool.hatch.version].
#   4. Runs ruff + mypy + pytest. Aborts on any failure.
#   5. Commits as "Bump version to X.Y.Z", tags vX.Y.Z, pushes main + tag.
#   6. Restores the stashed work.
#
# If the script aborts before commit, the version edit is reverted.
# If push fails after commit, the commit + tag exist locally — push manually.

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 X.Y.Z" >&2
    exit 1
fi

VERSION="$1"

if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([abrc][0-9]+)?$ ]]; then
    echo "Error: version must be X.Y.Z (or X.Y.Zrc1, X.Y.Za1, X.Y.Zb1)" >&2
    exit 1
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$BRANCH" != "main" ]]; then
    echo "Error: must be on main, currently on '$BRANCH'" >&2
    exit 1
fi

git fetch origin main --quiet
if [[ "$(git rev-parse @)" != "$(git rev-parse @{u})" ]]; then
    echo "Error: local main is not in sync with origin/main" >&2
    echo "Run: git pull --ff-only origin main" >&2
    exit 1
fi

if git rev-parse "v$VERSION" >/dev/null 2>&1; then
    echo "Error: tag v$VERSION already exists" >&2
    exit 1
fi

STASHED=0
COMMITTED=0
cleanup() {
    if [[ "$COMMITTED" == "0" ]]; then
        git checkout -- querri/_version.py 2>/dev/null || true
    fi
    if [[ "$STASHED" == "1" ]]; then
        echo "Restoring stashed changes..."
        git stash pop --quiet 2>/dev/null || true
    fi
}
trap cleanup EXIT

if ! git diff --quiet HEAD -- || [[ -n "$(git ls-files --others --exclude-standard)" ]]; then
    echo "Stashing uncommitted changes..."
    git stash push --include-untracked --quiet --message "release.sh auto-stash for v$VERSION"
    STASHED=1
fi

echo "Bumping querri/_version.py to $VERSION..."
echo "__version__ = \"$VERSION\"" > querri/_version.py

echo "Running ruff..."
ruff check querri/ tests/

echo "Running mypy..."
mypy querri/

echo "Running pytest..."
pytest tests/ -q

echo "Committing..."
git add querri/_version.py
git commit -m "Bump version to $VERSION"
COMMITTED=1

echo "Tagging v$VERSION..."
git tag "v$VERSION"

echo "Pushing main..."
git push origin main

echo "Pushing tag..."
git push origin "v$VERSION"

echo ""
echo "Released v$VERSION."
echo "Watch the run:"
echo "  gh run watch \$(gh run list --workflow=release.yml --limit 1 --json databaseId -q '.[0].databaseId')"
