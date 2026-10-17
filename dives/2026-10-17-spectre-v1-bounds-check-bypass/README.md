# Spectre v1 (Spectre-PHT / bounds-check bypass)

**Security/offense · Branch prediction & cache side channels · Spectre v1: branch predictor mistraining, bounds-check bypass, cache timing reads · Depth: hard**

## Plain English first

Picture a librarian who works fast by guessing ahead. Every time you ask for a book, she doesn't wait for the front desk to confirm your library card covers that shelf — she's seen you ask for shelf-12 books a hundred times before, so while the front desk is still checking, she's already running to shelf 12, grabbing the book, and flipping to a page number written in pencil on its inside cover. If the front desk comes back and says "actually, your card doesn't cover shelf 12," she quietly puts the book back and tells you nothing happened. Officially, you never saw that book.

But she left a trace. To find that pencil-written page number fast, she memorized roughly where it was by *re-visiting a different shelf* — shelf-13A if the page number's first digit was 1, shelf-13B if it was 2, and so on — just enough to warm up her memory of that one spot. Now: if you ask her to re-fetch something from shelf-13B right after, she gets it to you noticeably faster than from 13A, because her memory of 13B is still warm from a few seconds ago. By timing how fast she responds across all 256 sub-shelves, you can figure out exactly which one she visited — and that tells you the pencil-written number on a page you were never allowed to read.

That's Spectre v1. The CPU is the librarian. Branch prediction is her guessing which way an `if` will go before the real answer (a slow, uncached bounds check) comes back. The "shelf 13" visits are cache lines. The trick isn't making the CPU read forbidden memory — it already *does* that, briefly, as an optimization every CPU performs billions of times a second. The trick is getting it to leave a provable, timeable fingerprint of a byte it was never supposed to look at, in a way that survives the CPU officially "undoing" the whole thing.

**Everyday example.** Say a program has a byte array `secret[]` you can't touch directly, and a function that does:
```
if (x < array1_size)
    y = array2[array1[x] * 256];
```
`array1_size` is 16, so indices 0–15 are legal. You've been calling this function with legal `x` values (0–15) a few hundred times — training the branch predictor to expect "yes, in bounds." Then, once, you flush `array1_size` from cache (so checking it takes time) and call it with `x = 1000`, pointing past the end of `array1` into memory that happens to contain a secret byte, say the ASCII value for `'Q'` (81). The CPU's predictor says "in bounds, go ahead" before the real check resolves. It speculatively reads `array1[1000]` → gets `81`, then speculatively reads `array2[81 * 256]` — pulling that one 64-byte cache line of `array2` into the CPU's cache. A few cycles later the real bounds check finishes, says "actually, out of bounds," and the CPU throws away every register change from that speculative detour. But the cache line for `array2[81*256]` is still warm. You then time a read to every one of the 256 possible `array2[i*256]` slots: 255 of them are slow (cache miss), one — `i=81` — is fast. You just read a byte you had no permission to read, without ever "successfully" executing the illegal load from the program's point of view.

**Now the same thing, technically.**

## 1. Bare-minimum context

- **Speculative execution**: CPUs execute ahead of resolved branches/dependencies, using predictions, and discard the results if the guess was wrong — a decades-old perf trick that is otherwise "architecturally invisible." ([Kocher et al., arXiv:1801.01203](https://arxiv.org/abs/1801.01203))
- **Branch prediction**: the CPU remembers past outcomes of a conditional branch (per branch, keyed loosely by address) and predicts the next one; it can be *trained* by an attacker who controls the inputs to that branch, even from a different context.
- **Cache timing side channel (Flush+Reload style)**: a shared cache line loaded recently answers much faster (~tens of cycles) than one that must come from RAM (~hundreds of cycles); timing a read reveals whether a specific address was touched.
- **"Architecturally invisible, microarchitecturally visible"**: register/memory state from a squashed speculative path is rolled back, but caches, TLBs, and branch predictor state are not — these form the covert channel.
- **Bounds check**: `if (x < size) array[x]` — the exact pattern an optimizing compiler leaves un-fenced, because fencing every branch is expensive (below).
- Source: [Kocher et al., "Spectre Attacks," arXiv:1801.01203 / IEEE S&P 2019](https://arxiv.org/abs/1801.01203); [Project Zero, "Reading privileged memory with a side-channel"](https://projectzero.google/2018/01/reading-privileged-memory-with-side.html).

## 1b. Real-world context

**What it is, in one paragraph.** Spectre v1 (CVE-2017-5753, "bounds check bypass," Spectre-PHT in later taxonomy) is a class of attacks where an attacker mistrains a CPU's conditional-branch predictor so the processor *speculatively* executes the "in-bounds" path of a bounds check that will actually fail, reads out-of-bounds data, and uses that data as an index into a second array — which pulls one specific cache line into the cache. Timing a read of that second array afterward reveals which line was touched, leaking the out-of-bounds byte. Disclosed January 3, 2018, alongside Meltdown, by researchers at Graz TU, Google Project Zero, Cyberus, and others.

**Why it exists.** Out-of-order, speculative CPUs have chased single-thread performance for 25+ years by guessing branch outcomes and memory dependencies ahead of time; undoing a wrong guess architecturally (registers, memory) was assumed to make it "as if it never happened." Nobody budgeted for microarchitectural state (caches) as a side channel until Spectre showed it was a *generic*, reliable, cross-privilege-boundary leak — not a one-off bug in one CPU.

**Where it's used (as an attack, and where its countermeasures live).**
- **Browsers** (Chrome/V8, Firefox, Safari): the most exploited surface, because JavaScript gives attackers a timer, a sandbox to mistrain branches in, and a shared process memory space with other sites' secrets. V8 shipped index masking and "poisoning," plus Site Isolation by Chrome 67 (2018). ([v8.dev/blog/spectre](https://v8.dev/blog/spectre))
- **Linux kernel**: every syscall boundary where a user-controlled index reaches a kernel array is a candidate gadget; patched incrementally with `array_index_nospec()`.
- **Compilers**: LLVM's Speculative Load Hardening (`-mspeculative-load-hardening`), MSVC's `/Qspectre`, both auto-insert mitigations at detected or suspected gadgets.
- **Cryptographic libraries** (OpenSSL, libsodium, NaCl, PQClean): branch/index patterns on secret key material are exactly the gadget shape Spectre v1 wants, so these are a standing target for targeted hardening research (below).
- **Cloud/VM hosts and multi-tenant systems**: any place an untrusted guest shares a core/cache with a victim.

**How it's used** (defender's lens — you don't "use" Spectre v1, you harden against it): a kernel dev wraps a user-controlled array index with `array_index_nospec(index, size)`; a compiler flag (`-mspeculative-load-hardening`, `/Qspectre`) auto-inserts barriers; a crypto library author runs a gadget scanner against secret-dependent branches. Typical integration: compile hot, security-sensitive code (syscall entry, interpreter dispatch, crypto) with SLH or targeted LFENCEs; leave cold code unmitigated for speed.

**When to use it / when not.** Mitigate v1 wherever untrusted input controls an array index that is checked before use, and the checked-but-not-yet-confirmed value can reach a second, secret-dependent memory access — classic in interpreters, JIT engines, syscall dispatch, and any code processing attacker-supplied offsets. Skip blanket mitigation (fence-every-branch) in code with no attacker-controlled index or no adjacent secret, because the cost (below) is severe and untargeted hardening is provably incomplete anyway.

**Who should care.** Browser/JS-engine engineers, OS kernel maintainers, compiler engineers, cryptographic-library authors, and anyone running multi-tenant infrastructure where attacker and victim share a core.

## 2. The one-liner — and what it hides

**"Spectre v1 tricks the CPU into executing code it shouldn't, and reads the result through the cache."** That sentence hides:
1. The CPU doesn't "break" anything — it's doing exactly what branch prediction and speculative execution are *supposed* to do; the bug is that the rollback is architectural-only.
2. Mistraining is deliberate and cheap: the attacker supplies ~25 "good" calls for every "bad" one, and doesn't need code injection — just control over an input that reaches a checked index.
3. The leak isn't a single read — it's a probe over 256 possible values, repeated up to 999 times per byte, picking the winner by majority vote.
4. The "secret" doesn't need to be adjacent to `array1` — it's whatever lands at `array1[attacker_controlled_offset]`, which can be arbitrary out-of-bounds memory, including across a security boundary (sandboxed JS reading process memory).
5. There is no clean fix — software mitigations are a tax on every checked branch, chosen case by case, and none is proven to catch every gadget shape.

## 3. The problem

Before Spectre, "architecturally invisible" meant *invisible, full stop* — a wrong speculative guess rolled back registers and memory and that was assumed to be the end of the story. Compilers and OS/kernel code freely wrote bounds checks like `if (x < size) use(array[x])`, trusting that even if the CPU peeked ahead on a bad guess, nothing observable happened.

The constraint Spectre forces: *any* microarchitectural state that a wrong-path instruction touches and that isn't rolled back (L1/L2/L3 cache lines, TLB entries, branch predictor tables) is a covert channel if an attacker can (a) control what gets touched and (b) measure the state afterward with a timer. On the i7 Surface Pro 3 used in the original paper, this leaked memory at **~10 KB/s** ([Kocher et al., §4.2](https://arxiv.org/abs/1801.01203)) — far below bulk-copy speed, but fast enough to exfiltrate specific secrets (keys, passwords, pointers) in seconds to minutes, and fast enough that a 2018 follow-up measured ~**1 bit/s** reliably defeating deployed *browser* mitigations (timer coarsening, SharedArrayBuffer removal) from pure JavaScript. ([Aleph Security, 2018](https://www.bleepingcomputer.com/news/security/some-spectre-in-browser-mitigations-can-be-defeated))

## 4. Mental model

**Analogy**: the librarian from the plain-English section — guesses ahead of a slow permission check, leaves a pencil-trace of what she fetched, "un-fetches" it on paper but the trace (a warm shelf) stays.

**Where it breaks**: real librarians don't literally run to a shelf and then "forget they ever went" — a CPU's rollback really is bit-exact at the architectural level (registers, memory, flags all restored as if the branch had been taken correctly from the start). The analogy also undersells how *statistical* the leak is: one trip to the shelf isn't enough to beat noise; the attacker needs hundreds of repeated trips (the training loop) before timing is reliable, because contention, prefetching, and CPU frequency scaling all jitter the signal.

## 5. The mechanism, traced

This replays the toy example above with the paper's actual code (Listing 4, `arXiv:1801.01203`, verified against the PDF):

```c
unsigned int array1_size = 16;
uint8_t array1[160] = { 1,2,3,... };   // last byte before secret
uint8_t array2[256 * 512];
#define CACHE_HIT_THRESHOLD (80)       // cycles

void victim_function(size_t x) {
  if (x < array1_size) {
    temp &= array2[array1[x] * 512];
  }
}
```

Goal: read the byte at `&secret[k]`, reached by setting `malicious_x = (size_t)(secret - array1)`.

**Step 1 — prep.** Flush every candidate cache line of `array2` (`_mm_clflush(&array2[i*512])` for all 256 `i`), so none of them starts "warm" by accident.

**Step 2 — train-then-attack, 30 calls per round.** For `j = 29` down to `0`:
- Flush `array1_size` itself (`clflush`) before every call, widening the window during which the real bounds check is still "in flight" and the branch predictor's guess is all the CPU has to go on.
- Pick `x`: branchless bit-twiddling sets `x = malicious_x` when `j % 6 == 0`, else `x = training_x` (a legal in-bounds index). That's **25 training calls, 5 attack calls** per round of 30 — deliberately avoiding an `if` here too, so the branch predictor doesn't pick up a tell from *this* decision.
- Call `victim_function(x)`.

On each of the 5 "attack" calls, the predictor — freshly trained 5-to-1 toward "in bounds" — speculates past the not-yet-resolved check, computes `array1[malicious_x]` (the real secret byte, say `81`), and speculatively executes `array2[81 * 512]`, pulling that one line into cache. Microseconds later the real check resolves false and the CPU squashes the speculative work architecturally — but `array2[81*512]`'s cache line is now warm.

**Step 3 — probe (Flush+Reload shape).** Read all 256 possible `array2[i*512]` with `rdtscp`-timed loads, in a shuffled order `mix_i = (i*167 + 13) & 255` (defeats a hardware stride prefetcher from "helpfully" warming neighboring lines and corrupting the signal). Any `time2 <= 80` cycles counts as a hit; `results[mix_i]++`.

**Step 4 — vote.** Repeat the whole round up to **999 times**. Find the best (`j`) and runner-up (`k`) scoring indices. Accept the guess when `results[j] >= 2*results[k] + 5` (or the 2-vs-0 edge case) — a simple confidence margin, not a fixed round count, so clean signals finish in far fewer than 999 rounds.

Result for this one byte: the index `j` that won is the secret byte's value. Repeat per byte to read out contiguous memory.

```
┌────────────┐ mistrain ┌───────────────────┐  speculate   ┌──────────────┐
│ 25 legal x │ ───────▶ │ branch predictor   │ ───────────▶ │ array1[x]=81 │
└────────────┘          │ says "in bounds"   │              │ (OOB secret) │
      +                 └───────────────────┘              └──────┬───────┘
┌────────────┐                                                     │
│ 5 malicious│                                                     ▼
│     x      │                                           array2[81*512] cached
└────────────┘                                                     │
                       real check resolves false                   │
                       architectural state rolled back              │
                                                                     ▼
                                              probe all 256 array2[i*512]
                                              with rdtscp; i=81 is fast
```

A second worked example from the same disclosure, Project Zero's PoC, nests two bounds checks and bounces the length value's cache line to another core to widen the speculation window further — a different trigger, same leak shape. ([Project Zero](https://projectzero.google/2018/01/reading-privileged-memory-with-side.html))

## 6. The math

**Why 256-entry probing, not a direct read.** The attacker can't read `array2[secret]` directly — that memory access never architecturally completes. Instead the *index* into a 256-wide array is forced to equal the secret byte, so the only thing left to measure is *which of 256 possible cache lines is warm*. This converts an unreadable byte into a 1-of-256 discrete signal measurable with coarse timers. The `*512` stride (or `*256` in Listing 1) exists so each candidate index lands on a distinct cache line (64B lines; 512B stride comfortably avoids any false sharing from hardware prefetch window overlap) — → *in plain terms: space the targets out far enough that reading one line never accidentally warms its neighbor.*

**Confidence margin, `results[j] >= 2*results[k] + 5`.** With noise (OS scheduling jitter, other cores' cache traffic, DVFS), a single round's "fast" measurement isn't reliable — a false hit can land on the wrong index by chance. Treat each of the 999 rounds as a noisy vote; a value is accepted once its vote count is more than double the nearest rival's plus a small margin, which is a simple two-sample separation test rather than a fixed statistical model — → *in plain terms: don't trust a single timing; trust a landslide.*

**Mistrain ratio, 5:1.** Branch predictors use saturating counters (commonly 2-bit) that need a handful of consistent outcomes to flip state and a handful of *inconsistent* ones to flip back; 5 "taken" (in-bounds) trainings per 1 "not taken" (speculative) attack keeps the counter saturated toward "predict taken" even though 1-in-6 calls disagrees — → *in plain terms: the predictor has short memory and a bias toward its most recent consistent pattern, so you only need to out-vote the outlier, not eliminate it.*

**Leak rate.** ~10 KB/s empirically (paper, i7 Surface Pro 3) — bounded by cache-probe time (256 timed reads) × rounds-to-confidence (up to 999) per byte, serialized per byte. No closed-form "bits per cycle" is given in the paper; it's an empirically measured end-to-end rate, not a derived bound.

## 7. Why it works

**Core insight**: speculative execution's rollback is *architectural*-only by design — registers, flags, memory are restored — but caches, TLBs, and branch-predictor tables were never part of that contract, because nobody designed them to be. Any instruction that executes on a mispredicted path and touches memory leaves a trace in *microarchitectural* state that survives the squash, and that trace is readable by anyone who can measure timing.

**Ablation — remove each piece:**
| Remove | What breaks |
|---|---|
| Branch mistraining | CPU predicts correctly most of the time; no reliable speculative window on attacker's chosen input |
| Flushing `array1_size` before the check | Check resolves from cache almost instantly; too narrow a speculation window to do the OOB read + second load |
| The second array (`array2`) indexed by the secret | No way to turn an unreadable register value into an observable cache-line signal |
| Flush+Reload (cache timing) | No channel to read back which line is warm |
| Shuffled probe order | Hardware prefetcher corrupts adjacent-line timings, inflating false positives |
| Vote-over-999-rounds | Single noisy sample is unreliable; accuracy collapses |

## 8. Design knobs & alternatives

- **Probe technique**: Flush+Reload (used here, needs a shared, flushable cache and a `clflush`-equivalent) vs Prime+Probe (works without `clflush`, needed on platforms that restrict it, noisier, needs eviction-set construction).
- **Stride size** (256 vs 512 in the paper's two listings, undocumented why both appear — plausibly just to avoid collisions with other nearby arrays in each demo): bigger strides reduce false sharing/prefetch bleed-through at the cost of more memory touched per probe.
- **Timer resolution**: `rdtscp` gives cycle-accurate timing; browsers deliberately coarsen `performance.now()` (5µs → 100µs in Chrome, plus jitter) as a mitigation — reducing but, per the 2018 Aleph bypass, not eliminating the channel (amplification via repeated sampling recovers signal at ~1 bit/s even through coarsened timers).
- **Mitigation alternatives and why the field didn't converge on one**: index masking (`array_index_nospec`) is cheap but only closes *known* gadget shapes you find and annotate; LFENCE-everywhere is complete-ish but 2–3× slower on real workloads (V8 Octane measurement) or up to 10× in adversarial microbenchmarks; Speculative Load Hardening is a middle ground (masks loaded values instead of halting the pipeline) at roughly half the LFENCE cost on Google's own Haswell numbers (SLH −36.4% vs LFENCE −74.8% on a microbenchmark; −29% vs −62% on a server QPS benchmark — i.e., SLH keeps ~1.8–2.5× more throughput than full fencing); targeted/selective hardening (only fence flagged branches, per static analysis) wins further but depends on the analysis finding every real gadget.

## 9. Where it breaks

- **Mitigations are provably partial, by the mitigators' own admission.** The Linux kernel's own docs say manually annotated `array_index_nospec` sites "may not cover all attack vectors." MSVC's `/Qspectre` docs give no full-coverage guarantee. LLVM's SLH explicitly skips constant-stack-offset loads as an optimization, leaving some loads unmasked.
- **Browser timer mitigations are defeated by amplification.** Chrome/Firefox/Safari's coarsened/jittered timers (2018) were shown bypassed by Aleph Security within months, recovering ~1 bit/s by repeating the measurement many times and statistically filtering jitter — timer coarsening raises the cost, it doesn't close the channel.
- **The "LFENCE is enough" misconception.** LFENCE is serializing and does stop speculation past it, but (a) it's expensive everywhere it's placed, so teams place it conservatively/incompletely, and (b) SLH's own correctness argument depends on CPUs *not* speculating on flags or certain register values — an assumption Intel's architecture manual does not formally guarantee (Silberstein et al., 2018).
- **"A microcode patch fixed Spectre" is false for v1.** Microcode/firmware updates targeted Meltdown and Spectre v2 (branch target injection, IBRS/IBPB); v1 (PHT) has stayed a software-mitigation-only problem on every mainstream CPU vendor's public guidance found in this research.
- **Shared-cache side channels extend past this one gadget**: speculative store bypass (CVE-2018-3639, a sibling variant), and — unrelated to Spectre mechanically but same cache-timing *family* — 2025 research found 7 of several audited LLM API providers (including OpenAI) shared prompt caches across users, letting an attacker infer another user's prompt via time-to-first-token (Gu et al., ICML 2025) — a reminder that "measure a shared cache's timing" as an attack shape outlives any single CPU bug.
- **Little is publicly characterized about v1 on some newer ARM client cores** relative to Intel/AMD, per research literature gaps found here — flagged as an open area, not a settled "ARM is immune" claim.

## 10. In the wild

- **Linux kernel**: case-by-case `array_index_nospec()` / `array_index_mask_nospec()` at syscall boundaries found by manual audit and later static/dynamic scanning; `barrier_nospec()` (an LFENCE) specifically on `copy_from_user` paths and the `swapgs` entry sequence (`FENCE_SWAPGS_KERNEL_ENTRY`/`USER_ENTRY`), both narrowly targeted rather than blanket.
- **V8/Chrome**: "poisoning" — a per-branch poison register that becomes zero on a mispredicted path and is multiplied into every subsequent load's result, applied not just to user bounds checks but to V8's own bytecode dispatch and function-entry type checks; measured under 20% cost on Octane, versus the 2–3× cost of fencing every branch that V8 rejected. WebAssembly gets index masking only on 32-bit (memories padded to a power-of-two size, top bits of the index masked); 64-bit Wasm relies on guard pages instead. Site Isolation (separate OS process per site, default since Chrome 67, 2018) is treated as the backstop that matters more than in-process mitigations, because it removes the shared address space entirely.
- **LLVM SLH**: ships as an opt-in flag, not default, reflecting that teams choose it only for genuinely sensitive code paths given its cost; needs retpolines for indirect calls/returns to be effective, and needs BMI2 for efficient x86 codegen of the masking sequence.
- **Compiler-generated mitigations miss near-variant gadgets**: Silberstein et al. (2018) reported Microsoft's compiler-inserted LFENCEs missing some gadget shapes close to but not identical to the canonical pattern — mitigations trained/tuned on one gadget shape generalize imperfectly.

## 11. Frontier (what's new, 2024–2026)

Spectre v1 detection and exploitation are settled science; the active work has moved to (a) **provable, targeted** hardening that doesn't pay the fence-everywhere tax, and (b) **finding gadgets nobody annotated**, including in silicon nobody can see inside.

1. **LightSLH — "Place Protections at the Right Place"** (Zhu, Huang, Xiong; USENIX Security 2025; [arXiv:2408.16220](https://arxiv.org/abs/2408.16220)). A fixpoint static analysis finds exactly which load sites are exploitable Spectre-v1 gadgets and hardens only those, rather than every branch or every load. On OpenSSL, libsodium, NaCl, and PQClean it achieved **0% measured overhead in half the evaluated cases** while finding **two previously unknown Spectre-v1 issues** the existing tools had missed — showing the gadget space in real crypto libraries wasn't even fully mapped as of 2024.
2. **Speculation-Passing Style (SPS)** (Arranz-Olmos, Barthe, Blatter, Xie, Zhang; [arXiv:2510.11573](https://arxiv.org/abs/2510.11573), 2025–26). A program transform that reduces proving *speculative* constant-time security to proving *ordinary* constant-time security on the transformed program — formally proven sound and complete (speculative-CT holds iff the SPS-transformed program is standard-CT). This turns "is this crypto code Spectre-v1-safe" into a problem existing constant-time verifiers (EasyCrypt, BINSEC, ctgrind) can already answer, rather than needing bespoke speculative-security tooling.
3. **dfence** (Davoli, Bognar, Daniel, Grégoire, Piessens, Rezk; [arXiv:2608.06124](https://arxiv.org/abs/2608.06124), 2026). Proposes a new CPU instruction generalizing Speculative Load Hardening to cover both PHT (v1) and speculative store bypass in one mechanism, with developer-annotated sensitive registers checked by a type system; implemented in the Proteus research CPU at **under 1% average overhead** — the first result in this research run claiming SLH-class protection at near-zero cost, though it requires new hardware.
4. **SpecRL** (Lai, Xiong, Suh, Tiwari, Luo; [arXiv:2502.16756](https://arxiv.org/abs/2502.16756), 2025). Uses reinforcement learning to search *black-box, post-silicon* microprocessors for speculative-execution leaks, rather than requiring source/RTL access — relevant because most gadget-finding tools assume you can see the code or the chip design, which an end user or auditor usually can't.

Seen in search results but not independently fetched/verified in this run (flagged, not cited as fact): *Phantom Trails* (pre-silicon transient-leak discovery, claimed USENIX Security 2025), *SpecASan* (ARM-MTE-style hardware tagging defense, claimed ISCA 2025), a claimed USENIX Security 2026 paper on Spectre against RISC-V silicon, *Teapot* (binary gadget scanning, claimed CGO 2025), *GadgetMeter* (claimed NDSS 2025). These line up with the two live threads above (targeted hardening, better gadget discovery) but should be checked at the source before being treated as established.

## 11b. Open problems

- **No formal, agreed definition of "speculative-execution security."** Multiple competing security notions exist (speculative constant-time, non-interference variants); SPS (above) only closes the gap for one such notion against one gadget class.
- **No tool proves a large real binary is gadget-free at scale.** Static analyses (LightSLH, Spectector-family tools) find *known* shapes; none claims completeness against unknown or compiler-introduced gadget shapes.
- **Whether PHT can be fixed in hardware at all remains unresolved in public documentation.** Every vendor statement found in this research treats v1 as a software-only mitigation target, unlike v2 (branch target injection) and Meltdown, which got microcode/hardware responses — it's unclear whether that's a fundamental limit of out-of-order execution or simply that nobody has shipped a hardware fix yet. dfence (above) is a hardware proposal, not a shipped part.
- **Coverage on non-Intel/AMD cores is thin in the literature.** This research found comparatively little systematic characterization of Spectre-v1 behavior on modern ARM client cores relative to x86 — an open measurement gap, not evidence of immunity.
- **No public head-to-head benchmark of the newest targeted-hardening tools (LightSLH, dfence, SPS) against each other on the same codebase** — each paper reports its own numbers against its own baseline.

## 12. Lineage

**Branch prediction & speculative execution (1990s out-of-order CPUs)** → **Spectre v1/v2 + Meltdown disclosed Jan 2018** (Kocher et al.; Lipp et al.) → **software mitigations**: kernel `array_index_nospec`, LLVM SLH, V8 poisoning/Site Isolation, MSVC `/Qspectre` (2018) → **sibling variants**: speculative store bypass / v1.1 (CVE-2018-3639, CVE-2018-3693) → **better verification**: Spectector and other speculative-CT checkers (2019+), "Ultimate SLH" (USENIX Security 2023) arguing existing SLH variants weren't fully protective in practice → **targeted/provable hardening and black-box gadget discovery** (LightSLH, SPS, dfence, SpecRL — 2025–26, above).

## 13. Hands-on (≤30 min)

Run `spectre_sim.py` (in this folder) — a simulation of the paper's mistraining loop logic (saturating-counter predictor model + the vote-over-rounds confidence check) that shows why the 5:1 training ratio and the `2×+5` margin were chosen, by sweeping both parameters and reporting recovery accuracy, without needing real `clflush`/`rdtscp` hardware access. For the real hardware experiment (needs a Spectre-vulnerable x86-64 Linux box), compile and run the paper's reference PoC from the official disclosure site, [spectreattack.com](https://spectreattack.com/), and watch `readMemoryByte` recover bytes of its own hardcoded secret string.

## 14. Question ladder

**Mechanism**
1. What exactly happens to the CPU's registers and memory when the real bounds check resolves "false" after speculative execution already ran?
2. Why does the attack flush `array1_size` before every training/attack call, specifically?
3. Walk through why the probe reads `array2[i*stride]` in shuffled order instead of `i = 0..255`.
4. What does "results[j] >= 2*results[k] + 5" actually test, in plain statistical terms?
5. Why is the leak serialized per-byte rather than parallelizable across bytes within one victim call?

**Why**
6. Why can't the attacker just read `array1[1000]` directly and skip the second array entirely?
7. Why does the mistraining loop use 5 "good" calls per 1 "bad" call instead of 1:1 or 10:1?
8. Why do browsers coarsen `performance.now()` instead of removing high-resolution timing entirely?
9. Why did V8 choose "poisoning" over inserting a barrier on every branch?

**Counterfactual**
10. What happens to the attack if the CPU never caches anything speculatively loaded (i.e., speculative loads bypass the cache hierarchy)?
11. What happens if `array1_size` were a compile-time constant instead of a runtime value?
12. If the attacker could not control the training inputs' timing (only their values), would mistraining still work?
13. What would change if the second array's stride were 64 bytes (one cache line) instead of 512?

**Adversarial**
14. How would you construct a Spectre v1 gadget in a language with no raw pointers (e.g., pure JavaScript)?
15. Given LLVM SLH masks loaded values via an `or`-with-predicate, how might an attacker find a load SLH forgot to mask?
16. How did the 2018 Aleph Security bypass defeat SharedArrayBuffer removal and timer coarsening specifically?
17. Why does targeted/selective hardening (LightSLH-style) trade completeness for speed, and what's the attacker's best move against it?

**Connection**
18. How does Spectre v1's cache-line leak relate to the 2025 finding of shared LLM-API prompt caches leaking other users' prompts via timing?
19. How does speculative store bypass (the "v1.1" sibling) differ mechanically from the bounds-check-bypass gadget here?
20. How does Flush+Reload here relate to Prime+Probe, and when would an attacker need the latter instead?

**Open**
21. Is there a hardware fix for Spectre-PHT that doesn't just move the cost from software to silicon, or is complete coverage fundamentally a software-era, continually-patched problem?
22. Can a static analysis ever be *complete* against all gadget shapes, including ones compilers introduce by accident during optimization?

<details><summary>Answers</summary>

1. Every architectural register, memory write, and flag that the speculative path touched is rolled back exactly as if the mispredicted branch had never been taken — the CPU's own ISA-visible state ends up bit-identical to the "correct" execution. What is *not* rolled back is anything in caches, TLBs, or the branch predictor's own tables, because those were never defined as part of the architectural contract.
2. Flushing `array1_size` forces its load to go to RAM (hundreds of cycles) instead of resolving from cache in a handful of cycles. That widens the window during which the branch predictor's guess is the only thing driving execution, giving the CPU enough idle time to speculatively execute `array1[x]` and `array2[...]` before the real check comes back.
3. A hardware stride prefetcher, seeing sequential accesses to `array2[0*512], array2[1*512], ...`, will start speculatively loading *ahead* of the requested address, warming lines the attack never touched and producing false "cache hit" timings. Shuffling the probe order (`mix_i = (i*167+13)&255`) breaks the sequential pattern so the prefetcher can't anticipate it.
4. It's a margin-of-victory test over noisy repeated samples: rather than trusting any single round's timing (which can be wrong due to scheduling jitter, other core activity, etc.), it waits until one candidate's vote count is more than double its nearest rival's (plus a small constant to handle low counts), treating that as strong enough evidence to stop.
5. Each byte needs its own full mistraining + 999-round probing cycle because the "secret" is only defined relative to one offset into `array1`; there's no way to get two bytes' worth of signal out of one victim-function call sequence, since each call's speculative detour reads exactly one `array1[x]` and touches exactly one line of `array2`.
6. The architectural read of `array1[1000]` never "completes" from the program's perspective — the moment the real bounds check resolves false, every result of that speculative read is discarded and unreadable through any normal means (it's not in a register the program can later access). The second array exists purely to convert that unreadable value into an observable side effect (a cache state change) before the rollback happens.
7. Branch predictors use short-memory saturating counters; a counter needs a consistent run of outcomes to "lock in" a prediction and a comparably short run of opposite outcomes to flip it back. 5:1 keeps the counter saturated toward "predict taken" across the attack calls without needing a perfect, suspicious-looking 100% training rate, and empirically was sufficient for the paper's demonstrated reliability.
8. Removing high-resolution timers entirely would break legitimate uses (animation, profiling, video sync) that web pages rely on; coarsening is a compromise that raises the attacker's required sample count (cost) without breaking those use cases — though as the 2018 bypass showed, raising the cost isn't the same as closing the channel.
9. Barriers on every branch cost 2–3× on V8's own Octane benchmark; poisoning (masking loaded values with a per-branch predicate) achieved under 20% cost by only ever changing the *value* a misspeculated load returns (forcing it to a safe/fixed value) rather than halting the pipeline to wait for the branch to resolve.
10. The attack's cache-timing channel disappears entirely — there is no warm/cold distinction to measure, because speculative loads never leave microarchitectural evidence in the cache. This is roughly the shape of some proposed hardware defenses (don't let speculative loads affect cache state until the branch is confirmed) — not deployed as of this research, but exactly where "fix it in hardware" proposals like dfence point.
11. If `array1_size` were a compile-time constant, the compiler can and typically does prove the bounds check always succeeds (or statically bound `x`), eliminating the runtime branch the attack mistrains — gadgets require a *runtime*-resolved check.
12. Yes — mistraining depends only on the *values* passed to the branch across repeated calls, not on fine-grained timing of those calls; the timing precision is needed for the later cache-probe step, not the training step.
13. A 64-byte stride would put every one of the 256 candidate indices on a *different* cache line still (since 64 bytes is exactly the line size), but with far less spatial margin — any prefetcher or alignment quirk touching line N+1 becomes much more likely to accidentally warm line N's neighbor, raising the false-positive rate; 512B gives generous separation at the cost of touching more total memory (128 KB array2 footprint vs 16 KB).
14. By shaping an object-property or typed-array access so the bounds check and the dependent load are both present in the JIT-compiled code — e.g., `if (i < arr.length) leak(arr2[arr[i]])` in JS, where the JIT emits a runtime length check on `arr` before the typed-array read, exactly mirroring the C gadget shape once JIT-compiled to machine code.
15. By auditing which loads SLH's static analysis classifies as "safe to skip" (e.g., constant-stack-offset loads, which LLVM's SLH explicitly excludes as an optimization) and checking whether an attacker can make a secret-dependent value reach one of those excluded load sites.
16. By repeating the timing measurement many times and statistically filtering the added jitter/coarsening rather than relying on a single precise sample — turning a "can't measure precisely" mitigation into "need more samples," recovering a reliable signal at roughly 1 bit/s even against coarsened timers and without SharedArrayBuffer.
17. Targeted hardening only protects load sites its static analysis actually flags as reachable gadgets; an attacker's best move is finding a load the analysis's model doesn't cover — e.g., an indirect call, a dynamically computed address, or a code path the analysis's call-graph/alias analysis under-approximates.
18. Both are the same underlying attack *shape* — timing a shared cache/resource to infer whether someone else recently touched a specific piece of data — applied at different layers: Spectre v1 times CPU cache lines to infer a byte from speculative execution; the LLM-API case times a server-side KV-cache hit to infer whether another user recently sent a specific prompt. Neither needs a CPU vulnerability — just a shared, timing-observable resource.
19. Speculative store bypass (CVE-2018-3639, sometimes called "Spectre v4") mistrains the memory disambiguator rather than a branch predictor — it exploits a CPU's guess that a load doesn't depend on an earlier, not-yet-completed store to the same address, letting the load speculatively return a stale value instead of the value about to be stored; the leak mechanism (cache timing afterward) is similar in spirit but the mispredicted structure being exploited is different.
20. Flush+Reload requires the attacker to be able to evict a specific line from a cache shared with the victim (`clflush` or equivalent) and then time a reload of that exact line; Prime+Probe instead fills an entire cache *set* with attacker-controlled data ("priming") and times how long it takes to re-read that same data afterward, inferring eviction by the victim without needing a flush instruction — useful on platforms (and cache levels) where `clflush`-equivalent instructions are restricted or unavailable to the attacker.
21. Open — this research found every current vendor and compiler response treating v1 as a software-mitigated-only problem, and a 2026 hardware proposal (dfence) still in research-CPU form, not shipped silicon. Whether a complete, low-cost hardware fix is achievable, or whether per-gadget software annotation is the only path, is unresolved in the sources reviewed here.
22. Open — the targeted-hardening line of work (LightSLH, SPS) narrows this by being *sound and complete relative to a defined gadget model*, but that completeness is bounded by the model's assumptions (known instruction semantics, no undocumented microarchitectural speculation behavior); none of the sources in this research claim completeness against gadget shapes introduced by future, undocumented CPU optimizations.

</details>

## 15. Go deeper next

1. **Spectre v2 (branch target injection)** — mistraining the *indirect* branch predictor (BTB) instead of a conditional-branch predictor, the variant that did get hardware mitigations (IBRS/IBPB).
2. **Meltdown** — the sibling 2018 disclosure that breaks the privilege check itself (not just the branch predictor), letting speculative execution read kernel memory directly; got a different mitigation path (KPTI) than Spectre.
3. **Speculative constant-time verification tooling** (Spectector-family, SPS above) — the formal-methods line of work trying to make "is this code Spectre-safe" a decidable, checkable property instead of a case-by-case audit.

## Sources

**Papers**
- Kocher et al., "Spectre Attacks: Exploiting Speculative Execution," [arXiv:1801.01203](https://arxiv.org/abs/1801.01203) (IEEE S&P 2019) — verified against the PDF directly.
- Zhu, Huang, Xiong, "Place Protections at the Right Place," USENIX Security 2025, [arXiv:2408.16220](https://arxiv.org/abs/2408.16220)
- Arranz-Olmos, Barthe, Blatter, Xie, Zhang, "(Dis)Proving Spectre Security with Speculation-Passing Style," [arXiv:2510.11573](https://arxiv.org/abs/2510.11573)
- Davoli, Bognar, Daniel, Grégoire, Piessens, Rezk, "dfence," [arXiv:2608.06124](https://arxiv.org/abs/2608.06124)
- Lai, Xiong, Suh, Tiwari, Luo, "SpecRL," [arXiv:2502.16756](https://arxiv.org/abs/2502.16756)
- Zhang, Barthe, Chuengsatiansup, Schwabe, Yarom, "Ultimate SLH," USENIX Security 2023, [eprint.iacr.org/2022/715](https://eprint.iacr.org/2022/715)

**Code / docs**
- Linux kernel, [Spectre hardware vulnerability admin guide](https://docs.kernel.org/admin-guide/hw-vuln/spectre.html)
- LLVM, [Speculative Load Hardening docs](https://llvm.org/docs/SpeculativeLoadHardening.html)
- Microsoft, [`/Qspectre` MSVC docs](https://learn.microsoft.com/en-us/cpp/build/reference/qspectre)
- V8 team, ["Mitigating side-channel attacks," v8.dev/blog/spectre](https://v8.dev/blog/spectre)
- Chromium, [Site Isolation / SSCA security page](https://www.chromium.org/Home/chromium-security/ssca/)
- [spectreattack.com](https://spectreattack.com/) — original disclosure site, reference PoC

**Articles**
- Project Zero, ["Reading privileged memory with a side-channel"](https://projectzero.google/2018/01/reading-privileged-memory-with-side.html)
- Aleph Security / BleepingComputer, ["Some Spectre in-browser mitigations can be defeated"](https://www.bleepingcomputer.com/news/security/some-spectre-in-browser-mitigations-can-be-defeated) (2018)
- Silberstein, Oleksenko, Fetzer, SIGARCH blog, ["Speculating about speculation"](https://www.sigarch.org/speculating-about-speculation-on-the-lack-of-security-guarantees-of-spectre-v1-mitigations/)

**Claims I could not fully verify** (flagged inline above): Intel/Arm advisory page details (fetches redirected/empty — check [Intel's Bounds Check Bypass page](https://www.intel.com/content/www/us/en/developer/articles/technical/software-security-guidance/advisory-guidance/bounds-check-bypass.html) and Arm's security-updates page directly); the LWN claim of "1,379 missed gadgets" (forum opinion, not a primary measurement); several 2025 frontier papers seen only in search snippets (Phantom Trails, SpecASan, RISC-V Spectre, Teapot, GadgetMeter) — not independently fetched in this run.
