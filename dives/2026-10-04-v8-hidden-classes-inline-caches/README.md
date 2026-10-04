# V8 hidden classes (Maps) + inline caches

`Computer science · Browsers/web internals · V8 Maps, inline caches, speculation + deopt · hard · 2026-10-04`

## 0b. Plain English first

**Explain it simply.** JavaScript lets you make an object like `{x: 1, y: 2}` and add or remove fields whenever you like. That freedom is a problem for speed: to read `p.x`, a naive engine must search the object for a field called `"x"` every single time, like flipping through a stack of papers looking for the one labelled "x".

V8 (the engine in Chrome and Node.js) cheats with two tricks. First, every object carries a small tag that says "I'm laid out like *this*" (the **hidden class**, V8 calls it a **Map**). All objects built the same way share one tag. Second, each place in your code that reads `p.x` keeps a sticky note (the **inline cache**): "last time, objects with tag #7 had `x` in the first slot." Next time, the engine glances at the object's tag; if it says #7, it grabs the first slot without searching. If the tag is different, it falls back to searching and updates its note. The faster tiers of the engine go further: they *bet* the note will stay true, compile code that assumes it, and bail out to slow code if the bet loses.

**Everyday example.** A waiter in a restaurant gets order slips. Slips from the tablet app are all printed in the same layout: table number in the top-left. After a few of them the waiter stops reading the header and just looks top-left. One day a handwritten slip shows up with the table number elsewhere. The waiter notices the layout is different (tag mismatch), stops, reads the slip properly, and mentally files "layouts A and B exist". If slips arrive in dozens of random layouts, the waiter gives up and reads every slip carefully. A very eager waiter (the optimizing compiler) might even pre-write the table number onto a ticket without looking, betting the layout holds; if the bet loses, the ticket is torn up and the waiter starts again.

**Now the same thing, technically.**

## 1. Bare-minimum context

- JS objects are dynamic string→value maps semantically; engines must make that fast anyway.
- Prototype chain: a property miss on the object continues up the `[[Prototype]]` chain.
- V8 tiers: Ignition (interpreter) → Sparkplug (baseline) → Maglev (mid) → TurboFan (top). [v8.dev/blog/maglev](https://v8.dev/blog/maglev)
- Smi = small integer stored inline in a tagged word (low tag bit 0); heap objects are tagged pointers. With pointer compression a tagged value is 32 bits.
- Feedback vector: per-function array on the heap where each op site (property load, call, `+`) records what it saw.
- JIT *speculation*: compile for observed types, guard with cheap checks, deoptimize on guard failure.

## 1b. Real-world context

**What it is.** A *Map* is V8's hidden class: an immutable-ish descriptor of an object's layout (which named properties, in what order, at which offsets, with which representations) plus its prototype and elements kind. An *inline cache* (IC) is a per-site memo keyed on Map that turns "find property `x`" into "compare Map, load at fixed offset".

**Why it exists.** Origin: the Self language (Ungar/Smith, 1980s) invented *maps* to make prototype-based objects as compact as class-based ones; Hölzle, Chambers, Ungar's *polymorphic inline caches* (ECOOP '91) extended single-entry ICs to several entries per site (median 11% speedup on their Self programs, 27% with type feedback for recompilation, ~2× fewer non-inlined sends) ([Self bibliography](https://bibliography.selflanguage.org/pics.html)). Without it, every `o.x` is a hash probe or linear scan: slow and memory-hungry (property names stored per object).

**Where it's used.**
- **Chrome / Chromium**: every web page's JS runs on V8.
- **Node.js, Deno**: server-side JS on V8; Node's performance advice is basically "keep shapes stable".
- **Electron apps** (VS Code, Slack): V8 inside.
- **Cloudflare Workers (workerd)**: V8 isolates.
- **SpiderMonkey** (Firefox): same idea, called *Shapes*, ICs expressed in *CacheIR*. **JavaScriptCore** (Safari): *Structures* + polymorphic ICs, tiers LLInt → Baseline → DFG → FTL. ([Speculation in JSC](https://webkit.org/blog/10308/speculation-in-javascriptcore/))

**How it's used.** Nothing to call: it's automatic. What you touch are inspection flags and coding habits.
```bash
node --allow-natives-syntax --trace-opt --trace-deopt --trace-ic app.js
```
```js
// d8 / node --allow-natives-syntax
%HasFastProperties(o)   // false => dictionary mode
%HaveSameMap(a, b)      // do two objects share a Map?
%DebugPrint(o)          // dumps Map, descriptors, elements kind
```
Habits: initialize all fields in the constructor in the same order; do not `delete` (set `undefined`/use `Map`); keep arrays homogeneous and packed; keep hot call sites ≤4 shapes.

**When to use / not.** You don't opt in; you decide whether to *design for* it. Worth caring on hot paths (parsers, ECS loops, serializers, framework internals). Not worth contorting cold code. Sign you picked wrong: `--trace-deopt` spam, `%HasFastProperties` false on hot objects, a profile full of `LoadIC_Megamorphic`.

**Who should care.** Node/backend engineers on hot paths, framework/library authors, perf engineers, and **security engineers** (the JIT's shape assumptions are the single richest browser-exploit surface).

## 2. The one-liner, and what it hides

*"V8 gives objects hidden classes so property access is a fixed-offset load."*

It hides:
1. Maps form a **transition tree** keyed by property *name and order*; `{x,y}` and `{y,x}` get different Maps.
2. The IC is a **monotonic state machine** (uninit → mono → poly ≤4 → mega) with a process-wide **stub cache** fallback.
3. Optimizing tiers don't just *use* the IC: they **bet** on it (CheckMaps + dependencies) and need **deoptimization**.
4. Field *representation* (Smi/Double/HeapObject/Tagged) is part of the shape and can change in place.
5. Every guard the compiler removes is a **security assumption**: a modelling bug turns into type confusion.

## 3. The problem

Semantically `o.x` is: walk the object's property table (hash map or sorted array), compare strings (interned, so pointer compares), if missing climb the prototype chain. That's tens of ns with several dependent loads, per access, and every object repeats its key names. Self measured a "Cartesian point" at 10 machine words without maps vs 3 with. A JS app does billions of accesses; V8 needs ~1 load.

## 4. Mental model

Map = **struct definition** discovered at runtime. Object = struct instance (`map*`, `properties*`, `elements*`, then in-object fields). IC = **JIT-style `switch (map)`** at each site.

Where it breaks: C structs are fixed; Maps are discovered *dynamically* and can **mutate** (field generalization, deprecation → "lazy migration") and be **abandoned** (dictionary mode). And the "switch" can be baked into machine code, which makes invalidation a first-class problem.

## 5. The mechanism, traced

Code:
```js
function getX(o) { return o.x; }
getX({x: 1, y: 2});
```

**Object creation.** Literal `{x:1,y:2}` starts from a root Map M0 (empty, with in-object slack) and follows transitions: `M0 --x--> M1 --y--> M2`. M2's DescriptorArray (shared with M1/M0 through ownership rules): `[x: field, in-object #0, Smi] [y: field, in-object #1, Smi]`.

**Layout (pointer compression, 4-byte tagged):**
```
offset  0   map        -> M2
offset  4   properties -> empty_fixed_array   (out-of-object overflow)
offset  8   elements   -> empty_fixed_array
offset 12   x          Smi(1)   (encoded 0b10)
offset 16   y          Smi(2)
```
(Without compression, words are 8 bytes and `x` sits at offset 24.) This is my derivation from the JSObject layout; check with `%DebugPrint`.

**Ignition + IC, first call.** Bytecode `LdaNamedProperty a0, [name x], [slot 3]` consults `feedback_vector[3]`: UNINITIALIZED → runtime `LoadIC::Load` does the real lookup in M2's descriptors, finds `x` at in-object index 0, builds a **handler** and stores `(weak M2, handler)` in the slot. The handler is typically a Smi bit-packed with `KindBits | IsInobjectBits | IsDoubleBits | FieldIndexBits` ([handler-configuration.h](https://chromium.googlesource.com/v8/v8.git/+/refs/heads/main/src/ic/handler-configuration.h)).

**Second call (monomorphic hit).** Slot holds M2: load `o.map`, compare, decode handler, load field at `index*word`. No lookup.

**Hot → optimized (Maglev/TurboFan).** The compiler reads slot 3 during graph building: monomorphic M2 + field handler ⇒ emit

```
CheckMaps  o, {M2}           ; deopt if o.map != M2
v = LoadField o, offset=12   ; Smi
```
roughly:
```asm
cmp  dword [rax + 0], M2_compressed
jne  deopt_entry
mov  r10d, [rax + 12]
```
(Illustrative sketch, not literal V8 output.) The compiler also *registers a dependency* of this code on M2 (the Map's `dependent_code` list): if M2 later becomes deprecated or its stability assumptions break, the code is invalidated.

**The bet loses.** Call `getX({y: 1, x: 2})`: Map M3 (`M0 --y--> --x-->`). `CheckMaps` fails ⇒ **eager deopt**: the deoptimizer uses the translation table to rebuild an Ignition frame from registers/stack, and execution resumes in the interpreter at the bytecode offset. The IC slot misses, sees a second Map, becomes **polymorphic** `[(M2,h1),(M3,h2)]`. The next optimization emits a 2-way `CheckMaps`.

**Elements path (parallel).** `arr[i]` ICs key on the Map's `elements_kind` (part of bit_field2). Pushing `1.5` onto a `PACKED_SMI_ELEMENTS` array transitions its Map to `PACKED_DOUBLE_ELEMENTS` and rewrites the backing store; code that assumed Smi elements guards on the Map and deopts.

### IC state machine
```
UNINIT --first Map--> MONO --2nd Map--> POLY(2..4) --5th Map--> MEGA
          (never goes back)                          \-> global stub cache probe
```

## 6. The math

There is no deep math; there are two useful cost models and one structural count.

**(a) Speculation break-even.** Let `t_f` = cost of guarded fast path, `t_s` = cost of generic path, `p` = probability the guard fails per execution, `C_d` = amortized cost of one deopt + re-tier. Expected cost per execution when speculating:

`E = (1 − p)·t_f + p·(t_s + C_d)`  ≈  `t_f + p·(t_s − t_f + C_d)`

Speculation beats always-generic when `E < t_s`, i.e. `p < (t_s − t_f) / (t_s − t_f + C_d)`.
→ in plain terms: a bet is worth it only if it loses *rarely enough* relative to how expensive losing is. Deopt costs microseconds-ish (my estimate, unmeasured), a fast load costs ~1 ns, so `p` must be tiny (≲1e-4 to 1e-3). That is why V8 waits for stable feedback and caps retries.

Using my measured numbers below (`t_f ≈ 1.0 ns`, `t_s ≈ 4.9 ns`), the generic path itself is only ~4–5× slower, which is the *cap* on the benefit of the whole machinery for this micro-case.

**(b) IC lookup cost by state.** `T_mono = t_cmp + t_load`; `T_poly(k) ≈ k·t_cmp (linear) + t_load`, k ≤ 4; `T_mega = t_hash + 1–2 probes of a global table + handler call`. Why 4? Linear scan cost grows with k while hit rate gains saturate; the constant `kMaxPolymorphicMapCount = 4` is an engineering cutoff, not derived. (Verified as constant in V8 source per research notes; I did not re-open the source myself.)

**(c) Shape explosion.** n properties added in all possible orders ⇒ up to n! root-to-leaf paths and `Σ n!/(n−k)!` Maps. Deterministic construction order collapses this to n+1 Maps per "class". → in plain terms: this is why order consistency matters.

**Stub cache sizing** (primary/secondary two-level hashed on (Map, name)): in `stub-cache.h` at main I fetched `kPrimaryTableBits = 12` (4096 entries) and `kSecondaryTableBits = 10` (1024). One of the research agents claimed 11/9; the primary source says 12/10, so treat 11/9 as wrong. Sizes have changed across versions.

## 7. Why it works

Core insight: **programs are far more regular than the language permits.** Real call sites see 1 shape >90% of the time (the Self/PIC measurements and decades of JS engine telemetry back this; I did not find a single canonical V8 number, so treat the figure as folklore with support). Ablations:
- **No Maps** → per-object name tables, hash lookups (slow, memory-heavy).
- **Maps but no ICs** → still need a lookup keyed on Map: slow path forever.
- **ICs but no speculation (Ignition/Sparkplug)** → one compare + load but no inlining, no escape analysis, no field type knowledge.
- **Speculation but no deopt** → unsound: any surprise miscomputes. Deopt is the *safety net that makes aggressive guards legal*.
- **Speculation but a bug in dependency/guard elimination** → type confusion (§9).

## 8. Design knobs & alternatives

| Knob | Effect |
|---|---|
| Poly limit (4) | smaller → earlier megamorphic; larger → slower poly checks |
| In-object slack tracking | over-allocate for constructors (research notes: +8 slots, counter 7), shrink after a few allocations |
| Dictionary mode | when delete/huge property counts: stop using Maps, use hash table; ICs can't specialize |
| Elements kinds (21) | specialize arrays: Smi/Double/Tagged × packed/holey; transitions only *generalize* |
| Tier thresholds | trade warm-up vs peak; Maglev at mid tier |
| Const field tracking | immutable fields can be embedded as constants in optimized code, invalidated on write |

Alternatives: **SpiderMonkey** CacheIR (ICs expressed as small IR that is both interpreted and compiled; reported 25–30% of compiled code is IC stubs, via Bernstein's CacheIR paper), **JSC** Structure + repatching ICs with DFG/FTL speculation, **Hermes** (static shape-ish with hidden-class cache), and classic *class-based* languages where shape is static and no guards are needed.

## 9. Where it breaks

**Performance:**
- **Megamorphic cliff.** My measurement (Node v24.12, one machine): mono 0.99 ns, 4-shape 4.06 ns, 8-shape 4.90 ns, 64-shape 4.80 ns per call (loop includes `i % len` and an array load). Cliff is mono→poly; mega adds little on top *here* because the stub cache hits.
- **`delete`** → dictionary mode; `%HasFastProperties` false.
- **Elements kind generalization is one-way**; a single `NaN`/`-0` makes a Smi array double; a hole makes it holey "forever" ([elements-kinds](https://v8.dev/blog/elements-kinds)). The famous "6×" in that post is about an out-of-bounds read bug, not holes.
- **Deopt loops**: repeated deopts lead V8 to stop reoptimizing (a research agent said "~30"; I could not verify the number, treat as unverified).

**Security (the big one).** The compiler removes `CheckMaps` when it *proves* the Map can't have changed between two points. The proof depends on a precise **side-effect model**. Wrong model ⇒ wrong Map assumption ⇒ type confusion ⇒ `addrof`/`fakeobj` ⇒ arbitrary R/W.
- **CVE-2020-6418**: `NodeProperties::InferReceiverMapsUnsafe` special-cased `kJSCreate` and *forgot to mark the result unreliable*, though `JSCreate` can run user code (e.g. a `Proxy` as 3rd arg to `Reflect.construct`). Inlined `Array.pop`; the side effect changed elements kind Smi→Double mid-function; the optimized code kept treating a double backing store as tagged. ([Project Zero RCA](https://googleprojectzero.blogspot.com/p/cve-2020-6418-chrome-incorrect-side.html))
- **CVE-2020-16009**: `Map::CanBeDeprecated()` wrongly said Maps with only Double/Tagged fields can't be deprecated (pointer compression, no unboxed doubles) so no code dependency was installed; the Map got deprecated anyway; in-place generalization Double→Tagged then led to Double/Tagged confusion. ([Project Zero RCA](https://googleprojectzero.blogspot.com/p/rca-cve-2020-16009.html))
- **CVE-2025-2135**: `InferMapsUnsafe()` handling of `TransitionElementsKindOrCheckMap` lacked an aliasing check, returning `kReliableMaps` when two IR nodes referred to the same runtime object ⇒ object-array vs double-array confusion; exploited within the V8 sandbox. ([Zellic](https://www.zellic.io/blog/pwning-v8ctf/))
- **CVE-2022-1134** ("Super IC"): confusion between `lookup_start_object` and `receiver` in the super-property IC. ([GitHub Blog](https://github.blog/security/vulnerability-research/the-chromium-super-inline-cache-type-confusion/)) (read by the research agent, not re-fetched by me)

Pattern: *an optimizer reasoning about Maps/elements kinds across an effect chain is a soundness proof written in C++*. The **V8 sandbox** (pointer-compression cage + indirection tables) limits what a corrupted heap can reach but doesn't fix the logic bugs ([v8.dev/blog/sandbox](https://v8.dev/blog/sandbox)).

**Misconceptions.** "Hidden classes are per-constructor" (no: per transition path). "Polymorphic is always bad" (≤4 is OK). "`delete` is slow because it's slow" (it flips the object to a different *representation*, hurting every later access). "Sandbox = JIT bugs harmless" (no, only contains them).

I dropped several CVE claims from the research notes that I could not confirm (an ID in the CVE-2026 range with a GitHub-repo-only source; unverified root causes for CVE-2022-1096 and CVE-2023-3079).

## 10. In the wild

- **Node/Chrome**: tiers Ignition → Sparkplug → Maglev (Chrome M117) → TurboFan. Maglev compiles "roughly 10× slower than Sparkplug, 10× faster than TurboFan"; −10% energy on Speedometer, −3.5% on JetStream ([v8.dev/blog/maglev](https://v8.dev/blog/maglev)). (A research agent said "20×"; primary source says 10×.)
- **Turboshaft**: CFG IR replacing Sea of Nodes in TurboFan's backend, "compile time got divided by 2" ([blog](https://v8.dev/blog/leaving-the-sea-of-nodes)).
- **React cliff**: a real-world shape/representation performance cliff documented by V8 ([v8.dev/blog/react-cliff](https://v8.dev/blog/react-cliff)).
- **Deviations from textbook PICs**: V8's ICs live in a heap-allocated feedback vector (not patched machine code), handlers are Smi-encoded data, plus a global stub cache for megamorphic sites; textbook PICs patch call-site code in place.

## 11. Frontier

Settled core, active periphery: the *idea* is 35 years old; recent work is on keeping the speculation sound and cheap.

- **Mutable heap numbers** (V8 blog, 2025-02-25): script-context slots own a mutable HeapNumber/Int32, avoiding allocation per update; ~2.5× on `async-fs`, ~1.6% JetStream2. Verified. https://v8.dev/blog/mutable-heap-number
- **Leaving the Sea of Nodes** (V8 blog, 2025-03-25): CFG IR migration, 2× compile time. Verified (date from research notes). https://v8.dev/blog/leaving-the-sea-of-nodes
- **CVE-2025-2135 writeup** (Zellic, 2025): aliasing bug in map inference found via V8CTF. Verified. https://www.zellic.io/blog/pwning-v8ctf/
- **Translation Validation for JIT Compiler in V8 (TurboTV)** (ICSE 2024): SMT-based validation of TurboFan optimizations, finds range-analysis bugs. https://kihongheo.kaist.ac.kr/publications/icse24.pdf (reported by research agent; not opened)
- **OptFuzz** (USENIX Security 2024): optimization-path-guided fuzzing; 36 new bugs across V8/JSC/SpiderMonkey/Hermes (per agent). https://www.usenix.org/system/files/usenixsecurity24_slides-wang-jiming.pdf (not opened)
- **DUMPLING** (NDSS 2025): fine-grained differential fuzzing comparing engine state; 8 new V8 bugs (per agent). https://www.ndss-symposium.org/wp-content/uploads/2025-1411-paper.pdf (not opened)
- Agent also listed *CoSSJIT* (OOPSLA 2025), *Understanding and Finding JIT Compiler Performance Bugs* (arXiv 2603.06551) and a Dec 2025 data-centric fuzzing paper (arXiv 2512.18102); I did not verify these, so they're only pointers.

## 11b. Open problems

- **Sound speculation.** No production-scale proof that "effect-chain Map inference" is correct; bugs recur (2020 → 2025 in the same function family). Obvious fix (always keep CheckMaps) loses much of the benefit. Approaches: translation validation (TurboTV), differential fuzzing, verified-speculation work (POPL'21, Vitek et al.).
- **Containment vs correctness.** V8 sandbox treats logic bugs as inevitable; open question whether containment gets strong enough to make JIT bugs non-critical.
- **Warm-up.** Feedback must be re-learned on every page load; caching/snapshotting profiles risks stale or attacker-influenced feedback.
- **Side channels.** IC state/tier changes create data-dependent timing; reported to undermine constant-time JS (JIT-Leaks, IEEE S&P 2020; DeJITLeak, ESEC/FSE 2022: from research notes, unopened).
- **Representation invariants** across Map deprecation (CVE-2020-16009 class) have no decidable, general checker.

## 12. Lineage

Smalltalk-80 inline caching (Deutsch & Schiffman 1984) → **Self maps** (Chambers/Ungar/Lee 1989) → **PICs** (Hölzle/Chambers/Ungar, ECOOP '91) → V8 hidden classes (2008, Crankshaft) → Ignition+TurboFan (2017) → Sparkplug (2021) → Maglev (2023) → Turboshaft / sandbox / mutable heap numbers (2024–25). Deutsch–Schiffman is from memory; unchecked here.

## 13. Hands-on (≤30 min)

[`ic_demo.js`](ic_demo.js): `node --allow-natives-syntax ic_demo.js`. Shows Map sharing, delete→dictionary mode, elements kinds, and mono/poly/mega timing. My run (Node v24.12.0, same machine, one run, no pinning, so noisy):

```
a,b share Map? true        a,c share Map? false
fast before delete: true   fast after delete : false   fast after x=undefined: true
monomorphic (1 shape)      0.99 ns/call
polymorphic (4 shapes)     4.06 ns/call
megamorphic (8 shapes)     4.90 ns/call
megamorphic (64 shapes)    4.80 ns/call
```
Then: add `--trace-deopt --trace-opt`, and `%DebugPrint(arr)` after each push to watch the elements kind change.

## 14. Question ladder

**Mechanism**
1. What exactly is in a JSObject's first three words?
<details><summary>Answer</summary>Map pointer, properties (overflow backing store), elements. In-object fields follow; with pointer compression each is 4 bytes, so the first field is at offset 12.</details>
2. What does a monomorphic LoadIC slot contain after the first miss?
<details><summary>Answer</summary>A weak reference to the Map plus a handler (typically a Smi encoding kind, in-object flag, double flag and field index).</details>
3. What happens on `getX({y:1,x:2})` after `getX` was optimized for `{x,y}`?
<details><summary>Answer</summary>CheckMaps fails → eager deopt → frame rebuilt for Ignition → IC becomes polymorphic → later reopt with 2-way check.</details>
4. How does `push(1.5)` on a Smi array change things?
<details><summary>Answer</summary>Map changes to PACKED_DOUBLE_ELEMENTS and the backing store is rewritten as unboxed doubles; one-way.</details>
5. Where does a megamorphic site look?
<details><summary>Answer</summary>Global two-level stub cache keyed on (Map, name); miss → runtime lookup.</details>

**Why**
6. Why do `{x,y}` and `{y,x}` have different Maps?
<details><summary>Answer</summary>Transitions are labeled by property name in insertion order; offsets depend on order.</details>
7. Why cap polymorphism at 4?
<details><summary>Answer</summary>Linear checks cost more per entry while hit-rate gains saturate; beyond that a hashed global lookup is cheaper. It's an engineering constant.</details>
8. Why is deoptimization necessary rather than a luxury?
<details><summary>Answer</summary>Guards can fail; without a way back to a generic tier the optimized code would need to be correct for all inputs, defeating speculation.</details>
9. Why does `delete` hurt later reads?
<details><summary>Answer</summary>Object flips to dictionary mode: no stable Map to key on, ICs can't specialize.</details>

**Counterfactual**
10. What if V8 never removed redundant CheckMaps?
<details><summary>Answer</summary>The CVE-2020-6418 class mostly disappears but every property access pays a compare, losing a chunk of optimized-code speed.</details>
11. What if the IC cap were 1?
<details><summary>Answer</summary>Any two-shape site would go megamorphic; the common "optional field" pattern would hit the stub cache constantly.</details>
12. What if elements kinds could transition back?
<details><summary>Answer</summary>Optimized code would need more dependencies and deopts; flip-flopping arrays would thrash. One-way keeps the lattice finite and monotone.</details>

**Adversarial**
13. How does an attacker turn a missing side-effect model into `addrof`?
<details><summary>Answer</summary>Use user-controllable code (Proxy, valueOf) at the unmodeled effect to change the Map/elements kind; optimized code still reads with old layout, so a double array's words are read as tagged pointers (leak) or a crafted double is read as a pointer (fake object).</details>
14. Can an attacker influence what the IC caches?
<details><summary>Answer</summary>Yes: they control which shapes reach a site, so they steer the feedback and thus which speculation the compiler makes (JIT-spray-like "feedback grooming").</details>
15. Why doesn't the V8 sandbox end this class?
<details><summary>Answer</summary>It bounds what corrupted pointers can reach, not the corruption itself; in-sandbox arbitrary R/W remains, and escapes target the boundary.</details>

**Connection**
16. How is this like a CPU branch predictor + pipeline flush?
<details><summary>Answer</summary>Guard = predicted branch, deopt = flush; both bet on regularity and trade rare large penalty for common cheap path.</details>
17. How do Shapes in SpiderMonkey differ?
<details><summary>Answer</summary>Same idea; ICs are expressed as CacheIR so the same IR can be interpreted or compiled.</details>
18. How does this relate to Spectre-style attacks?
<details><summary>Answer</summary>Both are speculation: one in hardware, one in software. Software speculation's guards are architecturally visible bugs; hardware's are microarchitectural leaks.</details>

**Open**
19. Can speculative JIT optimizations be formally verified at production scale?
<details><summary>Answer</summary>Unsettled; translation validation finds bugs but does not yet gate production releases.</details>
20. Can feedback be persisted safely across loads?
<details><summary>Answer</summary>Unsettled; trades warm-up for staleness and attacker-influenceable state.</details>

## 15. Go deeper next

1. **V8 sandbox & code pointer tables**: how containment of JIT bugs is engineered.
2. **Sea of Nodes → Turboshaft**: IR design tradeoffs.
3. **SpiderMonkey CacheIR**: ICs as an IR shared by interpreter and compiler.

## Sources

**Papers**
- Hölzle, Chambers, Ungar. PICs, ECOOP '91: https://bibliography.selflanguage.org/pics.html
- TurboTV, ICSE 2024: https://kihongheo.kaist.ac.kr/publications/icse24.pdf
- OptFuzz, USENIX Sec 2024: https://www.usenix.org/system/files/usenixsecurity24_slides-wang-jiming.pdf
- DUMPLING, NDSS 2025: https://www.ndss-symposium.org/wp-content/uploads/2025-1411-paper.pdf
- CacheIR: https://bernsteinbear.com/assets/img/cacheir.pdf
- Verified speculation, POPL'21: https://janvitek.org/pubs/popl21.pdf

**Code/docs**
- https://v8.dev/docs/hidden-classes · https://v8.dev/blog/fast-properties · https://v8.dev/blog/elements-kinds · https://v8.dev/blog/slack-tracking
- https://v8.dev/blog/maglev · https://v8.dev/blog/sparkplug · https://v8.dev/blog/leaving-the-sea-of-nodes · https://v8.dev/blog/mutable-heap-number · https://v8.dev/blog/sandbox · https://v8.dev/blog/react-cliff
- stub-cache.h: https://chromium.googlesource.com/v8/v8.git/+/refs/heads/main/src/ic/stub-cache.h
- handler-configuration.h: https://chromium.googlesource.com/v8/v8.git/+/refs/heads/main/src/ic/handler-configuration.h
- map.h: https://chromium.googlesource.com/v8/v8.git/+/refs/heads/main/src/objects/map.h
- JSC speculation: https://webkit.org/blog/10308/speculation-in-javascriptcore/

**Articles / writeups**
- Project Zero CVE-2020-6418: https://googleprojectzero.blogspot.com/p/cve-2020-6418-chrome-incorrect-side.html
- Project Zero CVE-2020-16009: https://googleprojectzero.blogspot.com/p/rca-cve-2020-16009.html
- Zellic CVE-2025-2135: https://www.zellic.io/blog/pwning-v8ctf/
- GitHub Blog Super IC: https://github.blog/security/vulnerability-research/the-chromium-super-inline-cache-type-confusion/
- mrale.ph monomorphism: https://mrale.ph/blog/2015/01/11/whats-up-with-monomorphism.html
- Bynens, shapes and ICs: https://mathiasbynens.be/notes/shapes-ics

*Verification notes: items marked "not opened"/"per agent" come from research subagent notes I did not re-fetch. Fetched and checked by me: stub-cache.h constants, Maglev blog numbers, Sea-of-Nodes 2× claim, elements-kinds post, mutable-heap-number post, Project Zero RCAs for CVE-2020-6418/16009, Zellic CVE-2025-2135.*
