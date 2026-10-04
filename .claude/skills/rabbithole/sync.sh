#!/usr/bin/env bash
# Copy the rabbithole skills (Claude: SKILL.md + config.json; Codex port) into the claude-skills repo. Does not commit or push.
set -euo pipefail
src="$(cd "$(dirname "$0")" && pwd)"
dest_repo="${CLAUDE_SKILLS_REPO:-$HOME/Documents/GitHub/claude-skills}"
[ -d "$dest_repo/.git" ] || { echo "not a git repo: $dest_repo" >&2; exit 1; }
mkdir -p "$dest_repo/rabbithole"
rsync -a --delete --exclude sync.sh --exclude .DS_Store "$src/" "$dest_repo/rabbithole/"
mkdir -p "$dest_repo/rabbithole-codex"
cp "$src/../../../.agents/skills/rabbithole/SKILL.md" "$dest_repo/rabbithole-codex/SKILL.md"
git -C "$dest_repo" status --short rabbithole rabbithole-codex
