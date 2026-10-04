# CDCL SAT solving: 1-UIP learning, backjumping, VSIDS, restarts, DRAT proofs

**Computer science · Formal methods · CDCL SAT solving · hard depth · 2026-10-04**

Files here: [`index.html`](index.html) (interactive version), [`cdcl.py`](cdcl.py) (tiny CDCL with trace, fuzzed vs brute force), [`php_blowup.py`](php_blowup.py) (pigeonhole experiment).

---

## 0b. Plain English first

**Explain it simply.** Imagine you must seat 200 wedding guests. Rules: "Ann won't sit with Bob", "Cal sits with Dee *or* Eve", and thousands more. You try a seating, hit a clash, and undo your last choice. A naive planner undoes only the last choice and, an hour later, makes the *same underlying mistake* again in a slightly different arrangement. A CDCL solver is a planner that, at each clash, stops and asks: *which of my choices actually caused this?* It writes that down as a new rule ("never seat Ann at table 1 **and** Cal at table 4"), jumps back to the choice that mattered (skipping innocent ones), and carries the new rule forever. Rules pile up; mistakes are never repeated in disguise.

**Everyday example.** Three guests: Ann, Bob, Cal. Rules: if Cal sits at the head table, so does Dee; if Dee is there, Eve and Fay must be too; but Eve and Fay can't sit together if Bob is at the head table. You seat Ann (fine), Bob (fine), then Cal. Dee, Eve, Fay all get forced, and Eve/Fay clash. The *real* culprit is "Dee at head table" combined with "Bob at head table", not Cal specifically, because Cal only mattered by forcing Dee. So the new rule is "not (Bob at head AND Dee at head)". You undo back to Bob's choice, Dee is now forbidden, and Cal is automatically forbidden too (Cal would force Dee). One clash taught you two things.

**Now the same thing, technically.**

---

## 1. Bare-minimum context

- **SAT**: given a boolean formula in CNF (AND of clauses, each an OR of literals), find a true/false assignment satisfying all clauses, or prove none exists. NP-complete.
- **Unit propagation (BCP)**: if a clause has all literals false except one unassigned, that one must be true. Repeat to fixpoint.
- **DPLL**: pick a variable, branch true/false, propagate, backtrack on conflict (1962).
- **Resolution**: from `(A ∨ x)` and `(B ∨ ¬x)` derive `(A ∨ B)`. Sound, and refutation-complete.
- **Decision level**: number of decisions on the trail up to a literal; propagated literals inherit the level of the decision that triggered them.
- **DIMACS CNF**: `p cnf nvars nclauses`, then one clause per line, ints, terminated by `0`.

## 1b. Real-world context

**What it is.** CDCL (conflict-driven clause learning) is DPLL plus: analyze each conflict into a new implied clause, jump back non-chronologically, and keep the learned clause. Add cheap data structures (two watched literals), an adaptive branching heuristic (VSIDS), and restarts, and you get the engine in nearly every modern SAT solver.

**Why it exists.** Plain DPLL on industrial formulas (millions of clauses) thrashes: it re-derives the same contradiction under every permutation of irrelevant decisions. GRASP (Marques-Silva & Sakallah, 1996/1999) introduced conflict analysis + learning + non-chronological backtracking; Chaff (Moskewicz et al., DAC 2001) made it fast with two-watched-literals and VSIDS, giving 1-2 orders of magnitude over predecessors; MiniSat (Eén & Sörensson, SAT 2003) made it small and hackable.

**Where it's used** (each verified in research unless marked):
- **Hardware verification**: bounded model checking and IC3/PDR in chip design flows reduce to repeated SAT calls (SAT BMC beat BDD model checking on an Alpha memory-subsystem study, CAV 2001 era).
- **SMT solvers**: Z3, CVC5, Yices use a CDCL core in the DPLL(T) architecture; theory solvers (arithmetic, bit-vectors, arrays) plug into CDCL via lemmas.
- **Package managers**: libsolv (DNF, Zypper, Conda/Mamba) is CDCL with watched literals; PubGrub (Dart pub, Poetry, uv via pubgrub-rs) is a CDCL-flavoured algorithm over version ranges, notable for human-readable failure explanations. Cargo's resolver is *not* full SAT.
- **Mathematics**: Boolean Pythagorean triples (Heule-Kullmann-Marek 2016: {1..7824} 2-colorable, 7825 not; ~200 TB proof, cube-and-conquer) and Schur number five = 160 (Heule, AAAI 2018; ~2 PB proof).
- **Cryptanalysis**: algebraic attacks on small stream ciphers (Bivium/Trivium/Grain-style) encoded to CNF, often with XOR/Gauss extensions.
- **Competitions as a driver**: Kissat won all three main-track gold medals (SAT, UNSAT, SAT+UNSAT) at SAT Competition 2024.

**How it's used.**

```python
from pysat.solvers import Cadical153
s = Cadical153(bootstrap_with=[[-1, 2], [-2, 3], [1, -3, 4]])   # DIMACS-style int literals
print(s.solve())                  # True
print(s.get_model())              # e.g. [-1, -2, -3, 4]
print(s.solve(assumptions=[1, -4]))   # incremental: solve under assumptions -> False
print(s.get_core())               # subset of assumptions responsible (UNSAT core)
```
CLI: `kissat input.cnf` or `cadical input.cnf proof.drat` (CaDiCaL logs a DRAT proof for UNSAT; check with `drat-trim input.cnf proof.drat`). Typical integration: encode problem to CNF (Tseitin transform for circuits, cardinality encodings for "at most k"), call solver, decode model; use assumptions for incremental queries.

**When to use / not.** Use for finite, boolean-encodable constraint problems where structure is rich (verification, planning, configuration, scheduling feasibility). Use **SMT** if you need arithmetic/arrays/strings natively; **CP-SAT / MaxSAT / MIP** if you need optimization; **ASP** for all-models/negation-as-failure modelling. Warning signs you picked wrong: parity/XOR-heavy or counting/pigeonhole-style constraints (see §9), or purely numeric/continuous structure.

**Who should care.** Verification/EDA engineers, build-and-dependency tooling authors, security researchers (symbolic execution backends), anyone calling Z3.

## 2. The one-liner — and what it hides

"CDCL = DPLL + learn a clause from each conflict." Hidden:
1. *Which* clause? (1-UIP over the implication graph, not just "negate the decisions")
2. Why is the learned clause **implied** (not a guess)?
3. Why does learning cost so little in practice? (watched literals)
4. How does it choose variables with no look-ahead? (VSIDS bumping from conflicts)
5. Why restart if restarting "throws work away"? (it keeps clauses, scores, saved phases)
6. What does it *prove* when it answers UNSAT, and can you trust it? (resolution proof; DRAT)

## 3. The problem

DPLL's chronological backtracking undoes the most recent decision even when it's irrelevant to the conflict, so the same unsatisfiable sub-structure is rediscovered exponentially often. Real-world instances have 10^5–10^7 variables with strong structure; pre-1996 solvers handled ~hundreds of variables of hard combinatorial instances. CDCL moved practical frontier to millions of variables on structured instances (not on random or crafted-hard ones).

## 4. Mental model

A detective's case board. Each decision is a hypothesis; propagation is deductions that follow. A conflict is a contradiction. Conflict analysis traces *why* back to a minimal set of hypotheses, then writes "these can't all be true" on the board permanently.

Where it breaks: a detective's note is a *specific* conclusion; a learned clause is a **resolution derivation**, and the whole run is a (possibly enormous) resolution proof. CDCL is bounded by what resolution can say. Short non-resolution arguments (counting, parity, pigeonhole) are invisible to it.

## 5. The mechanism, traced

Verified run of [`cdcl.py`](cdcl.py) on

```
C1 (¬3 ∨ 4)   C2 (¬4 ∨ 5)   C3 (¬4 ∨ 6)   C4 (¬5 ∨ ¬6 ∨ ¬2)   C5 (1 ∨ 2 ∨ 3 ∨ 7)
```

```
L1: decide +1
L2: decide +2
L3: decide +3
  L3: propagate +4 because [-3, 4]
  L3: propagate +5 because [-4, 5]
  L3: propagate +6 because [-4, 6]
CONFLICT [-5, -6, -2] @L3 -> learn [-2, -4], backjump to L2
  L2: assert -4 from learnt clause
  L2: propagate -3 because [-3, 4]
L3: decide +5
  L3: propagate -6 because [-5, -6, -2]
L4: decide +7
result: SAT
```

Implication graph at the conflict (level 3 only; levels 1,2 are fixed):

```
x3 (decision) ──C1──▶ x4 ──C2──▶ x5 ──┐
                       └──C3──▶ x6 ──┼──▶ ⊥  (C4 also uses x2 from level 2)
                                x2@L2 ┘
```

**1-UIP derivation** (backward over the trail, resolving away level-3 literals until exactly one remains):
1. Start: conflict clause `(¬5 ∨ ¬6 ∨ ¬2)`. Level-3 literals: ¬5, ¬6 (two). ¬2 is level 2.
2. Last-assigned level-3 literal on trail is `x6`; reason `C3 = (¬4 ∨ 6)`. Resolve on 6: `(¬5 ∨ ¬2 ∨ ¬4)`. Level-3 literals: ¬5, ¬4.
3. Next is `x5`; reason `C2 = (¬4 ∨ 5)`. Resolve on 5: `(¬2 ∨ ¬4)`. One level-3 literal left (¬4). **Stop.**
4. Learned: `(¬2 ∨ ¬4)`. **x4 is the UIP**: every path from decision x3 to ⊥ goes through x4. The decision x3 is a *later* UIP; 1-UIP picks the one nearest the conflict.
5. Backjump level = highest level among the *other* literals = level(x2) = 2. Undo levels 3. Now `¬2` is false, so the clause is unit and asserts `¬4`. Immediately C1 then forces `¬3`: we learned x3 is impossible without ever trying a different branch under it.

The clause is also **RUP** (reverse unit propagation): assume `2, 4`, propagate `5` (C2), `6` (C3), then C4 is falsified. That check is exactly what DRAT checkers run.

## 6. The math

**Resolution soundness.** If σ satisfies `(A ∨ x)` and `(B ∨ ¬x)`, then either x or ¬x is false under σ, so A or B holds: σ satisfies `(A ∨ B)`. → in plain terms: the resolvent never rules out a real solution.

**Why every learned clause is implied.** Conflict analysis only ever applies resolution to clauses in the formula or previously learned. By induction the learned clause is a resolvent of implied clauses, hence implied by F. Learning is *sound by construction*; keeping or deleting it changes only speed, never correctness (deleting loses information but not truth).

**Asserting property.** At the end of 1-UIP, exactly one literal ℓ is at the conflict level d, others at levels < d. Let b = max level of the others (0 if the clause is unit). Backjump to b: all others stay false, ℓ's variable is unassigned, so the clause is unit → ℓ forced. → in plain terms: the new clause immediately steers the search away from the exact dead end.

**VSIDS / EVSIDS.** Score s(v), bump amount Δ. On each conflict: s(v) += Δ for variables seen in analysis; then *either* multiply every score by ρ<1 (original), *or* leave scores and grow Δ ← Δ/ρ (MiniSat's trick; `var_decay` default 0.95 in MiniSat). Ordering is identical because only ratios matter, but the second is O(1) instead of O(n). Scores are rescaled by 1e-100 when they overflow. → in plain terms: variables that keep showing up in recent conflicts are where the trouble is, so branch there first.

**Restarts.** Luby sequence (u_i): 1,1,2,1,1,2,4,1,1,2,1,1,2,4,8,… scaled by a unit (e.g. 100 conflicts). It is within a log factor of the optimal universal restart schedule for Las Vegas algorithms of unknown runtime distribution (Luby–Sinclair–Zuckerman 1993). Note: one research agent printed the sequence incorrectly (with a "3"); the form above is the correct one. Modern solvers (Glucose, CaDiCaL, Kissat) instead use *dynamic* restarts that compare a fast and a slow exponential moving average of learned-clause LBD and restart when the fast one exceeds the slow one by a margin (Biere & Fröhlich, SAT 2015). Exact smoothing constants and margins are solver-specific and I did not verify them against primary source; don't quote them.

**LBD (glue).** LBD(C) = number of distinct decision levels among C's literals. Low LBD ⇒ clause links few decision groups ⇒ more reusable. Glucose (Audemard & Simon, 2009) keeps LBD ≤ 2 forever and periodically deletes about half of the rest, worst LBD first.

**Proof-complexity bounds** (why CDCL stalls):
- Pigeonhole PHP(n+1→n): every resolution refutation has size 2^Ω(n) (Haken 1985).
- Tseitin formulas on a graph G: resolution size 2^Ω(tw(G)) in general terms; expanders have linear treewidth, so exponential.
- CDCL is polynomially equivalent to general resolution *with restarts and suitable nondeterministic decisions/learning* (Pipatsrisawat & Darwiche, 2011; Atserias, Fichte & Thurley, 2011). Without restarts it is known only to simulate a restricted (regular-like) fragment. Caveat: the equivalence assumes an adversarially chosen decision policy, so it does **not** say real heuristics find the short proofs.

→ in plain terms: if resolution has no short proof, no CDCL run ever will; and even when it does, nobody can prove VSIDS finds it.

## 7. Why it works

- **Learning** turns each failure into a permanent pruning rule. Every learned clause cuts off an entire family of assignments (all those containing the culprit combination).
- **Non-chronological backjump** skips decision levels irrelevant to the conflict.
- **1-UIP** makes the learned clause *asserting immediately* and typically short.
- **Two watched literals** make propagation cost proportional to *relevant* clauses and make backtracking free.
- **VSIDS** builds focus on the "hard core" using only conflict feedback; **phase saving** + **restarts** keep that focus after throwing away the trail.

Ablation: remove learning → back to DPLL, exponential repeats. Remove restarts → heavy-tailed runtimes, stuck on bad early decisions (and the resolution-simulation theorem weakens). Remove watched literals → propagation dominates, backtracking cost O(n). Remove clause deletion → memory and propagation slow down (learned DB grows without bound). Remove minimization → clauses 30%-ish longer on average (reported in implementation notes; figure not independently verified).

## 8. Design knobs & alternatives

| Knob | Options | Tradeoff |
|---|---|---|
| Branching | VSIDS/EVSIDS, VMTF (move-to-front queue), CHB, LRB (bandit, Liang et al. 2016) | VMTF is cheap and strong when restarting often; VSIDS better in long "stable" runs |
| Restarts | Luby, geometric, glucose-style EMA | Aggressive restarts help UNSAT; fewer help SAT |
| Mode switching | Kissat/CaDiCaL alternate *focused* (VMTF, many restarts) and *stable* (VSIDS-like, few restarts, target phases) | Gets both SAT and UNSAT strengths |
| Clause DB | LBD tiers, activity, size cap | Memory vs. reuse |
| Minimization | local, recursive (MiniSat), binary-implication-based | Shorter clauses, small CPU cost |
| Inprocessing | bounded variable elimination, subsumption, vivification, probing | Big wins but complicates proofs and incrementality |
| Backtracking | non-chronological (default), chronological (Nadel-Ryvchin 2018 and since), graph-based (2026 paper below) | Chrono saves re-propagation on huge trails |

Alternatives: DPLL(T)/SMT (theories), local search (ProbSAT, great on random SAT, cannot prove UNSAT), cube-and-conquer (lookahead splits + CDCL leaves), BDDs (memory blow-up), cutting-planes/pseudo-Boolean solvers (stronger proof system; RoundingSat), XOR-aware solvers (CryptoMiniSat).

## 9. Where it breaks

- **Pigeonhole/counting.** I measured CaDiCaL 1.5.3 (via PySAT, 2026-10-04 run, laptop) on PHP(n+1→n): n=5: 137 conflicts; 6: 994; 7: 6,383; 8: 37,288; 9: 319,668; 10: 2,657,952 (26.9 s). Each extra hole multiplies conflicts by about 7–8. A human proves it in one sentence.
- **Parity/XOR chains, Tseitin on expanders**: exponential in resolution; need Gaussian elimination (CryptoMiniSat, newer XOR work).
- **Random 3-SAT near ratio ~4.27**: hard for everyone; phase-transition behavior.
- **Preprocessing can lose proof power** (variable elimination, blocked-clause elimination remove clauses; proof reconstruction can be exponentially larger).
- **Bugs**: solvers *have* returned wrong answers; fuzzing (Brummayer-Lonsing-Biere 2010) finds them. SAT competitions disqualify solvers for invalid models or wrong UNSAT; certified UNSAT proofs became mandatory in the main track years ago (check the current rules, I did not verify the exact year).
- **Misconceptions**: (a) "Clever data structures are the secret": real wins come from learning + propagation + heuristics together. (b) "Learned clauses are heuristics": they're proven consequences. (c) "Industrial instances are easy because of community structure": correlation is documented (Ansótegui et al., Newsham et al.), mechanism is unproven. (d) "Preprocessing is always safe for proof size."

## 10. In the wild

- **MiniSat**: ~2k LOC; `propagate()` walks watch lists, `analyze()` does 1-UIP + recursive minimization, `cancelUntil()` backjumps, `pickBranchLit()` pops a heap by activity; `var_decay`=0.95, `clause_decay`=0.999, Luby restarts by default.
- **Blocking literals**: each watch entry stores `(clause ref, blocker)`; if the blocker is already true the clause is not even loaded (cache win). Deviation from the textbook two-watch story.
- **Glucose**: LBD-based deletion and dynamic restarts. **CaDiCaL** (Biere): fully incremental with inprocessing; CaDiCaL 2.0 (CAV 2024) adds backtrackable inprocessing, user propagator, FRAT/LRAT/VeriPB proof output. **Kissat**: C reimplementation, no incremental interface, compact clause headers, aggressive inprocessing; 2022 and 2024 SAT Competition winner lineage.
- **Z3 / CVC5 / Yices**: CDCL(T): theory propagators and lemmas feed the same trail.
- **Cube-and-conquer** for the Pythagorean triples and Schur-5 results; proofs verified by formally verified checkers.

## 11. Frontier (what's new)

*Verified by me this session (page fetched):*
1. **Generalizing CDCL with Graph Backtracking**, Coutelier, Hader, Kovács, SAT 2026, arXiv 2605.28220: use implication-graph structure to decide exactly which assignments to undo, generalizing chronological and non-chronological backtracking; fewer re-propagations. https://arxiv.org/abs/2605.28220
2. **Lazy Reimplication in Chronological Backtracking**, Coutelier, Fleury, Kovács, SAT 2024: re-imply literals on demand rather than eagerly; works in CaDiCaL and Glucose. https://arxiv.org/abs/2501.07457
3. **Understanding CDCL Solvers via Scalability Studies and Proofdoors**, Zhang, Xia, Li, Li, Vardi, Ganesh, arXiv 2605.15506 (May 2026, revised Aug 2026): analysis of 76,000+ BMC instances; "proofdoor" (interpolant-sequence parameter) explains scaling where classical parameters don't. https://arxiv.org/abs/2605.15506
4. **SAT Competition 2024**: Kissat took all three main-track golds. https://cca.informatik.uni-freiburg.de/sat24medals/
5. **CaDiCaL 2.0**, Biere, Faller, Fazekas, Fleury, Froleyks, Pollitt, CAV 2024 (per research notes; paper link: https://link.springer.com/content/pdf/10.1007/978-3-031-65627-9_7.pdf, not opened by me).

*Reported by research agent, **not independently verified** (treat as leads):*
- Extending CDCL to disjunctions of parity equations (arXiv 2605.15002, SAT 2026 per agent).
- Learning to Rank Initial Branching Order of SAT Solvers (arXiv 2603.07176); One-shot SAT guidance with GNNs (arXiv 2505.16053); Neural approaches to SAT: design choices & interpretability (arXiv 2504.01173).
- AlphaMapleSAT: MCTS cube-and-conquer (arXiv 2401.13770, 2024).
- Practically feasible proof logging for pseudo-Boolean optimization (CP 2025, VeriPB/CakePB); Streaming LRAT certificates into Lean (arXiv 2607.00815).
- SAT Competition 2025: agent reports MallobSat (parallel track) and AE-Kissat-MAB as winners; not checked.

**Themes**: cheaper backtracking, learned/ML branching (still not displacing VSIDS/VMTF in top solvers as far as I could verify), stronger proof logging (DRAT → LRAT/FRAT → VeriPB, plus formally verified checkers), XOR/Gauss reasoning, parallel cube-and-conquer, LLM-assisted modeling.

## 11b. Open problems

1. **Why does CDCL work on industrial instances?** No theorem links instance structure to short proofs *and* to the heuristic finding them. Proposed correlates: modularity/community structure (Ansótegui et al.), hierarchical community structure metrics, backdoors/proofdoors. These explain correlation, not mechanism.
2. **Does CDCL (as actually run, with deterministic heuristics) p-simulate resolution?** The known simulation needs adversarial decisions and many restarts; the realistic case is open.
3. **Proof complexity of inprocessing**: how much extra power do elimination/vivification/BVA add, and when is it lost on proof reconstruction?
4. **Beyond resolution in practice**: extended resolution (DRAT/RAT lets you add definitions) and cutting planes are provably stronger; no CDCL-style system automatically finds such proofs on pigeonhole-like families at scale.
5. **Theory of restarts and clause deletion**: both are empirically essential, theoretically thin.
6. **Verified solvers at competition speed**: verified CDCL cores exist (Isabelle/IsaSAT line by Fleury, Blanchette, Lammich; Dafny work); the research notes claim "2x slower", which I could not verify. Proof checkers (cake_lpr, verified LRAT checking) cover trust more cheaply.

## 12. Lineage

DPLL (Davis-Putnam 1960; Davis-Logemann-Loveland 1962) → GRASP (Marques-Silva & Sakallah 1996; IEEE TC 1999) → SATO, Chaff (2001: 2WL, VSIDS) → MiniSat (2003/2005: minimization, small codebase) → Glucose (2009: LBD) → Lingeling/CaDiCaL/Kissat (inprocessing, mode switching, 2010s–) → graph backtracking, ML-guided branching, verified proofs (now).

## 13. Hands-on (≤30 min)

1. `python3 cdcl.py`: prints the traced run above and fuzzes 2000 random formulas against brute force (0 mismatches when I ran it). Modify the formula so the UIP is the decision (e.g. drop C1/C3 structure) and watch the learned clause change.
2. `python3 php_blowup.py` (needs `pip install python-sat`): reproduces the conflict blow-up table in §9. Predict n=11 before running (≈ ×8 → ~20M conflicts, several minutes).
3. Proof check: use `cadical input.cnf proof.drat` then `drat-trim input.cnf proof.drat` on any small UNSAT CNF; try deleting a line from the proof and see the checker reject it.

## 14. Question ladder

**Mechanism**
1. In the traced run, why is `¬2` kept in the learned clause but `¬3`, `¬5`, `¬6` are not?
<details><summary>Answer</summary>Level-3 literals are resolved away until only the UIP (¬4) remains at the conflict level. ¬2 is at a lower level so is never resolved; it stays as the "context" that made C4 dangerous.</details>
2. How does a solver pick the backjump level?
<details><summary>Answer</summary>Highest decision level among the learned clause's literals other than the asserting one (0 if unit). Ensures the clause becomes unit after the jump.</details>
3. Walk one propagation with two watched literals when a watched literal becomes false.
<details><summary>Answer</summary>Visit that literal's watch list. For each clause: if the other watch is true (or blocker true) skip; else look for a non-false replacement literal and move the watch; if none, the other watch is forced true (unit) or the clause is conflicting if it's false.</details>
4. What exactly does EVSIDS do instead of decaying all scores?
<details><summary>Answer</summary>Grows the bump increment by 1/ρ each conflict; relative order identical; rescale when floats overflow.</details>
5. What is checked by RUP?
<details><summary>Answer</summary>Assume the negation of the clause, unit-propagate on the formula (plus earlier proof lines); a conflict means the clause is implied.</details>

**Why**
6. Why 1-UIP rather than learning the decision-only clause?
<details><summary>Answer</summary>Decision-only clauses are long and rarely reusable; 1-UIP clauses are asserting, typically shorter, and abstract away irrelevant intermediate propagations.</details>
7. Why does backtracking cost nothing with two watched literals?
<details><summary>Answer</summary>The invariant only constrains watches relative to *current* assignments; unassigning variables can only make more literals non-false, so the invariant still holds with no updates.</details>
8. Why can deleting learned clauses never make the solver wrong?
<details><summary>Answer</summary>They're implied by F; removing them removes only redundant constraints (completeness still holds provided termination is preserved, e.g. don't delete clauses that are reasons of current assignments and keep growth of the kept set).</details>
9. Why do restarts help when the trail is thrown away?
<details><summary>Answer</summary>Heavy-tailed runtimes: bad early decisions trap the search; learned clauses, scores, and saved phases persist so restarting costs little and escapes the trap.</details>
10. Why is Luby sequence a sensible default with unknown runtime distribution?
<details><summary>Answer</summary>It is within a logarithmic factor of the optimal universal schedule (Luby-Sinclair-Zuckerman).</details>

**Counterfactual**
11. What if you learn the clause from the first-decision cut (all decisions)?
<details><summary>Answer</summary>Still sound, but longer clauses, weaker pruning; backjump is often just one level.</details>
12. What if VSIDS were static (scores fixed at start)?
<details><summary>Answer</summary>Loses dynamic focus on the current hard core; research notes and the literature treat static heuristics as clearly inferior on industrial instances.</details>
13. What if restarts are allowed only after exponentially growing intervals?
<details><summary>Answer</summary>That's geometric restarts: fine, but less adaptive than Luby/glucose; theory-wise the resolution-simulation proof needs enough restarts.</details>

**Adversarial**
14. Construct a family CDCL provably can't solve fast.
<details><summary>Answer</summary>Pigeonhole or Tseitin-on-expander formulas: resolution lower bounds apply to every CDCL run.</details>
15. How would you make a solver answer UNSAT wrongly?
<details><summary>Answer</summary>Bug in analysis/inprocessing (e.g. unsound elimination); this is why DRAT/LRAT proofs and independent checkers exist.</details>
16. How can preprocessing hurt a proof?
<details><summary>Answer</summary>Variable/blocked-clause elimination removes clauses that short proofs need; reconstructing in resolution can blow up.</details>

**Connection**
17. How does CDCL relate to SMT?
<details><summary>Answer</summary>CDCL(T): theory solvers detect theory conflicts, return lemma clauses; the SAT core learns/backjumps on them like any clause.</details>
18. How is PubGrub like CDCL?
<details><summary>Answer</summary>Learns "incompatibilities" from conflicts, backjumps, and keeps them; derivation tree gives readable error messages; domain is version ranges not booleans.</details>
19. Relationship between conflict analysis and resolution proofs?
<details><summary>Answer</summary>Each learned clause is a resolution derivation; the entire UNSAT run is a DAG of such derivations ending in the empty clause.</details>

**Open**
20. Can any practical solver find short extended-resolution proofs for pigeonhole-like formulas automatically?
<details><summary>Answer</summary>Open in practice; BVA-style preprocessing recovers some structure, but no general method.</details>
21. Is there a theorem explaining VSIDS on structured instances?
<details><summary>Answer</summary>No; only empirical correlations with community structure and decay-rate analyses.</details>
22. Can ML-based branching beat VSIDS/VMTF in a competition-grade solver?
<details><summary>Answer</summary>Unsettled. Reported results are promising on benchmark slices; I did not verify that any top competition solver ships a learned heuristic.</details>

## 15. Go deeper next

1. **Proof systems for solvers**: DRAT, LRAT, FRAT, VeriPB and verified checkers (cake_lpr).
2. **Cube-and-conquer** and how the Pythagorean/Schur results were split and certified.
3. **DPLL(T) / SMT lemma learning**: how theory conflicts enter the CDCL trail.

## Sources

**Papers / handbook**
- Marques-Silva & Sakallah, GRASP, IEEE Trans. Computers 1999: https://eprints.soton.ac.uk/262032/1/jpms-tcomp99.pdf
- Moskewicz et al., Chaff, DAC 2001: https://ieee-ceda.org/media/chaff-engineering-efficient-sat-solver
- Eén & Sörensson, An Extensible SAT-solver, SAT 2003: http://minisat.se/Papers.html
- Biere & Fröhlich, Evaluating CDCL Variable Scoring Schemes, SAT 2015: https://cca.informatik.uni-freiburg.de/papers/BiereFroehlich-SAT15.pdf
- Pipatsrisawat & Darwiche, On the Power of Clause-Learning SAT Solvers as Resolution Engines (AIJ 2011): http://reasoning.cs.ucla.edu/fetch.php?id=109&type=pdf
- Liang et al., Learning Rate Based Branching, 2016: https://www.ac.tuwien.ac.at/files/pub/Liang2016.pdf
- Brummayer, Lonsing, Biere, Fuzzing/delta-debugging SMT & SAT, SAT 2010: https://cca.informatik.uni-freiburg.de/papers/BrummayerLonsingBiere-SAT10.pdf
- Biere et al., CaDiCaL 2.0, CAV 2024: https://link.springer.com/content/pdf/10.1007/978-3-031-65627-9_7.pdf
- Heule, Schur Number Five, AAAI 2018: https://www.cs.utexas.edu/~marijn/Schur/
- Heule, Kullmann, Marek, Boolean Pythagorean Triples: https://arxiv.org/abs/1605.00723 (verified: ~200 TB uncompressed DRAT proof, 68 GB compressed certificate, 800 cores)
- Fleury et al., A Verified SAT Solver with Watched Literals: https://people.mpi-inf.mpg.de/~mfleury/sat_twl.pdf

**Frontier (verified by fetch)**: arXiv 2605.28220; arXiv 2501.07457; arXiv 2605.15506; https://cca.informatik.uni-freiburg.de/sat24medals/

**Code/docs**: MiniSat https://github.com/niklasso/minisat · Kissat (official) https://github.com/arminbiere/kissat · CaDiCaL https://github.com/arminbiere/cadical · PySAT https://github.com/pysathq/pysat · libsolv/PubGrub overview https://research.swtch.com/version-sat · Aalto CDCL notes https://users.aalto.fi/~tjunttil/2020-DP-AUT/notes-sat/cdcl.html

**Articles/other**: SAT competition slides https://satcompetition.github.io/2024/downloads/satcomp24slides.pdf

**Unverified / corrections log**
- Research agent said Schur-5 was 2023; primary page says AAAI 2018.
- Research agent's Handbook ch.4 link actually pointed to the preprocessing chapter: not cited.
- Research agent's "1-UIP gives highest backjump level" is wrong; not used.
- Restart EMA constants and Kissat header byte sizes: unverified, omitted.
- Claims of "verified solvers 2× slower", "30% fewer literals from minimization", SAT 2025 winners: unverified.
