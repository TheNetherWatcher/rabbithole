# Swiss tables: control bytes, SIMD group probing, tombstones and 7/8 load

*Computer science · Algorithms/data structures · Swiss tables (Abseil, hashbrown, Go 1.24) · hard*

A Swiss table is an open-addressing hash table with a **1-byte tag per slot**. One SIMD instruction compares a lookup key's 7-bit tag against **16 slots** (8 in Go), so full key comparisons are rare. A probe stops at the first **empty** slot, deletes write a tombstone only when needed, and tables run up to **7/8 full**.


## In everyday words: A strip of sticky notes lets the clerk check a whole row at a glance

Picture a mailroom with a wall of pigeonholes, arranged in rows of 16. Parcels are filed by a number worked out from the recipient's name, so the clerk goes straight to the right row. The slow part used to be what happens next: in a normal mailroom the clerk peeks into every pigeonhole in the row, one by one, reading each label in full.
The Swiss-table trick is a thin strip above each row with one tiny sticky note per pigeonhole, holding a short fingerprint of the name (not the whole name). The clerk glances at the strip and sees at once which pigeonholes *might* hold the parcel. Only those get opened. If the strip shows a blank spot in the row, the clerk knows the parcel was never pushed on to another row, so a "not here" answer comes quickly. If the row is totally full, the clerk follows a fixed hop pattern to another row and glances at its strip.

### Everyday example

Maya's parcel is filed in row 0. The fingerprint "5A" appears on two sticky notes in that row. The clerk opens both: the first holds somebody else's parcel (the fingerprint was a coincidence), the second is Maya's. Done after one glance and two peeks.
Now Noor asks for a parcel that was never filed. Her name points at row 1, which is completely full, so the clerk hops to row 2. Row 2 has blank notes and nothing matches "5A", so the clerk answers "not here" without visiting any other row. Later someone collects a parcel from full row 1. The clerk can't just blank that note, because Noor-style searches may have relied on the row being full to keep moving, so they stick on a "was here, keep looking" flag instead. Collecting a parcel from a row that still has blanks needs no flag at all.
Now the same thing, technically.

## §1 · Bare-minimum context: Six ideas you need first

- **Hash table**: a hash function maps a key to a number; the table turns that number into a slot index (here, `hash & mask` with a power-of-two size).
- **Chaining vs open addressing**: chaining hangs a linked list off each bucket; open addressing stores entries in the array itself and probes neighbouring slots on collision.
- **Load factor**: entries ÷ slots. Open addressing gets slower as it rises; the table resizes at a chosen ceiling.
- **SIMD compare + movemask**: one instruction compares 16 bytes to a value and another packs the 16 results into a 16-bit integer you can bit-scan.
- **Tombstone**: a marker left by a delete so probe sequences that passed through the slot keep going.
- **Cache line**: the CPU fetches 64 bytes at a time, so a 16-byte tag group is one cheap load.

## §1b · Real-world context: Rust, Go and Google C++ all store maps this way

### What it is

A Swiss table is an open-addressing hash table with a separate array of one-byte control tags, one per slot. A full slot's byte holds 7 bits of the key's hash; special values mean "empty" and "deleted". Lookups compare a whole group of tags to the key's 7-bit tag with one SIMD instruction and only run the real key comparison on the few matches. Google's Abseil library introduced it (Matt Kulukundis, CppCon 2017, "Designing a Fast, Efficient, Cache-friendly Hash Table, Step by Step").

### Why it exists

The standard C++ `std::unordered_map` chains through heap-allocated nodes: a pointer per entry and a likely cache miss per hop. Plain linear probing avoids pointers but compares full keys slot by slot and clusters badly near full. Swiss tables keep the flat layout and make each probe step cheap enough to run at 7/8 load. Rust's hashbrown README reports about 2× the speed of the previous std map and 1 byte of overhead per entry instead of 8 (the maintainers' own figures, no methodology given).

### Where it's used

**Abseil**flat_hash_map / flat_hash_set, the original. Apache-2.0.
**Rust std**`HashMap` is hashbrown since Rust 1.36 (July 2019). Apache-2.0 OR MIT.
**Go 1.24**The built-in `map` became a Swiss table in Go 1.24 (Feb 2025). Opt out with `GOEXPERIMENT=noswissmap`.
**CockroachDB**A standalone Go Swiss map library (`cockroachdb/swiss`).
**Proposals**An LLVM `FoldingSet` RFC and a Ruby `st_table` layer (Feature #22011) explored it; Ruby's benchmarks regressed (see "Where it breaks").

### How it's used

```
// Rust: nothing to tune except capacity and hasher
use std::collections::HashMap;
let mut m: HashMap = HashMap::with_capacity(1_000_000);
m.insert(42, "a".into());
let v = m.get(&42);

// C++ (Abseil)
absl::flat_hash_map m;
m.reserve(1'000'000);   // avoids rehashes while filling
m["x"] = 1;

// Go: no knobs at all
m := make(map[string]int, 1_000_000)   // hint only
```

Rust's std default hasher is `RandomState` (SipHash 1-3, "subject to change"). The standalone `hashbrown` crate defaults to foldhash, which is faster but does not claim HashDoS resistance against an interactive attacker.

### When to use it, when not

**Use** for general-purpose maps and sets, small-to-medium keys and values, lookup-heavy loads, anywhere you do not need stable pointers to elements.
**Skip** when you need pointer or reference stability across inserts (values move on rehash), when values are huge (move cost on growth), or when you hold untrusted keys under a weak hasher.

### Who should care

Backend and infra engineers (map-heavy services), systems and database authors, performance engineers reading flame graphs full of hash lookups, and security engineers reasoning about hash flooding.

## §2 · The one-liner: "A flat hash table with a 1-byte tag array" hides five things

**The one-liner:** "An open-addressing hash table with a 1-byte tag array, so one SIMD compare checks 16 slots at once."

### What it hides

- The tag is only **7 bits**, so false matches happen (about 1 per 128 occupied slots) and the full key is always compared before a hit is declared.
- The control byte has **three states** besides a tag: empty, deleted, sentinel. Whether a slot is empty or deleted decides if a probe stops, and getting it wrong breaks lookups.
- Probing is **per group, not per slot**, in triangular steps, and which groups get visited depends on how many are full: at 7/8 load, nearly half of 16-slot groups have no empty slot.
- **Erase sometimes writes empty instead of a tombstone**, using a "was this slot ever in a full window" test. That one trick is what keeps churn workloads from filling the table with tombstones.
- The **7/8 load factor** is only affordable because a group probe is cheap. Go and hashbrown chose different group widths and added different growth machinery around the same core.

## §3 · The problem: Chaining chases pointers; linear probing compares every key

**1 byte**of metadata per slot in a Swiss table, versus a pointer (8 bytes) per entry in a chained table (hashbrown README, vendor claim)

### What was broken

**Chaining** (`std::unordered_map` in libstdc++/libc++) allocates a node per entry. Each lookup follows at least one pointer to a separate heap object, typically a cache miss costing on the order of 100 ns versus about 1 ns for an L1 hit. The standard also forces pointer stability, which rules out the flat layout.
**Linear probing** stores entries inline and walks slots one after another. It is cache-friendly, but a probe step runs a full key comparison on each occupied slot, and runs of occupied slots (primary clustering) lengthen sharply as load grows, so it has to resize early (often at ≤50-70% load) and waste memory.
**The constraint that forced the design:** compare as little as possible per slot, stay inside one cache line per probe step, and keep the load factor high. A byte-sized fingerprint array turns "check up to 16 keys" into "one compare, then usually zero or one key checks".

## §4 · Mental model: A strip of tags above each row of slots

The mailroom: a strip of sticky notes above each row of pigeonholes. One glance at the strip tells you which pigeonholes could hold your parcel and whether the row has any blank spot.

### Where the analogy breaks

- Fingerprints really can collide (about 1 in 128), so "might hold" means "might", and the clerk always checks the full name before handing over a parcel.
- Hops between rows are not to the neighbouring row: the probe moves +1, then +2, then +3 groups, wrapping around a power-of-two number of groups.
- The strip is a separate array in memory from the pigeonholes. That is why one 16-byte load covers a group; the slots themselves are loaded only for matches.
- The "was here, keep looking" flag has a hidden cost in the real table: it uses up growth budget until the next rehash.

## §5 · The mechanism, traced: Find: one compare, then hop only while the group is full

Trace on a toy table: 4 groups of 8 slots (Go-style aligned groups, so it fits on screen). Keys K1 and K2 both carry tag `0x5A`.

  ← Back
  Next →
  
  

### The data structure

One allocation holds a control-byte array and a slot array of the same length. A control byte is either a 7-bit tag (top bit 0) or one of three special values with the top bit set. That top bit is the whole trick behind the cheap masks: "full" is `byte >= 0`, "empty or deleted" is a sign-bit test, and "empty" is one equality compare.

### Find, as code

```
// Abseil-style find, simplified. W = 16 on SSE2, 8 on NEON/portable.
probe = ProbeSeq(h1(hash) & capacity_mask)
loop:
    g = Group(ctrl + probe.offset)           // W control bytes
    for i in g.Match(h2(hash)):              // _mm_cmpeq_epi8 + _mm_movemask_epi8, then bit-scan
        if key_eq(slots[(probe.offset + i) & mask], key): return slot
    if g.MaskEmpty(): return NOT_FOUND       // an empty slot ends the search
    probe.next()                             // offset += index; index += W; offset &= mask
```

Going by the Abseil source read for this dive: capacities are `2k−1` so `& mask` wraps, `probe.next()` grows the step by W each time so offsets are triangular multiples of W, and when the group count is a power of two every group is visited once. Abseil and hashbrown start the window at *any* slot (`h1 & mask`), Go uses aligned groups; the traces and the simulator use aligned groups for clarity.

### Insert

Insert first runs `find` to avoid duplicates, then probes again for the first group with an empty *or deleted* slot, writes the tag and the value there, and decrements `growth_left`. If `growth_left` is zero the table rehashes first (see math and breaks).

### Erase

An erase cannot always write `empty`, because that could cut a probe path: a later lookup for a key that overflowed past this group would stop at the new empty and wrongly report "absent". Abseil writes `empty` only if the slot "was never full": there are empties in the window before and after it, and no 16-slot run of full slots spans it. Otherwise it writes `deleted`.

**Verify before quoting:** the exact window arithmetic of the "never full" test was read from `raw_hash_set.cc` in a research pass and flagged for double-checking. The behaviour (empty only when no probe could have passed) is certain; the precise bit-twiddle is not reproduced here.
**From memory, not re-verified:** Abseil keeps `W−1` cloned control bytes after the end of the array so an unaligned group load near the end wraps correctly.

## §6 · The math: Almost half of 16-slot groups are full at 7/8 load

### 1. False matches from a 7-bit tag

A wrong occupied slot has an independent 7-bit tag, so it equals the key's tag with probability 1/27 = 1/128.
E[false key compares per group visited] = occupied · 1/128
_→ in plain terms: a group with 14 of 16 slots full wastes about 0.11 key comparisons per visit. With more tag bits the filter would be sharper, but the control byte also needs the top bit for "empty/deleted", leaving 7._
Measured in the simulator (aligned groups, W = 16, 7/8 load): 0.231 false matches per *missing* lookup, about 2.1 groups × 0.11.

### 2. How many groups does a lookup touch?

A miss ends at the first group with an empty slot, so its cost is the expected number of groups until one has room. If a fraction *p* of groups are completely full and the probe sees them independently, this is a geometric distribution:
E[groups probed, miss] ≈ 1 / (1 − p)
_→ in plain terms: the fuller your groups, the more hops a "not here" answer needs._
The naive guess sets *p* = αW (every slot full with probability α). That is wrong because keys land in groups unevenly. Before any overflow, group occupancy is roughly Poisson with mean αW; with α = 7/8 and W = 16, P(X ≥ 16) ≈ 0.33. Overflow then pushes the excess into neighbouring probe targets, which raises the measured full-group share further:

load α | W | αW guess | Poisson before overflow | measured full groups | measured miss groups

0.75 | 16 | 0.010 | 0.156 | 0.189 | 1.25

0.875 | 16 | 0.118 | 0.331 | 0.476 | 2.09

0.875 | 8 | 0.344 | 0.401 | 0.603 | 2.93

0.95 | 16 | 0.440 | n/a | n/a | 4.80

All "measured" figures come from `swiss_sim.py` in this folder: aligned groups, a splitmix64 hash, 16K–32K slots, 20,000 lookups per row, one seed. They are a model of the design, not benchmarks of Abseil, hashbrown or Go. Treat the shape (nearly half of 16-wide groups full at 7/8) as the finding.

### Interactive: load factor vs. probes

Load factor 0.875
Group width8 slots 16 slots

### 3. Load factor and growth budget

Abseil keeps `growth_left`: the number of insertions allowed before a rehash. For capacity above 63 it starts at `capacity − capacity/8`, i.e. 7/8. Tombstones are not freed by erase; they stay counted against the budget. A table with live entries *n* and tombstones *d* must rehash when *n + d* reaches 7/8·capacity, even if *n* is small.
rehash when  n + d ≥ ⌊7/8 · capacity⌋
_→ in plain terms: deleted slots keep taking up room until a rehash clears them. A same-size rehash when the table is mostly tombstones; a doubling when it is mostly live._
Capacities are 2k−1 and growth goes to 2·capacity+1. Small tables (capacity ≤ 63) are allowed to fill to capacity−1 (a table within a single group may fill completely).

## §7 · Why it works: Filter cheaply for 16 slots, verify expensively for one

**The core insight:** separate the question "which slots could hold this key?" from "does this slot hold this key?". The first is answered for 16 slots in two instructions from one dense 16-byte line; the second, expensive, runs about once per lookup.

### Ablation: remove each piece

- **Drop the tag array** (compare keys directly): every probe step compares up to 16 full keys, which are bigger, scattered and slower, so you are back to linear probing's cost.
- **Make the tag 8 bits and drop the special values into a side bitmap**: sharper filter, but "empty" becomes a second memory read per group.
- **Treat deleted like empty**: a probe stops early at a slot where an overflowed key once passed, so a present key is reported absent. Correctness bug.
- **Never write empty on erase** (always tombstone): correct, but tombstones accumulate under churn and force rehashes (the simulator showed 19 rehashes versus 7 in the same run).
- **Probe slot-by-slot instead of group-wise**: more steps to reach an empty at high load; with W = 8 instead of 16 the simulator needs 2.93 groups per miss instead of 2.09 at 7/8.
- **Linear group stepping (+1, +1, +1) instead of triangular**: full groups clump, so one overloaded neighbourhood stretches every probe through it.

## §8 · Design knobs & alternatives: Same core, three different group widths and growth schemes

Knob | Abseil | hashbrown | Go 1.24

Group width | 16 (SSE2); 8 on NEON/portable | 16 on SSE2/NEON, one `usize` in the generic fallback (from memory, unverified) | 8 slots

Max load | 7/8 above 63 slots | 7/8 (same family) | 7/8 (`maxAvgGroupLoad = 7`)

Growth | whole table, ×2+1 | whole table | per table, split at 1024 slots; directory doubles as needed

Hasher | pluggable, default Abseil hash | foldhash default (crate); std uses SipHash 1-3 | runtime AES/wyhash-style, per-map seed

Small maps | inline slots for tiny capacity | no allocation until first insert | ≤ 8 entries: one group, no directory, no tombstones

User knobs | reserve, hasher | with_capacity, with_hasher | size hint only

### Alternatives and why Swiss won

- **Chaining**: stable pointers, simple, but pointer-chasing and 8 B/entry.
- **Robin Hood / linear probing**: great cache behaviour and low variance, lacks the SIMD filter. Swiss tables won the standard-library slots, but I found no primary-source head-to-head, so call this "unverified debate".
- **Cuckoo / bucketised cuckoo**: worst-case O(1) lookups but costlier inserts and tighter load balance.

## §9 · Where it breaks: Tombstones, resize spikes and hash flooding

### Tombstone buildup

Under delete-heavy churn, tombstones occupy growth budget until a rehash. The "never full" erase rule avoids most of them. In the simulator (80% load, 60,000 delete+insert rounds, W = 16) disabling the rule triggered 19 rehashes; enabling it triggered 7. The rule has a cost too: with fewer rehashes the table spent more time near its ceiling and the average miss touched 2.04 groups instead of 1.67. Single seed, coarse sampling, simplified erase test.

### Resize spikes

Abseil and hashbrown rehash the whole table at once, so one insert can cost O(n). Go bounds this by splitting only the table that fills (≤ 1024 slots), at the price of a directory indirection. (A claim that Abseil resizes incrementally was checked and found unsupported.)

### HashDoS

If an attacker controls keys and the hash is predictable, they can force every key into the same groups and degrade lookups to O(n). History: Crosby and Wallach (USENIX Security 2003) showed it; the 2011 28C3 talk by Klink and Wälde hit PHP, ASP.NET, Ruby, Java and Python; Aumasson, Bernstein and Boßlet (2012) showed random seeds on MurmurHash/CityHash were not enough, which led to SipHash. Rust's std default is SipHash 1-3; hashbrown's default foldhash says it does not resist an interactive attacker.

### Where it loses on speed

Ruby's Feature #22011 (a Swiss-style layer under `st_table`) saw microbenchmark wins but ruby-bench showed +1.77% geomean interpreter time and up to +12.5% on single benchmarks, with up to +20% memory on one benchmark; still under investigation, and a hash-function bug may have skewed it. Go issue #70700 notes the swiss benchmarks use predictable key order and no cold-map cases; the linked CLs made small-map lookups about 1.7× faster for unpredictable keys.
**Misconception:** "7-bit tags make false positives a correctness risk." They never do: a tag match only nominates a slot, and the stored key is always compared in full.
**Gotcha:** iteration order is not stable across inserts (rehash moves everything) and Go deliberately randomises it. Pointers and references to values are invalidated by a rehash.
Not found in the research pass: any CVE specific to hashbrown, Go's swiss map or Abseil, and any hashbrown issue about tombstone accumulation. Absence of search results is not proof of absence.

## §10 · In the wild: Go added a directory of tables; hashbrown added a scalar fallback

- **Abseil** `flat_hash_map`: the reference, 16-byte groups, 7/8 load, `reserve` to avoid rehashes.
- **Rust std**: hashbrown since 1.36 (July 2019); SIMD on SSE2/NEON with a portable fallback; SipHash by default in std, foldhash in the standalone crate.
- **Go 1.24** (Feb 2025): groups of 8, a directory of tables capped at 1024 slots (extendible-hashing style), small maps that skip the directory, iteration starting at random offsets, and an opt-out flag. The release notes credit a "2-3% average" CPU reduction across a benchmark suite, but that figure covers several runtime changes together, not the map alone.
- **CockroachDB** `swiss`: a library variant; reportedly slightly better at large sizes and worse on tiny maps (secondary report).

### Deviations from the CppCon talk

Go adds the directory and per-table growth; hashbrown adds a generic scalar fallback and a Rust-friendly API; Go randomises iteration offsets; Go's 8-slot groups hold one empty slot at 7/8 where Abseil's 16 hold two, which the Go source comments on explicitly.

## §11 · Frontier: CPU design settled; work moved to GPUs, deletes and theory

On the CPU side the design is settled: Abseil, Rust and Go all adopted group probing. Active work moved to GPUs, concurrent designs with cheap deletes, and theory.

- **Go 1.24 Swiss map**, 2025, [go.dev blog](https://go.dev/blog/swisstable): production-scale adoption with a directory-of-tables twist. (Performance figures in secondary posts are unverified.)
- **DLHT**, Katsarakis, Gavrielatos, Ntarmos, HPDC 2024, [arXiv 2406.09986](https://arxiv.org/abs/2406.09986): a concurrent, non-blocking, resizable table using closed addressing with cache-line chaining and immediate reuse of deleted slots; reports over 1.6 billion requests/s. The most direct answer to the tombstone critique.
- **WarpSpeed**, McCoy and Pandey, ALENEX 2026, [arXiv 2509.16407](https://arxiv.org/abs/2509.16407): a library and benchmark over eight GPU hash table designs with fingerprint metadata and lock-free queries.
- **A Fine-Grained Analysis of SIMD-Based Hash Table Implementations**, Nicaud and Rotondo, arXiv preprint (Oct 2026), [2610.02385](https://arxiv.org/html/2610.02385): analyses SIMD open addressing with Wormald's differential-equation method. Its experiments simulate its own model; it does not benchmark Abseil, hashbrown or Go.
- **Hive Hash Table** ([arXiv 2510.15095](https://arxiv.org/pdf/2510.15095), 2025) and **HierarchicalKV** ([arXiv 2603.17168](https://arxiv.org/pdf/2603.17168), 2026): GPU tables reporting 1.5–2× and 1.4× over WarpCore on their own setups; venues unverified.

Not verified: the LLVM FoldingSet Swiss-table RFC (reported ~1.4% clang speedup) comes from a forum snippet only. I found no peer-reviewed 2024–26 critique of Swiss tables, and no VLDB/SIGMOD paper on learned hash functions in the window. Iceberg hashing (Bender et al., 2023) falls just outside it.

## §11b · Open problems: Tombstone-free deletes at SIMD speed are unsolved

- **Deletes without tombstones, at SIMD speed.** The "never full" trick helps but is probabilistic in effect. Closed-addressing designs like DLHT avoid tombstones at the cost of chaining; nobody has shown a clear winner for general-purpose maps.
- **Bounded insert tail latency.** Whole-table rehash is O(n). Go's table splitting bounds it; whether that is worth a directory lookup on every access across workloads is not settled (see Go #70700 on benchmark methodology).
- **Hash quality versus speed versus attack resistance.** foldhash and ahash are fast and not interactive-attacker-proof; SipHash is. Choosing per deployment is still manual.
- **Proving what the model predicts.** The simple αW model fails; the SIMD-analysis preprint above is a first rigorous attempt, still unreplicated on real implementations.
- **Robin Hood versus Swiss, and incremental resizing.** I found no primary-source comparison; mark as an open, partly folkloric debate.

## §12 · Lineage: From open addressing to Go 1.24 in 70 years

**1950s–70s** open addressing and linear probing, analysed by Knuth → **2003** Crosby and Wallach on hash flooding → **2012** SipHash (Aumasson, Bernstein) → **2017** Swiss tables, Kulukundis, CppCon → **2019** hashbrown into Rust std (1.36) → **2025** Go 1.24 builtin map → **2024–26** GPU and concurrent successors (DLHT, WarpSpeed).
The 1950s–70s entry is from general knowledge, not this research pass; the 2003, 2012, 2017, 2019 and 2025 dates are sourced above.

## §13 · Hands-on: Run a 1-second simulator and break the erase rule

Run the simulator in this folder (about a second, no dependencies):

```
python3 swiss_sim.py
```

It prints (1) groups probed per hit and miss and false tag matches at four load factors and two group widths, (2) the share of groups with no empty slot, and (3) a churn test with and without the "never full" erase rule and a 7/8 rehash. Try these:

- Change the tag from 7 bits to 3 (`h >> 61`) and watch the false matches per miss multiply by 16.
- Set `never_full_rule=True` but make `_was_never_full` always return `True`. Run the lookup test after churn: some present keys now report absent. That is the correctness bug the rule exists to avoid.
- Raise `load` to 0.95 and see why tables resize at 7/8.

The real-code experiment: in Rust, time `HashMap<u64,u64>` lookups for present vs absent keys at 50% and 87% load with `with_capacity` chosen to land exactly there.

## §14 · Question ladder

1. **Mechanism**: What exactly is compared in one SIMD step, and what comes out?
<details><summary>Answer</summary>

The key's 7-bit tag is broadcast to every byte of a register and compared to the group's 16 (or 8) control bytes; the result is packed into a bitmask with one bit per slot. Set bits are candidate slots.
</details>

2. **Mechanism**: Why does a probe stop at an empty slot but not at a deleted one?
<details><summary>Answer</summary>

Inserts fill the earliest free slot on the probe path, so a key absent from every group up to the first empty cannot be further along. A deleted slot may have been full when some other key overflowed past it, so stopping there could hide that key.
</details>

3. **Mechanism**: Walk the miss lookup of K2 in the trace.
<details><summary>Answer</summary>

G1 has no matching tag and no empty slot, so hop +1 to G2; G2 has no match and an empty slot, so stop with "absent" after 2 groups.
</details>

4. **Mechanism**: What happens on insert when growth_left is zero?
<details><summary>Answer</summary>

The table rehashes first: a same-size rehash that clears tombstones if enough are present, otherwise growth to 2·capacity+1, then the insert proceeds.
</details>

5. **Why**: Why a 7-bit tag rather than 8?
<details><summary>Answer</summary>

The top bit of the control byte marks empty/deleted/sentinel, which makes "full", "empty or deleted" and "empty" single cheap tests. That leaves 7 bits for the fingerprint.
</details>

6. **Why**: Why is the load factor 7/8 and not 1/2?
<details><summary>Answer</summary>

Because a probe step is one cheap group compare, not a slot-by-slot walk with full key compares. Memory per entry drops and the simulator shows hits still cost about 1.1 groups at 7/8.
</details>

7. **Why**: Why triangular steps over groups instead of +1 each time?
<details><summary>Answer</summary>

Linear steps make full groups clump, so one overloaded neighbourhood lengthens every probe crossing it. Triangular offsets scatter retries, and with a power-of-two group count still visit every group exactly once.
</details>

8. **Why**: Why does the naive α^W model underestimate probes?
<details><summary>Answer</summary>

Keys do not land in groups evenly: occupancy is roughly Poisson with mean αW, so many groups overflow and spill into later ones. At 7/8 with W=16 about 47.6% of groups are full, not 11.8%.
</details>

9. **Counterfactual**: What if erase always wrote empty?
<details><summary>Answer</summary>

Present keys that once overflowed past the erased slot would be reported absent. The simulator's test 2 in the hands-on shows it.
</details>

10. **Counterfactual**: What if the table never rehashed in place and only doubled?
<details><summary>Answer</summary>

Tombstone-heavy tables would double needlessly, wasting memory. Same-size rehash exists to reclaim tombstone budget.
</details>

11. **Counterfactual**: What if group width were 32?
<details><summary>Answer</summary>

Fewer hops at high load but a larger window (still ~one cache line with AVX2, not on SSE2), more occupied slots per group means more false matches per visit, and portability suffers.
</details>

12. **Adversarial**: How would you degrade a Swiss table you can feed keys to?
<details><summary>Answer</summary>

Find keys whose hashes land in the same groups: with a known or leaked seed, every key probes the same long path (HashDoS). Use a keyed hash like SipHash.
</details>

13. **Adversarial**: Why is a random seed alone not enough?
<details><summary>Answer</summary>

Aumasson, Bernstein and Boßlet (2012) showed weak hash functions can leak the seed (e.g. via collision behaviour or iteration order), so the hash must be a keyed PRF-like function such as SipHash.
</details>

14. **Adversarial**: How would you stress the "never full" erase rule?
<details><summary>Answer</summary>

Churn near the load ceiling so windows alternate between full and non-full: erases flip between tombstone and empty and rehashes get timed near the boundary.
</details>

15. **Connection**: How does Go's directory of tables relate to extendible hashing?
<details><summary>Answer</summary>

The directory is indexed by the high hash bits, each table has a local depth, entries can point to the same table, and a full table splits and doubles the directory only when its local depth equals the global depth.
</details>

16. **Connection**: How does DLHT answer the tombstone problem?
<details><summary>Answer</summary>

It uses closed addressing with cache-line chaining so a deleted slot is reusable immediately, at the price of chaining instead of open addressing.
</details>

17. **Open**: Is there a tombstone-free delete for SIMD open addressing that is as fast as erase-to-tombstone?
<details><summary>Answer</summary>

Unsettled; the never-full trick avoids most but not all, and chained or concurrent designs trade lookup shape for it.
</details>

18. **Open**: When is a Swiss table slower than the structure it replaced?
<details><summary>Answer</summary>

Ruby's st_table experiment lost on real benchmarks; tiny maps and unpredictable-key small maps (Go #70700) were weak spots until fixed. The answer depends on workload and hash.
</details>


## §15 · Go deeper next: Three adjacent topics

- **Extendible hashing**: the directory-and-split scheme Go borrowed.
- **SipHash and hash-flooding defences**: why a seed alone is not enough.
- **Lock-free and concurrent hash tables (DLHT, GPU tables)**: what changes when deletes and resizes must not block.

## Sources: Papers, code and docs

### Papers and talks

- [DLHT, HPDC 2024](https://arxiv.org/abs/2406.09986)
- [WarpSpeed, ALENEX 2026](https://arxiv.org/abs/2509.16407)
- [Nicaud and Rotondo, SIMD hash tables, arXiv 2610.02385](https://arxiv.org/html/2610.02385)
- [Hive Hash Table](https://arxiv.org/pdf/2510.15095) · [HierarchicalKV](https://arxiv.org/pdf/2603.17168)
- [Iceberg hashing (2021 preprint)](https://arxiv.org/pdf/2109.04548)
- [Crosby and Wallach 2003](https://www.usenix.org/legacy/events/sec03/tech/full_papers/crosby/crosby.pdf) (URL not verified)
- [Aumasson, Bernstein, Boßlet 2012 slides](https://www.aumasson.jp/siphash/siphashdos_appsec12_slides.pdf)
- Kulukundis, "Designing a Fast, Efficient, Cache-friendly Hash Table, Step by Step", CppCon 2017 (slides URL not confirmed)

### Code and docs

- [Abseil raw_hash_set.h](https://github.com/abseil/abseil-cpp/blob/master/absl/container/internal/raw_hash_set.h) · [hashtable_control_bytes.h](https://github.com/abseil/abseil-cpp/blob/master/absl/container/internal/hashtable_control_bytes.h) · [raw_hash_set.cc](https://github.com/abseil/abseil-cpp/blob/master/absl/container/internal/raw_hash_set.cc)
- [Abseil Swiss tables design](https://abseil.io/about/design/swisstables)
- [Go 1.24 release notes](https://go.dev/doc/go1.24) · [Go swiss map blog](https://go.dev/blog/swisstable) · [internal/runtime/maps](https://github.com/golang/go/tree/master/src/internal/runtime/maps)
- [golang/go #70700](https://github.com/golang/go/issues/70700)
- [hashbrown](https://github.com/rust-lang/hashbrown) · [std HashMap docs](https://doc.rust-lang.org/std/collections/struct.HashMap.html) · [foldhash](https://github.com/orlp/foldhash)
- [Ruby Feature #22011](https://bugs.ruby-lang.org/issues/22011) · [cockroachdb/swiss](https://github.com/cockroachdb/swiss)

### Could not verify

- hashbrown SSE2/NEON/generic group widths (source files returned 404 for the research agent).
- Exact "was never full" window arithmetic; cloned control bytes in Abseil; Chromium usage of Abseil maps.
- Third-party Go map benchmark claims; the LLVM FoldingSet 1.4% figure; any CVEs.
- The pre-2003 lineage entry.

## Code

`swiss_sim.py` (simulator) and `sim_output.txt` (its output) back every number marked "measured".
