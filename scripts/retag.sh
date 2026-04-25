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

TAG="$1"
COMMIT="${2:-HEAD}"
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"

if [[ "$COMMIT" == "HEAD" && -n "$(git status --porcelain)" ]]; then
  echo "error: working tree has uncommitted changes; commit them before retagging HEAD" >&2
  echo "       or pass an explicit commit SHA: ./scripts/retag.sh $TAG <commit>" >&2
  exit 1
fi

echo "==> Deleting release + remote tag '$TAG' from $REPO"
gh release delete "$TAG" --repo "$REPO" --yes --cleanup-tag 2>/dev/null \
  && echo "    Release deleted" \
  || echo "    No release found (skipped)"

# cleanup-tag handles the remote, but if there was no release the tag may
# still exist on the remote
git push origin --delete "$TAG" 2>/dev/null \
  && echo "    Remote tag deleted" \
  || echo "    Remote tag already gone (skipped)"

echo "==> Deleting local tag '$TAG'"
git tag -d "$TAG" 2>/dev/null \
  && echo "    Local tag deleted" \
  || echo "    No local tag (skipped)"

echo "==> Creating tag '$TAG' at $COMMIT"
git tag "$TAG" "$COMMIT"

echo "==> Pushing tag '$TAG' to origin"
git push origin "$TAG"

echo "Done."
