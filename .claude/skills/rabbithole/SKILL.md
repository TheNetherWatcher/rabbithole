---
name: rabbithole
model: haiku
description: Deep, web-researched dive into ONE random non-trivial topic in a configurable subject (default CS — ML/AI, security, systems, distributed, DBs, networking, crypto, compilers, blockchain, graphics, hardware...; also math, physics, biology, medicine, economics, or any free-form subject) opening with real-world context (where/how/why it is used), then explained down to the mechanism, math, design reasoning, failure modes, and latest research, ending with a question ladder. Saves a README plus a layered interactive HTML page per dive (skim cards with a hero emblem, each expanding into its in-depth section). Logs every dive to history.md and the private rabbithole repo; can turn a dive into a blog post. Use when the user says /rabbithole, "deep dive", "teach me something random in CS" (or any subject), "rabbit hole", or asks to blog a past dive.
---

# rabbithole

One topic. All the way down. Researched from the web, explained in chat, saved to the repo.

All files live in the current working directory (the repo root): `history.md` is here, dives go in `dives/`, blog posts in `blog/`. Never read or write history anywhere else.

## Invocation

| Command | What happens |
|---|---|
| `/rabbithole` | Random topic, **hard** depth: full mechanism + math + design + failure modes, PLUS a frontier section (≥3–5 recent papers) and an open-problems section |
| `/rabbithole research` | Random topic, **research** depth: everything in hard, but frontier-heavy — topic must have active recent research, 2–3 key recent papers dissected in depth, extra open-debates research |
| `/rabbithole <topic>` | User-chosen topic, hard depth (add `research` anywhere for research depth) |
| `/rabbithole blog [slug]` | Turn a saved dive (default: latest) into a blog post in `blog/` |
| `/rabbithole history` | Show past dives grouped by domain (the visual version is `dives/index.html`) |
| `/rabbithole upgrade [slug]` | Convert a classic dive (single hand-written `index.html`, no `dive.json`) to the card format: write `dive.json`, `sections/`, `img/` from its README + existing page (reuse its widgets), build, rebuild the hub, commit `dive: upgrade <topic> to cards` |
| `subject:<name>` (combine with any of the above) | Pick the topic from another subject for this run, e.g. `/rabbithole subject:physics research`. `<name>` is a key in `config.json` → `subjects`, or any free-form subject (`subject:"music theory"`) |

## Configuration

`config.json` (next to this file) holds defaults:
- `subject` — default subject key when no `subject:` token is given (`cs` out of the box).
- `subjects.<key>` — `label` + `domains` list for each preset subject.
- `research_model` — model for the Step 2 research subagents (`haiku` by default; `sonnet`/`opus` for a harder topic). The skill itself runs on Haiku via the `model:` frontmatter, since the job is research + presentation, not novel reasoning. A `model:<name>` token in the invocation overrides `research_model` for that run.

Resolve the subject once per run: `subject:` token > `config.json` `subject`. If the subject is free-form (not a preset key), derive 10–15 mechanism-rich domains for it yourself before Step 1 and use those. The rest of the skill is subject-agnostic: "system", "implementation", "in the wild" mean the real-world practice of that subject (labs, instruments, clinical protocols, markets, proofs…), not software, unless the subject is CS.

## Step 1 — Pick the topic (random modes)

1. Read `history.md`. Never repeat a topic. Don't repeat the domain of the last 2 dives.
2. Domains: the resolved subject's `domains` list from `config.json` (or the derived list for a free-form subject).
3. Choose at the **mechanism level**, never the category level.
   - Bad: "neural networks", "blockchain", "encryption", "Kubernetes" (non-CS: "quantum mechanics", "the immune system", "inflation").
   - Good: "classifier-free guidance and why it trades diversity for fidelity", "Raft split votes and randomized timeouts", "Spectre v1 via branch predictor training", "JIT deoptimization in V8", "LSM-tree compaction: leveled vs tiered", "PagedAttention and KV-cache fragmentation", "TLS 1.3 0-RTT replay", "EVM gas metering and storage refunds", "io_uring submission/completion rings", "flow matching vs diffusion".
4. Prefer topics where something non-obvious happens inside, and where there is real recent work to report. In research mode this is a hard requirement: the topic must have meaningful papers/advancements from the last ~2 years.
5. Actually be random: mentally enumerate ~10 candidates across different domains, then pick one — don't default to the most famous.

## Step 1b — Log the entry (before any research)

Once the topic is picked (or confirmed, for `topic:` modes), write its `history.md` row NOW, before launching any research. This reserves the topic so it is never repeated, even if the run dies mid-research.

1. Append a row to `history.md`:
   `| YYYY-MM-DD | <domain> | <topic> | <hard|research> | [dive](dives/YYYY-MM-DD-<slug>/) · [html](dives/YYYY-MM-DD-<slug>/index.html) | — |`
   (last column = blog link, filled by `/rabbithole blog`). For any subject other than `cs`, write the domain as `<Subject label>: <domain>` (e.g. `Physics: condensed matter`) so history stays readable.
2. Fix the slug and folder name here; Steps 3–5 reuse them.
3. Do not commit or push yet; that happens in Step 5 with the dive.
4. If the run is abandoned before the dive is saved (user cancels, topic unresearchable), delete the row again.

## Step 2 — Web research (mandatory, before writing)

Do not explain from memory alone. Research first, thoroughly.

- Fan out: launch 3–4 parallel `general-purpose` subagents (one message) with `model` set to the resolved `research_model` (default `"haiku"`), each with a distinct angle, each told to return dense notes with source URLs:
  1. **Foundations** — original paper(s), canonical explanation, the actual algorithm/spec/math.
  2. **Implementation reality** — how real systems do it (source code, engineering blogs, docs, RFCs, kernel/compiler source), and where they deviate from the paper. Also return the adoption context for section 1b: which real products/systems use it, why they adopted it, how practitioners call/configure it (API, flags, sample usage), and when people choose alternatives.
  3. **Frontier** — new papers (arXiv, conference proceedings: NeurIPS/ICML/ICLR/USENIX Security/CCS/S&P/OSDI/SOSP/SIGMOD/VLDB/PLDI etc.), recent advancements, benchmarks, what changed in the last 1–2 years. Use WebSearch `extended` mode here.
  4. **Breakage + open problems** — known attacks, CVEs, failure modes, critiques, misconceptions, replication failures, and what remains unsolved.
- Every agent also returns **figure candidates**: up to 4 figures from its sources that explain the mechanism better than prose (architecture diagrams, worked examples, the key result plot). For each: source URL, figure number and caption, and the source's license as stated on the page (arXiv abs page sidebar, repo LICENSE, docs footer). Unknown license means "not open".
- Frontier agent (angle 3) runs in BOTH modes and must return ≥3–5 recent papers/advancements (last ~2 years) with links, or explicitly report that the topic is settled and where active work moved to.
- In research mode, weight angle 3 heaviest and add a 5th agent for "open problems & active debates" (position papers, workshop discussions, conflicting results).
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

## Step 4 — HTML companion (always): layered cards

Every dive ships a page at `dives/YYYY-MM-DD-<slug>/index.html` with two layers: a **skim layer** (hero emblem, TL;DR, stat tiles, then one short card per section) and a **deep layer** (each card's "Go deeper" expands that section's full content in place). A reader should get the whole topic in ~3–5 minutes from the briefs alone, and open only the parts they want.

You do NOT hand-write `index.html`. You write source files, and `build.py` (next to this SKILL.md) stitches them with the shared template (`template/`) into one self-contained file. Look at `dives/2026-10-10-pagedattention-kv-cache/` as the reference example and copy its structure.

### Source files (in the dive folder)

```
dive.json          meta, hero, tldr, why, stats, ordered cards, questions
sections/NN-*.html one fragment per card: the deep content for that section
img/hero.svg       hero emblem (or img/hero.txt for ASCII art)
img/<card>.svg     one small visual per card
```

**`dive.json`** shape:

```json
{
  "meta": {"title": "...full title...", "short": "2–5 word name", "subject": "Computer science",
           "domain": "LLM systems", "topic": "...", "depth": "hard", "date": "YYYY-MM-DD"},
  "hero": "img/hero.svg",
  "tldr": "2–3 sentences, <b> on the 2–3 key facts",
  "why": "<b>Why it matters:</b> one sentence",
  "stats": [{"v": "96.3%", "l": "what the number means"}],
  "cards": [
    {"id": "plain", "group": "Plain English", "tone": "plain", "kicker": "In everyday words",
     "title": "Headline that states the takeaway", "visual": "img/plain.svg",
     "file": "sections/00-plain.html", "brief": "<p>…</p>"},
    {"id": "quiz", "builtin": "quiz", "kicker": "§14 · Question ladder", "title": "Test yourself",
     "visual": "img/quiz.svg", "brief": "<p>N questions…</p>"}
  ],
  "questions": [{"type": "Mechanism", "q": "...", "a": "...", "sec": "mech"}],
  "figures": {
    "fig6": {"file": "img/fig/vllm-fig6-block-table.png",
             "caption": "What the figure shows, in one sentence, tied to this section",
             "source": {"cite": "Kwon et al., \"Efficient Memory Management …\", SOSP 2023",
                        "url": "https://arxiv.org/abs/2309.06180", "figure": "Fig. 6"},
             "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
             "modified": "cropped and recompressed"}
  }
}
```

- **Cards**: one per dive section, in dive order: plain-English (`tone: "plain"`), 1 context, 1b real-world, 2 one-liner, 3 problem, 4 mental model, 5 mechanism, 6 math, 7 why it works, 8 knobs, 9 where it breaks, 10 in the wild, 11 frontier, 11b open problems, 12 lineage, 13 hands-on, 14 question ladder (`builtin: "quiz"`, no `file`), 15 go deeper, sources. A `group` on a card starts a labelled band: "Plain English", "Context", "Technical deep dive", "Research edge", "Practice & self-test", "Further".
- **Card `title`** states the takeaway, not the section name ("Contiguous reservation wastes 60–80% of KV memory", not "The problem"). `kicker` carries the section number and name.
- **Card `brief`**: the skim layer. 2–4 sentences or ≤3 bullets, ≤60 words, with the section's single most important number or fact. It must stand on its own: someone who reads only briefs should understand the topic. If the deep part has an interactive widget, end with `<p class="mini">… interactive inside.</p>`.
- **`questions`**: the full question ladder (Step 3 §14) with answers. `type` is the group (Mechanism, Why, Counterfactual, Adversarial, Connection, Open). `sec` is the card id that teaches the answer. Answers are HTML strings.
- **`stats`**: 3–5 key numbers. A value that is a single number plus a unit ("96.3%", "128 KiB") counts up on screen; ranges ("2–4×") stay static.

**`sections/*.html`**: plain HTML fragments, no `<html>`/`<body>`, no `<h2>` (the card supplies the title; start subsections at `<h3>`). Content = the full section from the dive, same facts and links as the README. Use the content kit classes from `template/app.css`: `.eq` (equation, with `<small>→ in plain terms: …</small>`), `.grid`+`.gc` (where-it's-used cards), `.two` with `.use`/`.skip`, `.callout.mis|.gotcha|.flag|.tip`, `table`, `pre><code` (copy buttons are automatic), `blockquote`, `.widget` + `.stepbar` + `.ctl` + `.bar` (interactive widgets), `button.btn`, `.mini`. A section may include its own `<style>` (scope selectors under a unique id) and `<script>` (wrap it in an IIFE; it runs at page load, collapsed or not). Prefix every element id with the card id (`mech-step`, not `step`) so ids never collide. Links open in a new tab (`target="_blank" rel="noopener"`).

Where the topic has a process, the mechanism section gets a Back/Next step-through of the traced example. Add an interactive widget (slider, toggle, simulator) when a parameter's effect is the point; skip it when forced. Render equations as legible HTML (sub/sup, Unicode math) in `.eq` blocks.

### Images

The hero, card visuals and your own diagrams are hand-authored inline SVG: no AI-generated images, no stock photos. Real figures from sources go only in the deep layer, under the rules in "Reference figures" below. SVGs are inlined raw, so they pick up the page theme. Color them ONLY with the palette helper classes, never hex colors: fills `f-bg f-bg2 f-panel f-code f-line f-ink f-mute f-acc f-acc2 f-ok f-warn f-bad f-hl f-none`, strokes `s-ink s-mute s-line s-acc s-acc2 s-ok s-warn s-bad`, text `t-ink t-mute`. Motion helpers: `draw` (stroke draws in when scrolled into view; stagger with `style="--d:1"`), `flow` (dashes travel along a path), `pulse`, `float`, `blink`. No ids inside card visuals.

**Hero emblem (`img/hero.svg`)**: an abstract picture of the core mechanism, not a literal illustration and with no text. Built from geometry (grids, blocks, nodes, edges, waves, lattices) that encodes the idea. PagedAttention's hero is a pool of KV blocks with scattered allocated blocks, block-table pointers running to them, a shared copy-on-write block pulsing and the next block blinking in. Other examples: BBR, a pipe whose rate line probes up and settles on a plateau; XOR filters, a hypergraph peeling edge by edge; ML-KEM, a lattice with a noisy point snapping to a vertex.
- `viewBox="0 0 1200 320"`, `preserveAspectRatio="xMidYMid slice"`. Keep important shapes within y 60–280 and x 60–1140, since edges get cropped on some screens.
- 3–4 top-level `<g class="layer" data-depth="0.05…0.32">` groups, back to front. The page staggers their intro and moves them at different speeds on scroll (parallax). Put a subtle background (dot pattern via `<pattern>`) in the first layer.
- Animate at most 2–3 elements (`flow`, `pulse`, `blink`). Nothing frantic. ≤ ~12 KB: use `<pattern>` and loops instead of thousands of elements. Generate with a short Python script when there are many shapes.
- ASCII alternative: for terminal-flavoured topics (schedulers, syscalls, allocators, shells) you may set `"hero": "img/hero.txt"` with ≤ 12 lines × 70 cols of box-drawing/ASCII art. It plays a scramble-then-resolve intro.

**Card visuals (`img/<id>.svg`)**: one per card, `viewBox="0 0 160 100"`, a glyph-sized diagram of that card's idea (utilization bars for the problem, block-table arrows for the mechanism, a curve with a minimum for the math, a sawtooth for thrash, a timeline for frontier, a terminal for hands-on). 5–25 shapes, ≤ 2 KB. A tiny label (`t-mute`) is fine; sentences are not.

### Reference figures (from papers, docs, repos)

Inside the deep layer, real figures from the sources make a section concrete: the paper's own architecture diagram next to your step-through, the headline result plot next to the numbers. Aim for 6–16 per dive, placed where the text discusses them, never as a gallery. Card visuals and the hero stay hand-drawn SVG.

**License gate (hard rule).** Citing is not permission. Embed a figure only when its source carries an open license: CC BY, CC BY-SA, CC0, public domain, or a permissive code/docs license (Apache-2.0, MIT, BSD) for figures in a repo or its docs. CC BY-NC is allowed in this private repo but must never go into blog posts. Do NOT embed ND-licensed figures (no modified copies), arXiv's default "non-exclusive license to distribute", publisher PDFs (ACM/IEEE/Springer copyright), vendor blogs, or anything with an unstated license. For those, link to the figure ("see Fig. 3 of [paper]") or redraw the idea as an original diagram (below) whose source says what it is adapted from. `build.py` enforces this: it refuses non-open licenses and ND, and every figure needs a caption, cite, URL and license.

Check the license on the source itself: the arXiv abs page names it in the sidebar (`curl -sL https://arxiv.org/abs/<id> | grep -oE 'licenses/[a-z-]+/[0-9.]+|nonexclusive-distrib'`); repos have a LICENSE file; docs sites state it in the footer or repo.

**Getting the image.**
- arXiv papers: download the source tarball (`https://arxiv.org/e-print/<id>`) into a new empty folder in the scratchpad and extract it there. The `figures/` (or `graphs/`) folder has the original vector PDFs/PNGs, and grepping the `.tex` for `includegraphics` maps file → figure number, caption and any `trim=`. Only read image files from it; never run or `\input` anything. Newer papers also serve PNGs from their HTML version (`https://arxiv.org/html/<id>`).
- Docs and repos: the image file from the repo (`raw.githubusercontent.com/...`).
- Never screenshot a rendered PDF page when the original figure file is available.

**Preparing it**: `python3 <skill-dir>/fig.py <src.pdf|png|jpg> dives/<folder>/img/fig/<source>-fig<N>-<what>.png [--trim L,B,R,T]` renders PDFs, applies a LaTeX-style trim, strips white margins, caps width at 1400 px and writes a palette PNG (20–80 KB). Look at every result (Read the PNG) before using it; re-crop if it carries a stray caption or whitespace.

**Placing it**: register it under `figures` in `dive.json`, then drop `<figure data-fig="<id>"></figure>` into the section HTML where the text refers to it. Two side by side: wrap them in `<div class="fig-pair">…</div>`. Precede a figure with a sentence that says what to look at. `build.py` turns each placeholder into a numbered figure (page order) with the image, your caption, a "Source: … · Fig. N · license · modifications" line, click-to-zoom, and appends a "Figure credits" list to the sources card (or the card with `"credits": true`). Captions are your own words, not the paper's caption copied.

**Original diagrams** (always allowed, and the fallback when no source is openly licensed): draw your own SVG at `img/fig/own-<what>.svg` (viewBox ~640–900 wide, palette classes only, no hex colors, labels ≥12 px, real values from the dive, ≤12 KB) and register it with `"original": true` and no license: `{"original": true, "file": "img/fig/own-x.svg", "caption": "…", "source": {"cite": "…", "url": "…", "figure": "Fig. N"}}`. Give `source` only when the drawing is adapted from a specific figure or article; the page then credits it "Original diagram · adapted from …". Original SVGs are inlined, so they follow the light/dark theme, and they are numbered with the other figures. Preview them by rendering a copy with a `<style>` block that maps the palette classes to colors (`rsvg-convert` or `qlmanage -t`), and look at the result. A dive with no openly licensed sources should still get 4–8 original diagrams.

### Build and verify

```bash
python3 <skill-dir>/build.py dives/YYYY-MM-DD-<slug>   # writes index.html (prints size, card count, skim/deep minutes)
python3 <skill-dir>/build.py --hub dives                # refreshes dives/index.html, the visual index of all dives
```

`<skill-dir>` is the directory containing this SKILL.md (`.claude/skills/rabbithole` in the rabbithole repo). Never edit the generated `index.html` by hand; fix the sources or the template and rebuild. Template changes (`template/app.css`, `app.js`, `dive.html`, `hub.html`) apply to every dive on rebuild.

Verify before finishing. `file://` pages can't be opened by the browser tools, so serve the repo: `python3 -m http.server 8765 --bind 127.0.0.1` (in the background), open `http://127.0.0.1:8765/dives/<folder>/index.html` with `mcp__claude-in-chrome__*`, and check: no console errors; the hero renders; cards expand and collapse; the step-through and widgets work inside expanded cards; figures render, zoom opens and Esc closes it, and the credits list is complete; quiz reveal and ✓/✗ marks update the ring; no horizontal overflow at 375 px (test in a 390 px iframe if the window won't resize). Stop the server afterwards.

What the template gives every page for free (don't rebuild these): sticky top bar with a progress ring, Expand-all toggle (deep mode, remembered), light/dark toggle, side dot-nav, scroll reveal, stat count-up, card expand animation, "Got it" checkboxes, quiz with self-marking, progress saved per browser (`localStorage` key `rh:p:<folder>`), deep links (`#c-<card id>` opens that card), `prefers-reduced-motion` support.

Do NOT create a Claude artifact and do NOT use the Artifact tool. The deliverable is the built HTML file plus its sources in the dive folder, committed to the repo. In chat, mention the file path in one line.

## Step 5 — Save + log + push

1. Write the dive to `dives/YYYY-MM-DD-<slug>/README.md` (same content as chat, answers collapsed in `<details>`; it is the plain-markdown fallback and the source for blog mode) AND the Step 4 sources (`dive.json`, `sections/`, `img/`), then run `build.py` for the dive and `build.py --hub dives`. Put any code from the hands-on section in the same folder.
2. The `history.md` row was already written in Step 1b. Confirm it exists and its links match the saved folder; fix it if the slug changed. Do not append a duplicate.
3. **Guard before pushing**: run `git remote get-url origin`; it must be `https://github.com/TheNetherWatcher/rabbithole.git` (or the ssh equivalent), and `history.md` must exist in the cwd. If not, stop and tell the user — never push dives to another repo.
4. `git add` the new dive folder (README.md, dive.json, sections/, img/ including img/fig/, index.html, code) + `dives/index.html` + `history.md` by explicit path (never `git add .`/`-A`), commit `dive: <topic>`, `git push`. Commit messages carry NO `Co-Authored-By`, `Signed-off-by`, or AI attribution lines.

## Skill sync (when the skill itself changes)

The skill (`SKILL.md`, `config.json`, `build.py`, `fig.py`, `template/`) lives only here (`.claude/skills/rabbithole/`). The claude-skills repo links to this repo as the `rabbithole-repo` git submodule, with `rabbithole` symlinked to `rabbithole-repo/.claude/skills/rabbithole`, so there is no copy to keep in sync, only a pinned commit to bump. After any edit:
1. Commit here (`skill: <change>`, no attribution lines) and push.
2. Run `.claude/skills/rabbithole/sync.sh`: it moves the claude-skills submodule to the pushed `origin/main` and prints `git status` there.
3. Commit the new pointer in claude-skills (`update rabbithole skill`, no attribution lines) and push.

## Blog mode (`/rabbithole blog [slug]`)

1. Load the dive (default: most recent row in `history.md`) from its README.md.
2. Write `blog/YYYY-MM-DD-<slug>.md` with front matter (`title`, `date`, `tags`, `summary`). It's a narrative essay, not the dive reformatted: hook with the surprising thing, build the mechanism as a story, keep the best 1–2 diagrams and the key equation (reference figures only if CC BY / CC0 / permissive, never NC, with the same credit line), end with the open question. ~1500–2500 words. First person is fine. Keep sources.
3. Show draft in chat, ask for edits before committing.
4. On approval: update blog column in `history.md`, commit `blog: <title>`, push.
