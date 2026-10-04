#!/usr/bin/env bash
# Symlink this skill into Codex's skills dir so `codex` can run $rabbithole from the repo root.
set -euo pipefail
src="$(cd "$(dirname "$0")/.." && pwd)"
dest="${CODEX_HOME:-$HOME/.codex}/skills/rabbithole"
mkdir -p "$(dirname "$dest")"
if [ -e "$dest" ] && [ ! -L "$dest" ]; then
  echo "refusing to replace non-symlink: $dest" >&2; exit 1
fi
ln -sfn "$src" "$dest"
echo "linked $dest -> $src"
