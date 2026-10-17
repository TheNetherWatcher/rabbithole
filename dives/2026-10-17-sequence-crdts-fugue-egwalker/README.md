# Sequence CRDTs for collaborative text: RGA, Fugue and Eg-walker

**Computer science · Distributed systems · Sequence CRDTs for collaborative text (interleaving, tombstones, event-graph replay) · hard**

Interactive version: [index.html](index.html). Runnable simulation: [seq_crdt_sim.py](seq_crdt_sim.py).

> Trust note: Eg-walker claims and numbers were checked against the paper's LaTeX source and rendered figures. Fugue's algorithm, Definition 4 and benchmarks were quoted from its arXiv HTML. RGA mechanics are a secondary-source summary (the original paper was not retrievable). Items marked "abstract only", "snippet" or "from memory" were not verified.

## Plain English first

Two housemates photocopy a shared shopping list and each add a word at the bottom (*eggs*, *bread*) with no referee to decide who goes first. "Line 3" means different things once someone adds a line above it, so every written character gets a permanent name tag and an addition says "put this right after tag `o4`". That fixes one problem and creates two: both housemates said "right after *milk*", so a tie-break must order them, and a careless rule weaves the words into `ebgrgesad`; and to stay safe the app keeps a tag for every letter ever typed, so the file outgrows the text.

**Now the same thing, technically.**

## 1. Bare-minimum context

- Replication without a leader; goal is strong eventual consistency (same operations seen, same state).
- Two operations are *concurrent* if neither author saw the other.
- OT transforms index operations; CRDTs give elements IDs so operations commute.
- A *tombstone* is a deleted element kept as a hidden marker.
- *Interleaving*: characters of two concurrent runs end up woven together.

## 1b. Real-world context

A sequence CRDT stores a document as a list of characters with unique IDs plus metadata that decides where concurrent insertions go. Zed [tried OT in 2017 and chose a CRDT](https://zed.dev/blog/crdts). Used in **Yjs** (YATA-derived), **Automerge**, **Loro** (Fugue text, Eg-walker), **diamond-types**, and Zed's editor. Not CRDTs: **Figma** (server-authoritative, last-writer-wins per property) and **Google Docs** (OT, central server, 2010 source). Notion says offline pages migrate to a "new CRDT data model"; the text algorithm is not stated.

```js
import * as Y from 'yjs'
const doc = new Y.Doc()
const text = doc.getText('note')
text.insert(0, 'milk')
// exchange updates: Y.applyUpdate(otherDoc, updateBytes)
```

Use a text CRDT for offline or peer-to-peer editing; skip it when one always-reachable service owns the document (server-ordered OT or field-level last-writer-wins carries far less metadata).

## 2. The one-liner, and what it hides

"Unique IDs make all copies converge." It hides: (1) the tie-break decides readability, not just convergence; (2) tombstones can't be dropped; (3) metadata outweighs the text (105 kB text saves to 168 kB in the Fugue paper's benchmark); (4) a CRDT isn't needed for most of history (Eg-walker); (5) convergence is not intention preservation.

## 3. The problem

- Positions shift: on `Helo`, User 1's `Insert(3,'l')` and User 2's `Insert(4,'!')`; applying the second as-is gives `Hell!o`.
- OT is quadratic on diverged branches: trace A1 6.3 s, trace A2 **61.1 min** (Eg-walker paper, Fig. 8).
- CRDTs are heavy: Automerge 241–848 MiB, Yjs 19–30 MiB while merging; Eg-walker's steady state is about 1 MiB or less.

Forcing constraint: every replica must compute the same order for concurrent inserts independently, and deleted elements can't be forgotten.

## 4. Mental model

A library shelf where each book has a barcode and instructions say "put me after book 7731". Breaks where: two librarians shelve runs after the same book (needs a tie-break); a discarded book must leave a bookmark; there is no head librarian.

## 5. The mechanism, traced

Start from `XZ`. A types `abc` backwards (insert `c`, `b`, `a`, each at index 1); B types `xyz` the same way.

**RGA** (insert after an anchor, ties by descending (lamport, replica) ID): all six inserts share anchor `X`, sorted `x(5,B) a(5,A) y(4,B) b(4,A) z(3,B) c(3,A)` → `XxaybzcZ`. Interleaved.

**Fugue** (insert: left origin has no right child → right child of it, else left child of the next element; list = in-order walk; same-side siblings by ID): `c` becomes a left child of `Z`, `b` a left child of `c`, `a` a left child of `b`; B builds a parallel chain under `Z`. Subtrees are contiguous → `XabcxyzZ`.

**Eg-walker** keeps the event graph and plain text; during a merge it builds a temporary CRDT over the concurrent stretch with two states per character: prepare (`NotInsertedYet`, `Ins`, `Del n`) and effect (`Ins`, `Del`), moved by `apply`, `retreat`, `advance`. At a *critical version* (all earlier events are ancestors, all later ones descendants) the state is discarded. Worked example from the paper: `hi` → `hey` and `Hi` concurrently, then `!`, giving `Hey!`.

## 6. The math

- order(n) = order(L₁)…order(Lₚ), n, order(R₁)…order(R_q), siblings on a side in ID order. Order depends only on the set of nodes, so inserts commute.
- RGA: place after `prev`, then skip while `next.id > e.id`.
- Eg-walker merge of branches with k and m events: O((k+m) log(k+m)); worst case O(n² log n); poor traversal order made one trace up to 8× slower.
- Prepare state counts deletions (`Del n`) so retreating one of two concurrent deletes doesn't resurrect the character.

## 7. Why it works

Identity turns "where" into a relationship each replica resolves the same way; the tie-break decides readability. Ablation: no IDs → shifted indexes; no ID tie-break → divergence; no tombstones → dangling anchors; per-character tie-break → interleaving; no prepare/effect split → pairwise transformation again; no clearing → S1 merge 1.8 → 9.8 ms, S3 3.6 → 24.4 ms (Fig. 9).

## 8. Design knobs and alternatives

OT (quadratic merges), RGA (forward non-interleaving proved; backward interleaves), Yjs (RLE structs; partial GC), Fugue/FugueMax (maximal non-interleaving for FugueMax), Eg-walker (event graph; conjectured maximal non-interleaving; plain text only). Knobs: GC, run-length encoding, cached text, traversal order.

## 9. Where it breaks

Interleaving (Fugue Figs. 1–2); the 2019 PaPoC paper's errata; tombstones and causal stability; metadata (about 23 bytes per live character, 13 per character counting tombstones; simple Fugue variants 618–685 bytes/char); Eg-walker limits (plain text, worst case, single-node benchmarks, conjectured property); rich text, move, undo, cursors.

## 10. In the wild

crdt-benchmarks B4 (259,778 ops, 104,852 final chars): Yjs 5.7 s / 159,929 B; Loro 3.1 s / 258,228 B; Automerge 14.3 s / 129,116 B. "CRDTs go brrr": Automerge (old) 291 s / 880 MB, Yjs 0.97 s / 3.3 MB, diamond-types native 0.056 s / 1.1 MB. Fugue: 94k ops/s, 2.4 MB vs Yjs 39k ops/s, 3.3 MB. Deviations: Yjs RLE and partial GC; diamond-types range tree + rope; Zed anchors, fragments and version-vector deletes; Figma no CRDT.

## 11. Frontier

- **Eg-walker** (Gentle & Kleppmann, EuroSys 2025, [arXiv 2409.14252](https://arxiv.org/abs/2409.14252)): A2 merge 23.5 ms vs OT 61.1 min vs Yjs 74.2 ms vs Automerge 520 ms; steady-state RAM 73 KiB–1 MiB; plain text only.
- **Fugue / FugueMax** (Weidner & Kleppmann, IEEE TPDS 2025, [arXiv 2305.00583](https://arxiv.org/abs/2305.00583)): defines and proves maximal non-interleaving.
- Pointers (abstract or snippet only): [ESBT](https://arxiv.org/abs/2607.28101) (Jul 2026), [Brocco Byzantine CRDT layer](https://arxiv.org/abs/2606.18966) (Jun 2026), [undo/redo for registers](https://arxiv.org/abs/2404.11308) (PaPoC 2024), [JSON CRDT moves](https://arxiv.org/abs/2311.14007) (2023).

## 11b. Open problems

Is Eg-walker's tie-break maximally non-interleaving? Safe tombstone GC without a known replica set. Rich-text blocks. Undo, move and cursors. Semantic merge conflicts. Byzantine replicas.

## 12. Lineage

OT (1989, from memory) → WOOT (2006) / Logoot (2009), from memory → RGA (Roh et al., JPDC 2011) → YATA/Yjs (2016, from memory) → interleaving anomalies (PaPoC 2019) → Peritext (CSCW 2022) → Fugue (2023, TPDS 2025) → Eg-walker (2024, EuroSys 2025).

## 13. Hands-on

```
python3 seq_crdt_sim.py
forward typing (a, b, c)
  RGA    -> XxyzabcZ   runs stay whole
  Fugue  -> XabcxyzZ   runs stay whole
backward typing (c, b, a)
  RGA    -> XxaybzcZ   INTERLEAVED
  Fugue  -> XabcxyzZ   runs stay whole
```

Try: forward vs backward; different word lengths; flip RGA's skip rule; add a third replica; delete a character on one replica and insert after it on another.

## 14. Question ladder

**Mechanism**

1. On `Helo`, why must `Insert(4,'!')` become `Insert(5,'!')` on User 1, and how do IDs avoid this?
2. In Fugue, when is a new node a right child and when a left child?
3. What do s_p and s_e mean in Eg-walker, and why two?
4. Why does s_p count deletions?

**Why**

5. Why does an in-order walk keep a typed run contiguous?
6. Why must same-side siblings use a total order on IDs?
7. Why does RGA interleave backward but not forward typing?
8. Why do CRDTs keep everything in memory while Eg-walker doesn't?

**Counterfactual**

9. What if tombstones were dropped on delete?
10. What if Eg-walker never cleared at critical versions?
11. What if RGA's skip rule were ascending?

**Adversarial**

12. How can a malicious replica break an ID-based CRDT?
13. What event-graph shape approaches O(n² log n)?
14. Why can no algorithm meet the 2019 non-interleaving definition?

**Connection**

15. How is Eg-walker like `git rebase`?
16. How do version vectors relate to safe tombstone removal?

**Open**

17. Is Eg-walker's tie-break maximally non-interleaving?
18. Can a log-based design support rich text?

<details><summary>Answers</summary>

1. User 1 has already inserted before index 4, so the index names a different spot; "after `o4`" names the same character everywhere.
2. No right child at the left origin → right child of it; otherwise left child of the next element.
3. s_e: state in the latest document; s_p: state at the version the event's author saw. The event is interpreted against s_p, its output position computed against s_e.
4. Two concurrent deletes of one character: retreating one must not resurrect it while the other applies.
5. A subtree is one unbroken block in an in-order walk.
6. Order must depend only on the node set, not arrival order.
7. Forward typing chains each character to the previous one; backward typing shares one anchor, so per-character ID comparison alternates the two users.
8. A CRDT needs its IDs to integrate any future operation; Eg-walker only needs them while merging concurrent events.
9. A concurrent insert anchored on the deleted character has nothing to attach to; removal is safe only when causally stable.
10. A CRDT over all history: sequential traces slow about 5–7×.
11. Still converges; typed order flips for same-anchor inserts.
12. Reusing an ID with different content (equivocation); needs Byzantine-resilient designs.
13. Many long alternating branches forcing repeated retreat and advance; the paper says unlikely, and traversal order made one trace up to 8× slower.
14. The 2019 definition cannot be guaranteed by any algorithm (errata); Fugue's *maximal* version is achievable.
15. Both rebase a DAG of operations into a linear history with the same effect.
16. Causal stability (everyone has seen the delete), learned via version vectors or acknowledgements, makes removal safe; it needs a known replica set.
17. Unknown; conjectured, analysis left to future work.
18. Open; the authors believe the idea generalises, but clearing doesn't hold for Peritext.

</details>

## 15. Go deeper next

1. Causal broadcast and version vectors. 2. Peritext and rich-text CRDTs. 3. OT correctness (TP1/TP2).

## Sources

Papers: [Eg-walker](https://arxiv.org/abs/2409.14252), [Fugue](https://arxiv.org/abs/2305.00583), [PaPoC 2019](https://martin.kleppmann.com/2019/03/25/papoc-interleaving-anomalies.html), [RGA](https://doi.org/10.1016/j.jpdc.2010.12.006), [Peritext](https://inkandswitch.com/peritext/), [Gomes et al.](https://arxiv.org/abs/1707.01747), [Bauwens & Gonzalez Boix](https://soft.vub.ac.be/~jibauwen/publications/mplr20-from-causality-to-stability-jimbauwens.pdf).
Code/docs: [Yjs](https://github.com/yjs/yjs), [Automerge](https://github.com/automerge/automerge), [Loro](https://github.com/loro-dev/loro), [eg-walker-reference](https://github.com/josephg/eg-walker-reference), [crdt-benchmarks](https://github.com/dmonad/crdt-benchmarks).
Articles: [CRDTs go brrr](https://josephg.com/blog/crdts-go-brrr/), [Automerge 2.0](https://automerge.org/blog/automerge-2/), [Zed](https://zed.dev/blog/crdts), [Figma](https://www.figma.com/blog/how-figmas-multiplayer-technology-works/), [Google Drive 2010](https://drive.googleblog.com/2010/09/whats-different-about-new-google-docs.html), [Notion offline](https://www.notion.com/blog/how-we-made-notion-available-offline).
Figures 8, 9, 10 and 12 are from the Eg-walker paper, CC BY 4.0, recompressed.
