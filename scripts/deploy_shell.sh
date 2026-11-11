#!/usr/bin/env bash
# Build the static shell and copy it into the main-site repository.
#
#   scripts/deploy_shell.sh [path-to-tokenfly-repo]     (default: ../tokenfly)
#
# It only copies files. Review `git status` in the main-site repo, then commit
# and push there yourself: pushing redeploys tokenfly.ai on Render.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
target_repo="${1:-$here/../tokenfly}"
target="$target_repo/aiverse/snow"

[ -f "$target_repo/server.py" ] || { echo "not the tokenfly repo: $target_repo" >&2; exit 1; }

cd "$here/web"
[ -d node_modules ] || npm ci
# production build: data comes from this repo's GitHub Pages
NEXT_PUBLIC_DATA_BASE="${NEXT_PUBLIC_DATA_BASE:-https://tokenflyai.github.io/snow/data/v1}" npm run build

rm -rf "$target"
mkdir -p "$target"
cp -R out/. "$target/"
echo "copied $(find "$target" -type f | wc -l | tr -d ' ') files to $target"
echo "next: cd $target_repo && git status   (commit + push when you are happy)"
