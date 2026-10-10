# E-graphs and equality saturation: union-find, rebuilding, extraction, and why Cranelift won't saturate

**Compilers/PL · E-graphs, congruence closure, equality saturation, aegraphs · hard · 2026-10-03**

> Verification note: research was done 2026-10-03 by four parallel research passes (foundations, implementation, frontier, breakage) that read primary PDFs, arXiv abstracts, docs.rs, and source on GitHub `main`. Tags: *(secondary)* = seen only in a search summary or secondary listing; *(unverified)* = could not be confirmed. Every number from `mini_egraph.py` was produced by running it in this folder. The AC blowup formula was derived here and cross-checked against Rosin/Ullrich/Hack (EGRAPHS 2026) and the demo's output for n = 2..6.

---

## 0b. Plain English first

**Explain it simply.** Picture a librarian who keeps a "same-meaning" binder. Every time someone proves two phrases mean the same thing ("twice a, then halved" = "a"; "a times two" = "a shifted left by one"), the librarian doesn't erase the old phrase. They staple the new phrase to the same page. Pages can point at other pages ("the thing on page 7, halved"), so one stapled fact can make many other pages equal too, and they have to go round and staple those as well.

A normal optimizing compiler is a cook who follows a recipe of tweaks in a fixed order, throwing away the old version each time. If it does step 3 before step 5 it may miss a shortcut that only appears the other way round. The binder approach avoids that: apply every known tweak, keep every version, and only at the end flip through the binder and pick the cheapest phrase on the page you care about. That's an **e-graph** (the binder), **equality saturation** (keep stapling until nothing new turns up), and **extraction** (pick the cheapest phrase).

**Everyday example.** A calculator program sees "take *a*, multiply by 2, divide by 2". The binder starts with four pages: *a*, 2, "*a*×2", and "(*a*×2)÷2". Round 1: one rule says "×2 is the same as shift-left-by-1", so "*a* shifted by 1" is stapled onto the "*a*×2" page. Another rule says "(x×y)÷z = x×(y÷z)", so "*a*×(2÷2)" is stapled onto the last page. Round 2: "anything divided by itself is 1", so "2÷2" joins the page for "1". Round 3: "x×1 = x" puts "*a*×(2÷2)" (now known to be "*a*×1") on the same page as "*a*". The last page and page *a* become one page. Round 4 finds nothing new. Flip to that page, take the shortest phrase: just *a*. The compiler deletes both the multiply and the divide.

**Bridge:** now the same thing, technically.

---

## 1. Bare-minimum context

- **Term / AST**: a tree like `(/ (* a 2) 2)`. Rewrites turn one term into an equal one. ([egg tutorial](https://docs.rs/egg/latest/egg/tutorials/_01_background/index.html))
- **Union-find**: a forest that answers "are x and y in the same set?" in near-constant amortized time; `find` returns the set's canonical representative, `union` links two roots. ([Wikipedia](https://en.wikipedia.org/wiki/Disjoint-set_data_structure))
- **Hash-consing**: never build the same node twice; a hash map from node → id gives structural sharing (a DAG instead of a tree).
- **Congruence**: if a ≡ b then f(a) ≡ f(b). The "closure" is everything you can derive this way. ([Nelson & Oppen 1980](https://web.eecs.umich.edu/~weimerw/2011-6610/reading/nelson-oppen-congruence.pdf))
- **Phase ordering**: an optimizer's passes destroy information, so the order you run them in changes the output. That's the problem e-graphs attack.
- **Datalog / conjunctive query**: rules over relations joined on shared variables; relevant because modern e-matching is a database join. ([relational e-matching](https://arxiv.org/abs/2108.02290))

---

## 1b. Real-world context

**What it is.** An *e-graph* is a data structure that stores a large (even infinite) set of equivalent programs compactly, by grouping nodes into *e-classes* (sets of nodes known to be equal) whose children point to e-classes, not to individual nodes. *Equality saturation* (eqsat) is the algorithm that repeatedly applies rewrite rules *without deleting anything*, adding each rewritten form to the matching e-class, until no rule adds anything new ("saturation") or a limit hits. Then an *extractor* picks the cheapest representative under a cost model.

**Why it exists.** Destructive rewriting forces you to choose a rule order, and a greedy choice can block a better one later (phase ordering). Tate, Stepp, Tatlock and Lerner (POPL 2009) proposed keeping all choices and deciding at the end. The idea sat in research for a decade because the data structure was slow: in Herbie (a floating-point accuracy tool) the old Racket e-graph simplifier took **98.1% of Herbie's runtime**. egg (POPL 2021) made it fast, and the egg backend is "over **3000×** faster than Herbie's initial simplifier" ([egg §6.1](https://arxiv.org/pdf/2004.03082)). Before e-graphs, people hand-ordered pass pipelines (LLVM's ~100-pass `-O2`) and hand-wrote peepholes (InstCombine), where Alive found 8 bugs in 334 hand-coded transforms ([cited in Cranelift RFC](https://github.com/bytecodealliance/rfcs/blob/main/accepted/cranelift-egraph.md)).

**Where it's used** (checked against source/primary pages unless tagged):

- **Cranelift / Wasmtime**: production mid-end since Jan 2023 ([#5587](https://github.com/bytecodealliance/wasmtime/pull/5587)), as an *acyclic* e-graph ("aegraph") with ISLE rewrite rules in `cranelift/codegen/src/opts/*.isle`; does GVN, LICM, constant folding, algebraic simplification in one pass.
- **Herbie**: floating-point accuracy rewriting; Racket core calls Rust egg via FFI (`egg-herbie`), plus an egglog backend ([repo](https://github.com/herbie-fp/herbie)).
- **Tensat** (MLSys 2021): tensor-graph superoptimization with ILP extraction; "up to 16% speedup … 48× less time optimizing" vs TASO ([arXiv](https://arxiv.org/abs/2101.01332)).
- **Luminal** (Rust ML inference compiler): lowers its graph to (a fork of) egglog and searches kernel variants by measured GPU time ([repo](https://github.com/luminal-ai/luminal)).
- **ROVER** (Imperial + Intel authors): RTL datapath rewriting, "up to a 63% reduction in circuit area" ([arXiv](https://arxiv.org/abs/2406.12421)). SEER does HLS via MLIR + e-graphs (ASPLOS 2024, *secondary*).
- **Ruler / Enumo**: *synthesize* rewrite rules with eqsat; Ruler's rule sets are 5.8× smaller and found 25× faster than a CVC4-based tool ([arXiv](https://arxiv.org/abs/2108.10436)).
- **lean-egg**: Lean 4 tactic that turns theorems into rewrite rules, searches with egg, and rebuilds a Lean proof (POPL 2026, [PDF](https://thok.eu/publications/2026/popl-theorem.pdf)).
- **RisingLight** (educational OLAP DB): SQL optimizer built on egg 0.9.5 ([repo](https://github.com/risinglightdb/risinglight)); **wasm-mutate** uses egg to generate semantically equal fuzz mutants ([Cargo.toml](https://github.com/bytecodealliance/wasm-tools/blob/main/crates/wasm-mutate/Cargo.toml)).

Not found: no upstream LLVM or GCC e-graph pass; claims about Certora, DataFusion, Mojo using egg could not be confirmed *(unverified, don't repeat them)*.

**How it's used.** Library route (egg 0.11, verbatim from `tests/simple.rs`):

```rust
use egg::*;
define_language! { enum SimpleLanguage {
    Num(i32), "+" = Add([Id; 2]), "*" = Mul([Id; 2]), Symbol(Symbol), } }

let rules: Vec<Rewrite<SimpleLanguage, ()>> = vec![
    rewrite!("commute-add"; "(+ ?a ?b)" => "(+ ?b ?a)"),
    rewrite!("add-0"; "(+ ?a 0)" => "?a"),
    rewrite!("mul-1"; "(* ?a 1)" => "?a"),
];
let expr: RecExpr<SimpleLanguage> = "(+ 0 (* 1 foo))".parse().unwrap();
let runner = Runner::default().with_expr(&expr).run(&rules);
let (cost, best) = Extractor::new(&runner.egraph, AstSize).find_best(runner.roots[0]);
// best = foo
```

Typical knobs: `Runner` defaults are `iter_limit 30`, `node_limit 10_000`, `time_limit 5 s`; default scheduler `BackoffScheduler` with match limit 1,000 and ban length 5 iterations, both doubling each time a rule gets banned ([run.rs](https://github.com/egraphs-good/egg/blob/main/src/run.rs), [docs](https://docs.rs/egg/latest/egg/struct.BackoffScheduler.html)). Language route: **egglog** (`(datatype …)`, `(rewrite …)`, `(run 10)`, `(extract …)`), or `pip install egglog` for the Python bindings. Compiler route: Cranelift ISLE rules such as

```
(rule iadd_x_plus_zero (simplify (iadd ty x (all_zero ty))) (subsume x))
```

**When to use / when not.** Use full eqsat when result quality matters far more than search time and the rule set interacts in ways you can't order by hand: hardware datapaths, tensor graphs, numerical accuracy, rule synthesis, theorem proving, superoptimization. Don't use it in a JIT or fast AOT compiler's hot path. Cranelift tried egg and measured **23% overhead just to round-trip through the e-graph with zero rewrites**, against an optimizer budget of ~10% of compile time ([Fallin 2026](https://cfallin.org/blog/2026/04/09/aegraph/)). Signs you picked wrong: you're hitting `NodeLimit` on every run, outputs change when you add an unrelated rule, or extraction quality is dominated by a cost model you can't make accurate.

**Who should care.** Compiler engineers (mid-end design, phase ordering), ML-compiler people (graph rewriting, kernel fusion), hardware/EDA (datapath and logic optimization), verification people (proof search, translation validation), DB query-optimizer authors (Cascades is a cousin).

---

## 2. The one-liner and what it hides

*"Apply all rewrites at once, keep every version, pick the best at the end, so no phase ordering."*

It hides:

1. **Congruence maintenance is the hard, slow part**, not rewriting. Merging two classes can make parents equal, which can make *their* parents equal. egg's main trick (deferred *rebuilding*) is about *when* to do that work.
2. **Saturation usually never comes.** Termination is undecidable in general; real systems stop on node/time limits, and then the result depends on rule order and schedule again, so phase ordering comes back through the limits.
3. **"Pick the best" is NP-hard** when shared subexpressions count once, and the answer is only as good as the cost model.
4. **One unsound rule poisons everything**, because merges are global and congruence spreads them.
5. **E-graphs are pure-dataflow structures.** Loops, side effects, and variable binding need extra machinery (PEG θ-nodes, Cranelift's side-effect skeleton, slotted e-graphs).

---

## 3. The problem

Destructive rewriting commits. Take `(a*2)/2` and two rules: strength-reduce `x*2 → x<<1`, and the algebraic `(x*y)/z → x*(y/z)`. Run strength reduction first and the term becomes `(a<<1)/2`; the algebraic rule no longer matches, and you've lost `a`. Zucker shows exactly this failure for *eager* e-graph rewriting ([smart-constructor aegraph](https://philipzucker.com/smart_constructor_aegraph/)). Production compilers paper over it by running passes many times in hand-tuned orders.

The obvious fix (search all orders) is exponential: k rules applicable in n places gives a branching tree of terms, most of which share almost all of their structure. The constraint that forced the e-graph design is **sharing**: represent all those terms in space roughly proportional to the *distinct* subterms plus the equalities among them. The second constraint is **speed**: before egg, the e-graph upkeep dominated runtime (98.1% of Herbie), so the idea was a research curiosity.

---

## 4. Mental model

**Analogy:** a spreadsheet where each cell (e-class) holds a *set* of formulas that all evaluate to the same value, and formulas refer to other cells, not to other formulas. Proving a new equality = moving a formula into a cell, or merging two cells. Picking the output = for each cell, choosing which of its formulas to display.

**Where it breaks:** (1) merging two cells can make two *other* cells hold identical formulas (`f(A)` and `f(B)` once A and B merge), and those must merge too; spreadsheets never do that. (2) A cell may contain a formula that refers to itself (`a = a*1`), so a cell can stand for infinitely many expressions. (3) Choosing per cell independently is optimal only if every use pays for its own copy; once shared cells count once, the choices interact globally.

---

## 5. The mechanism, traced

Real output of `mini_egraph.py` on `(/ (* a 2) 2)` with the four egg-paper rules: `mul-two (* ?a 2)→(<< ?a 1)`, `div-assoc (/ (* ?a ?b) ?c)→(* ?a (/ ?b ?c))`, `div-same (/ ?a ?a)→1`, `mul-one (* ?a 1)→?a`.

**The structure** (egg's definitions, [§2.1](https://arxiv.org/pdf/2004.03082)):

```
E-graph = (U, M, H)
  U  union-find over e-class ids          find(e3) -> e0 after merges
  M  e-class id -> set of e-nodes          e0 -> {a, (* e0 e6), (/ e2 e1)}
  H  hashcons: canonical e-node -> id      ('*', 0, 1) -> e2
  e-node = (op, child e-class ids...)      children are CLASSES, not nodes
  parents[c] = e-nodes that use class c    needed to repair congruence
```

**Step 0 — add the term.** Each subterm is hash-consed bottom-up:

```
e0: {a}   e1: {2}   e2: {(* e0 e1)}   e3: {(/ e2 e1)}     root = e3
```
Note `2` appears twice in the term but once in the graph: sharing.

**Iteration 0 — read phase** (search every rule against every class; invariants intact):
```
mul-two    @ e2  {?a=e0}
div-assoc  @ e3  {?a=e0, ?b=e1, ?c=e1}
```
**Write phase** (instantiate RHS, `union(class, new)`; invariants now broken, merged ids go on a worklist):
```
mul-two:   add 1 -> e4, add (<< e0 e4) -> e5, union(e2,e5)
div-assoc: add (/ e1 e1) -> e6, add (* e0 e6) -> e7, union(e3,e7)
worklist = [e2, e3]
```
**Rebuild** (dedup worklist, re-canonicalize parents, merge newly congruent parents):
```
e0:{a}  e1:{2}  e2:{(* e0 e1),(<< e0 e4)}  e3:{(* e0 e6),(/ e2 e1)}  e4:{1}  e6:{(/ e1 e1)}
```

**Iteration 1.** `div-same` now matches `e6 = (/ e1 e1)` → `union(e6, e4)`. Rebuild visits e6's parents, finds `(<< e0 e4)` whose child id is no longer canonical, and rewrites its hashcons key to `(<< e0 e6)`. This re-canonicalization is the whole job of rebuilding.
```
e2:{(* e0 e1),(<< e0 e6)}   e3:{(* e0 e6),(/ e2 e1)}   e6:{(/ e1 e1), 1}
```

**Iteration 2.** `e6` now contains `1`, so `mul-one` matches `(* e0 e6)` inside e3 with `?a = e0` → `union(e3, e0)`. **The root class and `a` are now the same class.**
```
e0:{a, (* e0 e6), (/ e2 e1)}   e1:{2}   e2:{(* e0 e1),(<< e0 e6)}   e6:{(/ e1 e1), 1}
```
e0 now contains `(* e0 e6)`, a node whose child is its own class: a **cycle**. e0 represents `a`, `a*1`, `a*1*1`, … (infinitely many terms) in 3 nodes.

**Iteration 3.** Four matches, every union is a no-op → **saturated**. Final: 4 e-classes, 8 e-nodes.

**Extraction** (greedy bottom-up, `AstSize`: cost(node) = 1 + Σ cost(best child)):
```
e1: 2 -> cost 1      e6: 1 -> cost 1      e0: a -> cost 1   (beats (/ e2 e1) at 1+3+1=5)
e2: (* a 2) -> 3     root find(e3)=e0 -> "a"
```

```
            iteration 0                iteration 1             iteration 2
 e3:[ / e2 e1 ]       e3:[ / e2 e1 | * e0 e6 ]   ...     e0:[ a | * e0 e6 | / e2 e1 ]
      |   \                    |        \                         ^    |
 e2:[ * e0 e1 ]       e2:[ * e0 e1 | << e0 e4 ]           e6:[ / e1 e1 | 1 ]
                      e6:[ / e1 e1 ]   e4:[1]              (e0 points to itself: cycle)
```

**One added rule breaks termination.** Add `mul-comm (* ?a ?b)→(* ?b ?a)` and the same term never saturates: `(* 2 a)` plus `div-assoc` gives `(* 2 (/ a 2))`, then `a/4`, `a/8`, …. The demo prints e-nodes 9 → 12 → 13 → 20 → 28 → 39 → 52 → 67 → 84 → 103 and stops on the iteration limit (extraction still returns `a`, because it was found early).

**The loop itself** (egg Fig. 5b; the read/write split makes results independent of rule-list order within an iteration):
```python
while not saturated and under_limits:
    matches = [(rw, subst, c) for rw in rules for (subst, c) in ematch(rw.lhs)]  # read
    for rw, subst, c in matches:
        union(c, add(instantiate(rw.rhs, subst)))                              # write
    rebuild()                                                                   # once
```

---

## 6. The math

### 6.1 The invariants

Let `≡_id` be the union-find relation and `≡_node` the relation "two e-nodes are in the same class". The **congruence invariant** (egg Def 2.6) says `≡_node` equals its own congruence closure:

$$ f(a_1,\dots,a_k)\equiv_{node} f(b_1,\dots,b_k) \;\Leftarrow\; \forall i.\ \mathrm{find}(a_i)=\mathrm{find}(b_i) $$

→ in plain terms: two nodes with the same operator and the same *canonical* children must be in the same class.

The **hashcons invariant** (Def 2.7): $n \in M[a] \iff H[\mathrm{canon}(n)] = \mathrm{find}(a)$, where $\mathrm{canon}(f(a_1..a_k)) = f(\mathrm{find}(a_1)..\mathrm{find}(a_k))$.

→ in plain terms: the lookup table is keyed by nodes whose children are representatives, so "have I seen this node?" is one hash probe.

Why this form and not "keep a tree per term": the right-hand side quantifies over *classes*, so one equality `a ≡ b` instantly covers every term containing `a`. That's what makes the representation exponentially compact, and it's also why one merge can cascade.

### 6.2 Why deferring rebuild wins

Take n terms `f1(x), …, fn(x)` plus leaves `y1..yn`, then merge `x` with each `yi` (egg §3.2.1). Immediate maintenance repairs x's parent list after every merge: n merges × n parents = **O(n²)** hashcons updates. Deferred: all n merges go on the worklist, deduplicate to one canonical class, and its n parents are repaired once: **O(n)**. For w chains of depth d whose leaves get merged, immediate costs O(wd) repairs, deferred O(d), because the w upward paths coalesce after dedup.

→ in plain terms: rebuilding pays once per *distinct* dirty class per iteration, not once per merge.

Measured on egg's 32-test suite: **88× geometric-mean speedup on congruence closure, 21× on whole eqsat**, deferred vs immediate rebuilding *inside egg* (not vs Herbie; that's a common misquote). egg proves rebuilding terminates (Thm 3.1) via a lexicographically decreasing (|incongruent pairs|, |worklist|) but gives no online complexity bound ("likely highly workload dependent").

### 6.3 AC blowup, derived

Saturate `x1 + … + xn` (distinct leaves) under commutativity and associativity. Any regrouping and reordering is reachable, so every non-empty subset S of the leaves is the sum of *some* subterm: **2ⁿ − 1 e-classes**. A class for a subset of size k ≥ 2 contains one `+` node per *ordered* split of S into two non-empty parts: $2^k - 2$ of them. Summing,

$$ \#(+\text{-nodes}) = \sum_{k=2}^{n}\binom{n}{k}(2^k-2) = \sum_{k=0}^{n}\binom{n}{k}2^k - 2\sum_{k=0}^{n}\binom{n}{k} + 1 = 3^n - 2^{n+1} + 1 $$

(the k=0 and k=1 terms of the two sums cancel to −1, hence +1). Add the n leaf nodes: $3^n - 2^{n+1} + n + 1$ e-nodes, matching Rosin/Ullrich/Hack's EGRAPHS 2026 paper.

→ in plain terms: 10 summed variables → 1,023 classes and 57,012 nodes; 20 → over 3.4 billion nodes. Commutativity alone is mild; the *pair* with associativity is what explodes.

Demo output (exact match for n = 2..6): classes 3, 7, 15, 31, 63; e-nodes 4, 15, 54, 185, 608.

### 6.4 E-matching as a join

Relational e-matching (Zhang et al., POPL 2022) stores each e-node `f(j1..jk)` in class i as a tuple `R_f(i, j1, …, jk)`. Pattern `f(α, g(α))` becomes the conjunctive query

$$ Q(root,\alpha) \leftarrow R_f(root,\alpha,x),\ R_g(x,\alpha) $$

Backtracking checks the repeated α last: O(N²) for N matches. A join checks it during the join: O(N). Using **Generic Join** (worst-case optimal), the time is bounded by the AGM bound; Thm 10 gives $O(\sqrt{|Q(I)|\cdot\prod_i|R_i|})$. Reported: "over 6 orders of magnitude faster" on deep patterns with repeated variables.

→ in plain terms: e-matching is NP-hard in *pattern* size, but patterns are tiny; in *e-graph* size, it's polynomial and a database planner does it well.

### 6.5 Extraction

With a monotone local cost (cost(f(c1..ck)) > every child cost), greedy bottom-up fixpoint is optimal for **tree cost** (each use counted separately). Under **DAG cost** (shared class counted once) it's NP-hard (Stepp 2011 thesis) and inapproximable to any constant factor (Goharshady et al. OOPSLA 2024). The standard exact method is ILP (Tensat):

$$ \min \sum_i c_i x_i \quad\text{s.t.}\quad \sum_{i\in root} x_i = 1,\quad x_i \le \sum_{j\in m} x_j\ \ \forall i,\ \forall m\in\mathrm{children}(i) $$

plus acyclicity via order variables $t_m$: $t_{g(i)} - t_m - \epsilon + A(1-x_i) \ge 0$.

→ in plain terms: pick exactly one node at the root; picking a node forces you to pick some node in each child class; and the picks must not form a loop. The cycle constraint is what makes the ILP slow; Tensat filters cycles during exploration and drops it.

---

## 7. Why it works

**Core insight:** equality is a *global* fact about classes, and congruence makes it propagate structurally, so you can apply a rewrite once to a class and every term that contains it benefits. Combined with hash-consing, a set of terms that grows exponentially in the number of rewrites applied often stays polynomial in the e-graph (that's Tensat's and the Showdown paper's argument for matrix chains: the exponential space of parenthesizations sits in O(n³) nodes).

**Ablations:**

- **Remove the union-find** → you can't tell that `e3` and `e0` are the same class; every merge would rewrite all pointers eagerly (expensive) or leave duplicate classes (wrong answers). Cranelift did remove it in 2025 ([#10471](https://github.com/bytecodealliance/wasmtime/pull/10471)), but only because its rules are directional and it never repairs congruence anyway.
- **Remove the hashcons** → `(/ e1 e1)` can be added twice into different classes; congruent nodes stay apart; the graph is no longer a DAG with sharing; matching cost multiplies.
- **Remove rebuild** (union without repairing parents) → after `union(e6, e4)`, `(<< e0 e4)` keeps a stale key; a future `add((<< e0 e6))` makes a duplicate class; some equalities are never discovered. This is what aegraphs accept on purpose (Fallin counts 2 misses in ~4M value nodes).
- **Remove the read/write split** → applying matches while searching makes results depend on rule-list order and can invalidate iterators mid-search.
- **Remove limits** → nontermination on ordinary rule sets (the `mul-comm` demo).
- **Remove e-class analyses** → no constant folding, no `x/x → 1 if x ≠ 0`; you're stuck with purely syntactic rules, and Herbie had to use unsound ones.

---

## 8. Design knobs and alternatives

| Knob | Effect | Typical value |
|---|---|---|
| Iteration / node / time limits | Bound blowup; also make the output depend on schedule | egg: 30 / 10,000 / 5 s |
| Rule scheduler | Which rules fire each round | egg BackoffScheduler: ban a rule after 1,000 matches for 5 iterations, doubling both |
| Rule set shape | Bidirectional (AC, distributivity) explodes; directional "toward cheaper" stays small | Cranelift: directional only, no general AC |
| Rebuild frequency | Per merge (simple, slow) vs per iteration (egg) vs never (aegraph) | per iteration |
| E-matching | Backtracking (de Moura & Bjørner code trees) vs relational/Generic Join | egglog: relational, semi-naive |
| Extraction | Greedy tree cost (fast) vs ILP / treewidth DP / SmoothE / e-boost (sharing-aware) | greedy unless sharing matters |
| Analyses | Semilattice data per class (constants, intervals, types) | constant folding at minimum |

**Competing approaches:**

- **Hand-ordered pass pipelines + peepholes** (LLVM InstCombine, MLIR greedy canonicalizer): fast, predictable, phase-order-sensitive, bug-prone at scale. Wins for fast compilers.
- **Cascades / Volcano query optimizers** (Graefe 1995): memo of equivalent plan groups, top-down with branch-and-bound. A close cousin of e-graphs; Cranelift's RFC cites it for its eager rule application.
- **Stochastic superoptimization** (STOKE, MCMC): the EGRAPHS 2026 "Rewrite System Showdown" finds neither dominates; MCMC was always within 0.3% of optimal on matrix chains, eqsat within 1% up to ~800 matrices and up to 65% off on some larger ones.
- **SMT synthesis** (Souper): discovers peepholes offline; same role Ruler plays for e-graph rule sets.
- **Aegraphs** (Cranelift): e-graph-flavoured sea-of-nodes, eager, one pass, limits of 5. Won for a JIT-speed compiler; full eqsat won where compile time is cheap.

---

## 9. Where it breaks

- **Blowup.** AC: 3ⁿ nodes (§6.3). Unguided eqsat on matrix-multiply optimizations found only 2 of 7 known optimizations after an hour and 60 GB; with ≤3 human "sketches" all 7 appear in seconds under 1 GB ([sketch-guided eqsat](https://arxiv.org/pdf/2111.13040)). Tensat reports multi-pattern rules causing "double exponential growth" and caps them separately.
- **Limits make results unpredictable.** Flatt (UW PLSE, 2025): limits make runtime predictable but results not; "adding new program optimizations results in the resource limits being triggered earlier, preventing optimizations that were previously applied" ([post](https://uwplse.org/2025/06/16/egraph-complexity.html)).
- **Unsound rule → collapse.** `x/x → 1` puts `0/0` in the class of `1`; any rule deriving `0/0 = 0` then merges 0 and 1, and congruence spreads it to every class built on them. Herbie relied on such rules and "must validate the results … and discard them if unsoundness was detected"; removing them made Herbie "useless on a large portion of its benchmark suite" (egglog paper). Herbie's FAQ still has an "Unsound rule application detected" warning.
- **Production blowup even with directional rules.** Cranelift [#13068](https://github.com/bytecodealliance/wasmtime/issues/13068)/[#13204](https://github.com/bytecodealliance/wasmtime/issues/13204) (2026): adding rules like `(x−z)−(y−z) → x−y` moved one fuzz case from 0.08 s to ~10 s, one rule firing ~3,000,000 times; fixed by subsuming `x−x → 0` for vectors. Also [#13476](https://github.com/bytecodealliance/wasmtime/issues/13476) (stack overflow in `constructor_simplify`).
- **Extraction ignores sharing.** Cranelift deliberately counts each use anew; [#12156](https://github.com/bytecodealliance/wasmtime/issues/12156) shows costs saturating to infinity because of that.
- **Binders.** With names or de Bruijn indices, α-equivalent subterms don't share; de Bruijn needs shift rewrites that themselves blow up (§11).
- **Control flow and effects.** Loops make cyclic terms that greedy extraction can't extract; PEGs used θ-nodes plus a pseudo-Boolean solver; Cranelift keeps side-effecting instructions in a fixed CFG "skeleton" and only floats pure ops.

**Misconceptions:**

- *"Eqsat eliminates phase ordering."* Only at saturation. Under limits, order returns through scheduling; eager aegraphs reintroduce it outright (Zucker's `(a*2)/2`).
- *"E-graphs give optimal output."* Only w.r.t. explored space × cost model × exact extractor (NP-hard, inapproximable).
- *"It's rewriting with backtracking."* Nothing is undone; space only grows; choice is deferred to extraction.
- *"egg is 88× faster than Herbie's old e-graph."* No: 88× is deferred vs immediate rebuild inside egg; vs Herbie's original simplifier it's >3000×.
- *"The aegraph caused Wasmtime CVEs."* The wasmtime GHSA list shows the miscompile CVEs (e.g. CVE-2023-26489, CVE-2026-34971) are in backend ISLE *lowering*, not the egraph mid-end.

---

## 10. In the wild

- **Cranelift aegraph** deviates on every axis. Rules are applied *eagerly when a node is created*, in one RPO pass; no rebuild; union-find removed in 2025 (#10471); `MATCHES_LIMIT = 5` rewrites per ISLE call, `ECLASS_ENODE_LIMIT = 5`, `REWRITE_LIMIT = 5` recursion depth, `EXTRACTOR_FUEL = 500` ([egraph/mod.rs](https://github.com/bytecodealliance/wasmtime/blob/main/cranelift/codegen/src/egraph/mod.rs)); `subsume` drops alternatives outright. Pure ops float free and are placed back by **scoped elaboration** over the dominator tree, which yields GVN, LICM and rematerialization. Fallin's own 2026 evaluation: ~2% runtime win over a classical pipeline using the same rules, for ~7–8% more compile time; keeping multiple forms per value is worth ~0.1% ("in the noise"); average e-class has **1.13 nodes**. His conclusion: "the sea-of-nodes-with-CFG aspect of this mid-end works great, but the aegraph itself … may not (yet?) be pulling its weight."
- **egg** is textbook-plus: deferred rebuild, e-class analyses, backtracking pattern compilation (no inverted path index), backoff scheduling, explanations (FMCAD 2022: proofs 72.8% the size of Z3's on average).
- **egglog** replaces the single-language/single-analysis model with Datalog: functions with `:merge` expressions, semi-naive incremental matching; 3.34× faster than egg building the identical e-graph, 9.27× with semi-naive ([PLDI 2023](https://arxiv.org/abs/2304.04332)). Now supports `-j` parallel execution.
- **Herbie** uses egg with unsound rules plus post-validation; the egglog rewrite is sound via interval/non-zero analyses.
- **Tensat** caps multi-pattern rules with a separate iteration limit and pre-filters cycles so ILP extraction stays tractable.
- **Luminal** extracts by *measured GPU runtime* of candidates, sidestepping the cost-model problem at the price of benchmarking.

---

## 11. Frontier (what's new)

Primary-checked unless tagged.

1. **Slotted E-Graphs** — Schneider, Rossel, Shaikhha, Goens, Kœhler, Steuwer. PLDI 2025. E-classes are parameterized by *slots* (free variables); e-nodes point to classes through a renaming; congruence holds modulo renaming; each class stores a permutation group of its symmetries (Schreier–Sims). On a function-fission benchmark egg+de Bruijn exceeded 4 GB at 4 parameters (1,827k nodes, 52 s); slotted needed ≤214 nodes, 6 MB, 0.22 s. On Mathlib's `not_supIrred`, egg grew to 2.6M nodes and crashed at 40 GB; slotted finished under 1 s. Cost: 2.7× memory, 7.8× slower on a plain de Bruijn workload (prototype lacks egg's engineering). [PDF](https://steuwer.info/files/publications/2025/PLDI-Slotted-E-Graphs.pdf)
2. **SmoothE: Differentiable E-Graph Extraction** — Cai, Yang, Deng, Yu, Zhang. ASPLOS 2025 Best Paper. Each class gets a probability distribution over its nodes; minimize expected cost by gradient descent on GPU; acyclicity via a NOTEARS-style trace-of-matrix-exponential penalty per SCC. Comparable or better than 10-hour CPLEX on 4 of 5 datasets with 8–37× speedup; supports nonlinear costs. [PDF](https://www.csl.cornell.edu/~zhiruz/pdfs/smoothe-asplos2025.pdf)
3. **Fast and Optimal Extraction for Sparse Equality Graphs** — Goharshady, Lam, Parreaux. OOPSLA 2024 Distinguished Paper. Exact extraction linear-time for bounded treewidth (fine up to ~10 on Cranelift e-graphs); also shows extraction is inapproximable. *(secondary for venue page)* [page](https://2024.splashcon.org/details/splash-2024-oopsla/144/Fast-and-Optimal-Extraction-for-Sparse-Equality-Graphs)
4. **Semantic Foundations of Equality Saturation** — Suciu, Wang, Zhang. ICDT 2025. E-graphs as tree automata; eqsat = least fixpoint = universal model; two-way reductions to the database *chase*. Termination on one input is R.E.-complete; on all terms, **Π₂-complete**; on all e-graphs, undecidable. Gives "weak term acyclicity" as a syntactic sufficient condition. [arXiv](https://arxiv.org/abs/2501.02413)
5. **Optimism in Equality Saturation** — Arbore, Cheung, Willsey. PLDI 2026. E-class analyses are pessimistic and lose precision on cyclic SSA; naive optimism is unsound in e-graphs; they give an abstract-interpretation algorithm that analyzes optimistically during saturation, more precise than clang/gcc on examples. [arXiv](https://arxiv.org/abs/2511.20782)
6. **eqsat MLIR dialect** — Merckx, Lopoukhine, Coward, Cheng, De Sutter, Grosser. EGRAPHS 2025. E-graphs as native MLIR IR so matching/extraction reuse MLIR passes; follow-up Tamagoyaki (2026) reports 1.18× average speedup. **DialEgg** (Zayed, Dubach, CGO 2025) instead round-trips MLIR ↔ egglog. [arXiv](https://arxiv.org/abs/2505.09363)
7. **Rewrite System Showdown: Stochastic Search vs. EqSat** — Hong, Soi, Zhang, Aiken. EGRAPHS 2026. First head-to-head with identical rule sets on 5 benchmarks; neither Pareto-dominates; on Caviar/Halide inequalities 40% solved by both, 6% only eqsat, 3% only MCMC, ~50% by neither. [arXiv](https://arxiv.org/abs/2605.19005)
8. **Scaling via scheduling**: CERES (EGRAPHS 2026, *secondary*) matches Herbie expression quality with 8–12× less memory; EggMind (arXiv 2604.17364, Apr 2026, no venue) has an LLM synthesize saturation strategies, −45.1% cost, −69.1% peak RAM; parallel eqsat engine (CC 2026, *secondary*).
9. **New domains**: Quasar quantum-circuit eqsat (PLDI 2026, *secondary*: −33.5% total gates geomean); EqiForge tensor superoptimization deriving FlashAttention-style kernels (arXiv 2609.12330, Sept 2026, no venue: up to 2.74×); e-boost extraction for logic synthesis (ICCAD 2025, *secondary*: 558× faster than ILP).
10. **Equational proofs in Lean** — Rossel, Schneider, Kœhler, Steuwer, Goens. POPL 2026. Conditional rewrites, type classes, proof reconstruction from egg explanations. [PDF](https://thok.eu/publications/2026/popl-theorem.pdf)

**Dissection 1 — slotted e-graphs.** *Problem:* `λx. x+1` and `λy. y+1` never share; under de Bruijn, moving a subterm under a binder needs explicit shift rewrites, shifted copies of the same class aren't equal, and the graph explodes (81% of one 4,657-step egg explanation was shifts). *Mechanism:* a class `c(s1,s2)` is a function of its slots; an e-node `+(c1[s1↦x], c2[…])` carries a renaming per child; the hashcons key is the node's *shape* (renamings normalized), so α-variants hash together; symmetries like `x+y = y+x` live in the class's permutation group instead of as extra nodes. *Limits:* constant-factor overhead; matching must infer renamings; case studies, no broad suite. *Follow-up:* Zucker's "Lifting E-Graphs" (EGRAPHS 2026) uses thinning bitvectors on ids instead.

**Dissection 2 — the extraction line.** Greedy is sharing-blind; ILP is exact but slow mainly because of the acyclicity constraint. The treewidth DP exploits that real e-graphs are sparse. SmoothE relaxes to continuous probabilities, making extraction a GPU optimization problem and admitting nonlinear costs, with no optimality guarantee. e-boost combines parallel heuristics, pruning, and a warm-started ILP; it reports beating SmoothE by 19%, but it shares authors with SmoothE, so it's not an independent comparison. ASP (Yang & Sergey, EGRAPHS 2026) shows a naive answer-set encoding about matches tuned ILP.

**Dissection 3 — theory meets reality.** Suciu/Wang/Zhang make "will it terminate?" formally hopeless in general (Π₂-complete over all terms), so limits and schedulers are *necessary*, not just engineering. The Showdown then asks whether the e-graph's sharing is worth its cost against plain randomized search: mostly a tie, with the e-graph winning where an exponential space compresses well (matrix chains) and MCMC winning where rules are one-way or unsound. Cranelift's 1.13 nodes/class is the production version of the same message: when rules are directional, the "multiple versions" part barely matters.

---

## 11b. Open problems

- **Predictable scaling.** Limits trade unpredictable runtime for unpredictable results. Flatt's parameterized-complexity work on "linear-matching" rules (UW) and schedulers like CERES attack it; nobody has a general guarantee. Hard because termination itself is undecidable (ICDT 2025).
- **Rule scheduling / guidance.** Backoff is a heuristic; sketches need a human; MCTS, RL and LLM strategies (EggMind) report wins on their own benchmarks without a shared suite. The obvious approach (learn which rule helps) fails because a rule's value shows up only many iterations later, after interacting with others.
- **Sharing-aware, cost-accurate extraction.** NP-hard and inapproximable; Cranelift's cost model can't see register pressure or instruction selection ("in a 'conventional compiler', cost func + extraction is everything", Fallin's Dagstuhl 2026 slides). Multi-root extraction changes the problem again.
- **Control flow and effects.** PEGs, RVSDG (eggcc, Jamey Sharp's optir), Cranelift's skeleton, E-Path (2026, unchecked) all disagree on representation. Fallin lists rewriting control flow in the skeleton as open (#5623, #6109).
- **Context-dependent equality** (`x ≠ 0` only inside a branch). Colored e-graphs copy per assumption and are "notably resource-intensive"; predicate e-graphs and relational contextual eqsat (2025–26) are early.
- **Binders.** Slotted vs lifting vs categorical approaches; overhead vs expressiveness not settled.
- **AC and theories natively.** Generic AC is 3ⁿ; bespoke multiset/polynomial handling (Zucker's "Omelets Need Onions", AC-canonizing e-graphs at EGRAPHS 2026) is an active direction.
- **Is the e-graph worth it at all in fast compilers?** Fallin's 2026 data says the multi-version part is "within the noise" for Cranelift; the counter-position (UW PLSE's eggcc) is that you only see the benefit with richer, non-directional rule sets, which then need full eqsat. Unresolved, and the two positions are measuring different rule sets.

---

## 12. Lineage

- **1977** Kozen, finitely presented algebras (congruence closure origin; e-matching NP-completeness).
- **1980** Nelson & Oppen, congruence closure decision procedure (O(m²)); Downey–Sethi–Tarjan, O(m log m) with hashing; Nelson's thesis: the e-graph.
- **2002** Denali superoptimizer: e-graphs for codegen, saturate then SAT.
- **2005** Simplify prover (Detlefs, Nelson, Saxe): e-graph + backtracking e-matching.
- **2007** de Moura & Bjørner, efficient e-matching (code trees, inverted path index) in Z3.
- **2009** Tate, Stepp, Tatlock, Lerner, *Equality Saturation* (POPL): PEGs, Peggy for Java bytecode.
- **2011** Stepp thesis (extraction NP-hard); eqsat translation validation for LLVM (CAV).
- **1995 (side branch)** Graefe's Cascades memo for query optimization.
- **2021** egg (POPL, Distinguished Paper): rebuilding + e-class analyses; Ruler, Tensat, Diospyros.
- **2022** relational e-matching (POPL); small proofs (FMCAD); Cranelift RFC.
- **2023** egglog (PLDI); Cranelift aegraph on by default; EGRAPHS workshop series.
- **2024–26** guided eqsat, treewidth & differentiable extraction, slotted e-graphs, semantic foundations, MLIR dialects, Lean tactic, Fallin's "is the aegraph pulling its weight?" evaluation.

---

## 13. Hands-on (≤30 min)

`mini_egraph.py` in this folder (~170 lines, stdlib only): union-find, hashcons, deferred rebuild, backtracking e-matching, saturation loop, greedy extraction.

```bash
python3 mini_egraph.py
```

Expected (abridged):
```
--- (a*2)/2 with the egg-paper rules (no commutativity) ---
iter 0:    2 matches -> e-classes, e-nodes = (6, 8)
iter 1:    3 matches -> e-classes, e-nodes = (5, 8)
iter 2:    4 matches -> e-classes, e-nodes = (4, 8)
iter 3:    4 matches -> e-classes, e-nodes = (4, 8)
saturated: no rule adds new information
best   : a cost 1
--- same term, same rules + mul-comm: never saturates ---
iter 9:  134 matches -> e-classes, e-nodes = (19, 103)
iter limit hit
--- blowup: associativity + commutativity on a sum of n leaves ---
n=6: e-classes=  63 (2^n-1=  63)  e-nodes=  608
```

Experiments:

1. Comment out `eg.rebuild()` in `saturate`. Does `(a*2)/2` still reach `a`? Count duplicate classes (hint: stale keys like `(<< e0 e4)`).
2. Add `("zero-div", "(/ 0 ?a)", "0")` and a term containing `(/ 0 0)`. Watch `div-same` and `zero-div` merge `0` and `1`, then extract something absurd: e-graph collapse.
3. Swap the order of rules and change `iters=3`. With the read/write split, does the final e-graph change? Now apply matches *during* search instead and compare.
4. Change `extract`'s cost to count each class once (DAG cost) on `(+ (* x y) (* x y))` after adding `(* ?a ?b)` alternatives; see where greedy is wrong.

---

## 14. Question ladder

**Mechanism**

1. What exactly happens to the hashcons when `union(e6, e4)` runs, and when?
2. Why does e-class e0 end up containing a node whose child is e0, and what set of terms does it represent?
3. In egg's loop, why are all matches collected before any are applied?
4. What does `subsume` do in a Cranelift ISLE rule, and why must rules that drop uses use it?

**Why**

5. Why do e-nodes point to e-classes rather than to e-nodes?
6. Why does deferring rebuilding turn O(n²) work into O(n)?
7. Why is greedy extraction optimal for tree cost but not DAG cost?
8. Why did Cranelift choose eager, directional rewriting instead of saturation?

**Counterfactual**

9. What breaks if you keep the union-find but drop parent lists?
10. If every rule were directional and cost-decreasing, what would full eqsat buy over a single eager pass?
11. What happens to the `(a*2)/2` result if `mul-two` is applied destructively before `div-assoc`?

**Adversarial**

12. Construct a rule set and input that collapse the e-graph to one class.
13. How would you make egg's BackoffScheduler miss the optimal result on a term where it saturates without limits?
14. Given Cranelift's limits of 5, design a rule set that silently loses an optimization.

**Connection**

15. How is relational e-matching related to worst-case optimal joins in databases?
16. How does an e-graph differ from a Cascades memo?
17. How does egglog's `:merge` generalize egg's e-class analysis join?
18. How does eqsat relate to the database *chase*?

**Open**

19. Can you predict, before running, whether a rule set will saturate on your inputs?
20. Is there a cost model for extraction that captures register pressure without making extraction intractable?
21. Do slotted e-graphs' constant-factor costs disappear with egg-level engineering?

### Answers

<details><summary>1. Hashcons on union(e6, e4)</summary>
Nothing at union time: union only links e4 under e6 in the union-find, merges node sets, and pushes e6 on the worklist. At rebuild, `repair(e6)` walks e6's (now combined) parent list, removes each parent's stale key such as `(<< e0 e4)`, re-canonicalizes it to `(<< e0 e6)`, and reinserts it pointing at the parent's canonical class. If two re-canonicalized parents collide, their classes are unioned and pushed on the worklist.
</details>

<details><summary>2. The self-loop in e0</summary>
`mul-one` matched `(* e0 e6)` where e6 contains `1`, and unioned that node's class (e3) with e0. So e0 holds `(* e0 e6)`. The class represents `a`, `a*1`, `a*(2/2)`, `(a*1)*1`, … — every finite unrolling of the cycle, an infinite set, in 3 nodes.
</details>

<details><summary>3. Read/write split</summary>
Searching while the e-graph is mutating would see half-updated, non-canonical state and invalidate iterators; and applying rule A's results before searching rule B makes the outcome depend on the order rules are listed. Collecting first means each iteration is a function of the e-graph at its start, and invariants hold during search, so rebuilding can be deferred to once per iteration.
</details>

<details><summary>4. subsume</summary>
It marks the rewritten value as strictly better, so the e-class keeps only that value and drops the alternatives. It's required for correctness when the RHS uses fewer values than the LHS: elaboration might otherwise pick the old form, whose operands may not be available (dominance) at the placement point. It also keeps classes small.
</details>

<details><summary>5. Children are classes</summary>
That's what makes one equality cover every term containing the subterm: a parent automatically "contains" every alternative of its child, so the number of represented terms is the product of class sizes while storage is their sum. Pointing at nodes would require copying parents for each alternative child.
</details>

<details><summary>6. Deferred rebuild</summary>
Merges with overlapping upward paths dirty the same classes. Deduplicating the worklist to canonical ids means each dirty class is repaired once per rebuild, not once per merge. For n merges into one class with n parents, immediate repair touches n×n parent entries; deferred touches n.
</details>

<details><summary>7. Greedy vs DAG cost</summary>
With tree cost, a class's best cost is independent of who uses it, so choosing each class's minimum bottom-up is optimal (dynamic programming over a monotone cost). With DAG cost, a shared class is paid once; choosing a slightly costlier node that reuses an already-paid class can beat the locally cheapest one, so choices are coupled across the whole graph, giving set-cover-like hardness.
</details>

<details><summary>8. Cranelift's choice</summary>
Compile-time budget: egg round-tripping cost 23% with no rewrites vs ~10% for the whole optimizer. Directional rules (RHS no worse than LHS) mean the first good rewrite is almost always the final answer (2 misses in ~4M nodes), so saturation and rebuild buy little. Avoiding AC rules prevents blowup; limits of 5 bound worst cases.
</details>

<details><summary>9. No parent lists</summary>
After a union you couldn't find the e-nodes whose children changed without scanning the whole hashcons. Congruence repair becomes O(graph) per rebuild, or stale keys remain and congruent nodes stay in separate classes, missing equalities.
</details>

<details><summary>10. Directional rules</summary>
Little: if every rule moves strictly downhill in a single cost, the greedy eager result is usually already a local optimum. Eqsat still helps when two downhill paths diverge and only one leads to a deeper minimum, or when an uphill-then-downhill sequence is needed — which directional rule sets forbid by construction. That's Fallin's 1.13 nodes/class result.
</details>

<details><summary>11. Destructive mul-two first</summary>
The term becomes `(a<<1)/2`. `div-assoc` needs a `*` under the `/`, which is gone, so `a` is unreachable. That's phase ordering, and it's exactly Zucker's example of eager aegraph rewriting missing an optimization.
</details>

<details><summary>12. Collapse</summary>
Rules `x/x → 1` and `0/x → 0` with input containing `0/0`: `0/0` joins both 1's class and 0's class, so `0 ≡ 1`. Congruence then merges `x+0` with `x+1`, `x*0` with `x*1`, and so on; with `x*0 → 0` and `x*1 → x`, every x merges with 0. Everything ends in one class.
</details>

<details><summary>13. Backoff missing the optimum</summary>
Make the needed rule match explosively (e.g. a commutativity-style rule matching everywhere) so it exceeds its 1,000-match limit and is banned for 5 iterations right when its one useful application is needed; meanwhile a node limit fires. The result depends on the ban schedule, not on reachability.
</details>

<details><summary>14. Losing an optimization at limit 5</summary>
Write more than 5 rules whose LHS matches the same node, with the useful one produced last by ISLE's ordering: MATCHES_LIMIT truncates the rest. Or require a 6-deep rewrite chain to reach the good form: REWRITE_LIMIT stops at depth 5. Or one rule with cost(g) > cost(f) whose eager choice blocks a later win.
</details>

<details><summary>15. WCOJ connection</summary>
Each operator is a relation (class id, child ids…); a pattern is a conjunctive query; repeated pattern variables are join keys. Generic Join is worst-case optimal (runs within the AGM bound), so e-matching inherits its output-size optimality — cyclic patterns behave like the triangle query.
</details>

<details><summary>16. Cascades memo</summary>
Both group equivalent expressions whose children are groups. Cascades explores top-down, goal-directed, with physical properties and branch-and-bound pruning, and usually doesn't maintain congruence closure across merges; e-graphs explore bottom-up via saturation, maintain congruence, and extract afterwards.
</details>

<details><summary>17. egglog :merge</summary>
egg has one analysis per e-graph, joined with a semilattice join on class merge. egglog lets any function have a `:merge` expression resolving conflicting outputs for the same inputs (min, max, set union, or any expression), and congruence itself is the merge rule for constructor functions (union the ids). So analyses become ordinary Datalog functions, many per program.
</details>

<details><summary>18. The chase</summary>
Suciu, Wang and Zhang give two-way reductions: eqsat terminates iff some chase sequence terminates iff all "EGD-fair" ones do. Rewrite rules behave like tuple-generating plus equality-generating dependencies; e-graph merges are the EGD steps. This imports chase termination results, e.g. weak acyclicity → weak term acyclicity.
</details>

<details><summary>19. Predicting saturation</summary>
Not in general: all-terms termination is Π₂-complete. Sufficient syntactic tests exist (weak term acyclicity), and rule sets that are directional w.r.t. a well-founded order terminate. Practical prediction for real rule sets is open.
</details>

<details><summary>20. Register-pressure-aware extraction</summary>
Open. Register pressure depends on the schedule and live ranges, i.e. on the global choice; it's non-local and nonlinear. Options being explored: nonlinear costs (SmoothE), extraction with measured cost (Luminal), or folding lowering into extraction (Cranelift #8529). None is both accurate and tractable yet.
</details>

<details><summary>21. Slotted overhead</summary>
Unknown. The paper attributes part of the 2.7× memory / 7.8× time overhead to missing engineering (deferred rebuilding, compiled e-matching) and part to slots themselves (renamings per edge, permutation groups). No optimized implementation has been benchmarked yet.
</details>

---

## 15. Go deeper next

1. **Relational e-matching and worst-case optimal joins**: Generic Join, the AGM bound, and why egglog is a Datalog engine.
2. **RVSDG and sea-of-nodes IRs**: how Cranelift's skeleton, Graal and V8 TurboFan represent control and effects, and why that decides what an e-graph can rewrite.
3. **E-graph extraction as optimization**: ILP formulation, treewidth DP, SmoothE's NOTEARS acyclicity penalty.

---

## Sources

**Papers**

- Nelson & Oppen 1980, congruence closure: https://web.eecs.umich.edu/~weimerw/2011-6610/reading/nelson-oppen-congruence.pdf
- Tate, Stepp, Tatlock, Lerner, Equality Saturation (POPL 2009 / LMCS): https://arxiv.org/abs/1012.1802 · https://cseweb.ucsd.edu/~rtate/publications/eqsat/
- de Moura & Bjørner, Efficient E-matching (CADE 2007): https://inst.eecs.berkeley.edu/~cs294-260/sp24/papers/efficient-ematching.pdf
- Willsey et al., egg (POPL 2021): https://arxiv.org/abs/2004.03082
- Zhang et al., Relational E-matching (POPL 2022): https://arxiv.org/abs/2108.02290
- Flatt et al., Small Proofs from Congruence Closure (FMCAD 2022): https://arxiv.org/abs/2209.03398
- Zhang et al., egglog / Better Together (PLDI 2023): https://arxiv.org/abs/2304.04332
- Yang et al., Tensat (MLSys 2021): https://arxiv.org/abs/2101.01332
- Nandi et al., Ruler (OOPSLA 2021): https://arxiv.org/abs/2108.10436
- Koehler et al., Sketch-guided eqsat: https://arxiv.org/abs/2111.13040 · Guided Equality Saturation (POPL 2024): https://dl.acm.org/doi/abs/10.1145/3632900
- Goharshady, Lam, Parreaux, Sparse e-graph extraction (OOPSLA 2024): https://2024.splashcon.org/details/splash-2024-oopsla/144/Fast-and-Optimal-Extraction-for-Sparse-Equality-Graphs
- Sun, Zhang, Ni, E-Graphs as Circuits / treewidth: https://arxiv.org/abs/2408.17042
- Cai et al., SmoothE (ASPLOS 2025): https://www.csl.cornell.edu/~zhiruz/pdfs/smoothe-asplos2025.pdf · https://github.com/cornell-zhang/SmoothE
- Schneider et al., Slotted E-Graphs (PLDI 2025): https://steuwer.info/files/publications/2025/PLDI-Slotted-E-Graphs.pdf
- Suciu, Wang, Zhang, Semantic Foundations of Eqsat (ICDT 2025): https://arxiv.org/abs/2501.02413
- Merckx et al., eqsat MLIR dialect (EGRAPHS 2025): https://arxiv.org/abs/2505.09363 · Tamagoyaki: https://arxiv.org/abs/2602.16707
- Zayed & Dubach, DialEgg (CGO 2025): https://2025.cgo.org/details/cgo-2025-papers/44/DialEgg-Dialect-Agnostic-MLIR-Optimizer-using-Equality-Saturation-with-Egglog
- Arbore, Cheung, Willsey, Optimism in Equality Saturation (PLDI 2026): https://arxiv.org/abs/2511.20782
- Hong, Soi, Zhang, Aiken, Rewrite System Showdown (EGRAPHS 2026): https://arxiv.org/abs/2605.19005
- Rosin, Ullrich, Hack, Associativity and Commutativity in Eqsat (EGRAPHS 2026): https://compilers.cs.uni-saarland.de/papers/ullrich_egraphs2026-paper17.pdf
- Rossel et al., Equational reasoning in ITPs by eqsat (POPL 2026): https://thok.eu/publications/2026/popl-theorem.pdf
- EggMind, LLM-guided strategy synthesis: https://arxiv.org/abs/2604.17364
- EqiForge: https://arxiv.org/abs/2609.12330
- e-boost (ICCAD 2025): https://arxiv.org/abs/2508.13020
- Zucker, Omelets Need Onions (EGRAPHS 2025): https://arxiv.org/abs/2504.14340
- Colored e-graphs: https://arxiv.org/abs/2305.19203
- ROVER: https://arxiv.org/abs/2406.12421
- SEER (ASPLOS 2024): https://arxiv.org/abs/2308.07654
- EGRAPHS 2026 program: https://pldi26.sigplan.org/home/egraphs-2026

**Code / docs**

- egg: https://docs.rs/egg · https://github.com/egraphs-good/egg/blob/main/src/run.rs · https://github.com/egraphs-good/egg/blob/main/tests/simple.rs
- egglog: https://github.com/egraphs-good/egglog · egglog-python: https://github.com/egraphs-good/egglog-python
- Cranelift egraph: https://github.com/bytecodealliance/wasmtime/blob/main/cranelift/codegen/src/egraph/mod.rs · rule README: https://github.com/bytecodealliance/wasmtime/blob/main/cranelift/codegen/src/opts/README.md
- Cranelift RFC: https://github.com/bytecodealliance/rfcs/blob/main/accepted/cranelift-egraph.md
- Wasmtime PRs/issues: #5382, #5587, #6167, #10471, #10524, #12156, #13068, #13204, #13476 (https://github.com/bytecodealliance/wasmtime)
- Wasmtime advisories: https://github.com/bytecodealliance/wasmtime/security/advisories
- Herbie: https://github.com/herbie-fp/herbie · FAQ: https://fpbench.cs.washington.edu/doc/2.1/faq.html
- Luminal: https://github.com/luminal-ai/luminal · RisingLight: https://github.com/risinglightdb/risinglight
- eggcc: https://github.com/egraphs-good/eggcc · optir: https://github.com/jameysharp/optir · egg discussion #106: https://github.com/egraphs-good/egg/discussions/106
- awesome-egraphs: https://github.com/philzook58/awesome-egraphs

**Articles / talks**

- Fallin, "The acyclic e-graph: Cranelift's mid-end optimizer" (2026): https://cfallin.org/blog/2026/04/09/aegraph/
- Fallin, Dagstuhl slides (Jan 2026): https://cfallin.org/assets/cfallin-aegraphs-dagstuhl-20260108.pdf · EGRAPHS 2023 slides: https://cfallin.org/pubs/egraphs2023_aegraphs_slides.pdf
- Cranelift Progress 2022: https://bytecodealliance.org/articles/cranelift-progress-2022
- Flatt, e-graph complexity (UW PLSE 2025): https://uwplse.org/2025/06/16/egraph-complexity.html
- UW PLSE, phase ordering: https://uwplse.org/2025/04/14/Phase-ordering.html
- Zucker, smart-constructor aegraph: https://philipzucker.com/smart_constructor_aegraph/
- Bernstein, "What's in an e-graph?": https://bernsteinbear.com/blog/whats-in-an-egraph/
