# Linux EEVDF scheduler: virtual lag, eligibility, virtual deadlines

**Computer science · OS/kernels · EEVDF (Earliest Eligible Virtual Deadline First) in Linux · hard · 2026-10-04**

Code in this folder: [`eevdf_sim.py`](eevdf_sim.py), a toy exact-arithmetic EEVDF simulator mirroring `kernel/sched/fair.c`.

---

## 0b. Plain English first

**Explain it simply.** Picture one barista (the CPU) and a line of customers (programs). Everyone should get a fair share of the barista's time. The old Linux rule (CFS) was: "serve whoever has been served the least so far." Fair, but it had no way to say "this customer only wants a 20-second chat, serve them quickly." Linux bolted on a pile of guesses (heuristics) about who "seems interactive."

EEVDF replaces the guesses with two honest ideas. **Fairness**: keep a running ledger of who is owed time and who has had too much. Only people who are owed time (or square) are allowed to be served next. **Urgency**: every customer states how long a turn they want. Short-turn customers get an earlier "finish-by" time. Among everyone allowed, serve whoever's finish-by time comes first. Short turn = served sooner, but total time over the day is still equal. Latency and fairness become two separate dials.

**Everyday example.** Three people share a whiteboard: Ann and Bob each want 3-minute turns, Cy wants 1-minute turns. All three are equally "owed" at the start. Cy's finish-by is earliest (1 min vs 3), so Cy goes first for 1 minute. Now Cy has had more than average, so Cy is *not allowed* until the others catch up. Ann goes (her finish-by ties with Bob's), then Bob. When everybody is square again, Cy's next finish-by is again the earliest, so Cy jumps in. After a full day each has had exactly the same total minutes, but Cy got many more, shorter turns, so Cy never waited long.

**Now the same thing, technically.**

---

## 1. Bare-minimum context

- A CPU scheduler picks which runnable task runs next on each core's **runqueue** (per-CPU; the load balancer separately moves tasks between runqueues).
- **Weight** `w` comes from nice value (nice 0 → 1024; each nice step ≈ 1.25×).
- **vruntime** `v` = CPU time consumed scaled by `1024/w`, so heavy tasks age slower.
- **Proportional share / GPS**: ideal fluid scheduler gives each task `w_i/Σw` of the CPU at every instant. Real schedulers approximate it with discrete slices.
- Linux keeps runnable entities in a **red-black tree**; `sched_entity` is the schedulable unit (task or cgroup group).
- **cgroups** nest entities hierarchically; each level has its own runqueue.

## 1b. Real-world context

**What it is.** EEVDF is a proportional-share scheduling algorithm from Stoica & Abdel-Wahab (1995). Linux 6.6 (Oct 2023) replaced CFS's "pick smallest vruntime" logic with it. Each task has a *weight* (how much CPU it deserves) and a *request size/slice* (how long a turn it wants). The scheduler runs the *eligible* task (not ahead of its fair share) with the *earliest virtual deadline*.

**Why it exists.** CFS equalised vruntime but had no notion of latency, so Linux accreted heuristics: `sched_latency_ns`, `sched_min_granularity_ns`, `sched_wakeup_granularity_ns`, `GENTLE_FAIR_SLEEPERS`, sleeper bonuses. They conflicted and were hard to reason about. Corbet's LWN piece reports EEVDF let Zijlstra delete ~450 lines of such code (secondary claim, not re-counted here). Latency-sensitive workloads (audio, UI, RPC servers) needed a first-class way to ask for short turns without raising weight (= stealing CPU share).

**Where used** (all via mainline Linux ≥ 6.6):
- **Ubuntu 24.04 LTS (kernel 6.8), Debian 13 (6.12), Fedora, Arch**: every default desktop/server on a modern kernel runs it.
- **Android GKI kernels on 6.6+**: the fair class for apps and system_server.
- **Kubernetes/containers**: `cpu.weight` (cgroup v2) maps to entity weight; EEVDF arbitrates inside each group runqueue.
- **sched_ext schedulers** (Meta, Valve): `scx_lavd` is named after a "latency-criticality-aware virtual deadline", the same idea re-implemented in BPF.
- **Game/audio stacks** (PipeWire, Steam): rely on short-slice requests and `sched_setattr`.
- **Cloud databases/RPC servers**: p99 wakeup latency is the visible effect.

**How it's used.** Most users touch nothing. Knobs:

```c
// per-task custom slice (Linux >= 6.12): ask for 0.5 ms turns, normal weight
struct sched_attr a = {
    .size = sizeof(a),
    .sched_policy = SCHED_OTHER,
    .sched_nice = 0,
    .sched_runtime = 500 * 1000,   // ns; kernel clamps to [100us, 100ms]
};
syscall(SYS_sched_setattr, 0, &a, 0);   // 0 = calling thread
```

```bash
nice -n -5 ./app                           # weight, i.e. CPU share
cat /sys/kernel/debug/sched/base_slice_ns  # default slice (needs debugfs)
cat /sys/kernel/debug/sched/features       # PLACE_LAG RUN_TO_PARITY DELAY_DEQUEUE ...
echo NO_RUN_TO_PARITY > /sys/kernel/debug/sched/features   # A/B test a feature
```

Default base slice (verified in `fair.c`): `700000 ns × (1 + ilog2(min(ncpu, 8)))` = 0.7 / 1.4 / 2.1 / 2.8 ms for 1 / 2 / 4 / ≥8 CPUs. Distro docs often say "3 ms" (older constant 0.75 ms × 4).

**When to use / not.**
- Use the fair class + custom slice for latency-sensitive but non-RT work (UI threads, RPC workers, audio mixers that aren't hard-RT).
- Skip for hard deadlines: use `SCHED_DEADLINE` (admission-controlled CBS/EDF) or `SCHED_FIFO/RR`. EEVDF *virtual* deadlines give uniformity of allocation, not timeliness guarantees against arbitrary load.
- Skip for workload-specific policy (database background-task isolation, game frame pacing): `sched_ext`.
- Signs you picked wrong: p99 latency tracks nr_running even with tiny slices (you need RT or isolation), or short-slice threads thrash caches with context switches.

**Who should care.** Backend/infra engineers chasing tail latency; SREs reading regressions after a kernel upgrade (6.5→6.6); audio/game devs; kernel and BPF-scheduler authors; anyone running tight cgroup CPU limits.

---

## 2. The one-liner, and what it hides

> "EEVDF runs the eligible task with the earliest virtual deadline."

It hides:
1. **"Virtual"**: what clock? V is a *weighted average* of all vruntimes, which moves when tasks join, leave, or reweight.
2. **"Eligible"**: lag `≥ 0`, tested without division in fixed point, with overflow handling. What if lag is large or tasks sleep?
3. **Sleep**: a task that sleeps leaves the average. If lag is forgotten at sleep, tasks can game it; if remembered, placement must compensate for the task's own effect on V.
4. **Slice vs weight**: slice sets *when*, weight sets *how much*; they are orthogonal.
5. **One CPU only**: EEVDF decides within one runqueue. Cross-CPU fairness is the (unchanged) load balancer's job.

## 3. The problem

CFS picks the smallest vruntime. That yields long-run fairness but a task that wakes after sleeping gets *placement near min_vruntime* and wins immediately, the only latency lever, controlled by tunables with mixed units (ns, scaled by log2(ncpu)). A task wanting 100 µs turns and one wanting 10 ms turns both got the same treatment unless priority was abused. Lag was unbounded in theory for unfairly placed sleepers and was not even a tracked quantity. Server regressions and desktop stutter were each fixed by retuning one knob and breaking another.

Needed: (a) a *bounded-error* fairness guarantee, (b) a per-task latency request orthogonal to weight, (c) fewer magic numbers.

## 4. Mental model

**Bank ledger + stopwatch.** Lag is your account balance with the CPU: positive = the CPU owes you time; negative = you overdrew. Only non-negative accounts may be served (eligibility). Each request carries a due date (virtual deadline); serve the earliest due date among the eligible.

**Where it breaks:** the "bank" is a *relative* ledger. V (the reference) is the weighted mean of everyone currently queued, so balances change when others arrive or leave without you doing anything. That is why sleeping/waking, reweighting, and cgroups produce most of the real bugs.

## 5. The mechanism, traced

Runnable by `python3 eevdf_sim.py`: three equal-weight (1024) CPU-bound tasks; A and B ask slice = 3 ms, C asks 1 ms. Virtual time advances 1 per ms (equal weights). `*` = eligible.

```
t= 0 V= 0.00 A(v=0.00,vd=3.00*) B(v=0.00,vd=3.00*) C(v=0.00,vd=1.00*) -> C   # earliest deadline wins
t= 1 V= 0.33 A(v=0.00,vd=3.00*) B(v=0.00,vd=3.00*) C(v=1.00,vd=2.00 ) -> A   # C ran: v=1 > V, ineligible
t= 2 V= 0.67 A(v=1.00,vd=3.00 ) B(v=0.00,vd=3.00*) C(v=1.00,vd=2.00 ) -> B   # A ineligible too
t= 3 V= 1.00 A(v=1.00,vd=3.00*) B(v=1.00,vd=3.00*) C(v=1.00,vd=2.00*) -> C   # all square: C deadline 2 < 3
t= 4 V= 1.33 A(v=1.00,vd=3.00*) B(v=1.00,vd=3.00*) C(v=2.00,vd=3.00 ) -> A
...
CABCABABCCABCABABCCABCAB      # 24 ms: A=8, B=8, C=8
```

What to see:
- **Equal CPU** (8/8/8) because eligibility forces everyone back to V.
- **C asks for shorter turns**, so its deadline `ve + 1` is always earlier than `ve + 3`. Over 24 ms it still gets 8 ms, like A and B. Short slice = low latency, no extra share.
- At `t=7→8` B finishes its 3 ms request (`v=3 ≥ vd=3`), gets `vd = 3 + 3 = 6` (`update_deadline()`).
- Weights: H(w=2048) vs L(w=1024) with equal slices gives `HLHHLHHLHHLH`: H 8, L 4 → 2:1. H's vruntime advances at half speed, so it stays eligible longer.

Kernel flow for the same events:

```
tick / wakeup
  update_curr(): vruntime += delta * 1024 / w          # real time -> virtual
  update_deadline(): if v >= vd: vd = v + slice*1024/w # new request
  -> need resched?  pick_eevdf():
        if only 1 queued: return it
        if curr eligible && still inside protected slice (RUN_TO_PARITY): keep curr
        if leftmost (min deadline) is eligible: take it       # common O(1) path
        else heap-descend: go left while left->min_vruntime is eligible
                           (tree sorted by deadline, augmented with subtree min vruntime)
```

Real code (`kernel/sched/fair.c`, current master, fetched 2026-10-04):

```c
static struct sched_entity *pick_eevdf(struct cfs_rq *cfs_rq, bool protect)
{
	...
	/* Pick the leftmost entity if it's eligible */
	if (se && entity_eligible(cfs_rq, se)) { best = se; goto found; }
	/* Heap search for the EEVD entity */
	while (node) {
		struct rb_node *left = node->rb_left;
		/* Eligible entities in left subtree are always better choices, since they have earlier deadlines. */
		if (left && vruntime_eligible(cfs_rq, __node_2_se(left)->min_vruntime)) { node = left; continue; }
		se = __node_2_se(node);
		if (entity_eligible(cfs_rq, se)) { best = se; break; }
		node = node->rb_right;
	}
found:
	if (!best || (curr && entity_before(curr, best))) best = curr;
	return best;
}
```

The tree key is the *deadline*; each node stores `min_vruntime` of its subtree so whole subtrees with no eligible task are pruned. Pick is O(log n).

**Sleep and wake** (the subtle part). On dequeue, `update_entity_lag()` stores `vlag = V − v`, clamped. On enqueue, `place_entity()` restores it:

```
v_i = V − vlag_i'      where vlag_i' = vlag_i · (W + w_i) / W
deadline = v_i + slice·1024/w_i    (new tasks: half a slice, PLACE_DEADLINE_INITIAL)
```

The inflation exists because adding the entity changes V itself (derivation in §6). `DELAY_DEQUEUE` (6.12): a task going to sleep with *negative* lag stays on the tree as `sched_delayed`, ineligible, burning off lag in virtual time; it is only really dequeued when picked (then lag ≥ 0 by definition) or woken. `DELAY_ZERO` clips lag to ≤ 0 on delayed dequeue.

## 6. The math

**Setup (paper).** Tasks `i` with weight `w_i`. Virtual time advances at rate inversely proportional to total weight:

```
V(t) = ∫₀ᵗ dτ / Σ_j w_j(τ)
```
→ in plain terms: V is "how much service one unit of weight should have received so far". A task with weight w ideally got `w·ΔV` of CPU.

**Lag.** `lag_i(t) = S_i(t₀,t) − s_i(t₀,t)` = ideal minus actual service. Positive = owed.

**Kernel form.** Track virtual lag to avoid a `w_i` everywhere:

```
lag_i = w_i (V − v_i),     vlag_i = V − v_i,     V = Σ w_j v_j / Σ w_j
```
→ plain: V is the weighted mean vruntime; being left of the mean means being owed.

**Eligibility.** `lag_i ≥ 0 ⇔ V ≥ v_i ⇔ Σ w_j (v_j − v₀) ≥ (v_i − v₀) Σ w_j`. The kernel uses the right side (cross-multiplied) because the division loses precision (comment in `fair.c`: "using `avg_vruntime() > se->vruntime` is inaccurate"). It also keeps `sum_w_vruntime = Σ (v_j − v₀) w_j` relative to a moving `zero_vruntime` so the sums don't overflow, and uses `__int128` for the product.

**Virtual eligible time and deadline (paper):**
```
V(e) = V(t₀) + s(t₀,t)/w          V(d) = V(e) + c/w
```
(`c` = request size). Kernel: `vd_i = ve_i + r_i/w_i` with `ve_i = v_i`, `r_i` = slice in ns, divided by weight via `calc_delta_fair`. → plain: a request of size c at weight w "costs" c/w virtual time; heavy tasks have short virtual deadlines per real ms, so they run more.

**Placement derivation** (from the kernel comment). Adding entity `i` with virtual lag `vl_i` and weight `w_i` to a queue with total weight `W`, mean `V`:
```
V' = (W·V + w_i (V − vl_i)) / (W + w_i) = V − w_i·vl_i/(W + w_i)
vl'_i = V' − v_i = vl_i − w_i·vl_i/(W + w_i) = vl_i · W/(W + w_i)
```
So the lag *after* joining is strictly smaller than before: the newcomer drags the mean toward itself. To preserve lag, inflate: `vl_i = vl'_i · (W + w_i)/W`. This is the `lag *= load + weight; lag /= load` in `place_entity()`. → plain: a creditor who walks in changes the average, so you must pre-compensate or their credit evaporates.

**Lag conservation and bounds (paper).** `Σ_i lag_i(t) = 0` always (everyone's ledger sums to zero, since V is the weighted mean). Theorem (Stoica 95, slides): with request size `c` for task `k`, quantum `q`:
```
−c < lag_k(t) < max(c_max, q)
```
and a request completes no later than `d + q` after its virtual deadline. The proof sketch partitions tasks by whether their deadline is before/after `d`; since lags sum to zero and the "after" group can't be owed more than `q`, the "before" group's requests all finish by `d + q`. → plain: nobody is ever more than about one maximum slice ahead or behind the ideal fluid schedule; that's optimal for a quantised scheduler.

**Why not simpler:** WFQ-style "smallest virtual finish time" with no eligibility can serve a task *ahead* of its fluid schedule (WF2Q's observation): the eligibility gate is what gives the lower lag bound.

## 7. Why it works

Two properties factor the problem:
- **Eligibility** ⇒ bounded unfairness. Task ahead of V cannot be picked; time is only handed to tasks at or behind the mean.
- **Deadline order among eligibles** ⇒ latency *chosen by the task*. Short `r_i` ⇒ earlier `vd_i` ⇒ picked first among eligibles.

Ablations:
- *Remove eligibility* → pure EDF on virtual deadlines: a stream of tiny-slice tasks starves the rest; lag unbounded.
- *Remove deadlines (pick min vruntime)* → CFS: fair, no latency control.
- *Remove lag memory (PLACE_LAG off)* → sleep resets debt: a task can sleep briefly each slice and wipe negative lag.
- *Remove DELAY_DEQUEUE* → same exploit via ineligible-then-sleep; or lag preserved forever and penalising long sleepers.
- *Remove RUN_TO_PARITY* → every wakeup with a slightly earlier deadline preempts: context switches explode (hackbench-style regressions after merge).

## 8. Design knobs & alternatives

| Knob | Effect |
|---|---|
| nice / `cpu.weight` | share of CPU (slope of vruntime) |
| `sched_runtime` (custom slice, ≥ 6.12) | latency/switch-rate; 100 µs–100 ms |
| `base_slice_ns` (debugfs) | default slice; ×(1+log2 ncpu) scaling |
| `RUN_TO_PARITY` | protect current until lag 0 or min slice; fewer switches |
| `PREEMPT_SHORT` | shorter-slice wakeup may cancel parity protection |
| `PLACE_LAG`, `DELAY_DEQUEUE`, `DELAY_ZERO` | sleep/wake lag policy |
| `PLACE_DEADLINE_INITIAL` | new tasks start with half slice |
| `NEXT_BUDDY` (default false) | cache-locality hint, off by default in current master |

Alternatives: CFS (min vruntime + heuristics, easier but latency by tuning); BFS/MuQSS/BORE (burst-score heuristics, favoured on some desktop kernels); `SCHED_DEADLINE` (hard EDF+CBS reservations); stride/lottery (O(1) / probabilistic, no latency input); BPF `sched_ext` (arbitrary policy). EEVDF won mainline because it has *one* theory-backed rule and removes tunables.

## 9. Where it breaks

- **Regressions at merge (6.6)**: over-scheduling when lag ≈ slice (fixed by "curb wakeup preemption"/RUN_TO_PARITY, per LKML/LWN reporting); vhost/netperf and schbench/tbench shifts attributed to lag-based placement (secondary reports; magnitudes vary by hardware: *unverified*).
- **CVE-2024-35985** (verified, Debian tracker): `reweight_eevdf()` scaled vlag without the clamp used elsewhere; an s64 multiply overflowed, `entity_eligible()` returned false for everything, `pick_eevdf()` returned NULL → NULL deref. "Rare, but fatal when it does happen." Fixed in 6.9-rc6 (commit 1560d1f6eb6b), backported. The overflow-guarded `vruntime_eligible()` (`check_mul_overflow`, `__int128`) in current source is the same class of defence.
- **Per-CPU only**: no cross-CPU fairness; bursty tasks pile on one CPU until the load balancer (tens to 100+ ms) reacts.
- **cgroup hierarchies**: reweighting a group entity changes vruntime *units* of queued members; lag clamping and deadline pushes interact. Entity-placement fixes were still landing around 6.13 (Jan 2025 last-minute fix per Phoronix) and later (*exact later commit history unverified: research notes had inconsistent dates*).
- **Tick granularity**: accounting is tick-based; with 3 ms slice and HZ=1000 a task can hit its deadline up to 1 ms early or late. Hrtick exists but is off by default (`HRTICK` feature, false in the file fetched).
- **Misconception: "short slice = more CPU."** No: same weight ⇒ same long-run share; you only get it in smaller, earlier pieces (and pay switch cost).
- **Misconception: "EEVDF is real-time."** Virtual deadlines are not wall-clock deadlines; bound is `d + q` in *virtual* terms on one runqueue.
- **Heterogeneous cores**: EEVDF itself is capacity-blind; P/E-core and EAS decisions live in wakeup placement and load balancing.

## 10. In the wild (and deviations)

Linux deviates from the 1995 paper:
- Time is **tick/clock-driven**, not exact quanta; deadline updated in `update_deadline()` after `v ≥ vd` (comment: "strictly `vd_i += N*r_i/w_i`... good enough").
- **Lag is clamped** on dequeue and remembered across sleep (paper assumes tasks leave/arrive with zero or "positive" lag).
- **RUN_TO_PARITY** (not in paper): protects current so wakeups don't thrash.
- **Slice-protection with shortest slice in queue** (`cfs_rq_min_slice`) when running to parity.
- **Hierarchical**: each cgroup has its own cfs_rq; group entities participate in their parent's EEVDF with `h_load` weights.
- **Augmented rbtree**: key = deadline, aug = subtree min_vruntime (and min_slice) for pruning.
- **Delayed dequeue** (6.12) is a Linux-specific answer to sleep-based lag gaming; the paper has none.
- Docs states: "There are ongoing discussions on how to manage lag, especially for sleeping tasks."

## 11. Frontier

All arXiv entries were confirmed to exist via the arXiv API on 2026-10-04 (titles/dates below are from it). Research-agent summaries about venues and speedups are *not* independently verified unless stated.

- **Proxy Execution (Stultz et al., Google)**, generalised priority inheritance: mutex-blocked task stays queued and the lock owner runs *on its behalf*. Kconfig `SCHED_PROXY_EXEC` exists in master but depends on `EXPERT` and **`!SCHED_CLASS_EXT`**: merged, experimental, not yet combined with sched_ext (verified in `init/Kconfig`).
- **sched_ext** (merged Linux 6.12): BPF-defined scheduler class. Production examples: Valve/Igalia `scx_lavd` (latency-criticality-aware virtual deadline; reported fleet use at Meta per Phoronix/LPC 2025, *secondary*). Docs: <https://docs.kernel.org/scheduler/sched-ext.html>.
- **SchedCP**, "Towards Agentic OS: An LLM Agent Framework for Linux Schedulers" (arXiv 2509.01245, Sep 2025): MCP-server control plane where LLM agents synthesize and deploy sched_ext policies; claims up to 1.79× on kernel build (abstract-level; *unreplicated*).
- **Mixture-of-Schedulers** (arXiv 2511.11628, Nov 2025): learned router over expert sched policies.
- **UFS, "Unfair by design"** (arXiv 2605.02377, May 2026): eBPF sched_ext scheduler for mixed DB workloads: restricts background tasks to idle CPU, preempts instantly, uses eBPF-map hints against priority inversion. Motivating claim: OS priorities don't isolate.
- **Affinity Tailor** (arXiv 2604.27915, Apr 2026): userspace-guided kernel scheduling at Google; compact CPU sets as *affinity hints* not hard partitions, to recover locality (cache/chiplet LLC). (Headline numbers in research notes: +12%/+7%; *not verified*, check paper.)
- **Latency-Aware Group Scheduling** (arXiv 2508.15703, Aug 2025): reduces context switching in densely packed clusters.
- **AKTS** (arXiv 2609.12276, Sep 2026): sub-µs kernel policy switching for LM agents (title/date verified; content unread).
- **Ekiben** (arXiv 2306.15076, EuroSys 2024 per research notes): safe Rust scheduler framework with live upgrade; older but the basis of "scheduler dev velocity" line.

Common thread: after EEVDF fixed the *mechanism* for per-runqueue fairness+latency, active work moved to **policy** (BPF/LLM-synthesised schedulers), **locality** (affinity hints), and **priority inversion** (proxy execution).

## 11b. Open problems

1. **Expressing latency SLOs.** Slice is a proxy; "p99 ≤ 5 ms" is not expressible without changing weight or relying on RT. Custom slice (6.12) is the first step.
2. **Cross-CPU fairness.** EEVDF's theorem is per-runqueue; global share depends on a periodic load balancer that predates it. No global lag.
3. **Cgroup hierarchy correctness.** Reweighting nested group entities moves vruntime units; clamping + reweight cascades have produced bugs (CVE-2024-35985 was one).
4. **Heterogeneous / SMT / NUMA.** Capacity, cache and sibling-thread effects aren't in the lag model.
5. **Tick-free precision.** Deadline hit detection quantised by the tick unless hrtick (costly).
6. **Interactive tuning.** Gaming/desktop communities still ship BORE or tuned slice defaults (CachyOS), suggesting the default slice (0.7–2.8 ms) and parity protection don't fit every interactive profile (*anecdotal*).
7. **Policy synthesis safety.** LLM-written BPF schedulers: verifier proves memory safety, not fairness or starvation-freedom.

## 12. Lineage

GPS (Parekh–Gallager, 1993) → WFQ/PGPS (Demers–Keshav–Shenker, 1989) → WF2Q (Bennett–Zhang, 1996) · stride scheduling (Waldspurger, 1995) → **EEVDF (Stoica–Abdel-Wahab, 1995; revisited RTSS 2000)** → CFS (Molnár, 2007, Linux 2.6.23) → **EEVDF in Linux (Zijlstra, 6.6, 2023)** → DELAY_DEQUEUE + custom slices (6.12) → sched_ext (6.12) → proxy execution (experimental).

## 13. Hands-on (≤30 min)

```bash
python3 eevdf_sim.py             # trace + fairness check (this folder)
```

Experiments to try by editing the script:
1. Change C's slice to 1/3/6; watch switch rate vs total CPU stay 8/8/8.
2. Delete the `eligible()` filter in `pick()`: C monopolises, shares drift.
3. On a real Linux ≥ 6.12 box:
```bash
sudo mount -t debugfs none /sys/kernel/debug 2>/dev/null
cat /sys/kernel/debug/sched/features
# schbench / cyclictest p99 with default vs short slice (python: os.sched_setattr unavailable; use libc syscall as in §1b)
echo NO_RUN_TO_PARITY | sudo tee /sys/kernel/debug/sched/features
```
Compare `perf sched latency` before/after.

## 14. Question ladder

**Mechanism**
1. Walk `pick_eevdf()` when leftmost-by-deadline is ineligible. Which subtree does it descend?
2. What does `update_deadline()` do and when?
3. Why does the kernel compare `avg >= key*load` rather than `avg/load >= key`?
4. What does `place_entity()` multiply lag by, and why `(W+w)/W`?
5. What state does a `sched_delayed` task hold?

**Why**
6. Why must V be the *weighted* average?
7. Why is the tree keyed on deadline but augmented with min_vruntime?
8. Why is lag stored as *virtual* lag?
9. Why do deadlines use `slice/weight`?

**Counterfactual**
10. Remove eligibility: what pathological workload appears?
11. Slice = 0.1 ms for all tasks: what happens to throughput and fairness?
12. PLACE_LAG off: describe an exploit.
13. Task weight doubles while queued: what must be rescaled?

**Adversarial**
14. How can a task game EEVDF through sleeping, and which feature closes it?
15. How can unprivileged code shorten its slice to degrade others? What bounds the damage?
16. How did CVE-2024-35985 turn weights into a kernel NULL deref?

**Connection**
17. How does EEVDF relate to WF2Q and why does the eligibility test match?
18. How does `cpu.weight` interact with hierarchical group entities?
19. How is `SCHED_DEADLINE` different from a virtual deadline?

**Open**
20. Can per-runqueue lag bounds compose into a global fairness bound with a periodic balancer?
21. What would a latency-SLO interface (not slice) look like?
22. How should lag be defined across heterogeneous cores?

<details><summary>Answers</summary>

1. If the leftmost (min-deadline) node is not eligible, loop: go to the left child while the left subtree's `min_vruntime` is eligible (an eligible task exists there, with earlier deadlines); else test the current node; else go right. First eligible node found = earliest-deadline eligible.
2. When `v ≥ vd` (request consumed): set `vd = v + slice·1024/w` and reschedule.
3. Division truncates, losing precision; cross-multiplication is exact. Needs 128-bit or overflow checks.
4. `(W+w)/W` inflation, because adding the task pulls V toward its vruntime and shrinks its apparent lag; this pre-compensates (derivation in §6).
5. Its (clamped, ≤0) vlag and deadline; it stays on the tree, ineligible, aging in virtual time until picked or woken.
6. So that `Σ lag_i = 0` (conservation) and V is the fluid-model reference: each task should have received `w_i·ΔV`.
7. Deadline order gives the answer among eligibles; min_vruntime lets whole subtrees be pruned by eligibility → O(log n).
8. `lag = w·vlag`; vlag is weight-independent so reweight is a single scaling and comparisons avoid `w`.
9. The same request costs less virtual time at higher weight, so heavier tasks get earlier deadlines and more CPU per unit of V.
10. A flood of tiny-slice tasks always has the earliest deadline and starves long-slice tasks; lag unbounded.
11. Many more switches/cache misses: throughput drops, fairness bound shrinks (lag ≤ slice).
12. Sleep for a moment each slice and wake: negative lag is discarded, so you re-enter near V and effectively never pay back overconsumption.
13. vruntime/vlag/deadline must be rescaled (the `reweight_entity`/`reweight_eevdf` path), with the same lag clamp, else overflow (CVE-2024-35985).
14. Short sleeps to reset negative lag. `DELAY_DEQUEUE` keeps them queued/ineligible, burning lag.
15. Setting a short `sched_runtime` makes you preempt-prone and early-deadline, but eligibility caps your share to your weight, so damage is extra context switches, not extra CPU.
16. `reweight_eevdf()` computed vlag without the clamp; `weight` is 20-bit fixed-point; the s64 product overflowed, `entity_eligible()` returned false for all, `pick_eevdf()` returned NULL.
17. Same eligibility gate (start time ≤ virtual time); WF2Q uses it to cap how far ahead of GPS a flow can run, EEVDF to bound lag.
18. A group has a sched_entity per CPU whose weight derives from `cpu.weight`; it competes in its parent's EEVDF; its inner tasks have their own EEVDF; `h_load` carries effective weight.
19. SCHED_DEADLINE uses wall-clock runtime/deadline/period with admission control and CBS; EEVDF's are virtual and relative to a fair-share reference, no guarantees.
20. Open; the balancer equalises load, not lag, and runs on ≫ slice timescales.
21. Open; candidates: latency-nice, SLO hints via sched_ext maps, proxy-execution-aware slices.
22. Open; capacity scaling of vruntime (as PELT does for util) is the obvious but unsettled approach.

</details>

## 15. Go deeper next

1. **Per-entity load tracking (PELT) and load balancing** (what EEVDF doesn't do).
2. **sched_ext / BPF schedulers** (`scx_lavd`, DSQs, verifier limits).
3. **SCHED_DEADLINE: CBS + EDF admission control** (the real-time counterpart).

## Sources

**Papers / primary**
- Stoica & Abdel-Wahab 1995 EEVDF (lecture slides, UNC): <http://www.cs.unc.edu/~jeffay/courses/pisa/eevdf.pdf>
- EEVDF revisited, RTSS 2000: <https://users.soe.ucsc.edu/~sbrandt/rtss2000/proceedings/6.pdf> (not read)
- arXiv: [2509.01245](https://arxiv.org/abs/2509.01245) · [2511.11628](https://arxiv.org/abs/2511.11628) · [2605.02377](https://arxiv.org/abs/2605.02377) · [2604.27915](https://arxiv.org/abs/2604.27915) · [2508.15703](https://arxiv.org/abs/2508.15703) · [2609.12276](https://arxiv.org/abs/2609.12276) · [2306.15076](https://arxiv.org/abs/2306.15076)

**Code / docs**
- `kernel/sched/fair.c`, `kernel/sched/features.h`, `init/Kconfig` (torvalds/linux master, fetched 2026-10-04)
- <https://docs.kernel.org/scheduler/sched-eevdf.html> · <https://docs.kernel.org/scheduler/sched-ext.html>
- CVE-2024-35985: <https://security-tracker.debian.org/tracker/CVE-2024-35985>

**Articles**
- LWN: <https://lwn.net/Articles/925371/> · <https://lwn.net/Articles/969062/> · <https://lwn.net/Articles/968575/>
- Phoronix 6.6 merge / 6.13 EEVDF fix: <https://www.phoronix.com/news/Linux-6.6-EEVDF-Merged> · <https://www.phoronix.com/news/Linux-6.13-Last-Minute-EEVDF>
- Zaccaria notes: <https://www.vittoriozaccaria.net/blog/notes-on-linux-eevdf/> · Kernel Internals: <https://kernel-internals.org/sched/eevdf/>
- Meta lavd (secondary): <https://www.phoronix.com/news/Meta-SCX-LAVD-Steam-Deck-Server>

*Unverified in this dive: regression magnitudes from forum/LKML summaries, Affinity Tailor headline numbers, exact dates of later placement-fix commits, Meta fleet-wide scx_lavd claim.*
