# Static approximate-membership filters: XOR / binary fuse (peeling) vs Ribbon (banded Gaussian elimination)

**Computer science · Algorithms/data structures · XOR/binary fuse filters via hypergraph peeling vs Ribbon filters · hard · 2026-10-04**

Companion page: [index.html](index.html). Runnable demos: [peel_demo.py](peel_demo.py), [fuse_ribbon_demo.py](fuse_ribbon_demo.py).

---

## 0b. Plain English first

**Explain it simply.** Picture a bouncer at a club with a guest list of a million names. The list is too big to carry, so the bouncer carries a small cheat-sheet instead: a board of numbered slots with a number in each. To check a visitor, the bouncer hashes the name into three slot numbers, adds up (XORs) the three numbers on the board, and compares the result to a short "secret code" derived from the name. If they match, the visitor is waved through. Everyone on the list *always* matches. A stranger matches only by luck: with an 8-bit code, 1 in 256.

The clever part is how the board is filled in. We need, for every guest, "slot a + slot b + slot c = my code", all at the same time. That is a big puzzle. The trick: find a guest who owns one slot *alone* (nobody else touches it), park that guest on a stack, forget about them for now, and repeat. Eventually every guest is on the stack. Then fill the board in reverse: the last guest parked gets their lonely slot set to whatever makes their sum work; each earlier guest has already-fixed neighbours when their turn comes. The board only needs about 1.23 slots per guest for this to work out almost every time. Ribbon filters solve the same puzzle differently: as a school-style system of equations where every equation only touches a short nearby stretch of slots, so it can be solved in one pass, with as little as ~5-10% spare room.

**Everyday example.** Three guests (Ana, Ben, Cy) and a board of six slots in three pairs (A0 A1 | B0 B1 | C0 C1). Ana → A0, B0, C0 and code 5. Ben → A0, B1, C1 and code 3. Cy → A1, B0, C1 and code 6. Slot C0 is touched only by Ana, A1 only by Cy, and after those two are parked, A0 is touched only by Ben. Park Ana, Cy, Ben (in that order). Fill backwards: Ben first (set A0 to 3), then Cy (set A1 to 6), then Ana (set C0 so the sum is 5, which turns out to be 6). Board: A0=3, A1=6, B0=0, B1=0, C0=6, C1=0. Ana: 3+0+6 → 5 ✓. A stranger who hashes to A1, B1, C0 sums to 0 and is rejected unless their own code is 0.

**Bridge:** now the same thing, technically.

---

## 1. Bare-minimum context

- **AMQ filter**: answers "is x in S?" with no false negatives and false-positive rate ε. Info-theoretic minimum ≈ log₂(1/ε) bits per key ([Carter et al. 1978]; [Pagh–Pagh–Rao 2005]).
- **Bloom filter**: k hash positions in a bit array; needs ≈ 1.44·log₂(1/ε) bits/key (44% over minimum).
- **Fingerprint**: f-bit hash of the key; collision with a random stranger has probability 2^-f.
- **XOR / GF(2) linear algebra**: addition mod 2; a system of XOR equations can be solved with Gaussian elimination.
- **Random hypergraph**: each key is an edge joining 3 slots (vertices). *Peeling* removes degree-1 vertices repeatedly; the leftover is the *2-core*.
- **Static**: the full key set is known up front; no inserts or deletes after build (LSM SSTables, Parquet segments, blocklists).

## 1b. Real-world context (where, how, why)

**What it is.** A way to store an immutable set of keys so you can ask "might x be in it?" in ~3 memory reads using ~9 bits per key for a 0.4% false-positive rate. Instead of *inserting* keys, you *solve* for a table such that XOR of three cells equals each key's fingerprint.

**Why it exists.** Bloom filters guard disk/network lookups but waste 44% over the information-theoretic minimum and need k scattered probes. For data that never changes, the table can be *computed*, not grown: 23% overhead (XOR, 2019), 13% / 8% (binary fuse, 2022), or <10% with a tunable knob (Ribbon, 2021), down to <1% with experimental variants. Filters in an LSM tree stay in RAM for hours, so every saved bit is multiplied by lifetime.

**Where it's used (verified):**
- **RocksDB** — `NewRibbonFilterPolicy`: Ribbon for compaction output, Bloom for flushes. Blog: ~30% memory saved vs Bloom (7 vs 10 bits/key typical), ~4.4× construction CPU (140 vs 32 ns/key), ~20% query CPU; break-even at ~1 hour of filter lifetime.
- **Mozilla Firefox CRLite** — certificate revocation moved from Bloom cascades to "Clubcard": a partitioned two-level cascade of Ribbon filters; users download ~300 kB/day (4 MB snapshot every 45 days + deltas).
- **FastFilter/xor_singleheader** (C), **xorfilter** (Go), **xorf** (Rust), fastfilter_java/cpp — reference implementations of xor and binary fuse filters.
- **Bioinformatics, analytics, networking** — ZOR's abstract lists storage systems, analytics, networking, bioinformatics as consumers of peeling-based filters.
- **Not adopted (as far as I found):** ClickHouse, DuckDB, Parquet use (split-block) Bloom filters; I found no evidence of xor/fuse there.

**How it's used.**

```c
#include "binaryfusefilter.h"            // FastFilter/xor_singleheader
binary_fuse8_t f;
binary_fuse8_allocate(n, &f);            // ~1.13*n bytes
binary_fuse8_populate(keys, n, &f);      // keys: uint64_t[n], pre-hashed; returns false after 100 failed seeds
bool maybe = binary_fuse8_contain(x, &f);// 3 loads + XOR + compare; FPR ~ 1/256
binary_fuse8_free(&f);
```

```cpp
// RocksDB: Ribbon with Bloom-equivalent 10 bits/key; Bloom for L0/flush
table_options.filter_policy.reset(rocksdb::NewRibbonFilterPolicy(10.0));
// bloom_before_level (since 6.24): use Bloom on levels below the given one
```

Typical: 8-bit fingerprints (ε≈0.39%, ≈9 bits/key) or 16-bit (ε≈1.5e-5, ≈18 bits/key); keys pre-hashed to 64 bits.

**When to use / not.** Use when the set is built once and queried many times (SSTables, immutable segments, blocklists, k-mer sets). Avoid when you need inserts/deletes (Bloom, cuckoo, quotient filters), when the build must stream (Bloom), or when build memory is tight (peeling holds all hashes: ~24 B/key transient per implementation notes, unverified exactly). Pick binary fuse for speed; Ribbon for tunable/smaller space and LSM integration; Bloom for very short-lived filters (L0).

**Who should care.** Storage/DB engineers (LSM filters), infra (blocklists, cert revocation), search/index and genomics engineers (membership over huge immutable sets), anyone paying RAM per key.

## 2. The one-liner and what it hides

*"XOR filters are Bloom filters that are smaller and faster because you precompute a table where three cells XOR to the fingerprint."* It hides:

1. **Why the table can always be computed**: only if the 3-uniform hypergraph is peelable, which needs ≥1.22× slots per key — a phase transition, not a heuristic.
2. **Why the FPR is exactly 2^-f** (and when it isn't).
3. **How binary fuse beats the threshold** (1.22 → 1.13/1.08) by restricting keys to windows of consecutive segments (spatial coupling).
4. **That Ribbon abandons hypergraphs entirely**: banded linear algebra, a different space/time tradeoff.
5. **What breaks**: duplicates, construction failure retries, adversarial keys, memory spike, 64-bit hash assumption, no updates.

## 3. The problem

Bloom filter at ε = 1%: ~9.6 bits/key optimal-k, 7 probes into a large bit array (cache misses). Information minimum is log₂(100) ≈ 6.64 bits/key. For ε = 2^-8: Bloom ≈ 11.5 bits vs 8 bits minimum. In a 10-billion-key LSM, 3 bits/key is 3.75 GB of RAM. Static sets don't need Bloom's incremental insertability, so the constraint "must be insertable one key at a time" is what costs the 44%.

## 4. Mental model

A **bulletin board of sticky notes**. Each guest has three notes assigned; the notes must XOR to the guest's code. Filling the board = solving every guest's equation at once. Peeling = repeatedly set aside a guest who owns a private note, then fill the board in reverse so that private note absorbs the slack. The analogy breaks on sharing: the board has only ~1.23 slots per guest while each guest touches 3, so slots are heavily shared. Solvability is not a local guarantee; it comes from a global property of the random hypergraph (no dense core below ~82% load).

## 5. The mechanism, traced (3-bit fingerprints, 6 slots)

Keys and their hashed positions (one slot per block): 

```
Ana: A0 B0 C0   fp=5 (101)      slots: A0 A1 | B0 B1 | C0 C1
Ben: A0 B1 C1   fp=3 (011)
Cy : A1 B0 C1   fp=6 (110)
degrees: A0=2 A1=1 B0=2 B1=1 C0=1 C1=2
```

**Peeling** (queue starts with degree-1 vertices {A1, B1, C0}):
1. Pop C0 (degree 1, only Ana): push (Ana, via C0) on stack. Decrement A0→1, B0→1.
2. Pop A1 (only Cy): push (Cy, via A1). B0→0, C1→1.
3. Pop A0 (only Ben now): push (Ben, via A0). B1→0, C1→0.
Stack = [Ana/C0, Cy/A1, Ben/A0]; all 3 keys peeled ⇒ the 2-core is empty ⇒ success.

**Assignment (reverse stack, B initially all 0):**
- Ben via A0: A0 = fp(Ben) ^ B1 ^ C1 = 3 ^ 0 ^ 0 = **3**
- Cy via A1: A1 = 6 ^ B0 ^ C1 = **6**
- Ana via C0: C0 = 5 ^ A0 ^ B0 = 5 ^ 3 ^ 0 = **6**

Board: `A0=3 A1=6 | B0=0 B1=0 | C0=6 C1=0`. Check Ana: 3^0^6 = 5 ✓. Ben: 3^0^0 = 3 ✓. Cy: 6^0^0 = 6 ✓. 

**Why reverse order works:** the vertex a key was peeled through is, at peel time, touched by no other *unpeeled* key. Every later-peeled key... in reverse, any key assigned later was peeled *earlier*, and its assigned vertex is not shared with keys peeled after it, so it never disturbs them. Each cell is written at most once.

**Query** y: h = (A1, B1, C0), fp(y) = 4 (100). Sum = 6^0^6 = 0 ≠ 4 → reject. If fp(y) were 0, false positive.

**Binary fuse query, as shipped** (FastFilter/xor_singleheader `binaryfusefilter.h`):

```c
hash = murmur64(key + seed);  f = (uint8_t)(hash ^ (hash >> 32));
h0 = mulhi(hash, SegmentCountLength);           // uniform over the first SegmentCount segments
h1 = (h0 + SegmentLength) ^ ((hash >> 18) & SegmentLengthMask);   // next segment, random offset
h2 = (h0 + 2*SegmentLength) ^ (hash & SegmentLengthMask);          // segment after that
return f == (F[h0] ^ F[h1] ^ F[h2]);
```

Segment length is a power of two, `2^floor(ln(n)/ln 3.33 + 2.25)` (arity 3), array size factor `max(1.125, 0.875 + 0.25·ln(10^6)/ln n)`; build retries up to `XOR_MAX_ITERATIONS = 100` seeds; keys are sorted into segment-order buckets first for cache locality; the current C code detects and drops duplicate keys when a round fails.

**Ribbon, traced.** Each key becomes (start s, w-bit coefficient word c with bit 0 set, r-bit fingerprint b). Insert: if pivot row s is empty, store; else XOR the new equation with the stored one, shift out leading zeros (c ← c≫j, s ← s+j) and continue. If c becomes 0 with b=0 the equation was redundant; with b≠0 the system is inconsistent ⇒ new seed. Back-substitution from the last row up: Z[i] = b_i ⊕ ⨁_{j>0, c_i[j]=1} Z[i+j]. Query: XOR the Z rows selected by c's set bits, compare to b — all within a w-row window (64 rows × 8 bits = 64 B, about one cache line), versus three random cache misses for xor.

## 6. The math

**(a) Information bound.** A filter for S (|S|=n, universe u) accepts a set A ⊇ S with |A| ≈ n + εu. Each distinct stored state must "cover" the C(u,n) possible sets; one A covers C(n+εu, n) of them. States needed ≈ C(u,n)/C(εu,n) ≈ (1/ε)^n ⇒ n·log₂(1/ε) bits.
→ *In plain terms: each key must "pay" for forgetting everything except its ε-sized neighbourhood.*

**(b) Why Bloom wastes 44%.** Optimal Bloom has half the bits set; each bit carries <1 bit of information. m/n = log₂e · log₂(1/ε) ≈ 1.44·log₂(1/ε).
→ *You pay for entropy you don't use because a Bloom filter's bit array is only 50% informative.*

**(c) Why FPR = 2^-f.** For y ∉ S, the three cells hold values determined by other keys' random fingerprints; their XOR is (effectively) uniform on f bits and independent of fp(y), so P[XOR = fp(y)] = 2^-f. Bits per key = f × (slots/key) = 1.23f (xor), ≈1.13f (fuse-3), ≈1.08f (fuse-4).
→ *Space is the fingerprint width times slot overhead; the overhead is the whole game.*

**(d) Peeling threshold.** Slots m, keys n, c = n/m. Each slot has Poisson(3c) incident edges. Let q = probability that an edge, seen from one endpoint, survives peeling (is not removed via its other two endpoints). An endpoint u keeps the edge alive iff u has ≥1 other surviving edge: probability 1 − e^{−3cq}. The edge survives iff both other endpoints do:

   q = (1 − e^{−3cq})²

q = 0 is always a solution (full peeling). A nonzero solution (a 2-core) appears at the smallest c where the curve c(q) = −ln(1−√q) / (3q) bottoms out. Numerically (my run): c\* = 0.8185 for k=3 ⇒ slots/key ≥ 1/c\* = **1.2218** (≈1.23 with slack); k=4: c\* = 0.7723 ⇒ 1.295; k=5: 0.7018 ⇒ 1.425.
→ *Below ~82% load a random 3-hypergraph has no dense knot; above it, a knot of unsolvable keys appears suddenly. Larger arity peels worse; arity 3 is the sweet spot.*

Why not simply use orientability (every key can be assigned its own cell; threshold ≈ 0.918 ⇒ 1.089 for k=3, from the literature, not re-derived here)? Orientable ≠ peelable: a solution exists but greedy peeling can't find it; Gaussian elimination can, at O(n³)-ish cost (or banded cost → Ribbon).

**(e) Fuse windows.** Keys pick a start segment s and use segments s, s+1, s+2. The two end segments have lower degree, so peeling starts there and a "wave" moves inward, the spatial-coupling / threshold-saturation effect Walzer proved (arXiv:2001.10500) moves the peeling threshold toward c^orient. Result: 1.125 (arity 3) or 1.075 (arity 4) at large n, with the size factor growing for small n (code above).

**(f) Ribbon.** Equations ⟨h(x), Z⟩ = b(x) over GF(2), where h(x) = 0^s · c · 0^{m−s−w} has one random block of width w per row. Dietzfelbinger–Walzer (arXiv:1907.04750): such matrices with m = n/(1−ε) columns have full row rank whp for w = O(log n / ε) and elimination costs O(n/ε²). Ribbon uses w=64 (a machine word) and obtains ε of a few percent; paper: <10% overhead at modest CPU cost, <1% with an experimental balanced variant; follow-up BuRR (SEA 2022) "well below 1%" by *bumping* the few rows that don't fit into a fallback.
→ *Shorter band = faster solve but more slack needed; wider band = tighter packing; w is the dial.*

## 7. Why it works

Core insight: **sparse random constraint systems with ~1.22 variables per equation are solvable by a trivial greedy order**, and a solved table plus a random fingerprint gives exact 2^-f false-positive rate with one XOR. Ablation:
- Remove the *3-way* split → arity 2 peels only up to c<0.5 (2.0 slots/key).
- Remove the *retry with new seed* → failures near threshold (≈18% at 1.23 for n=20000 in my demo) become hard errors.
- Remove the *fingerprint randomness* → FPR no longer 2^-f; adversarial queries could pick y whose XOR equals fp(y).
- Remove *windows* → back to 1.22.
- Ribbon: remove the *band* → dense Gaussian elimination, O(n³).

## 8. Design knobs & alternatives

| Knob | Effect |
|---|---|
| fingerprint bits f | FPR 2^-f; bits/key = f × factor |
| arity 3 vs 4 (fuse) | 1.125 vs 1.075 factor; arity 4 slightly slower query (4 loads) |
| segment length | locality vs peeling success; power of two from empirical formula |
| Ribbon width w, r | space overhead vs CPU; r bits solution per row |
| Ribbon *standard / homogeneous / balanced / BuRR* | speed ↔ space ↔ never-fails ↔ <1% |
| Bloom/Ribbon hybrid (RocksDB) | Bloom where lifetime is short |

Alternatives: Bloom/blocked Bloom (streaming insert), cuckoo/quotient/vector-quotient (delete, resize), prefix filter, Aleph/InfiniFilter (growing). Static filters won where the set is immutable and RAM matters.

## 9. Where it breaks

- **Construction can fail** (retry seed; ≤100 in the C library, expected ≈1.1 tries). Close to the threshold failures are common (my demo: 82% at 1.23, n=20000).
- **Duplicates** can prevent peeling (two identical edges form a 2-core). Current C binary-fuse code detects and removes them on a failing round; older/other ports may just error. Deduplicate.
- **Adversarial keys**: attacker-chosen keys with a *known* seed can build a 2-core. Use a secret/random 64-bit seed per build; the filter is not adversarially robust for *queries* either (a false positive is deterministic for given seed; see Naor–Yogev-style models).
- **Build memory**: peeling holds all key hashes + counters; sorting into segment buckets helps cache but not memory.
- **n limits**: library `size` is `uint32_t`; 8-bit fingerprints cap ε at 2^-8 and 64-bit hashes are assumed (32-bit hash + 10^8 keys collides).
- **Small n**: size factor rises sharply below ~10^5 (e.g. 1.2+); xor/fuse can be bigger than Bloom at high ε.
- **No updates**: any change ⇒ rebuild. Dynamic filters have a provable Ω(n)-bit penalty (Kuszmaul–Walzer, STOC 2024).
- **Misconceptions**: "xor always beats Bloom" (not at large ε or tiny n); "static is useless" (most big filters live in immutable files); "Ribbon is slow" (queries ~20% in RocksDB's own numbers; construction is the cost).

## 10. In the wild

- **RocksDB**: hybrid by level; `bloom_equivalent_bits_per_key` lets you keep the same FPR as Bloom while spending ~30% less; one full filter per SST file.
- **Firefox CRLite/Clubcard**: Ribbon in a two-level cascade; because filters are rebuilt on a schedule, a static structure is natural.
- **xor_singleheader**: 8/16/32-bit variants, serialization/mmap (flat array + seed + segment parameters), pre-hashed `uint64` keys.
- **Deviation from paper**: fuse construction sorts hashes into segment buckets (not in the textbook peeling), uses `mulhi` instead of `%`, and XOR-offsets within segments instead of independent hashes.

## 11. Frontier (verified against arXiv/abstract pages unless flagged)

1. **ZOR filters** — Limasset, arXiv:2602.03525 (Feb 2026). Deterministic peeling: instead of restarting on failure, abandon <1% of keys into a small side structure; within 1% of the information bound, fuse-like query speed, slower build in the prototype.
2. **Fingerprint Filters Are Optimal** — Kuszmaul, Liang, Zhou, FOCS 2025, arXiv:2510.18129. Any dynamic filter needs ≥ n·log ε⁻¹ + n·log e − o(n) bits: fingerprinting (the 1978 Carter et al. idea) is tight for dynamic filters.
3. **Space Lower Bounds for Dynamic Filters and Value-Dynamic Retrieval** — Kuszmaul & Walzer, STOC 2024, DOI 10.1145/3618260.3649649. Dynamic filters: n·log ε⁻¹ + Ω(n) bits, a provable gap to static.
4. **Tight Bounds and Phase Transitions for Incremental and Dynamic Retrieval** — Kuszmaul et al., SODA 2025, arXiv:2410.10002.
5. **Grafite** — Costa, Ferragina, Vinciguerra, SIGMOD 2024, arXiv:2311.15380: range filter with O(1) query and FPR ≤ ℓ/2^(B−2) for any data and any query workload (robust to adversarial/correlated queries).
6. **Memento filter** — Eslami & Dayan, SIGMOD 2025, arXiv:2408.05625: dynamic range filter; in WiredTiger it doubles range-query throughput when 50% of queries are empty.
7. **Aleph filter** — Dayan, Bercea, Pagh, arXiv:2404.04703 (VLDB 2024, per search results): expandable filter with constant-time operations, memory-vs-FPR on par with static filters if the growth is predicted.
8. **Peeling close to the orientability threshold** — Walzer, arXiv:2001.10500: spatial coupling as the theory behind fuse-style windows.
9. **BuRR / Fast succinct retrieval and AMQ using Ribbon** — Dillinger, Hübschle-Schneider, Sanders, Walzer, SEA 2022, arXiv:2109.01892: space overhead well below 1%.
10. Unverified by me, flagged: Diva (VLDB 2025), Zeno filter (SIGMOD 2026), parallel BuRR construction (arXiv:2411.12365) — appear in search results but I did not open them.

## 11b. Open problems

- **Fast construction near the bound.** Ribbon/ZOR reach ~1% overhead but pay in build time (RocksDB: ~4.4× Bloom's build CPU); fuse is fast but ≥8% over. Nobody has both at all scales.
- **Deterministic, restart-free build** with no side structure (ZOR still needs one).
- **Adversarial robustness**: static fuse/Ribbon filters give no guarantee against adaptive query adversaries; adaptive/robust Bloom constructions (Naor–Yogev) cost extra and rely on one-way-function-like assumptions.
- **Range filters with worst-case guarantees at static-filter space** (Grafite closes much; correlated/adaptive workloads still contested).
- **External-memory / SIMD / GPU peeling**: the peeling phase is inherently sequential and cache-hostile; no mature GPU xor/fuse builder that I found.
- **Learned filters** (partitioned learned Bloom filters, NeurIPS 2024): gains depend on query distribution; adversarial robustness and drift unresolved.

## 12. Lineage

Bloom 1970 → Carter et al. 1978 (fingerprint filters, bound) → Bloomier filters (Chazelle et al. 2004) → Dietzfelbinger–Pagh 2008 (succinct retrieval/AMQ) → Botelho–Pagh–Ziviani 2013 (peeling for perfect hashing) → **XOR filters (Graf–Lemire 2019/2020)** → Dietzfelbinger–Walzer 2019 (banded elimination) → **Ribbon (Dillinger–Walzer 2021)** / BuRR 2022 → Walzer 2020 (spatial coupling) → **binary fuse (Graf–Lemire 2022)** → ZOR (2026).

## 13. Hands-on (≤30 min)

```
python3 peel_demo.py          # peeling phase transition + a real 8-bit xor filter
python3 fuse_ribbon_demo.py   # fuse-style windows vs threshold + a tiny Ribbon (w=64)
```

My runs (pure Python, n=20000 for xor and ribbon, n=100000 for fuse):

```
factor 1.10/1.18/1.21 -> peel success 0%;  1.23 -> 82%;  1.25 -> 100%      (theory threshold 1.2218)
xor8: 24633 slots, 9.853 bits/key, FPR 0.4155% (theory 0.391%)
fuse-style windows (L=2048): array/n 1.106 -> 0%, 1.147 -> 0%, 1.188 -> 100%, 1.229 -> 100%
Ribbon w=64 r=8: m/n 1.02 -> 0/10, 1.05 -> 7/10, 1.10 -> 10/10; 8.80 bits/key, FPR 0.378%
```

Try: change `positions` to 2 blocks (arity 2) and watch the threshold jump to ~2.0×; change the Ribbon width `W` to 16 and see the needed slack grow.

## 14. Question ladder

**Mechanism**
1. In the 3-key trace, why is it safe to assign Ana's slot C0 *after* Ben's and Cy's?
2. Why does each cell get written at most once?
3. In a Ribbon insert, what does `c & -c` compute and why do we shift?
4. In `binary_fuse8_contain`, why XOR the in-segment offset instead of adding it?

**Why**
5. Why 3 hash positions and not 2 or 4?
6. Why is the FPR exactly 2^-f and what must be true of the fingerprint hash?
7. Why does a windowed hypergraph peel at lower density than a uniform one?
8. Why is Ribbon's query cache-friendlier than XOR's?

**Counterfactual**
9. What if all keys had the same fingerprint? What if fingerprints were chosen non-randomly?
10. What if the array were 1.20n for plain XOR with n=10^6?
11. What if w=64 were w=1024 in Ribbon?
12. What if a duplicate key is inserted twice?

**Adversarial**
13. How would an attacker who knows the seed force a build failure?
14. How could an attacker find queries that are false positives?
15. How would you make build-time hash flooding harmless?

**Connection**
16. How does peeling relate to LDPC decoding and erasure codes?
17. How does this relate to cuckoo hashing's orientability threshold?
18. How do minimal perfect hash functions (BDZ/RecSplit/ShockHash) reuse these ideas?

**Open**
19. Can a fast, restart-free construction reach <1% overhead without a side structure?
20. Is there an adversarially robust static filter at ~1.1× the information bound?
21. Do learned filters beat fuse/Ribbon on realistic non-stationary workloads?

<details><summary>Answers</summary>

1. Ana's slot C0 was touched by nobody else among unpeeled keys when she was peeled, so no later-assigned key writes it and no earlier-assigned one reads it before it's set; her other two cells (A0, B0) are already final when she's assigned.
2. Each key is assigned exactly one cell: the one through which it was peeled; a cell gets peeled through only one key (degree 1 at that time).
3. It isolates the lowest set bit; bit_length−1 is the number of trailing zeros j. The reduced equation now starts at row i+j, so shift the word right by j to realign coefficient bit 0 with that pivot.
4. XOR with a mask < SegmentLength permutes positions inside the segment-aligned block, staying in-segment; adding could cross into the next segment and break the window structure.
5. Arity 2 peels only below load 0.5 (2.0 slots/key); arity 4 raises the threshold requirement to 1.295 slots/key without windows, and costs another memory read. 3 minimizes slots/key for plain peeling.
6. The XOR of three cells is uniform on f bits and independent of fp(y), because cells were set from other keys' independent random fingerprints; the fingerprint hash must behave like a random function independent of positions.
7. End segments have lower degree, which seeds peeling; once boundary keys peel, their neighbours drop to degree 1 in a wave (spatial coupling / threshold saturation), reaching beyond the uniform threshold.
8. Window of w consecutive rows ≈ one cache line, versus 3 random lines in XOR.
9. FPR becomes 100% for that fingerprint; non-random fingerprints let queries correlated with them be accepted systematically; solvability is unaffected.
10. Load 0.833 > 0.8185: a 2-core of ~Θ(n) keys remains whp; construction fails on essentially every seed.
11. Needs less slack (smaller ε) but elimination per key costs more and the query window spans 16 cache lines.
12. The two identical edges both sit on the same 3 slots; peeling cannot reduce them below degree 2 ⇒ failure on every seed, unless duplicates are detected/removed (current C binary-fuse code does that after a failing round).
13. Pick keys that all hash into the same few slots (≥ 1.23·slots) ⇒ a guaranteed 2-core; needs the seed or a weak hash.
14. With the filter (or seed) known, test candidate queries offline until ~2^f of them yield a false positive. With a secret seed the attacker only sees accept/reject, so each probe succeeds with probability 2^-f; once a false positive is found it stays a false positive forever (the filter is not adaptive).
15. Per-build random secret 64-bit seed with a strong mixer; reject-and-retry.
16. Both are peeling on sparse random hypergraphs; the 0.818 threshold is the same object as the BP erasure-decoding threshold of LDPC codes; spatial coupling is the same fix.
17. Orientability = each key assignable its own cell (threshold ≈0.918); peeling is a stricter, greedy-solvable subset.
18. BDZ builds MPHF via peeling; RecSplit/ShockHash use brute-force and cuckoo-style seeds; they target ~1.44–1.5 bits/key for MPHF.
19. Open; ZOR trades determinism for a side structure; spatial coupling + parallelism are active directions.
20. Open.
21. Open; depends on drift and adversarial queries.

</details>

## 15. Go deeper next

1. Minimal perfect hashing (BDZ → RecSplit → ShockHash → ConsensusRecSplit).
2. Spatial coupling and threshold saturation (LDPC codes ↔ hash tables).
3. Adaptive / robust filters (telescoping adaptive filter, Naor–Yogev model).

## Sources

**Papers**
- Graf & Lemire, *Xor Filters*, JEA 2020 — https://arxiv.org/abs/1912.08258
- Graf & Lemire, *Binary Fuse Filters*, JEA 2022 — https://arxiv.org/abs/2201.01174
- Dillinger & Walzer, *Ribbon filter: practically smaller than Bloom and Xor* — https://arxiv.org/abs/2103.02515
- Dillinger, Hübschle-Schneider, Sanders, Walzer, *Fast Succinct Retrieval and Approximate Membership using Ribbon* (SEA 2022) — https://arxiv.org/abs/2109.01892
- Dietzfelbinger & Walzer, *Efficient Gauss Elimination for Near-Quadratic Matrices…* (ESA 2019) — https://arxiv.org/abs/1907.04750
- Walzer, *Peeling Close to the Orientability Threshold* — https://arxiv.org/abs/2001.10500
- Limasset, *ZOR filters* — https://arxiv.org/abs/2602.03525
- Kuszmaul, Liang, Zhou, *Fingerprint Filters Are Optimal* — https://arxiv.org/abs/2510.18129
- Kuszmaul & Walzer, *Space Lower Bounds for Dynamic Filters and Value-Dynamic Retrieval* — https://doi.org/10.1145/3618260.3649649
- Kuszmaul et al., *Tight Bounds and Phase Transitions for Incremental and Dynamic Retrieval* — https://arxiv.org/abs/2410.10002
- Costa, Ferragina, Vinciguerra, *Grafite* — https://arxiv.org/abs/2311.15380
- Eslami & Dayan, *Memento Filter* — https://arxiv.org/abs/2408.05625
- Dayan, Bercea, Pagh, *Aleph Filter* — https://arxiv.org/abs/2404.04703

**Code / docs / articles**
- https://github.com/FastFilter/xor_singleheader (`binaryfusefilter.h`, read directly)
- https://rocksdb.org/blog/2021/12/29/ribbon-filter.html
- https://hacks.mozilla.org/2025/08/crlite-fast-private-and-comprehensive-certificate-revocation-checking-in-firefox/

*Verification notes:* numbers in the paper abstracts, the C source, the RocksDB blog, and the CRLite post were read from the primary page. Build memory ~24 B/key, RocksDB format-version requirements, Diva/Zeno/parallel-BuRR claims, and VLDB venue for Aleph came only from search-agent notes and are flagged where used. Orientability threshold 0.918 is quoted from literature knowledge, not re-derived.
