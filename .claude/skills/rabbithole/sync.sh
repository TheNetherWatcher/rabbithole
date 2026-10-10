#!/usr/bin/env bash
# Point the claude-skills repo's rabbithole-repo submodule at this repo's pushed origin/main. Does not commit or push.
# claude-skills links to this skill (rabbithole -> rabbithole-repo/.claude/skills/rabbithole) instead of copying it.
set -euo pipefail
dest_repo="${CLAUDE_SKILLS_REPO:-$HOME/Documents/GitHub/claude-skills}"
[ -d "$dest_repo/.git" ] || { echo "not a git repo: $dest_repo (clone https://github.com/TheNetherWatcher/claude-skills there)" >&2; exit 1; }
git -C "$dest_repo" submodule update --init --remote rabbithole-repo
git -C "$dest_repo" status --short
