#!/usr/bin/env bash
# Run one rabbithole research angle through Codex CLI with live web search.
# Usage: codex-research.sh <prompt-file> <out-file> [model]
# Writes Codex's final message (dense notes + URLs) to <out-file>; logs go to <out-file>.log.
set -euo pipefail
[ $# -ge 2 ] || { echo "usage: $0 <prompt-file> <out-file> [model]" >&2; exit 2; }
prompt_file="$1"; out="$2"; model="${3:-}"
command -v codex >/dev/null || { echo "codex CLI not found on PATH" >&2; exit 127; }
[ -f "$prompt_file" ] || { echo "no prompt file: $prompt_file" >&2; exit 2; }
args=(--search exec --skip-git-repo-check --ephemeral -s read-only -o "$out")
[ -n "$model" ] && args+=(-m "$model")
codex "${args[@]}" - <"$prompt_file" >"$out.log" 2>&1 || {
  echo "codex failed for $prompt_file (see $out.log)" >&2; exit 1; }
[ -s "$out" ] || { echo "codex wrote no output for $prompt_file" >&2; exit 1; }
