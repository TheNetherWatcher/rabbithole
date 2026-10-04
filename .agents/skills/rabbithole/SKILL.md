---
name: rabbithole
description: Deep, web-researched dive into ONE random non-trivial topic in a configurable subject (default CS — ML/AI, security, systems, distributed, DBs, networking, crypto, compilers, blockchain, graphics, hardware...; also math, physics, biology, medicine, economics, or any free-form subject) opening with real-world context (where/how/why it is used), then explained down to the mechanism, math, design reasoning, failure modes, and latest research, ending with a question ladder. Saves a README plus a polished interactive HTML page per dive. Logs every dive to history.md and the private rabbithole repo; can turn a dive into a blog post. Codex port of the Claude Code rabbithole skill. Use when the user says $rabbithole, /rabbithole, "deep dive", "teach me something random in CS" (or any subject), "rabbit hole", or asks to blog a past dive.
---

# rabbithole

One topic. All the way down. Researched from the web, explained in chat, saved to the repo.

Codex version of the Claude Code skill in `.claude/skills/rabbithole/`. Same dive format, same history, same repo; only the tooling differs. Run it from the repo root with web search on: `codex --search`, then `$rabbithole [args]`.

All files live in the current working directory (the repo root): `history.md` is here, dives go in `dives/`, blog posts in `blog/`. Never read or write history anywhere else.

## Invocation

| Command | What happens |
|---|---|
| `$rabbithole` | Random topic, **hard** depth: full mechanism + math + design + failure modes, PLUS a frontier section (≥3–5 recent papers) and an open-problems section |
| `$rabbithole research` | Random topic, **research** depth: everything in hard, but frontier-heavy — topic must have active recent research, 2–3 key recent papers dissected in depth, extra open-debates research |
| `$rabbithole <topic>` | User-chosen topic, hard depth (add `research` anywhere for research depth) |
| `$rabbithole blog [slug]` | Turn a saved dive (default: latest) into a blog post in `blog/` |
| `$rabbithole history` | Show past dives grouped by domain |
| `subject:<name>` (combine with any of the above) | Pick the topic from another subject for this run, e.g. `$rabbithole subject:physics research`. `<name>` is a key in `config.json` → `subjects`, or any free-form subject (`subject:"music theory"`) |

## Configuration

`.claude/skills/rabbithole/config.json` (shared with the Claude skill; read it from the repo root) holds defaults:
- `subject` — default subject key when no `subject:` token is given (`cs` out of the box).
- `subjects.<key>` — `label` + `domains` list for each preset subject.
- `research_model` — Claude-only; ignore it. Codex uses whatever model the session runs (`codex -m <model>` to change it).

Resolve the subject once per run: `subject:` token > `config.json` `subject`. If the subject is free-form (not a preset key), derive 10–15 mechanism-rich domains for it yourself before Step 1 and use those. The rest of the skill is subject-agnostic: "system", "implementation", "in the wild" mean the real-world practice of that subject (labs, instruments, clinical protocols, markets, proofs…), not software, unless the subject is CS.

## Step 1 — Pick the topic (random modes)

1. Read `history.md`. Never repeat a topic. Don't repeat the domain of the last 2 dives.
2. Domains: the resolved subject's `domains` list from `config.json` (or the derived list for a free-form subject).
3. Choose at the **mechanism level**, never the category level.
   - Bad: "neural networks", "blockchain", "encryption", "Kubernetes" (non-CS: "quantum mechanics", "the immune system", "inflation").
   - Good: "classifier-free guidance and why it trades diversity for fidelity", "Raft split votes and randomized timeouts", "Spectre v1 via branch predictor training", "JIT deoptimization in V8", "LSM-tree compaction: leveled vs tiered", "PagedAttention and KV-cache fragmentation", "TLS 1.3 0-RTT replay", "EVM gas metering and storage refunds", "io_uring submission/completion rings", "flow matching vs diffusion".
4. Prefer topics where something non-obvious happens inside, and where there is real recent work to report. In research mode this is a hard requirement: the topic must have meaningful papers/advancements from the last ~2 years.
5. Actually be random: mentally enumerate ~10 candidates across different domains, then pick one — don't default to the most famous.

## Step 2 — Web research (mandatory, before writing)

Do not explain from memory alone. Research first, thoroughly.

- Web search is required. If the `web_search` tool is not available (session started without `--search`), stop and tell the user to restart with `codex --search` — never write a dive from memory.
- Work through these angles one at a time, running several searches per angle and opening primary sources. After each angle, append dense notes with source URLs to a scratch file (`mktemp -d`, outside the repo) under that angle's heading, so nothing is lost before writing:
  1. **Foundations** — original paper(s), canonical explanation, the actual algorithm/spec/math.
  2. **Implementation reality** — how real systems do it (source code, engineering blogs, docs, RFCs, kernel/compiler source), and where they deviate from the paper. Also return the adoption context for section 1b: which real products/systems use it, why they adopted it, how practitioners call/configure it (API, flags, sample usage), and when people choose alternatives.
  3. **Frontier** — new papers (arXiv, conference proceedings: NeurIPS/ICML/ICLR/USENIX Security/CCS/S&P/OSDI/SOSP/SIGMOD/VLDB/PLDI etc.), recent advancements, benchmarks, what changed in the last 1–2 years. Search widely here: arXiv listing pages, venue proceedings, Semantic Scholar, author pages.
  4. **Breakage + open problems** — known attacks, CVEs, failure modes, critiques, misconceptions, replication failures, and what remains unsolved.
- The frontier angle (3) runs in BOTH modes and must return ≥3–5 recent papers/advancements (last ~2 years) with links, or explicitly report that the topic is settled and where active work moved to.
- In research mode, weight angle 3 heaviest and add a 5th angle for "open problems & active debates" (position papers, workshop discussions, conflicting results).
- Fetch primary sources (arXiv abs/pdf, RFCs, specs, source code) over secondary summaries whenever possible.
- Cross-check any number, date, or paper claim against ≥2 sources or a primary source. If unverified, say so.
- Never cite a paper, benchmark, or API you didn't see in research results.

## Step 3 — Write the dive (in chat)

Primary output is **chat markdown**. Structure:

### 0. Topic card
`Subject · Domain · Topic · Depth (hard|research)`

### 0b. Plain-English first (no jargon)
Mandatory, and it comes BEFORE any technical content. Written for a smart non-engineer:
- **Explain it simply** — 1–2 short paragraphs, zero unexplained jargon, built on an everyday analogy (restaurant, post office, library…). Say what problem it solves and what it does in human terms.
- **Everyday example** — one tiny concrete scenario with made-up but realistic specifics, walked through start to finish in plain words (no code, no symbols). This is the same story the technical trace in section 5 later replays with real data, so pick it to map cleanly.
- **Bridge line** — one sentence: "Now the same thing, technically." Everything below this point may use jargon (defined on first use).

Order of the whole dive is therefore: plain-English → example → real-world context (1b) → technical (everything after).

### 1. Bare-minimum context
At most ~6 bullets: the prerequisites the reader needs to follow along, each one line. Not a tutorial — just enough to not get lost. Link a source for each if they want more.

### 1b. Real-world context (where, how, why)
Ground the topic before diving in. Mandatory. Short subsections, each backed by research (name real systems, versions, numbers; never generic "used in many places"):
- **What it is, in one paragraph** — plain-language definition, no jargon left undefined.
- **Why it exists / why it's used** — the pain it removes, who asked for it, what people did before, what it costs to not have it.
- **Where it's used** — 4–8 concrete systems/products/companies/libraries/kernels/protocols that depend on it, with one line each on the role it plays there.
- **How it's used** — what a practitioner actually touches: the API / config flag / syscall / CLI / library call, a minimal real usage snippet, typical parameter values, and the usual integration pattern.
- **When to use it / when NOT to** — decision rule vs the main alternative; signs you picked wrong.
- **Who should care** — which roles (backend, infra, ML, security…) hit this and in what situation.

### 2. The one-liner — and what it hides
What everyone says about it in one sentence. Then list the 3–5 things that sentence hides; those are what the rest of the dive answers.

### 3. The problem
What was broken or impossible before. Which constraint forced this design. Concrete numbers.

### 4. Mental model
One analogy or picture, then exactly where the analogy breaks.

### 5. The mechanism, traced
Trace ONE concrete example end to end (one request / packet / training step / token / block / syscall). Show the actual data at each step. Pseudocode or small real code where it clarifies. ASCII diagrams for flows and state.

### 6. The math
Derive, don't state. Define every symbol. After each key equation: "→ in plain terms: …". Explain why the equation has *this* form and not a simpler one. Skip section if the topic has no real math — don't invent it.

### 7. Why it works
The core insight. Which property makes it correct / fast / secure. Ablation thinking: remove each key piece and say what breaks.

### 8. Design knobs & alternatives
Parameters and their tradeoffs. Competing approaches, and why this one won (or lost).

### 9. Where it breaks
Failure modes, edge cases, attacks, scaling limits. Misconceptions practitioners hold.

### 10. In the wild
Specific systems / libraries / products using it and how they deviate from the textbook version.

### 11. Frontier (what's new)
Mandatory in both modes. At least 3–5 recent papers / advancements (last ~2 years), each with year, venue, one-line contribution, and link. If the topic is genuinely settled, say so plainly and instead point to where the active work moved (adjacent problem, successor technique) with papers for that — never pad.

In research mode this section is the largest: dissect 2–3 key recent papers in depth (what problem they attacked, the mechanism of their method, results, limitations, follow-ups).

### 11b. Open problems
Mandatory in both modes. What's unsolved, contested, or has conflicting results — and why it's hard (what makes the obvious approach fail). Cite who's working on it where known. Research mode: go deeper, include competing positions.

### 12. Lineage
What it evolved from → what it is → what came after. Key papers with year.

### 13. Hands-on (≤30 min)
One experiment the reader can run or reason through to see the mechanism directly. Include runnable code if feasible.

### 14. Question ladder
15–25 questions that force understanding, not trivia. Group by:
- **Mechanism** — "what exactly happens when…"
- **Why** — "why X and not Y"
- **Counterfactual** — "what if we removed / changed…"
- **Adversarial** — "how would you break it"
- **Connection** — "how does this relate to…"
- **Open** — questions the field hasn't settled

Put each answer in a `<details><summary>Answer</summary>…</details>` block in the saved file; in chat, list the questions first, then an "Answers" section below so the reader can self-test.

### 15. Go deeper next
3 adjacent topics that build directly on this one.

### Sources
All URLs used, grouped by type (papers, code/docs, articles).

### Writing rules
- Depth over breadth. One topic, fully. No survey lists.
- No hand-waving: if you write "it learns to…", "figures out…", "is optimized for…", immediately say HOW.
- Concrete > abstract: real sizes, latencies, parameter counts, byte layouts.
- Reader is a working engineer: skip basics, define domain jargon on first use.
- Flag uncertainty explicitly.

## Step 4 — HTML companion (always)

Every dive ships a polished HTML page alongside the README: `dives/YYYY-MM-DD-<slug>/index.html`. It is the nicer way to read the dive, not a copy-paste of the markdown.

Requirements:
- **Self-contained single file**: inline CSS + JS, no build step. No external design kits; system fonts or one Google Font max. Must work offline.
- **Reading order**: plain-English explainer and everyday example first (visually distinct, open by default, friendly tone), then real-world context, then a clear "Technical deep dive" divider before the rest.
- **Complete**: contains every section of the dive, including 1b real-world context, frontier, open problems, question ladder, sources. Content must match the README (same facts, same links).
- **Layout**: sticky sidebar / top table of contents with scroll-spy, topic card header (subject · domain · topic · depth · date), a "TL;DR + why it matters" hero block, readable measure (~70ch), responsive down to phone width, light + dark via `prefers-color-scheme`.
- **Informative at a glance**: a "Where it's used" card grid (system → role), a "How it's used" code block with copy button, a pros/cons or "use it / skip it" two-column box, a key-numbers strip (latencies, sizes, params), callouts for misconceptions and gotchas.
- **Diagrams**: render flows and state as inline SVG (or styled HTML), not ASCII. Where the topic has a process, add a step-through (Back/Next) of the traced example. Add an interactive widget (slider, toggle, simulator) when a parameter's effect is the point; skip it when forced.
- **Math**: render equations legibly (inline MathML or KaTeX from cdnjs); each followed by its "in plain terms" line.
- **Question ladder**: each question in `<details>` with the answer, grouped by type, plus a "reveal all" toggle.
- **Sources**: grouped, links open in new tab.
- Accessibility: semantic headings, sufficient contrast, keyboard-operable controls, `prefers-reduced-motion` respected.
- Verify before finishing: render it headlessly if a browser is available (e.g. `npx -y playwright screenshot --viewport-size=390,844 file://$PWD/dives/<dir>/index.html shot.png`, plus a desktop-size shot) and look at the screenshots; otherwise at least check the HTML parses, every section/link is present, and JS has no syntax errors (`node --check` on extracted scripts). Say in chat which checks ran.

No hosted pages or artifacts. The deliverable is a plain HTML file in the dive folder, committed to the repo. In chat, mention the file path in one line.

## Step 5 — Save + log + push

1. Write the dive to `dives/YYYY-MM-DD-<slug>/README.md` (same content as chat, answers collapsed in `<details>`) AND `dives/YYYY-MM-DD-<slug>/index.html` (Step 4). Put any code from the hands-on section in the same folder.
2. Append a row to `history.md`:
   `| YYYY-MM-DD | <domain> | <topic> | <hard|research> | [dive](dives/YYYY-MM-DD-<slug>/) · [html](dives/YYYY-MM-DD-<slug>/index.html) | — |`
   (last column = blog link, filled by `$rabbithole blog`). For any subject other than `cs`, write the domain as `<Subject label>: <domain>` (e.g. `Physics: condensed matter`) so history stays readable.
3. **Guard before pushing**: run `git remote get-url origin`; it must be `https://github.com/TheNetherWatcher/rabbithole.git` (or the ssh equivalent), and `history.md` must exist in the cwd. If not, stop and tell the user — never push dives to another repo.
4. `git add` the new dive folder (README.md, index.html, code) + `history.md` by explicit path (never `git add .`/`-A`), commit `dive: <topic>`, `git push`. Commit messages carry NO `Co-Authored-By`, `Signed-off-by`, or AI attribution lines.

## Keeping the two skills in sync

This file (`.agents/skills/rabbithole/SKILL.md`) is the Codex port; `.claude/skills/rabbithole/SKILL.md` is the Claude original. Dive format, HTML spec, history and commit rules must match between them — when changing one, port the change to the other. Only tooling differs (research fan-out, model selection, HTML verification). `.claude/skills/rabbithole/sync.sh` mirrors both into the claude-skills repo.

## Blog mode (`$rabbithole blog [slug]`)

1. Load the dive (default: most recent row in `history.md`).
2. Write `blog/YYYY-MM-DD-<slug>.md` with front matter (`title`, `date`, `tags`, `summary`). It's a narrative essay, not the dive reformatted: hook with the surprising thing, build the mechanism as a story, keep the best 1–2 diagrams and the key equation, end with the open question. ~1500–2500 words. First person is fine. Keep sources.
3. Show draft in chat, ask for edits before committing.
4. On approval: update blog column in `history.md`, commit `blog: <title>`, push.
