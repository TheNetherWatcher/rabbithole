#!/usr/bin/env bash
# Copy rabbithole SKILL.md into the claude-skills repo. Does not commit or push.
set -euo pipefail
src="$(cd "$(dirname "$0")" && pwd)/SKILL.md"
dest_repo="${CLAUDE_SKILLS_REPO:-$HOME/Documents/GitHub/claude-skills}"
[ -d "$dest_repo/.git" ] || { echo "not a git repo: $dest_repo" >&2; exit 1; }
mkdir -p "$dest_repo/rabbithole"
cp "$src" "$dest_repo/rabbithole/SKILL.md"
git -C "$dest_repo" status --short rabbithole
