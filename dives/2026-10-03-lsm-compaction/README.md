# LSM-tree compaction: leveling vs tiering vs lazy leveling

**Databases/storage · LSM-tree compaction policy, write/read/space amplification · hard · 2026-10-03**

> Verification note: foundations (Monkey/Dostoevsky/O'Neil equations) were read from the primary PDFs. RocksDB defaults come from the RocksDB wiki and `advanced_options.h`; items marked *(unverified)* came from the researchers' memory or search-result summaries and were not fetched. Frontier papers were each checked on their arXiv abstract page.

---

## 0b. Plain English first

**Explain it simply.** Imagine a librarian who receives new books all day. Shelving each book in exactly the right alphabetical spot costs a walk across the library every time. So instead the librarian drops new books on a "recent" cart. When the cart is full, the whole cart is sorted once and shelved as a neat batch. Over time, you have many sorted batches, and finding a book means checking every batch. So the librarian periodically *merges* batches into bigger sorted batches. That merging is compaction.

The big question is *how eagerly to merge*. Merge constantly and finding a book is easy (few batches) but the librarian re-handles the same books over and over. Merge lazily and shelving is cheap but searching means checking many batches, and old, replaced copies pile up. Every database built this way (RocksDB, Cassandra, and others) is choosing a point on that dial.

**Everyday example.** A shop logs sales. Each day's 100 sales get sorted and stored as a "daily pile". Rule A (eager): when a new daily pile arrives, immediately merge it into the one big "history pile". Finding a sale means checking one pile, but every day you re-copy the entire history. Rule B (lazy): keep the daily piles; once you have 10, merge them into one "ten-day pile"; once you have 10 of those, merge into a "hundred-day pile". Copying is far less, but looking up a sale means checking up to ~10 piles per tier. Rule C (hybrid): lazy for the small recent tiers, eager for the single giant bottom pile, so old stuff stays tidy while recent writes stay cheap.

**Bridge:** now the same thing, technically.

---

## 1. Bare-minimum context

- **Memtable**: in-memory sorted buffer absorbing writes; flushed to disk as an immutable sorted file (SSTable / "run") when full. Writes are also appended to a WAL for durability.
- **Run**: one immutable sorted file (or set of files). Reads must consult every run that might contain the key.
- **Level**: a group of runs; level *i* holds roughly *T×* the data of level *i−1* (*T* = size ratio).
- **Bloom filter**: per-run probabilistic membership test, false-positive rate *p*; lets point lookups skip runs.
- **Amplification trio**: write amp (bytes written to disk per user byte), read amp (runs/pages touched per lookup), space amp (bytes on disk per live byte). Compaction trades among them.
- **DAM model**: cost = number of page I/Os. All the closed-form results below use it.

Primary sources: [O'Neil 1996](https://www.cs.umb.edu/~poneil/lsmtree.pdf), [Monkey SIGMOD'17](https://nivdayan.github.io/monkeykeyvaluestore.pdf), [Dostoevsky SIGMOD'18](https://nivdayan.github.io/dostoevsky.pdf).

---

## 1b. Real-world context

**What it is.** A log-structured merge tree stores data as immutable sorted runs and *compaction* is the background process that merges runs to bound read cost, discard overwritten/deleted data, and reclaim space. The compaction *policy* (when, which runs, how much) is the single biggest tuning lever in an LSM engine.

**Why it exists.** B-trees update pages in place: a random write per update, which is slow on spinning disks and wears SSDs. LSM turns random writes into sequential ones (one memtable flush) and pays later, in background merges. Facebook's MyRocks paper reported RocksDB using about half the space of compressed InnoDB and cutting storage write rate by more than half at similar latency ([MyRocks](https://engineering.fb.com/2016/08/31/core-infra/myrocks/); [Dong et al., CIDR'17](https://cidrdb.org/cidr2017/papers/p82-dong-cidr17.pdf)).

**Where it's used** (adoption from researcher notes; items marked * not verified this session):
- **RocksDB** at Facebook/Meta: MyRocks (MySQL engine), ZippyDB*.
- **Cassandra / ScyllaDB**: STCS (tiered) default; LCS (leveled); TWCS (time-window); Cassandra 5.0 adds UCS (CEP-26) unifying tiered and leveled via a scaling parameter. ScyllaDB's Incremental Compaction splits runs into ~1 GB fragments to avoid STCS's 2× temporary space spike.
- **CockroachDB Pebble**: Go RocksDB descendant; uses L0 *sublevels* to bound L0 read amp; operators watch sublevel count.
- **TiKV/TiDB**: RocksDB for raft-log and KV; Titan does key-value separation.
- **YugabyteDB*, Flink and Kafka Streams state stores*, LevelDB/Chrome IndexedDB*, Bigtable* (original design), HBase*, ClickHouse MergeTree* (LSM-like, no memtable).

**How it's used.** The practitioner touches options like these (RocksDB; values mix tuning-guide numbers and defaults, not one published reference config):

```cpp
rocksdb::Options o;
o.write_buffer_size = 64<<20;                    // memtable
o.max_write_buffer_number = 4;
o.level0_file_num_compaction_trigger = 4;        // L0 -> L1 trigger
o.level0_slowdown_writes_trigger = 20;           // default 20
o.level0_stop_writes_trigger = 36;               // default 36
o.max_bytes_for_level_base = 512<<20;
o.max_bytes_for_level_multiplier = 10;           // T, default 10
o.target_file_size_base = 64<<20;                // default 64 MB
o.level_compaction_dynamic_level_bytes = true;   // default since 8.4
o.compaction_pri = rocksdb::kMinOverlappingRatio;// default
o.max_background_jobs = 8;
o.max_subcompactions = 4;
o.compression = rocksdb::kLZ4Compression;
o.bottommost_compression = rocksdb::kZSTD;
// tiered instead: o.compaction_style = rocksdb::kCompactionStyleUniversal;
// TTL/log data:  o.compaction_style = rocksdb::kCompactionStyleFIFO;
```

**When to use / not.** Use leveled for read-heavy or space-sensitive workloads on SSD (tight space amp, ~1.11 with dynamic level bytes). Use tiered/universal for write-heavy ingestion where write amp dominates and you can afford 2× temporary space and more runs per read. Use FIFO for TTL'd caches/metrics (write amp ≈ 1). Pick a **B-tree** when read latency predictability matters more than write throughput, tail latency is critical (compaction/stalls are LSM-specific), or you want less operational tuning (InnoDB, Postgres, LMDB).

**Who should care.** Backend/infra engineers running RocksDB-backed stores; Cassandra/Scylla operators choosing strategies; anyone debugging p99 spikes, write stalls, disk-full-during-compaction, or SSD wear.

---

## 2. The one-liner and what it hides

*"Leveling = fast reads, slow writes; tiering = fast writes, slow reads."*

It hides:
1. The tradeoff is **not symmetric across levels**: space amp is set by the *last* level, update cost accumulates over *all* levels. Hence hybrids (lazy leveling).
2. **Bloom filter memory must be allocated non-uniformly** (Monkey), or lookup cost silently grows with the number of levels.
3. The formulas are **worst-case DAM bounds**; real write amp is shaped by partial compaction, compression, skew, and the SSD's own write amp (multiplicative).
4. Compaction is **also where deletes become real**, so it is a correctness hazard, not just a performance knob (tombstones, snapshots, `gc_grace`).
5. Compaction **competes with foreground I/O**: the "optimal" policy on paper can be a tail-latency disaster (write stalls).

---

## 3. The problem

A random 4 KB update to a B-tree touches a leaf page: ~1 random read + 1 random write, with write amp up to page-size / entry-size (e.g. 4096 / 100 ≈ 40×) from rewriting whole pages. An LSM instead batches: buffer *B·P* entries, write once sequentially. But now a key's versions can be in the memtable and in *any* run. Without merging, runs grow without bound and lookup cost grows with them; obsolete versions and tombstones never die. Compaction bounds that, at the price of rewriting data. Question: how many times should each byte be rewritten, and how many runs may a lookup face?

---

## 4. Mental model

**Analogy:** laundry. Wash small loads often (leveling: always merge into the one big pile, clothes are always sorted but you rewash the same shirts constantly) or let loads accumulate in baskets and wash baskets together (tiering).

**Where it breaks:** laundry has no cost for *finding* a shirt; here, a lookup must probe every basket (run) unless a Bloom filter says "not here." And deleting a shirt means writing a "delete marker" that must travel to the bottom of the pile before the shirt's space is reclaimed.

---

## 5. The mechanism, traced

Setup: buffer = 1 unit (one flush). Size ratio T = 3 for readability. Leveling vs tiering on the same insert stream (each arrival = one flushed run of size 1).

```
LEVELING (1 run per level; level i capacity T^(i+1)):
 flush1: L0=[1]
 flush2: merge into L0 -> [2]                         (rewrote 1)
 flush3: merge -> [3]  (3 > cap? cap(L0)=3, no)       (rewrote 2)
 flush4: merge -> [4] > cap 3 -> push down: L1=[4]    (rewrote 3)
 flush5: L0=[1]; flush6: [2]; flush7: [3]; flush8: [4] -> merge into L1 -> [8] (rewrote 4+4)
 each level re-merges its resident data up to ~(T-1)/2 times on average before overflowing

TIERING (up to T runs per level; merge all when T arrive):
 flush1: L0=[1]; flush2: L0=[1,1]; flush3: L0=[1,1,1] -> T runs -> merge -> L1=[3]  (wrote 3)
 flush4..6: same -> L1=[3,3]; flush7..9 -> L1=[3,3,3] -> merge -> L2=[9]            (wrote 9)
 each entry is written ~once per level; a lookup may face up to T-1 runs per level
```

Real code path in RocksDB (leveled): compaction picker scores each level (L0: `max(num_files / level0_file_num_compaction_trigger, total_size / max_bytes_for_level_base)`; L1+: `size / target`), compacts the highest score ≥ 1, picks the file with least overlap ratio in the next level (`kMinOverlappingRatio`), merges the file with its overlapping next-level files, optionally split into **subcompactions** by key range across threads ([wiki](https://github.com/facebook/rocksdb/wiki/Leveled-Compaction)). Merging drops shadowed versions and, at the bottom level, tombstones.

---

## 6. The math

Notation (Monkey/Dostoevsky): *N* entries, *B* entries/page, *P* buffer pages, *T* size ratio, *L* levels, *M* filter bits, *p_i* Bloom FPR at level *i*, *φ* write/read cost ratio (SSD asymmetry), *μ* scan-vs-seek factor, *s* scan selectivity.

**Levels** (Eq.1): the last level holds ≈ N(T−1)/T entries, so

L = ⌈ log_T( N·E / M_buffer · (T−1)/T ) ⌉

→ in plain terms: each level is T× bigger, so you need log base T of (data/buffer) levels. Bigger T = fewer levels (T→T_lim collapses to 1 level = a sorted array).

**O'Neil's origin of leveling cost** (Thm 3.1): with K disk components of ratios r_i = S_i/S_{i−1}, merge I/O is minimized when all r_i are equal; H = (2R/Sp)·(K(1+r) − ½).
→ each byte is read and written about (1+r) times per level, which is where leveling's ~T-per-level cost comes from.

**Update cost** (Monkey Eq.10):
- Leveling: W = (L/B)·((T−1)/2)·(1+φ)
- Tiering: W = (L/B)·((T−1)/T)·(1+φ)

→ under leveling each entry is merged ≈ (T−1)/2 times per level (it sits in a level while arrivals merge into it, then moves on); under tiering ≈ once per level. Why not simpler? Because the same *amount* of merge work happens per level in aggregate (bigger levels merge exponentially more data, exponentially less often), so the cost per entry per level is set only by *how many times a level's resident data is re-merged*.

**Zero-result lookup** (Eq.3): R = Σp_i (leveling, ≤1 run/level) or (T−1)·Σp_i (tiering). The filter FPR is p = e^(−(bits/entry)·ln²2).
**Monkey's optimization** (Lagrange): minimize R subject to total filter memory fixed → optimal p_i ∝ entries at level i, i.e. **p_i = T·p_{i−1}**: give the small levels tiny FPR, the huge last level a large one. Because probing *any* run costs one I/O regardless of its size, memory buys more I/O avoided on small levels.
Result: with enough memory R = O(e^(−M/N)), **independent of L**, versus O(L·e^(−M/N)) for uniform allocation.
→ uniform 10 bits/entry costs R ≈ L·0.008; Monkey's allocation removes the L factor.

**Dostoevsky's table** (worst case, Section 3):

| | Tiering | Leveling | Lazy leveling |
|---|---|---|---|
| Update W | O(L/B) | O(L·T/B) | O((L+T)/B) |
| Zero-result lookup R | O(T·e^(−M/N)) | O(e^(−M/N)) | O(e^(−M/N)) |
| Existing-key lookup V | O(1 + T·e^(−M/N)) | O(1) | O(1) |
| Short range | O(T·L) | O(L) | O(1 + (L−1)·T) |
| Long range | O(T·s/B) | O(s/B) | O(s/B) |
| Space amp | O(T) | O(1/T) | O(1/T) |

→ lazy leveling = tiering on levels 1…L−1, leveling at level L. It keeps leveling's lookup/space cost but cuts update cost from L·T to L+T, paying only on short scans.

**Fluid LSM-tree** generalizes: K = max runs at levels 1…L−1, Z = max runs at level L. Leveling K=Z=1; tiering K=Z=T−1; lazy K=T−1, Z=1.
- Eq.12: W = φ/(μB)·((T−1)/(K+1)·(L−1) + (T−1)/(Z+1))
- Eq.13: excess space = Z − 1 + 1/T  (T=10, 10 bits/entry: leveling 0.1, tiering 8.1)
Sanity: K=Z=1 gives (T−1)/2·L; K=Z=T−1 gives (T−1)/T·L (matches Monkey Eq.10).

*Caveat:* the exact closed forms of Monkey Eq.7/15/16 had garbled PDF extraction; structure above is verified, re-read the paper before quoting those two exactly.

---

## 7. Why it works

Key insight: **lookup and space cost are determined by the shape of the *last* level (it holds ~(T−1)/T of the data); update cost is determined by how often data is re-merged *across all* levels.** Those are different levels, so you can pick different policies for each. Ablation:
- Remove the size-ratio geometry (equal-sized levels) → O'Neil's theorem says merge I/O is no longer minimal.
- Remove Bloom filters → every run is probed; tiering lookups cost T·L I/Os.
- Uniform filters instead of Monkey's → lookup cost grows with L.
- Remove tombstone dropping at the bottom level → deleted data is never freed.
- Remove dynamic level sizing in RocksDB → space amp worse (static mode can approach ~2× worst case, *unverified*); with it ≈ 1.11 at T=10 because ~90% of data sits in the last level ([CIDR'17](https://cidrdb.org/cidr2017/papers/p82-dong-cidr17.pdf)).

---

## 8. Design knobs and alternatives

| Knob | Effect |
|---|---|
| Size ratio T | Larger T → fewer levels, cheaper lookups under leveling but more write amp (T/2 per level); under tiering larger T → fewer merges but more runs per level |
| Policy (K, Z) | Fluid LSM dial from leveling to tiering |
| Bloom bits/entry & allocation | Monkey: skew FPRs toward the large last level |
| File granularity | Partial compaction (RocksDB SST-granular) changes constants, not asymptotics |
| `compaction_pri` | `kMinOverlappingRatio` default picks least-overlap file → lowers write amp |
| `level_compaction_dynamic_level_bytes` | Bottom level defines target sizes; space amp ≈ 1.11 |
| Universal triggers | `max_size_amplification_percent` (default 200% *unverified*), size ratio, run count |
| Write-stall triggers | L0 slowdown 20 / stop 36; pending-bytes soft 64 GB / hard 256 GB |
| Key-value separation | WiscKey/BlobDB/Titan: store values separately → lower write amp, GC cost, slower scans |
| FIFO | No merging; TTL drop; write amp ≈ 1 |

Competing structures: B-trees (in-place, lower read amp, higher write amp), Bε-trees, LSM with KV-separation, learned/adaptive hybrids (see Frontier).

---

## 9. Where it breaks

- **Write stalls**: not a bug but deliberate backpressure when L0 file count or pending-compaction bytes exceed thresholds. Raising triggers moves the cliff later and deeper. Per [SILK (ATC'19)](https://www.usenix.org/conference/atc19/presentation/balmau): tail latency comes from client writes, flushes and compactions fighting for I/O bandwidth; they report up to 100× lower p99 by prioritizing flushes/low-level compactions and preempting long high-level ones (*search-summary figure; SILK scheduling logic is not in upstream RocksDB, unverified*).
- **L0 read amp**: L0 files overlap, so a point read may probe every L0 file; Bloom filters help, range scans can't skip. Mitigations: intra-L0 compaction, subcompactions, Pebble's sublevels *(L0 behavior from memory, unverified)*.
- **Space spikes**: universal compaction can need up to 2× disk during a full compaction; "leveling = 1.1× space" is a steady-state figure, snapshots/iterators pin old files.
- **Delete problem** ([Lethe, SIGMOD'20](https://arxiv.org/pdf/2006.04777v2)): no bound on how long a tombstone takes to reach the last level, so physical deletion (GDPR!) is unbounded. FADE (age-prioritized compaction) and KiWi (page-level secondary range deletes) reported 1.17–1.4× read throughput, 2.1–9.8× lower space amp, 4–25% more write amp *(search-summary numbers)*.
- **Write amp stacks**: total flash writes = app bytes × LSM WA (10–50× typical) × device WAF; compaction's large sequential rewrites keep device WAF low (1–2) on an uncrowded drive, worse when shared/near-full *(unverified)*.
- **Correctness hazards**: compaction is the only place data is deliberately discarded. Incidents: [PingCAP RocksDB DeleteRange corruption](https://pingcap.medium.com/how-we-found-a-data-corruption-bug-in-rocksdb-60e708769352); [CockroachDB Advisory 48860](https://www.cockroachlabs.com/docs/advisories/a48860) (range deletions concurrent with replica GC could corrupt/lose data; fixed in v19.1.9, v19.2.7, v20.1.0). Cassandra **zombie data**: if repair doesn't finish within `gc_grace_seconds` (default 864000 s = 10 days), a replica can purge a tombstone while another still holds the live row, which then resurrects.
- **Compaction storms** (many shards/column families compacting after bulk load/restart) *(from memory, unverified)*: mitigated by rate limiters, jitter, `max_background_jobs`.

Misconceptions: "stalls mean mis-tuning" (often it's sustained ingest > compaction bandwidth); "more threads is better" (SILK: scheduling beats parallelism); "deleting frees space now" (only after the tombstone hits the last level); "tombstone purge after gc_grace is safe" (only if repair completed).

---

## 10. In the wild

- **RocksDB**: leveled default; score-based picker; dynamic level bytes default since v8.4; subcompactions; universal and FIFO styles. Tuning guide's 512 MB-level example gives ≈33× write amp for leveled; wiki says leveled WA is "often larger than 10"; real systems see ~10–30× vs the paper bound.
- **Universal (tiered)**: write amp often 2–7× *(unverified)*; priorities: periodic age → space-amp trigger → size-ratio → run-count fallback.
- **Cassandra**: STCS default; UCS (5.0) unifies tiered/leveled with scaling parameter W and density-based sharding.
- **ScyllaDB ICS**: fragments of ~1 GB freed incrementally; Space Amplification Goal 1–2.
- **Pebble**: L0 sublevels, sublevel count >10 → read amp visible, >20 → stalls near; admission control on L0 overload *(unverified)*.
- **TiKV**: RocksDB + Titan for large values.

---

## 11. Frontier (what's new)

All seven checked on their arXiv abstract page unless noted.

1. **CAMAL: Optimizing LSM-trees via Active Learning**, SIGMOD 2025 ([arXiv 2409.15130](https://arxiv.org/abs/2409.15130)). Active-learning tuner; in RocksDB, 28% average and up to 8× gains.
2. **How to Grow an LSM-tree? Bridging Theory and Practice** (Mo, Luo, Idreos), SIGMOD 2025 ([arXiv 2504.17178](https://arxiv.org/abs/2504.17178)). *Vertiorizon*: hybrid vertical + horizontal growth balancing read/write/space cost.
3. **ArceKV: Workload-driven LSM-compactions under Dynamic Workloads**, arXiv Aug 2025, rev. Jan 2026, no venue stated ([2508.03565](https://arxiv.org/abs/2508.03565)). Relaxes structural constraints; lightweight decision engine picks compaction actions; ~3× faster in dynamic workloads.
4. **RESYSTANCE: Hidden Performance of Compaction via eBPF**, ICDE 2026 ([2603.05162](https://arxiv.org/abs/2603.05162)). eBPF + io_uring to cut syscall overhead in compaction: −50% compaction time, up to +75% throughput on write-heavy loads.
5. **DiaLSM: Write-Stall-Free Performance via Shard-based LSM-tree**, ICDE 2027 per the page, submitted 13 Sept 2026 ([2609.14370](https://arxiv.org/abs/2609.14370)). Shards write/flush/compaction path; up to 2.4× throughput, 94% fewer write stalls.
6. **Scavenger: Space-Time Trade-offs for KV-Separated LSM-trees** ([2508.13909](https://arxiv.org/abs/2508.13909)). I/O-efficient GC + space-aware compaction; beats BlobDB and Titan. *Venue discrepancy: page says ICDE 2024 but the ID implies Aug 2025; treat venue as the page's claim.*
7. **Rethinking LSM-tree based Key-Value Stores: A Survey** (Lv et al.), arXiv Jul 2025 ([2507.09642](https://arxiv.org/abs/2507.09642)). 100+ papers 2020–2025 on compaction unpredictability and amplification: a good citation hub.

**Pattern:** compaction is becoming adaptive/learned (CAMAL, ArceKV), stalls are attacked by sharding (DiaLSM), cost by kernel/offload tricks (RESYSTANCE), and KV-separation is co-designing GC with compaction (Scavenger).

*Coverage gaps (not searched):* object-storage LSMs (SlateDB, RocksDB-Cloud), Cassandra UCS papers, range-delete handling. *Seen only in search snippets, not cited as verified:* "Rethinking the Compaction Policies in LSM-trees" (SIGMOD'25), AXE (VLDB'25), CaaS-LSM (SIGMOD'24), Mnemosyne (SIGMOD'25), dLSM.

---

## 11b. Open problems

- **No dominant strategy.** [Sarkar et al., VLDB'21](https://arxiv.org/pdf/2202.04522) decompose any compaction strategy into four primitives (trigger, data layout, granularity, data-movement policy), benchmark 10 strategies, and find none wins on every metric.
- **Granularity done wrong.** [Spooky](https://mail.vldb.org/pvldb/volumes/15/paper/Spooky%3A%20Granulating%20LSM-Tree%20Compactions%20Correctly) argues partial-compaction granularity is often implemented incorrectly.
- **Tuning under workload shift.** Policy changes require rewriting data, so transition cost is hard and rarely modeled. Work: RL tuners ([2308.07013](https://arxiv.org/pdf/2308.07013)), robust tuning ([2311.10005](https://arxiv.org/pdf/2311.10005)), and the 2024–26 papers above.
- **Scheduling theory.** No clean optimal result trading tail latency vs write amp vs space; picking is heuristic (bLSM's spring-and-gear scheduler, SILK are partial answers) *(from memory)*.
- **Deletes/TTL.** Bounded-latency physical deletes remain mostly research (Lethe), not default.
- **Cloud/object storage.** Request pricing shifts the optimum; offloaded compaction (CaaS-LSM, unverified) is an open design space.
- **KV separation** cuts write amp but moves cost to GC and range scans.

Why hard: any change to the layout is paid for in rewritten data, workloads drift, and foreground/background I/O interact non-linearly.

---

## 12. Lineage

B-tree → **O'Neil et al., LSM-tree (1996)** (rolling merge, leveling) → Bigtable/LevelDB (2006–11) → bLSM (SIGMOD'12, scheduling) → **Monkey (2017)** (filter allocation) → **Dostoevsky (2018)** (lazy leveling, Fluid LSM) → WiscKey/Titan (KV separation) → SILK (2019), Lethe (2020), design-space benchmark (2021), Spooky (2022) → learned/adaptive and offloaded compaction (2024–26).

---

## 13. Hands-on (≤30 min)

[`lsm_sim.py`](lsm_sim.py): count-based simulator of leveling, tiering, lazy leveling; prints write amp, run count, and the theoretical W for comparison.

```
python3 lsm_sim.py 10 3
```
Actual output (insert-only, unique keys; unit = one flush):

```
T=10 L=3 N=1000 flushes
policy      write-amp  runs@end  peak runs   theory W
leveling        17.09         2          3      13.50
tiering          4.00         1         27       2.70
lazy             8.40         1         19       6.30
T=10 L=4 N=10000 flushes
leveling        22.49         3          4      18.00
tiering          5.00         1         36       3.60
lazy             9.40         1         28       7.20
T=4 L=5 N=1024 flushes
leveling        11.92         3          5       7.50
tiering          6.00         1         15       3.75
lazy             7.25         1         13       4.50
```
Read it: the sim counts the initial flush write (+1) and boundary effects the asymptotic formula drops, so absolute numbers sit above theory, but the *ordering and ratios* match: leveling ≈ (T−1)/2 per level, tiering ≈ 1 per level, lazy in between. Peak run count (a read-amp proxy) goes the opposite way: leveling ≤ L runs, tiering up to (T−1)·L. Exercise: add random keys with updates and measure space amp and dedup; add a Bloom-filter model and reproduce Monkey's L-independence.

---

## 14. Question ladder

**Mechanism**
1. Walk a flush through leveling at T=3 until it overflows into L1: how many bytes are rewritten?
2. Why does tiering write each entry about once per level while leveling writes it ≈(T−1)/2 times?
3. What does RocksDB's L0 score formula compute and why two terms?
4. What does `kMinOverlappingRatio` choose and why does it lower write amp?
5. What exactly makes a tombstone droppable?

**Why**
6. Why must Bloom FPR grow geometrically with level size under Monkey?
7. Why does lazy leveling use leveling only at the *last* level?
8. Why is space amp ≈1.11 with dynamic level bytes at T=10?
9. Why do equal size ratios minimize merge I/O (O'Neil Thm 3.1)?

**Counterfactual**
10. What if T→T_lim (one huge level)? What if T=2?
11. What if Bloom filters were free and perfect? Does tiering still lose?
12. What if the SSD had no write-amp penalty (WAF=1)? Does the optimal policy change?
13. What if compaction ran strictly at lower priority than foreground I/O? What happens to debt?

**Adversarial**
14. Craft a workload that maximizes L0 overlap and read amp.
15. How would an attacker (or buggy client) trigger a write-stall cascade?
16. Construct a Cassandra delete→resurrection scenario with a missed repair.
17. How can long-running iterators/snapshots defeat the space-amp bound?

**Connection**
18. How does this relate to external merge sort and to garbage-collected heaps (generational GC)?
19. How is SSD FTL garbage collection a nested LSM?
20. How does key-value separation reshape the policy math?

**Open**
21. Is there an optimal online compaction scheduler under drifting workloads with transition cost?
22. Can deletes be given a hard persistence bound without much write-amp?
23. How should the optimum shift on object storage with per-request pricing?

<details><summary>Answers</summary>

1. Per the section-5 trace: arrivals 2, 3, 4 each rewrite the resident L0 data (1, 2, 3 units) = 6 units of resident data rewritten, plus 4 flush writes; the size-4 run (> cap 3) then moves down to L1. Resident data is re-merged each arrival, which is the (T−1)/2 factor.
2. Tiering merges only when T runs accumulate, then writes the result once into the next level; leveling re-merges the arriving run with the *resident* level data on every arrival, so resident data is rewritten on average (T−1)/2 times before overflowing.
3. L0 score = max(num_files/trigger, total_size/max_bytes_for_level_base): file count matters because overlapping L0 files drive read amp; size matters for byte-based backlog.
4. Picks the file whose overlap with next-level files is smallest relative to its own size: least rewrite of the lower level per byte moved down.
5. Compaction reaches the bottommost level (nothing deeper can hold older versions) and no snapshot needs it.
6. Probing any run costs one I/O regardless of size; Lagrange optimization of Σp_i under a memory constraint gives p_i ∝ entries at level i, i.e. p_i = T·p_{i−1}.
7. The last level holds ~(T−1)/T of data, so it controls space amp and lookup cost; upper levels (little data) only affect update/scan costs, where tiering is cheaper.
8. With dynamic level bytes the last level is sized to its actual data and each level above is 1/T of the one below, so total = last × (1 + 1/T + 1/T² + …) = last × T/(T−1) = 1.111× at T=10 (the last level ≈ 90% of all data).
9. Merge I/O per level is proportional to (1+r_i); with a fixed product of ratios (fixed total size) the sum is minimized by equalizing ratios (convexity).
10. T→T_lim: L→1, a sorted array: reads optimal, each insert rewrites everything. T=2: tiering and leveling coincide.
11. Perfect filters make zero-result lookups free for both; tiering still pays on existing-key lookups and scans (up to T runs/level) but wins on writes.
12. WAF multiplies: policy ranking by LSM WA is unchanged, but the *absolute* endurance budget and cost balance (φ) shift, favoring lower-WA policies on worn/shared SSDs.
13. Debt accumulates, L0 files/pending bytes hit stall thresholds and writes stall hard anyway: the cliff just moves.
14. Random keys across the whole range with bursts of flushes faster than L0→L1 compaction: every L0 file spans the whole key space.
15. Burst writes beyond sustained compaction bandwidth, or bulk load that builds pending-compaction debt past 64 GB/256 GB.
16. Delete row; a replica is down/unrepaired past gc_grace; healthy replicas compact the tombstone away; the down replica returns still holding the row; repair treats it as live.
17. Pinned snapshots/iterators keep obsolete SSTs alive; compaction can't drop versions they might read.
18. Compaction is multiway merge sort run incrementally; levels with ratio T are generational GC with promotion.
19. The FTL writes log-structured pages and compacts blocks: stacked WA multiplies with the LSM's.
20. Values aren't rewritten during compaction, so keys-only merges shrink W; but GC must reclaim value logs and range scans lose locality.
21–23. Genuinely open; see section 11b.

</details>

---

## 15. Go deeper next

1. **Key-value separation** (WiscKey, BlobDB/Titan GC): how it rewrites the amplification math.
2. **Learned / robust LSM tuning** (Endure, CAMAL): treating the policy as an optimization with workload uncertainty.
3. **Compaction on disaggregated/object storage** (RocksDB-Cloud, SlateDB, CaaS-LSM): when requests are priced and local disks vanish.

---

## Sources

**Papers**
- O'Neil et al. 1996: https://www.cs.umb.edu/~poneil/lsmtree.pdf
- Monkey SIGMOD'17: https://nivdayan.github.io/monkeykeyvaluestore.pdf
- Dostoevsky SIGMOD'18: https://nivdayan.github.io/dostoevsky.pdf
- Dong et al., CIDR'17: https://cidrdb.org/cidr2017/papers/p82-dong-cidr17.pdf
- SILK ATC'19: https://www.usenix.org/conference/atc19/presentation/balmau
- Lethe SIGMOD'20: https://arxiv.org/pdf/2006.04777v2
- Sarkar et al. VLDB'21 (design space): https://arxiv.org/pdf/2202.04522
- Spooky: https://mail.vldb.org/pvldb/volumes/15/paper/Spooky%3A%20Granulating%20LSM-Tree%20Compactions%20Correctly
- RL tuning: https://arxiv.org/pdf/2308.07013 · Robust tuning: https://arxiv.org/pdf/2311.10005
- CAMAL https://arxiv.org/abs/2409.15130 · Vertiorizon https://arxiv.org/abs/2504.17178 · ArceKV https://arxiv.org/abs/2508.03565 · RESYSTANCE https://arxiv.org/abs/2603.05162 · DiaLSM https://arxiv.org/abs/2609.14370 · Scavenger https://arxiv.org/abs/2508.13909 · Survey https://arxiv.org/abs/2507.09642

**Code / docs**
- RocksDB Leveled Compaction: https://github.com/facebook/rocksdb/wiki/Leveled-Compaction
- RocksDB Universal Compaction: https://github.com/facebook/rocksdb/wiki/Universal-Compaction
- RocksDB tuning guide: https://github.com/facebook/rocksdb/wiki/RocksDB-Tuning-Guide
- `advanced_options.h`: https://raw.githubusercontent.com/facebook/rocksdb/main/include/rocksdb/advanced_options.h
- Cassandra tombstones: https://cassandra.apache.org/doc/latest/cassandra/managing/operating/compaction/tombstones.html
- CockroachDB storage layer: https://www.cockroachlabs.com/docs/stable/architecture/storage-layer.md
- TiKV RocksDB: https://tikv.org/blog/rocksdb-in-tikv/ · Titan: https://docs.pingcap.com/tidb/dev/titan-overview/

**Articles / incidents**
- MyRocks: https://engineering.fb.com/2016/08/31/core-infra/myrocks/
- ScyllaDB ICS: https://www.scylladb.com/2020/01/16/maximizing-disk-utilization-with-incremental-compaction/ · https://www.scylladb.com/2021/04/28/incremental-compaction-2-0-a-revolutionary-space-and-write-optimized-compaction-strategy
- Cassandra strategy guide / UCS: https://www.netdata.cloud/guides/cassandra/cassandra-choosing-compaction-strategy/ · https://docs.axonops.com/data-platforms/cassandra/architecture/storage-engine/compaction/ucs
- Cassandra resurrection: https://www.netdata.cloud/guides/cassandra/cassandra-data-resurrection-gc-grace/
- PingCAP corruption: https://pingcap.medium.com/how-we-found-a-data-corruption-bug-in-rocksdb-60e708769352
- CockroachDB advisory: https://www.cockroachlabs.com/docs/advisories/a48860
- RocksDB universal improvements: https://rocksdb.org/blog/2021/04/12/universal-improvements.html
