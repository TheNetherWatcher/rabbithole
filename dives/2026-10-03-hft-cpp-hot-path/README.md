# The tick-to-trade hot path: how HFT firms engineer C++ for nanoseconds

## 0. Topic card

`Hardware/architecture × compilers/runtimes · Tick-to-trade hot path in C++: kernel bypass, cache warming, branch/allocation-free code, tail-latency measurement · hard · 2026-10-03`

---

## 0b. Plain English first

### Explain it simply

Picture a tiny auction house. Hundreds of times a second, someone near the door shouts a new price ("apples, 100 dollars 25!"). Several professional bidders are in the room. When a price looks like a bargain, the first bidder to raise a paddle gets the deal. Second place gets nothing. It doesn't matter if they're a millionth of a second late.

A high-frequency trading (HFT) firm is one of those bidders. Its "paddle" is a computer program. The race is decided in microseconds (millionths of a second), sometimes nanoseconds (billionths). So the people who write these programs care less about a program being fast on average. They care that it is fast **every single time**, including the rare moment that matters, when it has been sitting idle for a while. Most of the craft is about not letting the computer do anything surprising: no pausing to tidy memory, no asking the operating system for permission, no "forgetting" the routine because it hasn't run for a while.

### Everyday example

The bidder (call them Ana) sits by the door. Each time a price is shouted, Ana:

1. hears it (the network card receives a message),
2. writes it on a whiteboard of current best prices (the "order book"),
3. checks a cheat sheet: "if apples drop below 100.30, buy" (the strategy),
4. checks the rules: "never buy more than 1,000 apples" (the risk check),
5. raises the paddle (sends an order).

Ana has learned some tricks:
- She keeps the cheat sheet in her hand, not in a drawer (data kept in the CPU cache, not in slow memory).
- She never leaves to fetch a new pen mid-auction; pens are laid out beforehand (no memory allocation).
- She doesn't go through the front office to get messages; she stands right at the door (kernel bypass).
- If no good price comes along for a long time, her arm gets stiff. So every few seconds she practises: runs through all five steps and lifts the paddle a centimetre without actually bidding (cache warming with dummy orders).

One day the shout is "apples, 100.25, 500 available!", below her 100.30 trigger. Ana updates the whiteboard, sees the trigger hit, checks 500 ≤ 1,000, and raises the paddle. She wins by a hair, because a rival had to walk back from the coffee machine.

**Now the same thing, technically.**

---

## 1. Bare-minimum context

- **Limit order book.** The exchange's list of resting buy (bid) and sell (ask) orders at each price. Feeds send Add/Modify/Delete messages. [Gross 2024 slides](https://github.com/CppCon/CppCon2024/blob/main/Presentations/When_Nanoseconds_Matter.pdf)
- **Market data over UDP multicast.** Exchanges broadcast binary messages (e.g. Nasdaq ITCH, CME MDP3, which is SBE-encoded). Orders go back over TCP (OUCH, FIX, iLink).
- **CPU memory hierarchy.** L1 ≈ 4 cycles, L2 ≈ 12, L3 ≈ 40–50, DRAM ≈ 60–100 ns. Data moves in 64-byte cache lines. [7-cpu Skylake](https://www.7-cpu.com/cpu/Skylake.html), [Drepper](https://www.akkadia.org/drepper/cpumemory.pdf)
- **Branch prediction.** The CPU guesses which way an `if` goes and runs ahead. A wrong guess costs ≈16–20 cycles on Skylake. [7-cpu](https://www.7-cpu.com/cpu/Skylake.html)
- **Kernel vs user space.** A normal socket `recv()` crosses into the kernel. Kernel-bypass NICs let user code read the NIC's receive ring directly. [Kernel timestamping doc](https://www.kernel.org/doc/html/latest/networking/timestamping.html)
- **Percentiles.** p99 = the latency that 99% of events beat. HFT cares about p99.9 and max during bursts, not the mean. [Gil Tene](https://qconsf.com/sf2012/dl/qcon-sanfran-2012/slides/GilTene_HowNotToMeasureLatency.pdf)

---

## 1b. Real-world context

### What it is, in one paragraph

"Low-latency C++" in HFT is a body of practice for building the **tick-to-trade** path. That path is the code that runs from the moment the last bit of a market-data packet arrives on the wire to the moment the first bit of the resulting order leaves. The goal is to make it short (single-digit microseconds in software, tens of nanoseconds in FPGAs) and, above all, **predictable**. The practice spans hardware (NIC choice, BIOS settings), the OS (core isolation, no interrupts), the C++ itself (no allocation, no virtual calls or branches on the hot path, cache-friendly data), and measurement (hardware timestamps at the wire, tail percentiles).

### Why it exists

- **The race is tiny and winner-take-all.** On the London Stock Exchange, latency-arbitrage "races" happen about once a minute per FTSE-100 symbol. The **modal winning margin is 5–10 µs**. Races cover ≈20% of volume, and the top 6 firms take >80% of race wins and losses. About $5B a year is at stake in global equities. [Aquilina, Budish, O'Neill, QJE 2022](https://www.nber.org/papers/w29011); [FCA OP50](https://www.fca.org.uk/publications/occasional-papers/occasional-paper-no-50-quantifying-high-frequency-trading-arms-race-new-methodology)
- **General-purpose stacks are tuned for throughput and fairness, not latency.** Carl Cook (Optiver): "Jitter is unacceptable – it means bad trades". The hot path runs only ≈0.01% of the time, so by default it is always cold. [Cook 2017 slides](https://github.com/CppCon/CppCon2017/blob/master/Presentations/When%20a%20Microsecond%20Is%20an%20Eternity/When%20a%20Microsecond%20Is%20an%20Eternity%20-%20Carl%20Cook%20-%20CppCon%202017.pdf)
- **Falling behind can also drop data.** Feeds burst to hundreds of thousands of updates a second. If you read too slowly, the NIC runs out of buffers and drops packets, which is an outage. [Gross 2024](https://github.com/CppCon/CppCon2024/blob/main/Presentations/When_Nanoseconds_Matter.pdf)
- **Before:** 2000s-era systems used kernel sockets, std containers and logging inline. A kernel TCP path adds ≈3.9 µs over raw ef_vi per Solarflare's own (vendor, non-STAC) slide. [STAC Summit 2017](https://docs.stacresearch.com/system/files/resource/files/STAC-Summit-5-Jun-2017-Solarflare.pdf)

### Where it's used

| System / firm | Role |
|---|---|
| **Optiver** | Public C++ talks (Cook 2017, Gross 2022/2024). Templates over virtuals, reverse-vector order books, the FastQueue shared-memory broadcast queue. |
| **IMC** | C++ "sits directly in the latency-critical loop… integrate FPGA-based systems". This is the hybrid CPU+FPGA model. [IMC job page](https://www.imc.com/us/careers/jobs/4634204101) |
| **Hudson River Trading** | C++ at the center of live trading. Its HRTbeat blog covers huge pages and devirtualisation. [HRT huge pages](https://www.hudsonrivertrading.com/hrtbeat/low-latency-optimization-part-1/) |
| **AMD Solarflare NICs (Onload, TCPDirect, ef_vi)** | The de facto kernel-bypass stack in colocated trading. [Xilinx-CNS/onload](https://github.com/Xilinx-CNS/onload) |
| **Cisco Nexus SmartNIC (ex-Exablaze ExaNIC)** | Raw-frame API, 780 ns median app→network→app, 6.2 ns hardware timestamps. [cisco/exanic-software](https://github.com/cisco/exanic-software) |
| **Real Logic SBE / Aeron / Agrona** | Zero-allocation flyweight codecs; reliable UDP and IPC messaging. CME MDP3 uses SBE. [SBE](https://github.com/real-logic/simple-binary-encoding) |
| **Quill / fmtlog / NanoLog** | Hot-path logging at ≈6–20 ns: binary-encode the arguments, format later on another core. [Quill](https://github.com/odygrd/quill), [NanoLog ATC'18](https://www.usenix.org/conference/atc18/presentation/yang-stephen) |
| **Counter-examples** | Jane Street writes its lowest-latency software in **OCaml** and its FPGAs in Hardcaml ([JS](https://www.janestreet.com/performance-engineering/)). LMAX and Chronicle use garbage-free **Java**. |

### How it's used (what a practitioner touches)

```bash
# Boot: isolate cores 2-7 from the scheduler, timer tick and RCU callbacks
GRUB_CMDLINE_LINUX="isolcpus=2-7 nohz_full=2-7 rcu_nocbs=2-7 nosmt transparent_hugepage=never intel_idle.max_cstate=0 processor.max_cstate=1"
pgrep -P 2 | xargs -i taskset -p -c 0 {}      # kernel threads to core 0 (Rigtorp guide)
tuned-adm profile network-latency

# Zero-code-change bypass first: LD_PRELOAD Onload with busy-polling
onload --profile=latency taskset -c 3 ./algo_trader
```

```cpp
// Hot thread skeleton: pinned, busy-polling, nothing allocates, one branch for "send or not".
template <class Strategy, class Sender>              // config picked once at startup → no virtuals inside
struct Engine {
    Strategy strat; Sender tx; Book book; Risk risk;
    void run() {
        pin_this_thread(3);
        mlockall(MCL_CURRENT | MCL_FUTURE);
        for (;;) {                                    // never sleeps, never yields
            if (auto* pkt = rx.poll()) [[likely]] on_packet(pkt);
            else if (warm_timer.due()) on_packet(&synthetic_tick, /*dry_run=*/true);   // keep caches hot
        }
    }
    void on_packet(const Packet* p, bool dry_run = false) {
        auto& m = *std::start_lifetime_as<AddOrder>(p->payload);   // C++23, no UB type-punning
        book.apply(m);
        Order o = strat.decide(book);                 // writes into a preallocated Order
        uint64_t err = risk.check(o);                 // all checks OR'ed into one flag word
        if (!err && !dry_run) [[likely]] tx.send(o);
        else if (err) [[unlikely]] [&]() __attribute__((noinline, cold)) { handle(err); }();
    }
};
```

Typical values:
- 1 hot thread per isolated physical core.
- `EF_POLL_USEC=100000` in the Onload latency profile.
- Warm-up dummy path every few µs to ms. Firms don't publish the interval.
- Integer prices in ticks.
- Preallocated pools sized for the worst day.

### When to use it / when NOT to

**Use** when:
- you're colocated,
- the competition is decided in µs,
- one hot thread per core is affordable,
- you can measure at the wire.

**Don't** when:
- you're in a cloud VM (noisy neighbours dominate),
- latency budgets are ≥ 50 µs (kernel + `busy_poll` is fine),
- the logic is simple enough for an FPGA to fire (C++ loses to 14 ns hardware),
- developer velocity matters more (Java, OCaml).

**Sign you picked wrong:** your p50 dropped but your *race win rate* didn't move. Your tail or your wire latency is elsewhere.

### Who should care

- Trading-infra and C++ engineers at market makers and prop shops.
- Exchange and matching-engine developers.
- Anyone building µs-SLA systems: ad bidding, telecom user plane, game servers, robotics control loops.
- Performance engineers who need the measurement discipline (coordinated omission, layout noise) even with no trading.

---

## 2. The one-liner, and what it hides

> "HFT C++ is about avoiding allocations and virtual functions and using kernel bypass."

What that hides:
1. **The real enemy is coldness, not slowness.** The hot path runs ≈0.01% of the time, so caches, TLB and branch predictors have forgotten it by the time it fires. Firms *run it constantly on fake data* to keep it warm.
2. **Tails, not means.** A 629× gap in mean latency (Disruptor vs ArrayBlockingQueue) hides a p99.99 gap of 8 µs vs 4.2 ms. Races are lost in the tail.
3. **Simple beats asymptotic.** Linear search beats binary search, and a vector beats `std::map`. That holds because the data is skewed toward the top of the book and memory access dominates.
4. **The machine is part of the program.** Same binary and same hardware give visibly different speed depending on BIOS/OS tuning (Cook slide 11). SMIs, C-state exits (≈90–170 µs) and other processes evicting your L3 are invisible to the C++.
5. **Software is no longer the fastest path.** FPGAs hit 13.9 ns on STAC-T0. Modern C++ sits in the 1–10 µs strategy layer and *parameterises* hardware that fires.

---

## 3. The problem

Concrete constraints a designer faces:

- **Physics floor.** Chicago (CME, Aurora) to New Jersey (Carteret/Secaucus): 1139.5 km geodesic, so the speed-of-light round trip is 7.6 ms.
  - Microwave networks measure 7.7 ms RTT, within 1.5% of c.
  - Market data shows CME→NJ reactions at ≈4.2 ms one-way, versus ≈6.65 ms for the best fiber.
  - [cISP paper (Bhattacherjee et al.)](https://courses.cs.duke.edu/fall21/compsci514/internal/readings/BhattacherjeeAABSTACGLMS22.pdf), [The Register 2013](https://www.theregister.com/2013/02/27/microwave_versus_fibre/)
  - Once everyone is on the same microwave path and in the same colo, what remains is **inside the box**.
- **The box budget.** "A very good minimum time (wire to wire) for a software-based trading system is around 2.5 µs" (Cook 2017). Gross 2024: strategy layer 1–10 µs, ultra-low-latency execution < 1 µs.
- **What eats the budget** if you do nothing:

| Cost | Typical | Source |
|---|---|---|
| Kernel TCP path vs raw ef_vi | +3.9 µs | [Solarflare slide](https://docs.stacresearch.com/system/files/resource/files/STAC-Summit-5-Jun-2017-Solarflare.pdf) |
| PCIe NIC round trip, 128 B packet | ≈1000 ns, of which ≈900 ns is PCIe | [Neugebauer SIGCOMM'18](https://www.cl.cam.ac.uk/teaching/1011/R02/papers/p327-neugebauer.pdf) |
| Context switch (unpinned) | 3–4.5 µs, plus cache-pollution aftermath | [Tsuna](https://blog.tsunanet.net/2010/11/how-long-does-it-take-to-make-context.html) |
| Core C6 exit | ≈90 µs measured, 133–170 µs per the driver table | [intel_idle](https://docs.kernel.org/6.19/admin-guide/pm/intel_idle.html), [Phoronix](https://www.phoronix.com/news/Intel-C6-Ice-Lake-Xeon-Idle) |
| 4-level page walk on TLB miss | ≈3 dependent loads ≈ 210 ns at 70 ns DRAM | [HRT](https://www.hudsonrivertrading.com/hrtbeat/low-latency-optimization-part-1/) |
| DRAM miss | 60–100 ns | 7-cpu, Drepper |
| Branch mispredict | 16–20 cycles ≈ 5 ns | 7-cpu |
| Exception thrown for control flow | ≥ 1.5 µs | Cook slide 22 |
| `std::pow` slow path (glibc 2.17) | 478 µs (!) vs 53 ns | Cook slide 47 |

So one page fault, one C-state exit or one thrown exception costs more than the whole budget. The design problem is **removing variance**, not shaving averages.

---

## 4. Mental model

**A Formula 1 pit stop.** Every tool is laid out in advance, each crew member does one job and never moves, and the car spends its whole race lapping, so tyres and brakes stay at temperature. A stop takes ≈2 s because nobody fetches anything, nobody waits for permission, and nobody has to remember how.

Mapping:
- **Tools laid out** → preallocated pools, no `malloc`.
- **One crew member per job** → one pinned thread per isolated core.
- **Car lapping** → the dummy warm-up path.
- **No radio to race control mid-stop** → no syscalls (kernel bypass).

**Where the analogy breaks:**
1. A pit crew practises the *same* motion. A warm-up path must exercise the *same code and data* as the real decision, but must **not** send. That one difference is a branch that has to be predicted correctly at the real moment.
2. Pit stops are serial and independent. CPU caches are shared: your neighbour's process can evict your L3 lines mid-race (Gross's "you're not alone").
3. In F1 a faster stop always helps. In HFT, shaving 100 ns of software is worthless if the race is decided by an FPGA 2 µs earlier.

---

## 5. The mechanism, traced

One packet, end to end: Ana's story with real data. A Nasdaq-ITCH-like **Add Order: SELL 500 @ 100.25** arrives. Our strategy buys whenever the best ask is ≤ 100.30, so this new offer crosses our trigger.

```
 wire ──► NIC ──DMA──► RX ring (hugepage) ──► [hot core 3: busy-poll]
                                                  │ parse (in place)
                                                  │ book.apply
                                                  │ strategy.decide
                                                  │ risk.check (1 branch)
                                                  ▼
 wire ◄── NIC ◄──doorbell/PIO── TX descriptor ◄── build order (prealloc)
          ▲                                                     │
   switch/tap timestamps both directions  ◄─── capture server ──┘ (offline)
```

**Step 0, before the packet (t = −∞).**
- The process started, `mlockall`'d, and touched every page of its pools and book. There are no first-touch page faults later.
- Hot arenas are on 2 MiB huge pages. ≈2000 TLB entries × 2 MiB ≈ 4 GiB reach, against 8 MiB with 4 KiB pages ([HRT](https://www.hudsonrivertrading.com/hrtbeat/low-latency-optimization-part-1/)).
- Thread pinned to isolated core 3; no other runnable task, so `nohz_full` stops the tick ([kernel no_hz](https://docs.kernel.org/timers/no_hz.html)).
- Every few µs–ms a **synthetic tick** runs the full path with `dry_run=true` (Cook slides 37–38). The book, strategy params, risk limits and order template stay in L1/L2, and the branch predictor stays trained.

**Step 1, NIC receive (≈ hundreds of ns, hardware).**
- The frame arrives: Ethernet + IP + UDP + MoldUDP64 header + ITCH message. The ITCH Add Order is a fixed-layout big-endian record with type `'A'`, stock locate, tracking, timestamp(6B), order ref(8B), side `'S'`, shares 500, stock "ABCD    ", price 1002500 (4 implied decimals).
- The NIC DMAs it into a pre-posted buffer in the RX ring and writes an event into the event queue. With ef_vi there is no interrupt and no kernel involvement.
- The NIC hardware-timestamps the frame (`SOF_TIMESTAMPING_RX_HARDWARE`).

**Step 2, notice (≈ tens of ns).** The hot loop spins on `ef_eventq_poll(&vi, evs, BATCH)`. It sees `EF_EVENT_TYPE_RX` and gets the buffer id and length. No syscall, no wake-up, no context switch.

```c
for(;;){ int n = ef_eventq_poll(&vi, evs, BATCH);   /* verbatim pattern from onload efsink.c */
  for(i=0;i<n;++i) if(EF_EVENT_TYPE(evs[i])==EF_EVENT_TYPE_RX) handle(EF_EVENT_RX_RQ_ID(evs[i])); }
```

**Step 3, parse in place (≈ few ns).**
- No copy into a "message object". The payload is viewed as a struct.
- The *legal* way is `std::start_lifetime_as<AddOrder>(buf)` (C++23, P2590) or `memcpy`/`std::bit_cast`, which compile to plain loads.
- `reinterpret_cast<AddOrder*>(buf)` is what most codebases actually do, and it is formally UB (§9).
- Endianness is swapped with `bswap`. Price stays an **integer** (1002500), with no floating point.

**Step 4, book update (≈ 10 ns in our lab).**
- Look up the order ref in an open-addressing hash map (order-ref → level/qty), preallocated.
- Then update the ask side: a `std::vector<pair<Price,Qty>>` stored **in reverse** (asks descending), so the best ask is at `back()`.
- The new 100.25 beats the old best ask of 100.27. A linear scan from the back finds the slot in **zero steps**, and `insert` at the end shifts nothing. This is Gross's version 3.

```
before asks (desc): ... 100.31x900  100.29x200  100.27x400   ← back() = best
after:              ... 100.31x900  100.29x200  100.27x400  100.25x500  ← push near end, 0 shifts
```

**Step 5, strategy (≈ tens of ns).**
- `Strategy<Side::Buy>::decide` is a template specialization. There is no `side == Buy ? … : …` branch and no virtual call.
- Read best ask 1002500 ≤ trigger 1003000 → fill the preallocated `Order{BUY, ABCD, 500, 1002500, IOC}`.

**Step 6, risk check (≈ few ns, one branch).**
- Each check (max qty, max notional, price band versus reference, position limit, kill switch) sets a bit in `uint64_t err`.
- **Single branch**: `if (!err) send(); else handle(err);`, and the handler is `noinline, cold` (Cook slide 16).
- This is the SEC Rule 15c3-5 pre-trade control, and it lives on the hot path, unlike in the Knight Capital story (§9).

**Step 7, send (≈ hundreds of ns, hardware).**
- The order bytes (OUCH-like, mostly a pre-built template; only the price, qty and token fields are patched) go into a TX buffer.
- ef_vi/TCPDirect pushes the descriptor (or PIO-writes small frames) and rings the doorbell.
- The NIC timestamps TX.
- On a warm-up pass (`dry_run`), everything up to here ran, and only the doorbell is skipped.

**Step 8, measure (offline).**
- A switch or Layer-1 tap (e.g. Arista 7130/MetaWatch, sub-ns timestamps) stamps the inbound market-data frame and the outbound order frame.
- A capture server matches them and records **wire-to-wire** latency for *every* packet into a histogram (Cook slides 50–52). There is no sampling and no in-process observer effect.

Illustrative budget (orders of magnitude only; firms don't publish exact splits):
- NIC + PCIe in ≈ 300–500 ns,
- software ≈ 100–300 ns,
- NIC + PCIe out ≈ 300–500 ns,
- total ≈ 1–2.5 µs.

The point: **PCIe and the NIC dominate**, which is why the next step is FPGA (§8).

---

## 6. The math

### 6.1 The wire floor

Let d be path length, c = 299,792 km/s, and n the refractive index (fiber ≈ 1.47, air ≈ 1.0003).

$$t_{\text{one-way}} = \frac{n\,d}{c}$$

- Fiber: 4.9 µs/km.
- Air: 3.34 µs/km.
- Chicago–NJ geodesic at 1139.5 km: 3.80 ms in air. Fiber runs ≈ 6.65 ms because of n *and* a longer right-of-way.

→ **In plain terms:** every kilometre of glass costs 1.5 µs more than air. That is why firms bought microwave towers. After that, everyone is equal, and **in-box µs decide**.

### 6.2 Average memory access time: why a cold hot path is slow

A path touches M cache lines. Each hits in level i with probability $h_i$ at latency $L_i$:

$$T_{\text{mem}} \approx M\left(L_1 + m_1 L_2 + m_1 m_2 L_3 + m_1 m_2 m_3 L_{\text{DRAM}}\right)$$

Here $m_i = 1-h_i$ is the miss rate at level i. Warm: $m_1 \approx 0$, so $T \approx M \cdot 1\,\text{ns}$. Cold, after another workload trashed the caches: $m_1 = m_2 = m_3 \approx 1$, so $T \approx M \cdot 80\,\text{ns}$.

For M = 512 lines (our lab's 32 KiB working set), that is ≈0.5 µs warm and up to ≈40 µs cold. The hardware prefetcher and memory-level parallelism hide most of the sequential case: our lab measured **p50 84 ns warm vs 542 ns cold**, 6.5×.

→ **In plain terms:** latency is multiplied by the miss rate, and an idle path's miss rate tends to 1. Warming forces $m_1 \to 0$ right before the moment that counts.

Why this form and not "bytes / bandwidth"? Because the hot path is **latency-bound**: dependent pointer loads (hash bucket → node → level) can't overlap. Bandwidth only matters for streaming. That is also why node containers (`std::map`: log N dependent misses) lose to contiguous arrays.

### 6.3 Tails compound across stages

A tick traverses N stages (NIC, parse, book, strategy, risk, send, …), each independently "slow" with probability p:

$$P(\text{tick hits at least one slow stage}) = 1-(1-p)^N$$

With p = 1% and N = 6, that is 5.9%. With N = 100 (fan-out services), 63%. [Dean & Barroso, The Tail at Scale](https://blog.acolyer.org/2015/01/15/the-tail-at-scale/)

→ **In plain terms:** a path is only as predictable as the product of its stages' predictability, so every stage's p99 matters, not just the slowest stage's p50.

### 6.4 Bursts, Little's law, and dropped packets

- Little's law: $L = \lambda W$ (mean items in system = arrival rate × mean time in system), valid for any stable system.
- During a burst, the arrival rate λ exceeds the service rate μ = 1/s, where s = per-message service time.
- The backlog then grows at λ − μ. A NIC ring of R slots overflows after

$$T_{\text{drop}} = \frac{R}{\lambda - \mu}$$

Example (made-up but realistic): λ = 5 M msg/s in a burst, s = 300 ns → μ = 3.33 M/s → backlog grows 1.67 M/s → a 4096-slot ring overflows in **2.5 ms**. Halve s to 150 ns (μ = 6.67 M/s > λ) and the ring never fills.

The queueing delay seen by the k-th message of the burst is $\approx k(s - 1/\lambda)$. So **the most important packets, right after news, wait longest.**

→ **In plain terms:** a small per-message cost difference flips you from "keeps up" to "falls behind and loses data". It is a cliff, not a slope. That is why Gross treats order-book update time as an availability issue.

### 6.5 Coordinated omission

- A load tester sends every interval Δ but waits for each reply.
- When one stall of length S occurs, it skips ≈ S/Δ − 1 samples that *should* have seen latencies S − Δ, S − 2Δ, …
- Recorded data: 1 slow sample. Truth: S/Δ slow samples.
- Tene's example: Δ = 1 ms, 10 stalls of ≈536 ms → ≈5,350 omitted samples; true p99.99 ≈ 582 ms vs a reported figure ≈35,000× smaller. [Tene](https://groups.google.com/g/mechanical-sympathy/c/icNZJejUHfE/m/BfDekfBEs_sJ)

→ **In plain terms:** if your measurement waits for the system, it stops measuring exactly when the system is worst. Wire taps don't wait, so they don't lie this way.

---

## 7. Why it works

**The core insight:** latency on a modern CPU is dominated by *events*, not *instructions*: cache misses, TLB misses, mispredicts, syscalls, interrupts, page faults, frequency transitions. A few hundred well-predicted, cache-resident instructions cost tens of ns. One event costs 100 ns–100 µs. So the craft is **eliminating events on the hot path, and pre-paying the unavoidable ones off the hot path**.

Ablation, removing each piece:

| Remove… | What breaks |
|---|---|
| Kernel bypass | +≈4 µs per packet in the kernel TCP path, plus syscall jitter and interrupt coalescing. |
| Busy-poll / pinned core | The thread sleeps → C-state exit (≈90+ µs) or a context switch (µs) on wake. |
| `isolcpus`/`nohz_full` | Timer ticks, RCU callbacks and kworkers land on your core; Rigtorp still saw 18 µs max jitter on a poorly isolated core. |
| Cache warming | First real packet after idle pays the cold miss chain: our lab shows 6.5× p50, ≈7× p99. |
| Preallocation + `mlockall` + prefault | `malloc` bookkeeping ("400 lines" in glibc `free`), page faults, THP compaction stalls. |
| Templates instead of virtuals | Indirect branch mispredicts at polymorphic sites, plus **lost inlining**, which is the bigger cost. |
| Single-branch risk check | N unpredictable branches; error code inlined into the hot path, polluting the i-cache. |
| Contiguous reverse-vector book | `std::map`: node allocation per level and log N dependent misses. Gross: "Most of the time, you don't want node containers." |
| Padding / single writer | False sharing: our lab went **1908 ms vs 82 ms (23×)** for two counters on one line vs separate lines. |
| Wire-level measurement | You optimise the wrong thing. Sampling profilers "miss the key events" (Cook). |

---

## 8. Design knobs & alternatives

**Network path.** Pick the cheapest layer that meets your budget:

| Path | Extra over raw ef_vi (vendor slide, 2017) | Code change | Use |
|---|---|---|---|
| Kernel + `busy_poll` | +3.9 µs (TCP) | none | ≥ 10 µs budgets |
| Onload / XLIO (LD_PRELOAD) | +300 ns UDP, +460 ns TCP | none | first step; socket code |
| TCPDirect | +15 ns UDP, +22 ns TCP | sockets-like API | order entry |
| ef_vi / libexanic raw frames | 0 | you write the protocol | hot feed handler |
| AF_XDP (upstream Linux) | best ≈ 6.5 µs RTT when tuned | moderate | portability, not tick-to-trade ([arXiv 2402.10513](https://arxiv.org/abs/2402.10513)) |
| FPGA (STAC-T0 13.9 ns) | n/a | HDL/HLS | simple, parameterisable triggers |

**CPU.**
- SMT off: the sibling shares L1/L2, ports and the predictor.
- Turbo: higher peak but frequency transitions, a tradeoff.
- C-states locked shallow.
- One socket for trading, noisy work on the other.
- Some disable all but one core per L3 or partition the LLC with Intel CAT (Cook slide 40, Rigtorp).

**Threading model.**
- Single-threaded hot path (Cook) vs pipeline over SPSC queues.
- If queues are used:
  - single writer;
  - head/tail on separate lines;
  - **cached opposite index**: the reader re-reads the writer's index only when it thinks the queue is empty. Rigtorp saw 5.5 M → 112 M ops/s and ≈3 → 0.15 cache misses per op ([rigtorp ringbuffer](https://rigtorp.se/ringbuffer/)).
- For one-to-many, Gross's FastQueue: seqlock-style write counter / read counter, readers detect overrun and never slow the writer.

**Process model.**
- Multiple processes over shared memory (`shm_open` + `mmap`) reduce operational risk; one crash doesn't take down the feed (Gross).
- Versioned headers with reserved bytes.

**Data layout.**
- Denormalise: copy the multiplier into the instrument struct so it sits on the same line (Cook).
- Integer ticks.
- Hash maps with contiguous hash+pointer arrays that can be prefetched: 14–24 ns → 7–9 ns versus `std::unordered_map` (Cook slides 29–35).

**Compiler.**
- `-O3 -march=native`, PGO, LTO, then BOLT layout (LBR samples).
- `[[likely]]`/`[[unlikely]]`, `__attribute__((cold,noinline))` immediately-invoked lambdas for error paths.
- `always_inline` where measured. The `inline` keyword is about ODR, not inlining (Cook slide 36).

**Alternatives and why C++ (mostly) won the software layer:**
- **Java** (LMAX, Chronicle): garbage-free code. Disruptor mean 52 ns / p99.99 8 µs. Good, but you fight the GC and JIT warm-up.
- **OCaml** (Jane Street): correctness first.
- **Rust**: promising, but anecdotally "a nightmare" on the hot path because of unsafe and aliasing gymnastics ([eFinancialCareers](https://www.efinancialcareers.com/news/C-vs-Rust-High-Frequency-Trading-Hell), anecdotal).
- **FPGA** won the *fastest* path. C++ moved up a layer to strategy, parameters and risk.

---

## 9. Where it breaks

**Operational: Knight Capital, 1 Aug 2012** ([SEC 34-70694](https://www.sec.gov/litigation/admin/2013/34-70694.pdf)).
- New code went to 7 of 8 servers. A **reused flag** woke dead "Power Peg" code on server 8.
- Its fill-tracking had been broken by a 2005 refactor that nobody retested.
- 45 minutes: 4M executions, 397M shares, ≈$3.5B long / $3.15B short, **>$460M loss**. (The common "$440M" was Knight's early estimate.)
- 97 warning emails went unread.
- The rollback made it worse: removing the new code from the 7 correct servers made them run Power Peg too.
- Pre-trade controls "were not capable of preventing the entry of orders".
- Lesson: speed engineering is worthless without automated, blocking risk gates, version-consistency checks, and no dead code behind flags.

**Microarchitecture traps:**
- **False sharing.** Padding to 64 B isn't enough on Intel parts whose spatial prefetcher pulls line *pairs*, so many pad to 128 B. `std::hardware_destructive_interference_size` is a compile-time guess; GCC warns about ABI hazards. Apple M-series reports 128 B lines (`sysctl hw.cachelinesize` on our test machine).
- **Denormals.** Up to ≈100× slower via microcode assist. A decaying EMA drifting toward 0 is the classic trigger. Fix: FTZ/DAZ. [Intel](https://www.intel.com/content/www/us/en/docs/onemkl/developer-guide-windows/2025-1/operating-on-denormals.html)
- **AVX-512 frequency licences.** On Skylake-SP, one AVX-512 burst downclocks the core and slows the scalar code after it. Mostly gone on Ice Lake+ (≤100 MHz), but voltage transitions remain. [Travis Downs](https://travisdowns.github.io/blog/2020/08/19/icl-avx512-freq.html)
- **SMIs.** Firmware interrupts invisible to the OS, sometimes ms long. Only detectable via `hwlatdetect`. An **irreducible floor**. [kernel hwlat](https://www.kernel.org/doc/Documentation/trace/hwlat_detector.rst)
- **THP.** khugepaged and direct compaction stall at random. Use explicit hugetlbfs.
- **TLB shootdowns.** Any `munmap`/`mprotect`/`MADV_FREE` by any thread IPIs every core running the process (Rigtorp).
- **Spectre mitigations.** KPTI made `getppid` 0.079 → 0.202 µs (+150%) ([Gregg](https://brendangregg.com/blog/2018-02-09/kpti-kaiser-meltdown-performance.html)). Rigtorp lists `mitigations=off`. I found **no primary source** that firms do this routinely. It is only defensible on single-tenant, locked-down boxes.

**C++ traps:**
- **Type-punning packet buffers.** `reinterpret_cast<Hdr*>(buf)->field` is UB (strict aliasing / object lifetime). It works until an optimiser proves otherwise. Use `memcpy`/`bit_cast` or C++23 `std::start_lifetime_as` ([P2590R2](https://open-std.org/jtc1/sc22/wg21/docs/papers/2022/p2590r2.pdf)); library support landed late.
- **Memory ordering.** x86 TSO hides `relaxed`-ordering bugs that break on ARM ([Arm learning path](https://learn.arm.com/learning-paths/servers-and-cloud-computing/arm-cpp-memory-model/3/)). Even on x86, the compiler can reorder relaxed ops, and TSO still reorders store→load. `volatile` gives neither.
- **Seqlock readers.** Gross notes FastQueue's reader `memcpy` is formally a data race, pending P1478 (byte-wise atomic memcpy).
- **Exceptions.** Zero-cost until thrown; then ≥1.5 µs (Cook), and the unwinder takes a global lock that scales badly across threads ([P2544](https://open-std.org/JTC1/SC22/WG21/docs/papers/2022/p2544r0.html)).
- **Hidden allocations.** `std::function` may allocate (use `inplace_function`). Thread-safe function-local statics cost 5–10%. Before gcc 7.1, placement new did a null check (Cook war stories).

**Measurement misconceptions:**
- Microbenchmarks run warm; production fires cold (Gross's "you're not alone": other processes evict you). `DoNotOptimize` doesn't stop the compiler computing the expression at compile time.
- `rdtsc` needs `lfence`/`rdtscp` fencing and an invariant TSC, and may be unsynchronised across sockets ([Paoloni](https://cis.temple.edu/~qzeng/cis3207-spring18/files/ia-32-ia-64-benchmark-code-execution-paper.pdf)).
- **Layout noise.** Changing environment size or link order flipped whether -O3 beats -O2 (Mytkowicz, ASPLOS'09). With layout randomised (Stabilizer, ASPLOS'13), -O3 vs -O2 was indistinguishable from noise on SPEC2006. So a "3% win" from an unrelated commit may be alignment. [Stabilizer](https://people.cs.umass.edu/~emery/pubs/stabilizer-asplos13.pdf)

**Misconceptions:**
- "Virtual calls are slow because of the vtable load." No: the cost is the indirect mispredict and the lost inlining.
- "Lock-free means no locks." Cook: it "may still require locks at the hardware level" (cache-line ownership).
- "Faster average = more wins." Race wins come from the tail at the moment of news.

---

## 10. In the wild

- **Optiver (Cook 2017).**
  - Single-threaded hot path.
  - Template config so there is "one virtual call at the top, none inside".
  - Custom `array_map` hash.
  - Dummy-path warming.
  - Switch-timestamp replay rig for measurement.
  - Deviation from textbook: *prefer approximations; do expensive work only when there's spare time.*
- **Optiver (Gross 2024).**
  - Reverse-vector book with linear search. He showed the branchless binary search `first += comp(first[half], value) * (length - half);` (the `*` is "needed for GCC to generate CMOV") and then showed that linear search wins anyway.
  - Kernel-bypass fan-out to processes on the same box.
  - FastQueue over shared memory, benchmarked against Aeron's BroadcastTransmitter and the LMAX Disruptor on an EPYC 9474F.
  - `ScopedTrace` with `__rdtsc()` pushed to a queue; Clang XRay for runtime patching.
  - Top-down `perf stat -M Frontend_Bound,Backend_Bound,Bad_Speculation,Retiring`.
- **HRT.** Explicit huge pages: 4.5× faster random access over a 32 GB dataset on Alder Lake. Devirtualisation posts.
- **Logging (Quill, fmtlog).**
  - Per-thread SPSC queues carry a format-string ID plus binary args, ≈6 ns p50.
  - A backend thread on a housekeeping core formats.
  - spdlog formatting inline is ≈271 ns p50 in Quill's benchmark.
- **Hybrid CPU+FPGA.** AMD's X3522 markets "offload business logic to NIC". Solarflare/LDA put the TCP fast path in the FPGA with control in Onload. Software precomputes "if price X arrives, fire order Y" and the FPGA fires.
- **Exchanges moving into the cloud.** CME announced (26 Jun 2024) Globex moving to a private Google Cloud region in Aurora with colocation ([CME](https://www.cmegroup.com/media-room/press-releases/2024/6/26/cme_group_and_googlecloudannouncenewchicagoareaprivatecloudregio.html)). Cut-over date unverified. Cloud-style NICs are why userspace stacks like Machnet matter.

---

## 11. Frontier (what's new)

| Year · venue | Work | Contribution |
|---|---|---|
| 2024 · STAC report AMD240422 | [AMD Alveo UL3524 + Exegy nxFramework](https://docs.stacresearch.com/news/AMD240422) | STAC-T0 record **13.9 ns** min tick-to-trade (507 B frames); prior record 24.2 ns; jitter ≈200 ps (Exegy claim). In-FPGA path only, not a full strategy. UL3524 transceivers < 3 ns ([product brief](https://www.xilinx.com/content/dam/xilinx/publications/product-briefs/2233051_Product_Brief_UL3524_Alveo_Accelerator_Card.pdf)). |
| 2024 · CppCon keynote | [Gross, "When Nanoseconds Matter"](https://github.com/CppCon/CppCon2024/blob/main/Presentations/When_Nanoseconds_Matter.pdf) | Most detailed public account: reverse-vector books, linear vs branchless search, FastQueue seqlock broadcast, top-down profiling, XRay. |
| 2023 · HPCA | [LightTrader](https://rebellions.ai/wp-content/uploads/2023/11/RebellionsIONHPCA23_LightTrader.pdf) (KAIST/Rebellions, DOI 10.1109/HPCA56546.2023.10070930) | FPGA networking + 7 nm CGRA DNN accelerator in the tick path. Burst-aware scheduler with DVFS; reported 6× faster DNN and 30–50× fewer missed queries. Numbers are from the summary; full paper not read. |
| 2024 · IEEE ICC | [Understanding Delays in AF_XDP](https://arxiv.org/abs/2402.10513) | Best AF_XDP RTT ≈6.5 µs, and only with careful busy-poll, need_wakeup and zero-copy tuning. Upstream Linux is still a µs-class path. |
| 2025 · Linux 6.15 | [io_uring zero-copy receive](https://www.phoronix.com/news/Linux-6.15-IO_uring) | NIC page pool DMAs straight to user memory; 188 Gbit/s on one core. A throughput result: no published latency comparison vs ef_vi. |
| 2023 · MICRO | [Demystifying CXL Memory](https://arxiv.org/abs/2303.15375) | Placing pages in CXL raises tail latency of µs-scale apps by 10–82% vs local DDR. Keep hot state out of CXL tiers. |
| 2026 · ISO C++26 (finalised Mar 2026) | [C++26](https://en.wikipedia.org/wiki/C%2B%2B26) | Static reflection (zero-overhead codec generation), `std::inplace_vector` (no heap), `<hazard_pointer>`, `<rcu>`, `std::execution`, contracts. Trivial relocatability deferred. `start_lifetime_as` came in C++23. |
| 2026 · arXiv 2608.02424 (preprint) | [LOBIN](https://arxiv.org/abs/2608.02424) (Oxford) | Builds order books and runs ML inference **inside programmable switches**; ≈45% of traffic handled entirely in-switch. |
| 2026 · arXiv 2608.00909, COLM 2026 | [FinHardBench](https://arxiv.org/abs/2608.00909) | Can LLMs write latency-aware RTL/HLS for 33 tick-to-trade tasks? 19–61% functionally correct, timing regressions up to 13.7×. |
| 2023 · arXiv 2309.04259 | [Bilokon & Gunduz, C++ Design Patterns for Low-latency Apps incl. HFT](https://arxiv.org/abs/2309.04259) | Academic microbenchmarks: cache warming and constexpr gave the biggest wins. |

**Where the action moved:** the fastest decisions migrated to FPGAs/ASICs and now switches. The C++ frontier is (a) making the 1–10 µs strategy layer predictable while it runs heavier models (LightTrader-style ML), (b) language features that remove UB from zero-copy parsing and add reflection-generated codecs, and (c) surviving exchange moves to cloud-like infrastructure.

---

## 11b. Open problems

1. **Deterministic latency on general-purpose CPUs.**
   - SMIs, microcode assists, uncore and memory-controller power management, and voltage transitions can't be turned off from software.
   - Even with `isolcpus` + `nohz_full`, residual timer interrupts appear (≈1 Hz tick by design, and Red Hat KB reports more).
   - Why hard: the CPU vendor, not the OS, owns these.
   - Who: Linux RT and nohz maintainers (Frederic Weisbecker et al.), hardware vendors.
2. **Verifying lock-free code at system scale.**
   - GenMC (MPI-SWS, PLDI'19) model-checks RC11/IMM programs, but small client programs only: state explosion, bounded loops.
   - Production seqlocks are formally racy in C++ today (P1478 pending).
3. **Performance measurement that isn't layout noise.**
   - Stabilizer showed layout effects swamp many "optimisations".
   - Firms want ±1% decisions on code where alignment alone moves ±several %.
   - Pinning alignment (`-falign-functions`, BOLT) helps but doesn't prove causality.
4. **One source of truth across CPU and FPGA.**
   - Strategy and risk checks get re-implemented in HDL/HLS.
   - No programming model guarantees the FPGA's "fire" logic and the C++ risk gate agree.
   - FinHardBench shows LLM-generated RTL isn't there yet.
5. **Is it socially worth it?**
   - Budish/Cramton/Shim (QJE 2015) and Aquilina et al. (QJE 2022) argue races are an artifact of continuous limit-order books. Frequent batch auctions would cut liquidity cost ≈17%.
   - Speed-bump evidence is mixed: it helps the adopting venue, but market-wide effects are inconclusive ([Aramian & Comerton-Forde](https://static1.squarespace.com/static/6310c0b9bb63a25599f4418c/t/65d4835e10387e459f6266a2/1708426079078/SpeedBumpFinal20240212.pdf)).
   - If market design changed, much of this engineering would be obsolete.
6. **Gaps in this dive.** Exact ns numbers in Gross's charts weren't extractable (images). No 2023–25 head-to-head paper compares Onload/ef_vi vs AF_XDP vs DPDK latency. Firm-internal splits of the tick-to-trade budget aren't public.

---

## 12. Lineage

- **2000s.** Kernel sockets, interrupt-driven NICs, std containers.
- **2007.** Drepper, *What Every Programmer Should Know About Memory*.
- **2008–2011.** Solarflare OpenOnload (user-space TCP/IP, LD_PRELOAD).
- **2010.** SEC Rule 15c3-5 mandates pre-trade controls.
- **2010–2011.** LMAX Disruptor and "mechanical sympathy" (Thompson): single writer, padding, ring buffers.
- **2010–2013.** Chicago–NJ microwave race (Spread Networks fiber 13 ms RTT → McKay microwave 8.2 ms).
- **2012.** Gil Tene, "How NOT to Measure Latency"; HdrHistogram.
- **2012.** Knight Capital.
- **2015.** Budish/Cramton/Shim, the HFT arms race paper.
- **2016–2017.** P0154 `hardware_destructive_interference_size` (C++17).
- **2017.** Cook, "When a Microsecond Is an Eternity".
- **2018.** NanoLog (ATC'18); Neugebauer PCIe characterisation (SIGCOMM'18).
- **2020.** Cisco buys Exablaze.
- **2022.** C++23 `start_lifetime_as`.
- **2022.** Aquilina/Budish/O'Neill quantify races (5–10 µs).
- **2022.** HRT huge pages.
- **2022.** Gross, "Trading at light speed".
- **2023.** AMD UL3524.
- **2023.** LightTrader (HPCA).
- **2024.** STAC-T0 13.9 ns.
- **2024.** Gross, "When Nanoseconds Matter".
- **2024.** CME → private Google Cloud announced.
- **2025.** io_uring zcrx.
- **2026.** C++26: reflection, `inplace_vector`, hazard pointers/RCU.
- **2026.** In-switch order books (LOBIN).

---

## 13. Hands-on (≤ 30 min)

[`hotpath_lab.cpp`](hotpath_lab.cpp) runs three experiments behind the folklore:

```bash
c++ -O2 -std=c++20 -pthread hotpath_lab.cpp -o lab && ./lab
```

Results on an Apple M-series laptop, macOS, clang 21 (your numbers will differ; compare ratios):

```
1) false sharing — 2 threads x 50M relaxed fetch_add
  same line : 1908 ms
  padded    : 82 ms                              → 23x
2) cold vs warm hot path (2000 samples each)
  cold (after cache trash)     p50= 542 ns  p99=1666 ns  p99.9=1875 ns
  warm (after warm-up call)    p50=  84 ns  p99= 208 ns  p99.9= 250 ns   → 6.5x p50, 8x p99
3) order book update, 1M ops, 90% within 5 ticks of best
  std::map<greater>            16.9 ns/update
  reversed vector + linear     10.9 ns/update    → 1.55x
```

Things to try:
- Change `kLine` from 128 to 8 in `Padded` and watch the 23× return.
- In experiment 3, make updates uniform over all 200 levels (`near` always false). The vector's linear scan and `insert` shifts grow, and `std::map` catches up. Data skew is the reason the vector wins.
- Shrink `g_junk` to 1 MiB. "Cold" stops being cold once the trash fits in L2.
- Remove the warm-up call `on_tick(i + 1)` and see "warm" degrade.
- On Linux x86, run under `perf stat -e cache-misses,branch-misses` and with `taskset -c` on an isolated core.

---

## 14. Question ladder

### Mechanism
1. What exactly happens, cycle-wise, between the NIC DMA completing and your code seeing the packet with ef_vi vs a kernel socket?
2. Why does Gross store bids ascending and asks descending, and what's at `back()`?
3. How does Rigtorp's SPSC queue's cached index reduce cache-coherence traffic?
4. In FastQueue, why does the reader check the write counter both before and after copying?

### Why
5. Why does linear search beat binary search on the order book even though it's O(N)?
6. Why fold all risk checks into one `uint64_t` instead of early-returning on each?
7. Why do firms prefer a busy-spinning `SCHED_OTHER` thread over `SCHED_FIFO`?
8. Why explicit hugetlbfs instead of transparent huge pages?

### Counterfactual
9. If you removed cache warming but kept everything else, which percentile moves most, and why?
10. If the market became a frequent batch auction every 100 ms, which of these techniques would still matter?
11. What if you used `std::map` but with a pool allocator? What's fixed, and what isn't?

### Adversarial
12. How could a dummy warm-up order end up sent to the exchange, and how do you make that impossible?
13. You see a 3% p50 improvement after an unrelated commit. How do you decide if it's real?
14. Which jitter source would you blame for a 2 ms spike that hits all isolated cores at once, and how do you confirm it?
15. Where is the UB in `auto* m = reinterpret_cast<const AddOrder*>(buf); return m->price;`, and why might it "work" for years?

### Connection
16. How is cache warming related to JIT warm-up in the JVM?
17. How does the Little's-law burst analysis relate to io_uring's CQ overflow or a Kafka consumer lag?
18. How does the Knight Capital failure map onto feature-flag practice in ordinary web services?

### Open
19. Can a general-purpose CPU ever offer a hard upper bound on tick-to-trade latency?
20. Will C++26 reflection make hand-written codecs and SBE-style generators obsolete in HFT?
21. If FPGAs and switches take every simple decision, what's left for C++, and does "nanosecond C++" still matter?

### Answers

<details><summary>1. ef_vi vs kernel socket path</summary>

**ef_vi:** the NIC DMAs into a user-registered buffer and writes an event into a user-mapped event queue. The spinning thread's next `ef_eventq_poll` load sees it, ideally from cache if DDIO placed it in LLC. No interrupt, no mode switch, no copy.

**Kernel:** the NIC raises an interrupt (or NAPI polls), the driver builds an skb, the IP/UDP stack processes it, and it is queued on the socket. The thread blocked in `recv` gets woken through the scheduler, does a syscall return, and the data is copied to the user buffer. Each step adds cache misses and possible context switches. Solarflare measured ≈+3.9 µs for TCP.
</details>

<details><summary>2. Reverse vector</summary>

The best price (highest bid, lowest ask) sits at the **end** of the vector. Most adds, modifies and deletes happen near the top of the book. `vector::insert`/`erase` cost is proportional to elements *after* the position, so operations near the end shift almost nothing. At the front they would shift the whole book.
</details>

<details><summary>3. Cached index in SPSC</summary>

Normally the consumer reads `writeIdx` on every pop. That pulls the producer's cache line into shared state, and the producer's next write must invalidate it, so the line ping-pongs. With a cached copy, the consumer only re-reads `writeIdx` when its cached value says the queue is empty, and the producer does the same for `readIdx`. Cross-core transfers drop from ≈per-op to ≈per-batch: Rigtorp saw ≈3 → 0.15 misses/op and 20× throughput.
</details>

<details><summary>4. FastQueue double check</summary>

The writer never waits for readers, so it can lap a slow reader and overwrite data mid-copy. Reading the write counter before and after copying (seqlock-style) tells the reader whether the region could have been overwritten during the `memcpy`. If so, it discards the copy and reports overrun. The copy itself is formally a data race in C++, hence P1478.
</details>

<details><summary>5. Linear beats binary</summary>

Updates are heavily skewed toward the top few levels, so a scan from the best price terminates in 0–3 steps. Each step is a sequential, prefetchable, well-predicted access. Binary search over ≈1000 levels does ≈10 dependent, unpredictable probes across different cache lines, which means mispredicts or data-dependent loads. Expected cost, not worst-case complexity, matters for skewed data. Our lab: vector 10.9 vs map 16.9 ns/update.
</details>

<details><summary>6. One risk flag word</summary>

Each early-return branch must be predicted, and their outcome pattern is data-dependent. OR-ing branchless comparisons into a bit mask leaves **one** branch that is almost always "no error" and therefore perfectly predicted. The error handler is out-of-line and cold, so its instructions don't pollute the hot i-cache. You pay a few extra ALU ops to avoid potential 15–20-cycle mispredicts.
</details>

<details><summary>7. SCHED_OTHER spin vs SCHED_FIFO</summary>

On an isolated core with one runnable task, there's nothing to preempt you anyway. SCHED_FIFO adds RT throttling: by default RT tasks are limited to 95% CPU (`sched_rt_runtime_us`), so a spinning FIFO thread gets forcibly descheduled. It also risks starving per-CPU kernel threads that need to run. Rigtorp recommends a busy-waiting SCHED_OTHER thread.
</details>

<details><summary>8. hugetlbfs vs THP</summary>

THP is opportunistic: khugepaged collapses pages in the background and the kernel may do direct compaction on fault. Both cause unpredictable stalls (`compact_stall`). Explicit hugetlbfs pages are reserved at boot, mapped with `MAP_HUGETLB`, and prefaulted at startup, so you get the TLB-reach win (≈4 GiB vs 8 MiB) with no runtime surprises.
</details>

<details><summary>9. Remove cache warming</summary>

The **first real event after idle**, which is the one that matters, gets slow. The tail percentiles and specifically "latency after quiet period" move most. The median might barely change during busy periods, because back-to-back packets keep things warm naturally. In our lab, cold vs warm is 6.5× at p50 and 8× at p99.
</details>

<details><summary>10. Batch auctions</summary>

Sub-ms speed would stop deciding who wins: orders arriving anywhere within the 100 ms window are treated equally. What survives:
- **throughput** (process the whole batch's data),
- **correctness** and risk,
- **avoiding drops**,
- maybe compute-heavy pricing before the auction deadline.

Kernel bypass and the ns-level micro-optimisations would matter far less. That is the point of Budish et al.
</details>

<details><summary>11. std::map + pool allocator</summary>

The pool fixes allocation cost and fragmentation, and improves locality somewhat if nodes come from one arena. It doesn't fix:
- the **log N dependent pointer chases** with unpredictable branches,
- the larger node footprint (3 pointers + colour per entry), so fewer levels per cache line,
- the lack of sequential prefetchability.
</details>

<details><summary>12. Dummy order leaks</summary>

How it could happen: the "don't send" decision is one runtime flag. A bug, a reused flag (Knight!), or a refactor that moves the check can turn warm-up into real orders.

Defences:
- make the dry-run send target a **different sink** (a null TX object chosen by template/type, or a TX ring the NIC never transmits);
- give warm-up orders an exchange-invalid or self-rejecting field;
- add independent risk checks, including on the FPGA/NIC or a gateway;
- add a wire-level monitor that kills the session on unexpected orders.
</details>

<details><summary>13. Is a 3% win real?</summary>

Treat it as layout noise until proven otherwise (Mytkowicz ASPLOS'09; Stabilizer ASPLOS'13).

- Rerun with different link orders and alignments, or with randomisation.
- Use many runs and look at distributions and confidence intervals, not single numbers.
- Check top-down counters for a plausible mechanism (fewer misses or mispredicts).
- Confirm at the wire with hardware timestamps under replayed production data, not a microbenchmark.
</details>

<details><summary>14. 2 ms spike across all cores</summary>

Prime suspect: an **SMI**. It stalls all cores invisibly to the OS and can last ms. Other candidates: a TLB-shootdown storm, or the memory/uncore power state.

To confirm: run `hwlatdetect` / the hwlat tracer on the box (it spins with IRQs off and looks for TSC gaps), and correlate with BIOS settings (disable features like memory patrol scrub if allowed). Check `/proc/interrupts` deltas to rule out OS-visible interrupts.
</details>

<details><summary>15. reinterpret_cast UB</summary>

No `AddOrder` object exists at `buf`; there is only a char/byte array. Accessing it through `const AddOrder*` violates object-lifetime and strict-aliasing rules. Misalignment can be UB too if the struct needs alignment the buffer doesn't provide.

It "works" because compilers usually emit plain loads and nothing in the TU lets them exploit the UB. Inlining, LTO, or a new optimisation can reorder or eliminate loads based on aliasing assumptions.

Fixes: `memcpy`/`std::bit_cast` (optimised to loads) or C++23 `std::start_lifetime_as<AddOrder>(buf)`.
</details>

<details><summary>16. Cache warming vs JIT warm-up</summary>

Both pre-pay one-time or decaying costs before the critical moment: the JIT compiles hot methods and builds profiles; cache warming loads lines and trains predictors. The difference: JIT warm-up is mostly one-time (compiled code stays), while cache/predictor state **decays** whenever other code runs, so HFT warming must be **continuous**. JVM trading shops (LMAX, Chronicle) need both.
</details>

<details><summary>17. Bursts elsewhere</summary>

Same math: when arrival rate > service rate, backlog grows at λ−μ until a bounded buffer overflows. That buffer could be the NIC ring here, an io_uring CQ (overflow → `-EBUSY`/dropped completions handled via the overflow list), or a Kafka consumer (lag grows until retention deletes unconsumed data). The cliff is the same; only the buffer differs.
</details>

<details><summary>18. Knight and feature flags</summary>

Lessons for any service:
- Dead code behind a flag is live.
- Reusing a flag's meaning across versions is dangerous during **partial rollouts**: old binaries interpret the bit the old way.
- Verify version consistency across the fleet before enabling.
- Rollback is a deployment too, so reason about the state you're rolling back to.
- Alerts must be designed as alerts (97 unread emails).
</details>

<details><summary>19. Hard bound on a CPU?</summary>

Not today. SMIs, microcode assists, DRAM refresh and power-management transitions are outside OS control, and caches/coherence add data-dependent timing. You can make violations rare and characterise them statistically, not bound them. Hard real-time systems use simpler cores, locked caches/scratchpads, or FPGAs, which is partly why the hardest deadlines moved to FPGAs.
</details>

<details><summary>20. C++26 reflection vs codec generators</summary>

Plausibly it replaces external generators for *simple* schemas: reflection can generate field-by-field encode/decode at compile time from a struct with zero runtime cost.

But exchange schemas (SBE XML, ITCH specs) originate *outside* C++. Generators also handle versioning, multiple languages, and documentation. Open question: adoption depends on compiler maturity and on whether teams trust compile-time-generated hot code.
</details>

<details><summary>21. What's left for C++?</summary>

Open. One view: C++ becomes the "control plane": strategy, risk, parameter computation, model inference at 1–10 µs, while FPGAs fire. Predictability still matters there (falling behind on parameters = stale triggers). Another view: as exchange architecture (cloud regions, speed bumps, batch auctions) changes, the payoff for the last ns shrinks. Expect the skill set to shift toward co-design and measurement rather than micro-tricks.
</details>

---

## 15. Go deeper next

1. **Seqlocks and the C++ memory model.** Why byte-wise atomic memcpy (P1478) is needed, and how Boehm's "Can seqlocks get along with programming language memory models?" frames it.
2. **FPGA tick-to-trade pipelines.** How a 14 ns STAC-T0 path parses, decides and transmits without leaving the transceiver/MAC.
3. **Top-down microarchitecture analysis (TMA).** How `Frontend_Bound / Bad_Speculation / Backend_Bound / Retiring` is derived from pipeline slots, and how to act on each.

---

## Sources

### Papers
- Aquilina, Budish, O'Neill, *Quantifying the High-Frequency Trading "Arms Race"*, QJE 2022: https://www.nber.org/papers/w29011 · FCA OP50: https://www.fca.org.uk/publications/occasional-papers/occasional-paper-no-50-quantifying-high-frequency-trading-arms-race-new-methodology · BIS WP 955: https://www.bis.org/publ/work955.pdf
- Budish, Cramton, Shim, *The HFT Arms Race*, QJE 2015: https://ideas.repec.org/a/oup/qjecon/v130y2015i4p1547-1621.html
- Neugebauer et al., *Understanding PCIe performance for end host networking*, SIGCOMM 2018: https://www.cl.cam.ac.uk/teaching/1011/R02/papers/p327-neugebauer.pdf
- Bhattacherjee et al., cISP: https://courses.cs.duke.edu/fall21/compsci514/internal/readings/BhattacherjeeAABSTACGLMS22.pdf
- Castillon du Perron et al., *Understanding Delays in AF_XDP-based Applications*, ICC 2024: https://arxiv.org/abs/2402.10513
- Sun et al., *Demystifying CXL Memory*, MICRO 2023: https://arxiv.org/abs/2303.15375
- LightTrader, HPCA 2023: https://rebellions.ai/wp-content/uploads/2023/11/RebellionsIONHPCA23_LightTrader.pdf
- LOBIN, arXiv 2608.02424: https://arxiv.org/abs/2608.02424
- FinHardBench, arXiv 2608.00909: https://arxiv.org/abs/2608.00909
- Bilokon & Gunduz, arXiv 2309.04259: https://arxiv.org/abs/2309.04259
- Yang et al., NanoLog, USENIX ATC 2018: https://www.usenix.org/conference/atc18/presentation/yang-stephen
- Curtsinger & Berger, Stabilizer, ASPLOS 2013: https://people.cs.umass.edu/~emery/pubs/stabilizer-asplos13.pdf
- Mytkowicz et al., *Producing Wrong Data…*, ASPLOS 2009: https://evaluate.inf.usi.ch/biblio/keyword/7
- GenMC, PLDI 2019: https://www.mpi-sws.org/~michalis/papers/pldi2019-genmc.pdf
- Drepper, *What Every Programmer Should Know About Memory*: https://www.akkadia.org/drepper/cpumemory.pdf
- LMAX Disruptor paper: https://lmax-exchange.github.io/disruptor/disruptor.html
- Paoloni, *How to Benchmark Code Execution Times on Intel*: https://cis.temple.edu/~qzeng/cis3207-spring18/files/ia-32-ia-64-benchmark-code-execution-paper.pdf
- Aramian & Comerton-Forde, *Are Speed Bumps Beneficial?*: https://static1.squarespace.com/static/6310c0b9bb63a25599f4418c/t/65d4835e10387e459f6266a2/1708426079078/SpeedBumpFinal20240212.pdf

### Talks & standards
- Cook, CppCon 2017 slides: https://github.com/CppCon/CppCon2017/blob/master/Presentations/When%20a%20Microsecond%20Is%20an%20Eternity/When%20a%20Microsecond%20Is%20an%20Eternity%20-%20Carl%20Cook%20-%20CppCon%202017.pdf
- Gross, CppCon 2024 slides: https://github.com/CppCon/CppCon2024/blob/main/Presentations/When_Nanoseconds_Matter.pdf · https://cppcon.org/2024-keynote-david-gross/
- Gross, Meeting C++ 2022: https://meetingcpp.com/2022/Talks/items/Trading_at_light_speed__designing_low_latency_systems_in_Cpp.html
- Tene, *How NOT to Measure Latency*: https://qconsf.com/sf2012/dl/qcon-sanfran-2012/slides/GilTene_HowNotToMeasureLatency.pdf · https://groups.google.com/g/mechanical-sympathy/c/icNZJejUHfE/m/BfDekfBEs_sJ
- P2590R2 `start_lifetime_as`: https://open-std.org/jtc1/sc22/wg21/docs/papers/2022/p2590r2.pdf
- P0154 interference size: https://open-std.org/Jtc1/sc22/wg21/docs/papers/2016/p0154r1.html
- P2544 exceptions: https://open-std.org/JTC1/SC22/WG21/docs/papers/2022/p2544r0.html
- C++26: https://en.wikipedia.org/wiki/C%2B%2B26
- STAC Summit 2017 Solarflare: https://docs.stacresearch.com/system/files/resource/files/STAC-Summit-5-Jun-2017-Solarflare.pdf
- STAC AMD240422: https://docs.stacresearch.com/news/AMD240422 · Exegy: https://www.exegy.com/exegy-amd-new-record/
- SEC Knight Capital order 34-70694: https://www.sec.gov/litigation/admin/2013/34-70694.pdf

### Code & docs
- Onload / ef_vi: https://github.com/Xilinx-CNS/onload · efsink.c: https://raw.githubusercontent.com/Xilinx-CNS/onload/master/src/tests/ef_vi/efsink.c
- ExaNIC: https://github.com/cisco/exanic-software
- Rigtorp low-latency guide: https://rigtorp.se/low-latency-guide/ · ring buffer: https://rigtorp.se/ringbuffer/ · SPSCQueue: https://github.com/rigtorp/SPSCQueue
- SBE: https://github.com/real-logic/simple-binary-encoding · Aeron: https://github.com/real-logic/aeron
- Quill: https://github.com/odygrd/quill · fmtlog: https://github.com/MengRao/fmtlog
- HdrHistogram: https://github.com/HdrHistogram/HdrHistogram
- BOLT: https://github.com/llvm/llvm-project/tree/main/bolt
- papipp: https://github.com/david-grs/papipp
- Linux timestamping: https://www.kernel.org/doc/html/latest/networking/timestamping.html · no_hz: https://docs.kernel.org/timers/no_hz.html · intel_idle: https://docs.kernel.org/6.19/admin-guide/pm/intel_idle.html · hwlat: https://www.kernel.org/doc/Documentation/trace/hwlat_detector.rst
- 7-cpu Skylake: https://www.7-cpu.com/cpu/Skylake.html
- Intel denormals: https://www.intel.com/content/www/us/en/docs/onemkl/developer-guide-windows/2025-1/operating-on-denormals.html
- Arm C++ memory model: https://learn.arm.com/learning-paths/servers-and-cloud-computing/arm-cpp-memory-model/3/

### Articles
- HRT huge pages: https://www.hudsonrivertrading.com/hrtbeat/low-latency-optimization-part-1/
- Jane Street performance engineering: https://www.janestreet.com/performance-engineering/
- IMC job page: https://www.imc.com/us/careers/jobs/4634204101
- Brendan Gregg KPTI: https://brendangregg.com/blog/2018-02-09/kpti-kaiser-meltdown-performance.html
- Travis Downs AVX-512: https://travisdowns.github.io/blog/2020/08/19/icl-avx512-freq.html
- Tsuna context switches: https://blog.tsunanet.net/2010/11/how-long-does-it-take-to-make-context.html
- The Register microwave vs fibre: https://www.theregister.com/2013/02/27/microwave_versus_fibre/
- Tail at Scale summary: https://blog.acolyer.org/2015/01/15/the-tail-at-scale/
- Phoronix io_uring zcrx: https://www.phoronix.com/news/Linux-6.15-IO_uring · C6: https://www.phoronix.com/news/Intel-C6-Ice-Lake-Xeon-Idle
- CME / Google Cloud: https://www.cmegroup.com/media-room/press-releases/2024/6/26/cme_group_and_googlecloudannouncenewchicagoareaprivatecloudregio.html
- eFinancialCareers Rust anecdote: https://www.efinancialcareers.com/news/C-vs-Rust-High-Frequency-Trading-Hell
