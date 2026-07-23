#!/usr/bin/env bash
# retag.sh — Delete a GitHub release + tag and re-create at HEAD.
#
# Usage:
#   ./scripts/retag.sh v0.1.0
#   ./scripts/retag.sh v0.1.0 abc1234   # tag a specific commit instead of HEAD

set -euo pipefail

usage() {
  sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'
}

if [[ $# -eq 0 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -gt 2 ]]; then
  usage >&2
  exit 1
fi

TAG="$1"
COMMIT_ARG="${2:-HEAD}"

if [[ ! "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "error: release tag must have the form vX.Y.Z: $TAG" >&2
  exit 1
fi

if ! COMMIT="$(git rev-parse --verify --quiet "${COMMIT_ARG}^{commit}")"; then
  echo "error: commit does not exist: $COMMIT_ARG" >&2
  exit 1
fi

if [[ "$COMMIT_ARG" == "HEAD" && -n "$(git status --porcelain)" ]]; then
  echo "error: working tree has uncommitted changes; commit them before retagging HEAD" >&2
  echo "       or pass an explicit commit SHA: ./scripts/retag.sh $TAG <commit>" >&2
  exit 1
fi

if ! python3 -c 'import tomllib' 2>/dev/null; then
  echo "error: retagging requires Python 3.11 or newer" >&2
  exit 1
fi

PROJECT_VERSION="$(
  git show "${COMMIT}:pyproject.toml" \
    | python3 -c 'import sys, tomllib; print(tomllib.loads(sys.stdin.read())["project"]["version"])'
)"
RUNTIME_VERSION="$(
  git show "${COMMIT}:src/querido/__init__.py" \
    | sed -n 's/^__version__ = "\([^"]*\)"$/\1/p'
)"

if [[ -z "$RUNTIME_VERSION" || "$PROJECT_VERSION" != "$RUNTIME_VERSION" ]]; then
  echo "error: project version '$PROJECT_VERSION' does not match runtime version '$RUNTIME_VERSION'" >&2
  exit 1
fi

if [[ "${TAG#v}" != "$PROJECT_VERSION" ]]; then
  echo "error: tag '$TAG' does not match package version '$PROJECT_VERSION' at $COMMIT_ARG" >&2
  exit 1
fi

git fetch --quiet origin refs/heads/main
MAIN_COMMIT="$(git rev-parse --verify 'FETCH_HEAD^{commit}')"
if ! git merge-base --is-ancestor "$COMMIT" "$MAIN_COMMIT"; then
  echo "error: target commit must be part of origin/main" >&2
  exit 1
fi

if ! git show-ref --verify --quiet "refs/tags/$TAG" \
  && ! git ls-remote --exit-code --tags origin "refs/tags/$TAG" >/dev/null 2>&1; then
  echo "error: tag '$TAG' does not exist locally or on origin; create new tags with git tag" >&2
  exit 1
fi

REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
ACTIVE_RUNS="$(
  gh run list --repo "$REPO" --workflow release.yml --limit 100 \
    --json headBranch,status,url \
    --jq ".[] | select(.headBranch == \"$TAG\" and .status != \"completed\") | .url"
)"
if [[ -n "$ACTIVE_RUNS" ]]; then
  echo "error: release workflow for '$TAG' is still active; wait for or cancel it before retagging" >&2
  echo "$ACTIVE_RUNS" >&2
  exit 1
fi

PYPI_STATUS="$(
  curl -sS -o /dev/null -w '%{http_code}' "https://pypi.org/pypi/querido/${PROJECT_VERSION}/json"
)"
if [[ "$PYPI_STATUS" == "200" ]]; then
  echo "error: querido $PROJECT_VERSION is already published to PyPI and must not be retagged" >&2
  echo "       publish a new patch version instead" >&2
  exit 1
fi
if [[ "$PYPI_STATUS" != "404" ]]; then
  echo "error: could not verify PyPI release status (HTTP $PYPI_STATUS)" >&2
  exit 1
fi

gh release view "$TAG" --repo "$REPO" >/dev/null

echo "==> Deleting release + remote tag '$TAG' from $REPO"
gh release delete "$TAG" --repo "$REPO" --yes --cleanup-tag
echo "    Release and remote tag deleted"

echo "==> Deleting local tag '$TAG'"
git tag -d "$TAG" 2>/dev/null \
  && echo "    Local tag deleted" \
  || echo "    No local tag (skipped)"

echo "==> Creating tag '$TAG' at $COMMIT"
git tag "$TAG" "$COMMIT"

echo "==> Pushing tag '$TAG' to origin"
git push origin "$TAG"

echo "Done."
