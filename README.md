# rabbithole

One topic at a time (CS by default, any subject on request), all the way down — mechanism, math, design reasoning, failure modes, and the latest research.

- `dives/` — full deep dives (one folder per topic), generated via the `/rabbithole` Claude Code skill
- `blog/` — blog posts written from dives
- `history.md` — log of every dive

## Usage (Claude Code, from this folder)

```
/rabbithole              # random topic, hard depth
/rabbithole research     # random topic, frontier / recent papers
/rabbithole <topic>      # pick the topic
/rabbithole blog [slug]  # turn a dive into a blog post
/rabbithole history      # list past dives

/rabbithole subject:physics          # random topic from another subject
/rabbithole subject:"music theory"   # any free-form subject
/rabbithole model:sonnet             # heavier research subagents for this run
```

Defaults (subject, research model) live in `.claude/skills/rabbithole/config.json`. The skill runs on Haiku; research subagents default to Haiku too.

## Codex

Separate Codex port in `.agents/skills/rabbithole/` — Codex picks it up automatically from this repo, no install. Same dive format and history.

```
codex --search        # web search is required
$rabbithole [args]    # same args as above
```
