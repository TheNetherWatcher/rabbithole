---
name: rabbithole
description: Deep, web-researched dive into ONE random non-trivial CS topic (ML/AI, security, systems, distributed, DBs, networking, crypto, compilers, blockchain, graphics, hardware...) explained down to the mechanism, math, design reasoning, failure modes, and latest research, ending with a question ladder. Logs every dive to history.md and the private rabbithole repo; can turn a dive into a blog post. Use when the user says /rabbithole, "deep dive", "teach me something random in CS", "rabbit hole", or asks to blog a past dive.
---

# rabbithole

One CS topic. All the way down. Researched from the web, explained in chat, saved to the repo.

All files live in the current working directory (the repo root): `history.md` is here, dives go in `dives/`, blog posts in `blog/`. Never read or write history anywhere else.

## Invocation

| Command | What happens |
|---|---|
| `/rabbithole` | Random topic, **hard** depth (mechanism + math + design + failure modes + recent work) |
| `/rabbithole research` | Random topic, **research** depth: frontier-focused, papers from the last ~18 months, open problems, what's contested |
| `/rabbithole <topic>` | User-chosen topic, hard depth (add `research` anywhere for research depth) |
| `/rabbithole blog [slug]` | Turn a saved dive (default: latest) into a blog post in `blog/` |
| `/rabbithole history` | Show past dives grouped by domain |

## Step 1 — Pick the topic (random modes)

1. Read `history.md`. Never repeat a topic. Don't repeat the domain of the last 2 dives.
2. Domains: ML/AI · LLM systems · security/offense · cryptography · OS/kernels · distributed systems · databases/storage · networking/protocols · compilers/PL/runtimes · blockchain · graphics/GPU · hardware/architecture · algorithms/data structures · browsers/web internals · formal methods.
3. Choose at the **mechanism level**, never the category level.
   - Bad: "neural networks", "blockchain", "encryption", "Kubernetes".
   - Good: "classifier-free guidance and why it trades diversity for fidelity", "Raft split votes and randomized timeouts", "Spectre v1 via branch predictor training", "JIT deoptimization in V8", "LSM-tree compaction: leveled vs tiered", "PagedAttention and KV-cache fragmentation", "TLS 1.3 0-RTT replay", "EVM gas metering and storage refunds", "io_uring submission/completion rings", "flow matching vs diffusion".
4. Prefer topics where something non-obvious happens inside, and where there is real recent work to report.
5. Actually be random: mentally enumerate ~10 candidates across different domains, then pick one — don't default to the most famous.

## Step 2 — Web research (mandatory, before writing)

Do not explain from memory alone. Research first, thoroughly.

- Fan out: launch 3–4 parallel `general-purpose` subagents (one message), each with a distinct angle, each told to return dense notes with source URLs:
  1. **Foundations** — original paper(s), canonical explanation, the actual algorithm/spec/math.
  2. **Implementation reality** — how real systems do it (source code, engineering blogs, docs, RFCs, kernel/compiler source), and where they deviate from the paper.
  3. **Frontier** — new papers (arXiv, conference proceedings: NeurIPS/ICML/ICLR/USENIX Security/CCS/S&P/OSDI/SOSP/SIGMOD/VLDB/PLDI etc.), recent advancements, benchmarks, what changed in the last 1–2 years. Use WebSearch `extended` mode here.
  4. **Breakage** — known attacks, CVEs, failure modes, critiques, misconceptions, replication failures.
- In research mode, weight angle 3 heaviest and add a 5th agent for "open problems & active debates".
- Fetch primary sources (arXiv abs/pdf, RFCs, specs, source code) over secondary summaries whenever possible.
- Cross-check any number, date, or paper claim against ≥2 sources or a primary source. If unverified, say so.
- Never cite a paper, benchmark, or API you didn't see in research results.

## Step 3 — Write the dive (in chat)

Primary output is **chat markdown**. Structure:

### 0. Topic card
`Domain · Topic · Depth (hard|research)`

### 1. Bare-minimum context
At most ~6 bullets: the prerequisites the reader needs to follow along, each one line. Not a tutorial — just enough to not get lost. Link a source for each if they want more.

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
Recent papers and advancements with year, venue, one-line contribution, and link. What's contested or open. In research mode this section is the largest and goes deep on 2–3 key recent papers (what they changed, how, results, limitations).

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

## Step 4 — HTML only when it earns it

Default is chat only. Make an HTML companion **only** if the topic has something text can't show well: an interactive visualization, an animation of a process, a step-through state machine, a parameter you can drag to see the effect. Plain, self-contained single file (no external design kits), saved to `dives/<slug>/index.html`, and published with the Artifact tool. Mention it in chat with one line.

## Step 5 — Save + log + push

1. Write the dive to `dives/YYYY-MM-DD-<slug>/README.md` (same content as chat, answers collapsed in `<details>`). Put any HTML/code in the same folder.
2. Append a row to `history.md`:
   `| YYYY-MM-DD | <domain> | <topic> | <hard|research> | [dive](dives/YYYY-MM-DD-<slug>/) | — |`
   (last column = blog link, filled by `/rabbithole blog`).
3. `git add` the new files + `history.md`, commit `dive: <topic>`, `git push`.

## Blog mode (`/rabbithole blog [slug]`)

1. Load the dive (default: most recent row in `history.md`).
2. Write `blog/YYYY-MM-DD-<slug>.md` with front matter (`title`, `date`, `tags`, `summary`). It's a narrative essay, not the dive reformatted: hook with the surprising thing, build the mechanism as a story, keep the best 1–2 diagrams and the key equation, end with the open question. ~1500–2500 words. First person is fine. Keep sources.
3. Show draft in chat, ask for edits before committing.
4. On approval: update blog column in `history.md`, commit `blog: <title>`, push.
