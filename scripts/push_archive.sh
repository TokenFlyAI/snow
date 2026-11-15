#!/usr/bin/env bash
# Commit this run's forecast archive files (pipeline.run --archive DIR) to the orphan branch "archive"
# of the current repository and push them. Used by .github/workflows/forecast.yml; a failure here
# never affects the published forecast.
#
#   scripts/push_archive.sh DIR [MESSAGE]
set -euo pipefail
[ -d "${1:-}" ] || { echo "nothing to archive"; exit 0; }
src=$(cd "$1" && pwd)
msg=${2:-"archive: forecasts issued $(date -u +%Y-%m-%dT%H:%MZ)"}
[ -d "$src/forecasts" ] || { echo "nothing to archive"; exit 0; }

wt=$(mktemp -d)
cleanup() { git worktree remove --force "$wt" >/dev/null 2>&1 || true; }
trap cleanup EXIT
if git fetch -q --depth 1 origin archive 2>/dev/null; then
  git worktree add -q -f -B archive "$wt" FETCH_HEAD
else                                       # first run: start the orphan branch
  git worktree add -q -f --detach "$wt"
  git -C "$wt" checkout -q --orphan archive
  git -C "$wt" rm -rfq . >/dev/null 2>&1 || true
  git -C "$wt" clean -fdxq
fi
cp -R "$src/." "$wt/"
git -C "$wt" add -A
if git -C "$wt" diff --cached --quiet; then echo "archive unchanged"; exit 0; fi
git -C "$wt" commit -q -m "$msg"
for i in 1 2 3; do
  if git -C "$wt" push -q origin archive; then echo "archive pushed: $msg"; exit 0; fi
  sleep $((i * 5))
  git -C "$wt" fetch -q --depth 1 origin archive && git -C "$wt" rebase -q FETCH_HEAD
done
echo "archive push failed" >&2
exit 1
