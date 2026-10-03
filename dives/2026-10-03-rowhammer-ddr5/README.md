# Rowhammer on DDR5 — why in-DRAM mitigations keep failing

**Domain:** Security / Hardware · **Topic:** Rowhammer read-disturbance and the TRR → RFM → PRAC mitigation arms race on DDR5 · **Depth:** research

> Defensive/educational dive. It explains the *physics of the failure* and *why the defenses keep getting bypassed* — the mechanism and the mitigation design, not an attack recipe.

---

## 0b. Plain-English first

**Explain it simply.** Computer memory (RAM) is a huge grid of tiny buckets, each holding a little water. A full bucket means "1", an empty one means "0". The buckets are packed so tightly that sloshing one bucket over and over makes a neighbor you never touched slowly leak — and if it leaks past half-full before the automatic top-up truck comes around, its value silently flips from 1 to 0. That is Rowhammer: you corrupt data you were never allowed to touch, just by reading your *own* data very fast, very many times, right next to it.

Why anyone cares: a single flipped bit in the right spot — a permission flag, a pointer, a number in a security check — can hand an attacker control of a machine they share with you (a cloud server, your phone, a browser tab). It is a software-triggered *hardware* bug, so you cannot simply patch it away.

**Everyday example.** Imagine a library with shelves one millimeter apart. You repeatedly yank one book off a shelf and slam it back, thousands of times a second. The vibration is enough that the book on the shelf two rows over slips and falls — even though you never touched that shelf. The librarian (the memory's refresh system) walks the aisles re-shelving everything every 64 milliseconds. Rowhammer is yanking your book fast enough that the neighbor falls *before the librarian gets there*. The defenses are all variations on "a smarter librarian who watches which books you yank" — and attackers keep finding the moments the librarian isn't looking.

**Bridge line.** Now the same thing, technically.

---

## 1. Bare-minimum context

- **DRAM cell = 1 transistor + 1 capacitor (1T1C).** The bit is the capacitor's charge. Charge leaks, so it must be *refreshed* periodically. ([Kim et al. 2014 §2](https://users.ece.cmu.edu/~yoonguk/papers/kim-isca14.pdf))
- **Rows and the row buffer.** A *wordline* turns on a whole row of cells onto the *bitlines*; *sense amplifiers* read and restore them into the *row buffer*. Reading a row is destructive and immediately rewritten.
- **ACTIVATE / PRECHARGE / REFRESH.** `ACT` opens a row, `PRE` closes it, `REF` tops cells back up. The fastest you can reopen the same bank is `tRC` (~45–48 ns).
- **Refresh window `tREFW` = 64 ms** (DDR3/4; 32 ms DDR5), split into REFs every `tREFI` (~7.8 µs DDR3/4, ~3.9 µs DDR5). A victim row survives only if refreshed before it leaks past its noise margin.
- **HC_first** = hammer count to first bit flip. The single most important number: it has fallen ~10× per generation.
- **TRR / RFM / PRAC** are the three in-DRAM defenses, in historical order. This dive is mostly about why the first two failed and whether the third is enough.

---

## 1b. Real-world context

**What it is, in one paragraph.** Rowhammer is a read-disturbance phenomenon in DRAM: repeatedly activating ("hammering") one row electrically disturbs physically adjacent rows, leaking their charge fast enough to flip bits before the next refresh. First shown by Kim et al. (ISCA 2014): disturbance errors in **110 of 129 DDR3 modules**, with **as few as 139K reads** to a row, in **every module made in 2012–2013** ([paper](https://users.ece.cmu.edu/~yoonguk/papers/kim-isca14.pdf)). It is a *scaling* defect — it gets worse as cells shrink — not a bug any single vendor can fix.

**Why it exists / why it's a problem.** DRAM density doubles by shrinking cells and packing them tighter. Smaller cells hold less charge (smaller noise margin); tighter pitch means stronger capacitive/electromagnetic coupling between neighbors. So each generation needs *fewer* hammers to flip a bit. It breaks the most basic guarantee software assumes: that writing memory you don't own cannot change it. Before Rowhammer, memory integrity was taken for granted; now it is an active, unsolved hardware-security problem.

**Where it shows up (real systems):**
- **Cloud multi-tenant servers** — the canonical threat model: your VM hammers to flip a neighbor tenant's page-table entry.
- **Browsers** — Rowhammer.js triggered flips from JavaScript; no native code needed.
- **Android / mobile** — Drammer flipped bits deterministically on phones via the contiguous ION allocator.
- **AMD Zen desktops/servers** — ZenHammer (USENIX Sec 2024) reached AMD + the first DDR5 flip.
- **NVIDIA GPUs** — GPUHammer (USENIX Sec 2025) flipped GDDR6 on an RTX A6000, dropping an ML model's accuracy from ~80% to 0.1%.
- **SK Hynix DDR5** — Phoenix (S&P 2026, CVE-2025-6202) got root on a *default* DDR5 desktop in minutes.

**How a practitioner touches it (defensive side).** You don't "call" Rowhammer; you *observe* and *configure around* it:
```bash
# Watch corrected/uncorrected ECC errors per DIMM (rising CE = marginal cells / pressure)
sudo systemctl enable --now rasdaemon
sudo ras-mc-ctl --error-count
sudo ras-mc-ctl --summary
edac-util -v
```
Server BIOS exposes a **refresh-rate multiplier** (1×/2×/4× tREFI); the 2015 industry reflex was to force 2×. Memtest86 ships a Rowhammer test (test 13). JEDEC's modern answer is firmware/controller settings for RFM and (future) PRAC.

**When to care / when not.** Care if you run **multi-tenant hardware, a browser engine, a mobile platform, or an ML inference service on shared GPUs**, or if you certify hardware. You can mostly ignore it on a single-user, physically-secured, non-adversarial box — the attacker needs to run code on the same DRAM as the victim.

**Who should care.** Cloud/infra security, DRAM and memory-controller designers, browser/OS sandbox authors, ML-serving infra, and hardware-security researchers.

---

## 2. The one-liner — and what it hides

> "Rowhammer flips bits in memory you can't access by hammering an adjacent row; vendors added TRR to fix it."

What that sentence hides:
1. **Why** hammering a row disturbs a neighbor at all (it's three distinct physical effects, not "vibration").
2. That **TRR is a sampling heuristic with bounded state** — and that bound is exactly what every bypass exploits.
3. That the threshold **keeps collapsing** (139K → 4.8K → projected 128), so a defense that's cheap today is ruinous tomorrow.
4. That hammering isn't the only trigger — **RowPress** (holding a row *open*) and **Half-Double** (distance-2) break the "refresh the immediate neighbor" assumption.
5. That **DDR5's real fix is counting (PRAC), not sampling** — and the 2025–26 literature is busy showing even counting is expensive and leaky.

---

## 3. The problem

Software's bedrock assumption: memory you cannot name, you cannot change. DRAM scaling broke it. By the 20-nm node, the charge separating "1" from "0" and the spacing between rows both shrank to where normal-rate activations of one row leak a neighbor past its margin inside a single 64 ms refresh window.

The constraint that forces every design decision is **the activation budget vs. HC_first**. A single bank admits at most ~`tREFW / tRC` ≈ `64 ms / 47 ns` ≈ **1.36M activations per refresh window** (arithmetic, not a paper figure). If HC_first is 139K (DDR3, 2014) you need ~10% of that budget aimed at one victim — hard but doable. If HC_first is 4.8K (LPDDR4, 2020), it's trivial. Projected future chips sit near **128**. The defense problem is: *catch an over-activated row before it crosses a threshold that is shrinking out from under you, cheaply, across billions of rows.*

Concrete generation trend ([Revisiting RowHammer, ISCA 2020](https://arxiv.org/pdf/2005.13121), 1580 chips):

| Gen | HC_first (old node → new node) |
|---|---|
| DDR3 | 69.2K → 22.4K |
| DDR4 | 17.5K → 10K |
| LPDDR4 | 16.8K → **4.8K** |

Minimum observed overall: **9.6K** total (4.8K to each of two aggressors, double-sided). Bit flips per fixed activation count rose ~500× over the same span.

---

## 4. Mental model

**The leaky-bucket grid with a patrolling top-up truck.** Each cell is a bucket slowly leaking. The refresh truck tops every bucket every 64 ms. Hammering a row shakes its neighbors' buckets so they leak faster; flip = a neighbor empties past half before the truck arrives. TRR is "a spotter riding the truck who notes which buckets you've been shaking a lot and tops those neighbors early." PRAC is "a counter bolted to every bucket that rings a bell the moment it's been shaken too much."

**Where the analogy breaks:** the disturbance isn't mechanical vibration — it's three electrical effects (coupling, bridges, hot-carrier injection), and critically it can reach the **bucket two rows away** (Half-Double) and can be driven by **holding a bucket open** rather than shaking it (RowPress). A mechanical-vibration intuition predicts neither.

---

## 5. The mechanism, traced

Trace one double-sided disturbance on a DDR4 bank. Victim row **V**; aggressors **A₁ = V−1**, **A₂ = V+1**.

```
Row V-1 (A1)  ──┐        wordline toggles raise/lower voltage
Row V    (V)  ──┤ victim  ← coupling + leakage from BOTH sides
Row V+1 (A2)  ──┘

one hammer iteration:
  ACT A1   → wordline A1 high: charge dumped to bitlines, sensed, RESTORED
             (A1's toggle capacitively couples into V's cells, nudges leakage)
  PRE A1   → close A1
  ACT A2   → same from the other side of V
  PRE A2
  … repeat ~4,800× per aggressor before V's next REF …
```

Step-by-step with the physics ([Kim et al. 2014 §3](https://users.ece.cmu.edu/~yoonguk/papers/kim-isca14.pdf)):

1. **ACT A₁** raises A₁'s wordline. Its cells drive the bitlines; sense amps latch and immediately rewrite A₁ (destructive read + restore). Fine so far — A₁ is intact.
2. The wordline voltage swing **couples into V**: (a) *capacitive/EM coupling* briefly, partially turns on V's access transistors, bleeding charge; (b) *bridges* (process shorts) offer leakage paths; (c) *hot-carrier injection* from toggling alters transistor leakiness over time.
3. **PRE A₁**, then **ACT/PRE A₂** — V now gets disturbed from the other side too. Double-sided because both neighbors' coupling *adds*.
4. Each iteration bleeds a sliver of V's charge. V is not being refreshed (nobody activated V, and its scheduled REF is up to 64 ms away).
5. After ~**9.6K** total activations (worst DDR4-era chip), V's charge crosses the sense-amp decision point. Next time V is read, the sense amp latches the **wrong** value. **Bit flipped.**

The attacker never issued a single `ACT V`. Memory integrity violated purely by activity on V's neighbors.

**RowPress variant (the physics knob):** instead of fast ACT/PRE cycles, keep A₁ *open* (long `tAggON`). A held-open row keeps injecting disturbance without the recovery a precharge gives. Measured reductions vs. hammering: **~17.6× fewer activations at tAggON = 7.8 µs, ~159× at 70.2 µs**, and **a single activation at tAggON ≈ 30 ms** ([RowPress, ISCA 2023](https://arxiv.org/abs/2306.17061)). Worse when hot.

---

## 6. The math

### Refresh-window arithmetic
`tREFW = 64 ms`, `8192 REF` per window ⇒ `tREFI = 64 ms / 8192 = 7.8 µs` ([Kim 2014 §2.3](https://users.ece.cmu.edu/~yoonguk/papers/kim-isca14.pdf)). Max same-bank activations in a window ≈ `tREFW / tRC = 64 ms / 47 ns ≈ 1.36M` (derived). → *in plain terms:* the attacker's whole budget is ~1.36M hammers; a defense only has to make "aim 4.8K of them at one victim undetected" impossible.

### PARA — the stateless probabilistic defense
On every row close, with probability `p` the controller refreshes an adjacent row. No counters, no addresses. The chance a specific victim is **never** rescued over `N` aggressor activations is

$$P_{\text{miss}} = (1 - p)^{N} \quad(\text{or } (1 - p/2)^{N}\text{ if the coin picks one of two neighbors})$$

→ *in plain terms:* each hammer is an independent coin flip for "refresh your neighbor now." To dodge rescue for `N` hammers, *every* coin must come up tails — and that probability decays geometrically. With `p ≈ 0.001–0.005`, `P_miss` over a window is driven below the hardware hard-error budget (~10⁻¹⁵, [approx]) at **< 0.75%** performance cost. Why this form and not a counter: it needs **zero state** — the whole point. Its weakness is also in the equation: `P_miss` depends on `N`, and as HC_first (the `N` you must survive) shrinks, you must raise `p`, and overhead climbs.

### Graphene — counting with Misra–Gries
To refresh *exactly* the hot rows you must identify every row exceeding a threshold in a window, cheaply. Misra–Gries heavy-hitters: to find every element occurring more than `N/k` times in a stream of `N` items needs only **`k−1` counters**, and each stored estimate never exceeds the true count (**no false negatives**). Applied to Rowhammer: to catch any row reaching ~`T_RH/2` activations among `N_ACT` activations in a window,

$$\text{entries} > \frac{N_{ACT}}{T_{RH}/2} = \frac{2\,N_{ACT}}{T_{RH}}$$

→ *in plain terms:* you don't need a counter per row — you need a counter per "slot of hammering budget big enough to matter," which is ~`2·N_ACT/T_RH`. ([bound restated in surveys/CoMeT](https://arxiv.org/html/2402.18769v1); confirm constant against MICRO'20.) Why this beats naive per-row counters: storage shrinks from billions of rows to a few hundred entries per bank — but it still **scales inversely with T_RH**, so as the threshold falls (1000 → 125) storage balloons (~207 KiB → ~1.5 MiB per the CoMeT analysis).

---

## 7. Why it works (and what breaks if you remove a piece)

The core insight dividing the whole field: **sampling vs. counting.**

- **Sampling (TRR)** keeps a small fixed set of "hot candidate" rows. It works *only if* the real aggressors stay in that set. Remove the assumption that an attacker activates few distinct rows → the tracker overflows → an aggressor goes unrefreshed. That single property is what TRRespass, U-TRR, Blacksmith, ZenHammer, and Phoenix all exploit.
- **Counting (PRAC)** keeps an *exact* per-row count. It works because there is nothing to overflow and nothing to under-sample — the count is ground truth. Remove exactness (approximate/shared counters) and you reintroduce blind spots.

Ablation:
- Remove **refresh entirely** → DRAM loses data in milliseconds regardless of attacks. Refresh is load-bearing.
- Remove **neighbor-refresh-on-detection** from TRR → it's just normal refresh; flips trivially.
- Remove **exact counting** from PRAC → back to TRR's bounded-state failure.
- Remove the **Alert Back-Off window bound** from PRAC → attacker races activations in after the alert; the ~180 ns / ~3-ACT residual window is the controlled remnant of that risk.

---

## 8. Design knobs & alternatives

| Defense | Knob | Trade-off |
|---|---|---|
| **Increased refresh (2×/4×)** | tREFI multiplier | Cheap reflex; power + bandwidth cost; insufficient as HC_first drops (SAFARI: "not effective or desirable") |
| **ECC (SECDED)** | code strength | Corrects 1 / detects 2 bits per word; multi-flip words defeat it; correction-timing is itself a side channel (ECCploit) |
| **On-die ECC (DDR5)** | mandatory, 8 bits / 128 | Reliability only; can *mask* flips, hurting detection; not a Rowhammer guarantee |
| **PARA** | probability `p` | Stateless, <0.75%; only statistical; retune `p` as T_RH falls |
| **TRR** | #tracker entries, sample rate | Bounded state → many-sided/synchronized bypass |
| **Graphene/CoMeT** | #counter entries | Provable no-false-negative; storage ∝ 1/T_RH |
| **RFM (DDR5)** | RAAIMT, RAAMMT | Forces mitigation budget by ACT count; but *which* rows is still TRR-blind |
| **PRAC (DDR5)** | N_BO, N_mit∈{1,2,4}, ABO window | Exact; but RMW-per-precharge latency (~up to 10–18%) + new side/DoS channels |

Why counting won the design argument: sampling was repeatedly, structurally broken. Why it hasn't simply ended the problem: exact per-row counting at DRAM scale is expensive in area, latency, and energy — the entire 2024–26 PRAC-optimization literature exists to claw that cost back.

---

## 9. Where it breaks

**TRR — bounded tracking.** A tracker that remembers N rows is beaten by N+1 aggressors.
- *TRRespass* (S&P 2020): many-sided hammering (up to ~19 aggressors) overflowed trackers; flips on **13/42** DDR4 DIMMs across all three vendors ([paper](https://download.vusec.net/papers/trrespass_sp20.pdf)).
- *U-TRR* (MICRO 2021): used retention failures as a side channel to *see* exactly when/how many rows TRR refreshes; bypassed on **45 modules**, up to 99.9% of rows flippable ([arXiv](https://arxiv.org/abs/2110.10603)).
- *Blacksmith* (S&P 2022): non-uniform frequency/phase patterns flipped **all 40/40** DDR4 DIMMs.

**DDR5 TRR — Phoenix (S&P 2026, CVE-2025-6202).** SK Hynix DDR5 TRR samples over a long, complex schedule (best bypass pattern spanned **128 REF intervals**, ~8× the ~16 assumed). "Self-correcting synchronization" re-aligns after missed refreshes to land hammers in the sampler's blind spots. Flips on **15/15** SK Hynix DDR5 DIMMs (made Jan 2021–Dec 2024); **root on a default DDR5 desktop in ~109 s** ([ETH COMSEC](https://comsec.ethz.ch/research/dram/phoenix/)). On-die ECC did not help.

**The physics breaks the "refresh the neighbor" assumption too.**
- *Half-Double* (Google 2021): disturbance reaches **distance-2**. Heavily accessing row A plus a few accesses to intermediate B flips row C — and TRR's own refresh of B acts as an access that propagates it. An intrinsic silicon property that widens as geometry shrinks ([Google](https://security.googleblog.com/2021/05/introducing-half-double-new-hammering.html)).
- *RowPress* (ISCA 2023): pressing, not hammering — orthogonal to activation-count defenses.

**Misconceptions practitioners hold (each wrong):**
- "ECC fixes it" → ECCploit (S&P 2019) crafts multi-flip words and uses correction timing.
- "DDR5 is immune" → ZenHammer + Phoenix.
- "Server/ECC memory is safe" → ECCploit targeted server ECC; ZenHammer hit AMD server/desktop.
- "It needs physical access" → Project Zero 2015 did it from a sandboxed userland program; Rowhammer.js from JavaScript.
- "TRR solved it" → every bypass above.

---

## 10. In the wild

- **Exploits:** Google Project Zero 2015 (PTE flip → kernel privilege escalation from an unprivileged process); Drammer (deterministic, Android); Rowhammer.js (browser); Throwhammer (over the network via RDMA).
- **GPUHammer (USENIX Sec 2025):** GDDR6 on NVIDIA RTX A6000 (non-ECC by default); ~500K activations/window; a **single** weight-bit flip dropped model accuracy **~80% → 0.1%**; 56–80% drops across AlexNet/VGG16/ResNet50/DenseNet161/InceptionV3 ([arXiv](https://arxiv.org/abs/2507.08166)). ECC GPUs (H100, RTX 5090) detect/correct these.
- **Deployed defenses today (2025–26):** TRR + on-die ECC + RFM — all shown bypassable on default DDR5 (Phoenix). Google states PRAC is **not yet in the DDR5 systems it evaluated** — it's standardized for *future* revisions, not shipping.
- **2015 stopgap:** Apple/HP/Cisco/Lenovo/IBM BIOS updates forced 2× refresh (tREFI 7.8 → 3.9 µs). Partial and costly.

---

## 11. Frontier (what's new, 2024–2026)

The field has two live fronts: **(a) make PRAC practical and secure**, and **(b) attack PRAC itself.** Three papers dissected:

### Phoenix (ETH COMSEC + Google, IEEE S&P 2026) — CVE-2025-6202
*Problem:* prior DDR5 work (ZenHammer) got only a lone flip; DDR5 TRR was assumed sufficient. *Method:* reverse-engineered SK Hynix's TRR and found its sampling repeats over a **128-tREFI** window (8× longer than believed), leaving lightly-sampled sub-intervals; patterns self-synchronize into those blind spots and re-align after missed refreshes. *Result:* flips on all 15 tested DIMMs; first end-to-end DDR5 exploit on default settings, root in ~5 min (first flip ~109 s); on-die ECC bypassed. *Limitation / lesson:* sampling is structurally defeatable once the schedule is known — the capstone argument for moving to counting. ([PDF](https://comsec-files.ethz.ch/papers/phoenix_sp26.pdf) · [code](https://github.com/comsec-group/phoenix))

### QPRAC (HPCA 2025) — making PRAC secure *and* practical
*Problem:* naive PRAC mitigation queues are "tardy" — MOAT (ASPLOS 2025) showed counts can reach ~1150 against a threshold of 128 before mitigation lands. *Method:* an N-entry **priority service queue** per bank tracking the top-N most-activated rows, giving provable security bounds even at ultra-low thresholds. *Result:* claims JEDEC-compliant security down to **T_RH = 71**. *Limitation:* still pays per-activation counter cost; part of an unsettled design race (MOAT, Chronus, CnC-PRAC, CoMeT, one-hot counting). ([arXiv](https://arxiv.org/abs/2501.18861))

### PRACLeak (ISCA 2025) — the defense is a new side channel
*Problem:* does counting introduce its own leaks? *Method:* PRAC's ABO/RFM mitigation actions are observable via memory-access **latency** — a victim's mitigation events time-modulate an attacker's accesses. *Result:* a timing channel that leaks secrets, plus availability (forced-ABO DoS) concerns; i.e. the mitigation machinery itself is exploitable. *Follow-ups:* AutoPRAC (model-checking to auto-discover PRAC attacks); a CCS 2025 generalization that *both* sampling- and counting-based defenses leak via mitigation activity. ([arXiv](https://arxiv.org/abs/2505.10111))

**More, with links:**
- *GPUHammer* (USENIX Sec 2025) — Rowhammer on GPU GDDR6; ML weight corruption ([arXiv](https://arxiv.org/abs/2507.08166)).
- *MOAT* (ASPLOS 2025) — secure per-row counting; exposes queue tardiness ([arXiv](https://arxiv.org/abs/2407.09995)).
- *RowPress* IEEE Micro 2024 journal version ([arXiv](https://arxiv.org/abs/2406.16153)); combined RowHammer+RowPress characterization ([arXiv](https://arxiv.org/abs/2406.13080)).
- *CoMeT* (DSN 2024) — Count-Min-Sketch low-cost row tracking ([arXiv](https://arxiv.org/abs/2402.18769)).
- *SpyHammer* — Rowhammer as a temperature sensor, ±2.5 °C ([arXiv](https://arxiv.org/abs/2210.04084)); *FP-Rowhammer* — device fingerprinting from the vulnerable-cell map.
- *Fundamentally Understanding and Solving RowHammer* (Mutlu et al., ASP-DAC 2023) — best conceptual framing ([arXiv](https://arxiv.org/abs/2211.07613)).

*(Flagged unverified by the research pass: exact venues/dates for GPUThor, DejaVu, ScaleDisturb, PVAC, Loaded Dice, ARTA, AutoPRAC, FP-Rowhammer, SpyHammer — inferred from arXiv IDs.)*

---

## 11b. Open problems

- **Is PRAC enough, at what cost?** Exact counting closes sampling/undercount holes, but the precharge-time read-modify-write inflates timings (reported up to ~10–18% slowdown) and the spec "leaves some questions unanswered"; flips have still been observed on PRAC-capable paths (NDSS 2026 analysis). Verdict: major advance, not a closed case.
- **The threshold-setting problem.** Every counter scheme needs a safe threshold *below* HC_first — but HC_first keeps falling (139K → 4.8K → ~128 projected). A margin safe today may be unsafe next node; setting it low raises false-refresh overhead. No stable safe margin exists.
- **Counting at scale.** Exact per-row counters over billions of rows are expensive in area/latency/energy; where to store them (in-array vs. in-DRAM SRAM vs. controller) is unsettled.
- **Where should mitigation live?** DRAM-only (deployable, repeatedly failed), controller, or OS-cooperative (SAFARI's Self-Managing DRAM vs. VUSec/MSR's "commodity systems still need software defenses"). No consensus.
- **Verification.** No accepted method to *prove* a DIMM is Rowhammer-safe. TRR was proprietary and unauditable; "RowHammer-free" labels proved false. Aging effects are uncharacterized.
- **Supply-chain variation.** Vulnerability varies by vendor, die rev, batch, even within one chip — patterns don't transfer, defeating one-size thresholds and certification.
- **Economic misalignment.** TRR was *optional* in JEDEC and shipped as an undocumented black box; VUSec argues JEDEC's "self-interested companies" under-invest while end users bear the cost. Standardization lagged the threat by years.

---

## 12. Lineage

- **Pre-2014:** DRAM disturbance known as a reliability curiosity.
- **2014:** Kim et al. ISCA — Rowhammer named and shown exploitable; PARA proposed.
- **2015:** Project Zero weaponizes it (kernel privesc); 2× refresh stopgap; Rowhammer.js.
- **2016–2018:** Drammer (mobile), Throwhammer (network), ECC assumed safe.
- **2019:** ECCploit breaks ECC.
- **2020:** TRRespass breaks TRR; Revisiting RowHammer quantifies the HC_first collapse; Graphene (counting).
- **2021:** U-TRR reverse-engineers TRR; Half-Double (distance-2).
- **2022:** Blacksmith (40/40 DDR4).
- **2023:** RowPress (pressing ≠ hammering); SAFARI framing paper.
- **2024:** ZenHammer (AMD + first DDR5 flip); JEDEC PRAC in JESD79-5C; CoMeT, MOAT.
- **2025–26:** GPUHammer (GPUs/ML); QPRAC; PRACLeak (defense-as-side-channel); **Phoenix** (first full DDR5 exploit, CVE-2025-6202).

---

## 13. Hands-on (≤30 min, non-destructive)

You don't need to hammer anything. Observe the defenses and the budget math instead.

1. **Watch ECC/ RAS counters on a real box** (safe, read-only):
   ```bash
   sudo systemctl enable --now rasdaemon
   sudo ras-mc-ctl --summary        # memory controller + CE/UE totals
   sudo ras-mc-ctl --error-count    # per-DIMM corrected errors
   edac-util -v
   ```
   A rising CE count on one DIMM is the observable fingerprint of marginal cells.

2. **Compute your own activation budget.** Pick your DIMM's `tRC` (e.g. 46 ns) and `tREFW` (32 ms DDR5). Budget ≈ `tREFW/tRC`. Divide by a plausible HC_first (say 4800). The quotient is how many *independent victims* one refresh window could, in principle, threaten. Watch it balloon as you plug in the projected HC_first of 128.

3. **Reason through PARA.** With `p = 0.002` and `N = 50,000` hammers, `P_miss = (1−0.001)^{50000} ≈ e^{−50} ≈ 2×10⁻²²`. Now set HC_first (the `N` you must survive) to 128 and ask what `p` you'd need for the *same* safety — and what that does to overhead.

4. (Optional, your own hardware only) Memtest86 **test 13** runs a Rowhammer check from a bootable stick.

---

## 14. Question ladder

**Mechanism**
1. What are the three physical effects by which activating a row disturbs a neighbor?
2. Why is reading a DRAM row destructive, and what restores it?
3. Why is double-sided hammering worse than single-sided?
4. How does RowPress differ physically from classic hammering?
5. What makes Half-Double reach a distance-2 row?

**Why**
6. Why does HC_first fall with each process node?
7. Why did the field move from sampling (TRR) to counting (PRAC)?
8. Why is PARA stateless, and why is that both its strength and its weakness?
9. Why does Graphene need only ~`2·N_ACT/T_RH` counters instead of one per row?
10. Why doesn't on-die ECC stop Rowhammer — and why can it make detection *harder*?

**Counterfactual**
11. If HC_first stabilized at 50K forever, which defenses would suddenly be "good enough"?
12. Remove the ABO back-off window bound from PRAC — what attack reopens?
13. If trackers had unlimited entries, would TRR be secure? What would it cost?

**Adversarial**
14. How does Phoenix stay synchronized with a 128-tREFI sampling schedule?
15. Why does many-sided hammering defeat a bounded tracker?
16. How does ECCploit turn error *correction* into an oracle?
17. How could a mitigation mechanism (PRAC) itself leak secrets?

**Connection**
18. How does the sampling-vs-counting split mirror heavy-hitter problems in streaming/databases?
19. How is GPUHammer's ML-weight attack related to the page-table-entry attack conceptually?
20. How does the threshold-setting problem resemble a moving-target in any rate-limiter?

**Open**
21. Should Rowhammer mitigation live in DRAM, the controller, or the OS?
22. How would you *prove* a DIMM Rowhammer-safe?
23. Is PRAC's ~10–18% overhead acceptable, and who decides?
24. Does per-chip variation make certification impossible in principle?

<details><summary>Answers</summary>

1. Capacitive/EM coupling between adjacent wordlines (partially turns on neighbor transistors), conductive bridges/shorts, and hot-carrier injection that alters transistor leakiness over time.
2. Sensing dumps the capacitor's charge onto the bitline to detect it, draining the cell; the sense amplifier simultaneously rewrites the charge back ("restore").
3. The coupling from both bracketing aggressors (V−1 and V+1) adds, so the victim loses charge from two sides — fewer total activations to cross the margin.
4. RowPress keeps the aggressor row *open* (long tAggON) rather than rapidly toggling; cumulative leakage injected while open replaces the need for many ACTs — 1–2 orders of magnitude fewer, worse when hot.
5. Coupling isn't strictly nearest-neighbor; heavy access to a distance-2 row plus a little to the intermediate row propagates disturbance, and TRR's refresh of the intermediate row itself acts as an extra access.
6. Smaller cells hold less charge (smaller noise margin) and sit at tighter pitch (stronger coupling), so less injected disturbance flips a bit.
7. Sampling keeps bounded state and can be overflowed or dodged by learning the schedule (TRRespass→Phoenix); counting is ground truth with nothing to overflow.
8. PARA stores nothing — just a per-close coin flip; strength = zero area/state; weakness = only a statistical bound, and the required `p` rises as HC_first falls, raising overhead.
9. You only need to catch rows exceeding ~T_RH/2 activations within N_ACT total; Misra–Gries guarantees that with ~stream/threshold counters, far fewer than one-per-row.
10. On-die ECC is a reliability code, not adversarial; multi-flip words defeat SECDED, and by silently correcting isolated flips it hides the onset of corruption from monitoring.
11. Increased-refresh and PARA with modest `p` would be cheap and sufficient; the whole crisis is driven by HC_first collapsing.
12. The attacker races a burst of activations in after the alert but before mitigation; the bounded ~180 ns/~3-ACT window exists precisely to cap that.
13. Yes in principle, but one entry per row is billions of counters — the area/latency/energy is exactly why counting was avoided until PRAC's optimized forms.
14. It reverse-engineered the 128-tREFI sampling period and uses self-correcting synchronization to re-align hammers into lightly-sampled sub-intervals after any missed refresh.
15. The tracker holds N candidates; N+1 distinct aggressors guarantee at least one real aggressor is never selected for neighbor-refresh.
16. A corrected (single-bit) read takes measurably longer; timing it tells the attacker which flips the code absorbed, guiding them toward an undetectable multi-flip word.
17. PRAC's mitigation actions (ABO/RFM stalls) change memory latency observably; an attacker times their own accesses to infer a victim's activation/mitigation pattern (PRACLeak).
18. Both are "find elements exceeding a frequency threshold in a stream with bounded memory" — Misra–Gries / Count-Min-Sketch are the shared tools.
19. Both flip a single high-leverage bit — a PTE permission bit vs. a model weight — so a tiny, targeted corruption yields outsized control/damage.
20. A rate-limiter tuned to a threshold that itself drifts must either over-provision (overhead) or risk misses; HC_first is that drifting threshold.
21. Unsettled: DRAM-only is deployable but has failed repeatedly; OS-cooperative is flexible but needs new controller primitives; likely defense-in-depth across all three.
22. Open: no accepted test vectors; you'd need exhaustive characterization across patterns, temperature, aging, and per-chip variation — currently infeasible.
23. Contested: depends on workload and threat model; buyers ultimately pay in performance/power, and there's no neutral arbiter.
24. Possibly: if patterns don't transfer across chips, per-die certification may be the only sound approach, which is economically brutal.

</details>

---

## 15. Go deeper next

- **PRAC/RFM internals and the counter-optimization race** (QPRAC, MOAT, Chronus, CoMeT) — the live design frontier.
- **Side channels from defenses** (PRACLeak, ECCploit timing) — how adding a mitigation adds an oracle.
- **Memory integrity for ML accelerators** (GPUHammer, DeepHammer) — Rowhammer meets model security.

---

## Sources

**Papers**
- Kim et al., *Flipping Bits in Memory Without Accessing Them*, ISCA 2014 — https://users.ece.cmu.edu/~yoonguk/papers/kim-isca14.pdf
- Kim et al., *Revisiting RowHammer*, ISCA 2020 — https://arxiv.org/abs/2005.13121
- Luo et al., *RowPress*, ISCA 2023 — https://arxiv.org/abs/2306.17061
- Frigo et al., *TRRespass*, S&P 2020 — https://download.vusec.net/papers/trrespass_sp20.pdf
- Hassan et al., *U-TRR*, MICRO 2021 — https://arxiv.org/abs/2110.10603
- Cojocar et al., *ECCploit*, S&P 2019 — https://download.vusec.net/papers/eccploit_sp19.pdf
- *Phoenix*, IEEE S&P 2026 — https://comsec-files.ethz.ch/papers/phoenix_sp26.pdf
- Jattke et al., *ZenHammer*, USENIX Sec 2024 — https://www.usenix.org/system/files/usenixsecurity24-jattke.pdf
- Lin et al., *GPUHammer*, USENIX Sec 2025 — https://arxiv.org/abs/2507.08166
- *QPRAC*, HPCA 2025 — https://arxiv.org/abs/2501.18861
- *MOAT*, ASPLOS 2025 — https://arxiv.org/abs/2407.09995
- *PRACLeak*, ISCA 2025 — https://arxiv.org/abs/2505.10111
- *CoMeT*, DSN 2024 — https://arxiv.org/abs/2402.18769
- Mutlu et al., *Fundamentally Understanding and Solving RowHammer*, ASP-DAC 2023 — https://arxiv.org/abs/2211.07613
- Mutlu, *RowHammer Retrospective* (ISCA-50) — https://ar5iv.labs.arxiv.org/html/2306.16093

**Code / docs**
- Phoenix artifacts — https://github.com/comsec-group/phoenix
- ZenHammer code — https://github.com/comsec-group/zenhammer
- RowPress code — https://github.com/CMU-SAFARI/RowPress
- CVE-2025-6202 — https://app.opencve.io/cve/CVE-2025-6202

**Articles / vendor**
- Google, *Introducing Half-Double*, 2021 — https://security.googleblog.com/2021/05/introducing-half-double-new-hammering.html
- Project Zero, *Exploiting the DRAM Rowhammer bug*, 2015 — https://googleprojectzero.blogspot.com/2015/03/exploiting-dram-rowhammer-bug-to-gain.html
- Intel, *Rowhammer: whose issue to mitigate* — https://www.intel.com/content/www/us/en/security/security-practices/blogs/rowhammer-whose-issue-to-mitigate.html
- JEDEC timing reference — https://en.wikipedia.org/wiki/Memory_timings
