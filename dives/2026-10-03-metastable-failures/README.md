# Metastable failures: why a system stays down after the trigger is gone

**Distributed systems / system design · Metastable failures: retry storms, sustaining feedback loops, hidden capacity · hard · 2026-10-03**

> You asked for "system design". That is a category, so this dive narrows to one mechanism inside it that every large system meets eventually: the **metastable failure**. A short blip knocks the system over, the blip goes away, and the system *stays* down because of something it does to itself.

---

## 0b. Plain English first

### Explain it simply

Picture a popular sandwich shop with one cook who can make 100 sandwiches an hour. On a normal lunch rush about 70 people an hour come in, so the cook keeps up and nobody waits long. Customers have a rule: if no sandwich arrives within ten minutes, they assume the order got lost and **order again**, without cancelling the first one. On a normal day nobody waits ten minutes, so the rule never fires.

Now the stove goes out for fifteen minutes. Orders pile up. When the stove comes back, every waiting customer has already hit the ten-minute mark and re-ordered, so the cook faces two or three tickets for each hungry person. The cook works flat out, but by the time any sandwich is ready its customer has given up and placed another order. The kitchen is 100% busy and **nobody eats**. The stove is fine; it's the re-ordering rule that keeps the kitchen drowning. That is a metastable failure: a short trigger (stove out) pushes the system into a bad state that a **feedback loop** (re-ordering) keeps going after the trigger is gone. The only way out is to do something drastic: turn customers away for a while, throw out stale tickets, or stop accepting duplicate orders.

### Everyday example

The shop normally takes 70 orders an hour and can cook 100. At 12:20 the stove dies for 10 minutes; about 12 orders pile up. At 12:30 the stove is back. The oldest tickets are now 10 minutes old, so those customers re-order, adding 12 more tickets on top of the 12 pending, while new customers keep arriving. The cook starts on the oldest ticket. By the time it's done its customer has left (and re-ordered), so the sandwich goes in the bin. Every ticket the cook picks up is already "dead", because the line is longer than ten minutes. The shop now gets roughly 210 tickets an hour (70 people × up to 3 tries) against capacity for 100. The line never gets shorter. At 13:30, an hour after the stove was fixed, the cook is still busy and still nobody is eating. The manager finally announces "we're discarding every ticket older than ten minutes": the cook skips the dead tickets in seconds, the line clears, and the shop is back to normal within a minute.

**Now the same thing, technically.**

---

## 1. Bare-minimum context

- **Offered load λ vs capacity μ**: requests/s arriving vs requests/s the server can finish. Utilisation ρ = λ/μ. ([Brooker, "Latency sneaks up on you"](https://brooker.co.za/blog/2021/08/05/utilization.html))
- **Queueing delay explodes near ρ → 1**: for M/M/1, mean number in system = ρ/(1−ρ): 1 at ρ=0.5, 99 at ρ=0.99.
- **Little's law**: N = λW. Concurrency equals arrival rate times time in system, so latency up means more in flight.
- **Goodput ≠ throughput**: goodput counts only work that finished in time for someone to use it. ([Amazon Builders' Library, load shedding](https://builder.aws.com/content/3Eun1EEyX6p2e3VYNyRLSJzLuMV/using-load-shedding-to-avoid-overload))
- **Open vs closed system**: in an open system, new requests keep arriving regardless of how slow you are (internet traffic). In a closed system, a fixed set of clients waits for each reply before sending the next (most benchmarks). ([Schroeder et al., NSDI'06](https://www.usenix.org/conference/nsdi-06/open-versus-closed-cautionary-tale))
- **Timeout + retry**: the client gives up after T and sends another attempt. The server usually never finds out about the first one.

## 1b. Real-world context

### What it is, in one paragraph
A metastable failure, in the words of the paper that named it, occurs "in open systems with an uncontrolled source of load where a trigger causes the system to enter a bad state that persists even when the trigger is removed. In this state the goodput … is unusably low, and there is a **sustaining effect**, often involving work amplification or decreased overall efficiency, that prevents the system from leaving the bad state" ([Bronson et al., HotOS'21](https://sigops.org/s/conferences/hotos/2021/papers/hotos21-s11-bronson.pdf)). The name comes from physics: a ball sitting in a shallow dip is stable until a push sends it over the lip, after which it settles somewhere worse and won't come back by itself.

### Why it matters

- Metastable failures are the long outages. In the OSDI'22 study of 22 incidents, outages lasted **1.5 to 73.53 hours**, and 4–10 hours was the most common range. The study also found that **at least 4 of 15 major AWS outages** in the previous decade were metastable ([Huang et al., OSDI'22](https://www.usenix.org/system/files/osdi22-huang-lexiang.pdf)).
- The root cause gets misdiagnosed. "It is common for an outage that involves a metastable failure to be initially blamed on the trigger, but the true root cause is the sustaining effect" (Bronson). Teams fix the bad deploy, the outage repeats with a different trigger, and the loop was never touched.
- The loops are built from features that help on a normal day: retries, caches, failover, aggressive timeouts, connection reuse. You add them for reliability and efficiency, and they make up the trap.
- Before the name existed the pattern was already known as **congestion collapse**. Nagle, RFC 896 (1984): "This condition is stable. Once the saturation point has been reached … the network will continue to operate in a degraded condition." Jacobson's 1988 TCP fixes (exponential retransmit backoff, slow start, AIMD) were the networking cure. Distributed services rebuilt the same disease one layer up.

### Where it shows up (real incidents)

| System | Trigger | Sustaining loop |
|---|---|---|
| **AWS us-east-1, Oct 19–20 2025** | DynamoDB DNS race left an empty record | EC2's DropletWorkflow Manager "entered a state of congestive collapse": re-establishing leases took longer than the lease timeout, so work was re-queued forever. Fixed by throttling incoming work and restarting hosts selectively ([AWS](https://aws.amazon.com/message/101925/)) |
| **AWS us-east-1, Dec 7 2021** | Automated scaling on the internal network | "a large surge of connection activity"; a latent bug "prevented these clients from adequately backing off" ([AWS](https://aws.amazon.com/message/12721/)) |
| **AWS Kinesis, Nov 25 2020** | Capacity add pushed servers past OS thread limit | Shard-map caches had to rebuild while serving traffic; servers came back "at the rate of a few hundred per hour", about 17 h total ([AWS](https://aws.amazon.com/message/11201/)) |
| **Slack, Jan 4 2021** | Post-holiday reconnect surge hit an AWS Transit Gateway | Threads waiting on the network looked like idle CPU, so autoscaling scaled *down*; the later 1,200-server scale-up broke provisioning ([Slack](https://slack.engineering/slacks-outage-on-january-4th-2021/)) |
| **Slack, Feb 22 2022** | Consul agent rollout restarted memcached nodes | Cold cache led to scatter queries across every Vitess shard. Clients already had backoff with jitter, yet "automated retries still contributed to the load" ([Slack](https://slack.engineering/slacks-incident-on-2-22-22/)) |
| **Google Cloud, Jun 12 2025** | Bad Service Control push, then restart | Restarting tasks "created a herd effect" on a Spanner table because there was no randomized backoff ([GCP](https://status.cloud.google.com/incidents/ow5i3PPK96RduMcb1SsW)) |
| **Facebook link imbalance (2014)** | A burst of cache misses | The MRU connection pool kept picking the most congested link. It "defied explanation for more than two years"; the fix was one line of pool policy ([FB eng](https://engineering.fb.com/2014/11/14/production-engineering/solving-the-mystery-of-link-imbalance-a-metastable-failure-state-at-scale/)) |
| **Twitter GC (OSDI'22 §4)** | Load test peak | Queue grows → GC pressure → slower jobs → queue grows. Stayed below SLO with load 20% *lower* than before, "until the service is restarted" |

### How people defend against it (what you actually configure)

```json
// gRPC service config: retries + retry throttling (gRPC proposal A6)
{"methodConfig":[{"name":[{"service":"pkg.Svc"}],
  "retryPolicy":{"maxAttempts":4,"initialBackoff":"0.1s","maxBackoff":"1s",
                 "backoffMultiplier":2,"retryableStatusCodes":["UNAVAILABLE"]}}],
 "retryThrottling":{"maxTokens":10,"tokenRatio":0.1}}
```
Each server name has a token count starting at `maxTokens`. A failure takes away 1, a success adds `tokenRatio`, and retries stop while the count is ≤ `maxTokens/2`. Typical defaults elsewhere:

- **Envoy** `retry_budget`: `budget_percent` 20%, `min_retry_concurrency` 3. Envoy recommends budgets over the static `max_retries` (default 3) ([Envoy docs](https://www.envoyproxy.io/docs/envoy/latest/api-v3/config/cluster/v3/circuit_breaker.proto)).
- **Finagle `RetryBudget`**: `percentCanRetry` 0.2, `minRetriesPerSec` 10, `ttl` 10 s ([source](https://github.com/twitter/finagle/blob/develop/finagle-core/src/main/scala/com/twitter/finagle/service/RetryBudget.scala)).
- **AWS SDKs** (standard mode): 3 attempts and a 500-token retry quota. botocore/Go v2 charge 5 tokens per retry and 10 per timeout retry. An opt-in 2026 update (`AWS_NEW_RETRIES_2026=true`) charges 14 per transient retry so the quota engages sooner ([AWS blog](https://aws.amazon.com/blogs/developer/announcing-updated-retry-behavior-for-aws-sdks-and-tools/), [botocore](https://github.com/boto/botocore/blob/develop/botocore/retries/standard.py)).
- **Google SRE**: at most 3 attempts per request, per-client retries below 10% of requests, retry only at the layer directly above the failure, and return "overloaded; don't retry" upward ([SRE book](https://sre.google/sre-book/handling-overload/)).
- **Backoff**: full jitter, `sleep = random(0, min(cap, base·2^attempt))` ([AWS Architecture blog, 2015](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)).

### When to reach for which defense

| Use it | Skip it / beware |
|---|---|
| **Retry budget (ratio)** on every RPC client: cheap, bounds amplification to about 1.1–1.2× | A fixed `max_retries` count multiplies across layers |
| **Deadline propagation + drop expired work at dequeue**: cheapest way to stop burning capacity on dead requests | Only works if the protocol carries the deadline |
| **Adaptive LIFO + CoDel** on queue-heavy servers | Starves old requests; unfair under sustained overload |
| **Adaptive concurrency limits** (Netflix, Envoy, Uber Cinnamon) on large fleets | Can oscillate; minRTT probing causes periodic 503 spikes |
| **Circuit breaker**: zero added load at 100% failure | Turns partial failure into total failure in sharded systems (Brooker) |
| **Autoscaling** to keep headroom (stay out of the vulnerable band) | Too slow for minute-scale loops; can scale on the wrong signal (Slack 2021) |

### Who should care
Backend engineers who write retry and timeout code. SRE/infra owners of load balancers, meshes and autoscalers. Database and cache owners, since a cold cache is the classic sustaining effect. Platform and control-plane teams: the AWS 2025 outage was a control-plane recovery path collapsing. Anyone serving LLMs, where KV-cache preemption plus client retries looks like the same loop (still a research gap, see §11b).

---

> ## Technical deep dive

## 2. The one-liner, and what it hides

**"Retry storms take systems down."**

That sentence hides:

1. **Why the system stays down after the trigger is gone.** Ordinary overload ends when the load ends. This one has two equilibria (§6).
2. **That the server is 100% busy while goodput is zero.** The work is real. It's just useless, because it's served after the client has given up (§5).
3. **That vulnerability is invisible in normal metrics.** At 70% CPU the system looks healthy and is one 1.2-second hiccup from collapse. "Hidden capacity" can be 10× below advertised capacity (§6).
4. **That retries are only one of several loops.** Cold caches, GC, slow error paths, MRU connection pools and health checks that remove capacity all work the same way (§9).
5. **That the fix has to break the loop, not the trigger**, and naive fixes can create the next loop (AWS SimpleDB → DynamoDB, Spotify logging; §9).

## 3. The problem

Production systems run in what Bronson calls the **vulnerable state**, deliberately: "many production systems choose to run in the vulnerable state all the time because it has much higher efficiency than the stable state." HotOS'21's worked example:

- A database answers in under 100 ms below 300 QPS. Above that, latency is "an order of magnitude worse".
- The app sends a query plus 1 retry after a 1 s timeout, and normally runs at **280 QPS** (93% of capacity, looks healthy).
- A 10 s network blip. Afterwards, clients send **560 QPS** (every query plus its retry) and every query times out: zero goodput.
- Recovery requires load **under 150 QPS** (= 300/2), or retries capped under 20 QPS (280+20 = 300).

So the system was stable only below 150 QPS, half of what it could serve, and nobody knew, because the 150–300 band behaves perfectly until something bumps it.

The look-aside cache version is worse. With a 90% hit rate the app serves 3,000 QPS against a DB that handles 300. Lose the cache and the DB gets 10× its capacity. The app times out before misses can refill the cache, so the cache never warms. **Advertised capacity 3,000, hidden capacity 300.**

## 4. Mental model

**A ball on a landscape with two valleys.** The healthy valley is shallow and sits higher; the collapsed valley is deep. Load tilts the landscape: at low load the bad valley doesn't exist, and as load rises it appears and the wall between the valleys gets lower (the vulnerable band). A trigger is a kick. A small kick at low tilt rolls back; the same kick at high tilt goes over the wall. Once the ball is in the deep valley, removing the kick does nothing. You have to change the landscape (cut load, cap retries) or carry the ball out (restart, flush queues).

**Where the analogy breaks:**

- The landscape isn't fixed. The bad valley is *created* by the system's own policies (retry count, timeout, cache), so you can engineer it away. A physical potential doesn't care about your config.
- Real systems are stochastic and multi-dimensional. Isaacs et al. model the state as (queue length, number of requests waiting to retry), and noise alone can tip the system across the boundary without any discrete trigger.
- Some metastable faults aren't "stuck low" at all. Farahbakhsh et al. (2026) show oscillating metastable states, such as cluster membership flapping, which have no single bad valley.

## 5. The mechanism, traced

Replaying the sandwich shop with `metastable_sim.py` (in this folder). One server, μ = 100 req/s, FIFO queue, Poisson arrivals λ = 70/s, client timeout T = 1 s, up to 2 retries (3 attempts). The server doesn't know when a client has given up.

```
t (s)   event                                queue    attempts/s  served/s  goodput/s
------  -----------------------------------  -------  ----------  --------  ---------
0-20    steady state, ρ = 0.70               ~1-3     ~72         ~72       ~72
20-30   TRIGGER: server capacity -> 0         +72/s   rises        0          0
          queue wait passes T after ~1.4 s;
          timed-out requests get re-enqueued
          as attempt 2, the old copy stays queued
30      trigger removed, μ back to 100       ~1,870   ~210         100         0
30-120  every dequeued attempt is >1 s old:   +110/s   ~210         100         0
          server works on dead requests,
          clients time out, retry, enqueue more
120     still stuck. queue ≈ 11,800          11,826   210.1        100.0       0.0
```

**One request, end to end, at t = 40 s (10 s after the trigger is gone):**

```
 client C                          server queue (FIFO, ~3,000 deep)              server
 ───────                           ───────────────────────────────              ──────
 40.00 send req#3000 attempt 1 ──► [ ...~3,000 older attempts... | #3000a1 ]
 41.00 timeout, send attempt 2 ──► [ ...                    | #3000a1 ... #3000a2 ]
 42.00 timeout, send attempt 3 ──► [ ...                    | #3000a2 ... #3000a3 ]
 43.00 timeout, GIVE UP (no attempts left)
 ~70                                                       dequeue #3000a1 ─► serve (10 ms CPU)
                                                           client gone → WASTED
 ~71                                                       #3000a2 → WASTED
 ~72                                                       #3000a3 → WASTED
```

Queue depth from the sim: 1,871 at t=30, 2,971 at t=40, 5,191 at t=60, so a fresh attempt waits ~30 s for a 1 s timeout. Each user request costs the server 3 units of work and produces 0 goodput. Attempts arrive at 3 × 70 = 210/s against service at 100/s, so the queue grows by ~110/s, and the trigger is no longer needed to keep it that way.

**What breaks the loop** (same trigger, one change each; real output of `python3 metastable_sim.py`):

```
scenario                         goodput last 20 s   healthy again at   verdict
baseline (λ=70, 2 retries, FIFO)       0.0/s             never          STUCK
lower load λ=25 (< μ/3 = 33)          24.4/s             t=56 s         recovered
edge of band λ=30                     16.6/s             t=111 s        recovered, slowly
trigger only 0.5 s                    69.8/s             t=21 s         recovered
no retries                            69.8/s             t=51 s         recovered
retry budget 10%                      69.8/s             t=64 s         recovered
deadline-aware dequeue (drop expired) 69.8/s             t=30 s         recovered at once
LIFO queue                            69.8/s             t=30 s         recovered at once
```

Read the rows as the theory in §6:

- **No retries** recovers, but takes 21 s. The 700-request backlog drains at μ − λ = 30/s ≈ 23 s, all of it wasted work.
- **Deadline-aware dequeue** recovers almost immediately because skipping dead requests costs nothing. LIFO does the same thing differently: the freshest request, whose client is still waiting, gets served first.
- **λ = 30 is just under μ/3** and escapes only after ~80 s, because the drain rate μ − 3λ is only 10/s.
- **Minimum trigger that sticks** (scan in the sim): 1.5 s outage at λ=50, 1.2 s at λ=70, 1.1 s at λ=90. Higher load means a smaller kick is enough.

## 6. The math

### 6.1 Amplification from retries

Let each attempt fail (time out) independently with probability *p*, and let the client make up to *r* retries. Expected attempts per user request:

$$E[A] = \sum_{i=0}^{r} p^{i} = \frac{1-p^{r+1}}{1-p}$$

→ **in plain terms:** while things are healthy (p ≈ 0) each request costs ~1 attempt. As failure approaches certainty (p → 1) each request costs r+1 attempts.

Offered load at the server:

$$\lambda_{\text{eff}}(p) = \lambda \cdot \frac{1-p^{r+1}}{1-p}, \qquad \lambda_{\text{eff}}(0)=\lambda,\quad \lambda_{\text{eff}}(1)=(r+1)\lambda$$

With *d* layers each retrying independently, the factors multiply: (r+1)^d. Google's SRE book: 3 layers × 4 attempts = 4³ = **64×** on the database. AWS's Builders' Library cites **243×** for a five-deep stack, which is 3⁵ (three attempts per layer). Some summaries describe that as "three retries per layer", but 3 *retries* would give 4⁵ = 1,024. ([SRE](https://sre.google/sre-book/addressing-cascading-failures/))

### 6.2 Two fixed points (bistability)

The failure probability is itself a function of load. With FIFO and timeout T, an attempt fails if its queueing delay exceeds T. When λ_eff > μ the queue grows without bound, so delay → ∞ and p → 1. When λ_eff < μ the queue is short, so delay ≪ T and p ≈ 0. Look for self-consistent states p* = f(λ_eff(p*)):

- **Healthy:** p ≈ 0 ⇒ λ_eff ≈ λ. Self-consistent iff **λ < μ**.
- **Collapsed:** p ≈ 1 ⇒ λ_eff ≈ (r+1)λ. Self-consistent iff **(r+1)λ > μ**.

Both hold when

$$\frac{\mu}{r+1} \;<\; \lambda \;<\; \mu$$

→ **in plain terms:** in this band the system has two stable states, and nothing in the current load tells you which one you're in. Only history (whether something kicked you) decides. Below μ/(r+1) the collapsed state can't sustain itself. With μ=100 and r=2 the band is 33–100 req/s, exactly where the sim flips. (This fixed-point framing is my synthesis. HotOS'21's Fig. 2 shows the same band, and Brooker called it "bistability" in 2019.)

**Why this form and not a simpler one:** a single-equilibrium model ("load > capacity ⇒ slow") can't explain why cutting load from 70 back to 70 doesn't fix anything. You need a *load-dependent* amplification (p depends on load, and load depends on p). That loop is the sustaining effect in algebra.

### 6.3 OSDI'22's general version

Huang et al. measure load L and capacity C in abstract resource units (RU/s). "Organic" quantities (L_org, C_org) include the trigger but not the amplification; "system" quantities (L_sys, C_sys) include both. They define two amplification factors:

$$\alpha_L(t) = \frac{L_{\text{sys}}(t)}{L_{\text{org}}(t)} \le w_L^{*}, \qquad \alpha_C(t) = \frac{C_{\text{sys}}(t)}{C_{\text{org}}(t)} \ge \frac{1}{w_C^{*}}$$

- w*_L is the worst-case workload amplification: retries, or more expensive requests such as error logging.
- w*_C is the worst-case capacity degradation: GC, or a cache whose loss pushes the hit traffic onto the DB.

**Theorem 2 (stable region):**

$$C_{\text{stable}} = \frac{C_{\text{norm}}}{w_L^{*}\cdot w_C^{*}}$$

If normal load L_norm < C_stable, no trigger can cause a metastable failure.

→ **in plain terms:** your real safe capacity is your advertised capacity divided by the worst amplification your own policies can produce. Check it against the examples: 1 retry → w*_L=2 → 300/2 = **150 QPS** (HotOS DB example). Cache with 90% hit rate → w*_C = 10 → 3000/10 = **300 QPS** hidden capacity. "A policy with at most two retries will not amplify the work more than three times, while the policy with no cap effectively leaves the system with no stable region" (OSDI'22).

**Theorem 1 (necessary trigger):** a trigger can only matter if m_trigL + m_trigC ≥ C_norm − L_norm, i.e. the load spike plus the capacity drop must eat the whole headroom.

**Theorem 3 (degrees of vulnerability):** if w_L(Δt)·w_C(Δt) < C_norm/L_norm, a trigger lasting Δt can't tip the system. The amplification functions grow with trigger duration (retries only start after the timeout), so vulnerability is a *region* in (load × trigger size × trigger duration), not a yes/no.

→ **in plain terms:** this is why 78% CPU loss for 10 s recovered and 80% for 10 s didn't in their MongoDB reproduction, and why 80% for 9 s also recovered: "a 2%-decrease in available CPU or a 1-second increase in duration separated successful recovery from a metastable failure."

### 6.4 How long recovery takes

Once the loop is broken, a backlog B drains at the spare rate:

$$t_{\text{drain}} = \frac{B}{\mu - \lambda_{\text{eff}}}$$

→ **in plain terms:** near the edge of the band the denominator goes to zero and recovery time blows up. That is the sim's λ=30 run (μ − 3λ = 10/s, ~80 s). Amazon's "insurmountable backlog" article gives the operational version: a one-hour outage needs double capacity for another hour to drain. Dropping expired work changes the numerator from "all queued work" to "only live work", which is why deadline-aware dequeue recovers in ~0 s.

### 6.5 The 2025 formalisation: metastability as a CTMC property

Isaacs, Alvaro, Majumdar et al. (HotOS'25; arXiv 2510.03551) model a server as a continuous-time Markov chain over state (q, o) = (queue length, "orbit" = requests waiting to retry). Their definition: a CTMC is metastable if it has ≥ 2 disjoint sets of states such that the expected time to move *between* sets is much larger than the time to mix *within* a set. Spectrally, the generator matrix has a large gap after its first few eigenvalues, so the slow modes are the "valleys". In their toy model (1 thread at 10 RPS, queue bound 150, 5 RPS offered, 5 s timeout, 5 retries) the vector field shows a tipping region around **q ≈ 40 with ≥ 30 in orbit**.

## 7. Why it works (why the trap holds, and why the cures cure)

**The core insight:** the sustaining effect makes the cost of serving a request grow with how badly the system is doing. Healthy systems have per-request cost about constant. Metastable ones have cost(state) increasing in "badness" (more attempts per request, lower cache hit rate, more GC per job, more expensive error paths). Once badness pushes cost × load above capacity, badness grows on its own.

**Ablation: remove each piece of the trap:**

| Remove | Result | Why |
|---|---|---|
| Retries (r=0) | Recovers (sim t=51 s) | w*_L=1 ⇒ C_stable = C_norm; the band disappears |
| Timeouts on the *server* side (serve dead work) | Recovers instantly if the server drops expired attempts | Effective cost of a dead request → 0, so the loop can't burn capacity |
| FIFO (use LIFO) | Recovers instantly | Newest request has a live client, so p drops at once and the fixed point moves |
| Open-loop arrivals (closed system) | Self-limits | Clients wait for replies, so load falls as latency rises; this is why closed benchmarks such as YCSB and TPC-C can't show the failure (Brooker, ICPE'25) |
| The trigger | **Nothing changes** | That's the definition |

**Which cures work and why:**

- **Retry budgets** cap w*_L near 1.1–1.2 regardless of p, so the band shrinks to (μ/1.1, μ).
- **Client-side adaptive throttling** (Google): reject locally with probability max(0, (requests − K·accepts)/(requests+1)), with K=2. "Backends end up rejecting one request for each request they actually process": it bounds wasted backend work at 1:1.
- **CoDel-style queues**: when the queue hasn't been empty in N ms, cut the queue timeout from N to M ms (Facebook "Fail at Scale"). Requests that will miss their deadline get dropped before burning CPU.
- **Constant work** (AWS Route 53 health checks, Hyperplane): every cycle pushes the full configuration, whether or not anything changed, so there's no mode where work grows with how bad things are.

## 8. Design knobs and alternatives

| Knob | Lower | Higher | Note |
|---|---|---|---|
| Max attempts r+1 | Less amplification, more user-visible errors on transient blips | Band widens: lower bound μ/(r+1) falls | Google: ≤3 attempts; gRPC caps at 5 |
| Retry budget ratio | Safer under overload | Better transient masking | Finagle/Envoy 20%, Google 10% |
| Client timeout T | Faster failover in healthy state; more false timeouts, so earlier collapse | Fewer false timeouts; slower detection | Brooker: pick T at the p99.9 of downstream latency. OSDI'22 cache test: 2 s less vulnerable than 1 s |
| Queue bound / queue timeout | Sheds early, low wasted work | Absorbs bursts | SRE: queue ≤ 50% of thread pool |
| Cache hit rate | | Higher hit rate makes each RPS less vulnerable *but* lets you run at higher RPS, where vulnerability is larger | OSDI'22 Fig. 6c, the efficiency trap |
| Backoff | | Helps only if it reduces *total* work | "In open systems, deferring load does not work" (Brooker 2022) |
| Headroom (L_norm/C_norm) | Efficient, vulnerable | Robust, expensive | The core tradeoff; organisations optimise toward vulnerability |

**Competing approaches:**

- **Circuit breaker vs token-bucket retry budget.** Brooker's simulation favours the bucket: it "behaves like N retries when failure rates are low, and 'some percent retries' when the failure rate is higher", with no mode switching. Breakers add zero load at 100% failure but "are designed to turn partial failures into complete failures", which is bad for sharded backends.
- **Static limits vs adaptive concurrency** (Netflix Vegas/Gradient2, Envoy gradient controller, Uber Cinnamon with PID on shed ratio + modified-Vegas auto-tuner). Adaptive wins on fleets of thousands of services where hand tuning doesn't scale. Uber reports Cinnamon kept p99 ≈ 500 ms near capacity where its CoDel-based predecessor's goodput fell to 40%.
- **Server-side shedding vs end-to-end shedding.** Shedding at a deep service still wastes the upstream work. TopFull (SIGCOMM'24) and Rajomon (NSDI'25) push admission control to the graph entry, or price it through the graph.

## 9. Where it breaks

**Other sustaining loops besides retries:**

- **Look-aside cache:** cold cache → DB overload → app timeouts → fills never land → cache stays cold. Kinesis 2020 and Slack 2022 both had this cache rebuild competing with serving.
- **GC death spiral:** queue → heap → GC → slower jobs → longer queue (Twitter, OSDI'22). Brooker (2024): the loop needs unbounded concurrency, so a concurrency limit kills it.
- **Slow error paths:** stack traces, reverse DNS of the client, synchronous logging. Error handling consumes the same resource whose shortage caused the errors.
- **Health checks that remove capacity:** overloaded hosts fail checks and get pulled, so the rest get more load. AWS Oct 2025 NLB health-check flapping until automatic failover was disabled. SRE book: "health-checking itself makes the service unhealthy".
- **Autoscaling on the wrong signal:** network-blocked threads look idle (Slack 2021). A mass scale-up then overloads the provisioning control plane.
- **Connection/TLS storms on reconnect** (AWS Dec 2021).
- **MRU connection pools:** latency-sorted reuse concentrates traffic on the slowest link (FB 2014).

**Misconceptions:**

> **"Remove the trigger and it'll recover."** The definition says otherwise. OSDI'22 reports a Cassandra cluster at only 10–30% load that still didn't recover after the trigger was removed. AWS 2025: EC2 took hours after the DNS fix.

> **"Backoff with jitter fixes retry storms."** Backoff spreads load in time; it doesn't remove it. Slack 2022 had exponential backoff *with* jitter and retries "still contributed to the load". Only budgets and caps reduce total work.

> **"Load testing at peak will find it."** Peak load in the healthy valley looks great. You have to test with a trigger *and* at production scale: Bronson notes loop strength "is affected by constant factors that vary with scale, so small scale tests don't provide much confidence." Most benchmarks are also closed-loop, which hides the failure entirely.

> **"Our fix will prevent recurrence."** "Fix to break" (OSDI'22 §6.3): after the AWS SimpleDB incident, servers were made to retry the lock service *indefinitely*, and a similar DynamoDB metastable failure followed. Spotify added error-path logging after SPF1, which made every retry in SPF2 more expensive.

**Scaling limits of the defenses:**

- Retry budgets are per client. With 10,000 clients each allowed 10 retries/s minimum, the floor alone is 100k retries/s.
- Adaptive limiters estimate minRTT by periodically pinning concurrency low, which produces synchronised 503 spikes unless jittered (Envoy adds jitter for this).
- Load shedding is used in more than 50% of incidents, but "it is hard to know just how much the load needs to be reduced" (OSDI'22), so operators fall back to reboots.

## 10. In the wild (how real systems deviate from the textbook)

- **AWS SDKs:** a token-bucket retry quota rather than a pure ratio. Timeouts cost double (10 vs 5) because a timeout already burned server work. The 2026 opt-in update raises the transient-retry cost to 14 so the quota drains at ~22% sustained failure instead of later. Adaptive mode adds a *client-side* rate limiter that can delay first attempts, which AWS does not recommend as a default.
- **gRPC:** hedging and retries share one throttle. Servers can push back with `grpc-retry-pushback-ms`, and a negative value means "don't retry".
- **Facebook:** adaptive LIFO (FIFO normally, LIFO when a queue forms) plus CoDel timeouts. Memcache **leases** hand out one fill token per key every 10 s, cutting peak DB rate from 17K/s to 1.3K/s in their measurement. A **gutter pool** of ~1% of servers absorbs load from failed servers. Open-source descendant: HBase `AdaptiveLifoCoDelCallQueue`.
- **Google:** criticality classes (CRITICAL_PLUS … SHEDDABLE), deadline propagation, and the client-side throttle with K=2.
- **AWS architecture:** cells and shuffle sharding (Route 53: 2,048 virtual name servers, 4 per domain, ~730 billion combinations) limit the blast radius. **Constant work** removes modes entirely. **Static stability** pre-provisions so a recovery path never has to scale up under stress.
- **AWS post-2025:** throttling "based on the size of the waiting queue" for EC2 workflows, velocity control on NLB health-check failover, and a dedicated recovery-path scale test. The lesson: recovery paths need their own load testing.

## 11. Frontier (what's new, 2024–2026)

1. **Analyzing Metastable Failures**: Isaacs, Alvaro, Majumdar, Muniswamy-Reddy, Salamati, Soudjani (AWS / UCSC / MPI-SWS). *HotOS 2025.* A Python DSL (servers, queues, thread pools, timeouts, retry policies) feeds a ladder of tools: CTMC (ms–s), discrete-event simulation (minutes), emulator on the production RPC stack (hours), stress test. The abstract tools say where to look and the concrete ones confirm. Being applied to AWS control planes to find tipping points. [PDF](https://sigops.org/s/conferences/hotos/2025/papers/hotos25-106.pdf) · [code: metafor](https://github.com/mpi-sws-rse/metafor)
2. **Formal Analysis of Metastable Failures in Software Systems**: same group. *arXiv 2510.03551, Oct 2025* (no peer-reviewed venue found). Defines metastability through escape probabilities and the generator's eigenstructure, and gives algorithms to predict recovery time. [arXiv](https://arxiv.org/abs/2510.03551)
3. **Learning Metastable Dynamics**: Majumdar, Salamati, Singh, Soudjani. *arXiv 2609.14712, Sep 2026* (HSCC'26 per arXiv metadata). Learns a Koopman embedding (a latent space where the dynamics are linear) from observed trajectories and reads metastability off the dominant eigenvalues. Flags it after ~10% of the simulated run. Evaluated on simulations only. [arXiv](https://arxiv.org/abs/2609.14712)
4. **Characterizing Metastable Faults and Failures**: Farahbakhsh, Lu, Alvisi, Haeberlen, van Renesse (Cornell/Penn). *arXiv 2606.00942, May 2026* (under submission). Recasts metastability as "sins of composition": a cycle of components, each of whose locally stabilising action destabilises the next. Covers oscillating failures (cluster membership flapping at a large gaming platform) that the trigger/loop taxonomy misses. [arXiv](https://arxiv.org/abs/2606.00942)
5. **CSnake**: Qian, Tan, Zhang. *EuroSys 2026.* Finds self-sustaining cascading failures before deployment by stitching single-fault injections from different tests into causal chains and searching for cycles. 15 bugs in 5 widely deployed systems, 5 confirmed. [arXiv](https://arxiv.org/abs/2509.26529)
6. **Wasabi** ("If At First You Don't Succeed, Try, Try, Again…?"): Stoica, Sethi, Su, Zhou, Lu, Mace, Musuvathi, Nath. *SOSP 2024.* Fault injection at retry sites plus CodeQL + GPT-4 static checks. More than 100 new retry bugs (IF/WHEN/HOW to retry) in 8 Java applications. [PDF](https://bastoica.github.io/files/papers/2024_sosp_wasabi.pdf)
7. **Atropos**: Hu et al. *SOSP 2025.* Overload often comes from *one* culprit task hogging a lock or buffer pool, not from total demand. Atropos tracks per-task resource usage and cancels the highest-gain task through the application's own cancellation hooks. Integrated with MySQL, PostgreSQL, Elasticsearch and etcd; keeps 96% throughput with p99 within 1.16× of normal and drops < 0.01% of requests. [PDF](https://orderlab.io/paper/atropos-sosp25.pdf)
8. **Rajomon**: Xing et al. *NSDI 2025.* Market-based overload control for microservices: tokens on requests, per-API prices piggybacked through the call graph. 78% lower tail latency and 45% higher goodput than prior work. [USENIX](https://www.usenix.org/conference/nsdi25/presentation/xing)

Also: **HoliPaxos** (PVLDB 2025, Charapko et al.) folds failure and slowdown detection into MultiPaxos itself to avoid bolt-on metastability. **MSF-Model** (SRDS 2024, UCI/Roblox) is a queueing model for replicated storage. **RetryGuard** (arXiv 2511.23278) does graph-wide retry-policy control and reports 98% smaller storms than AWS default policies.

## 11b. Open problems

- **Predicting the vulnerable region before you're in it.** Bronson: hidden capacity "is determined by the behavior … of the system when it is in a failure state, so it is difficult to measure during normal operation." Isaacs et al.: "gains in recognition and reproduction have not yet transferred to analysis and prediction." Why it's hard: the CTMC state space blows up with the number of queues, exponential service-time assumptions "deviate considerably" as amplification grows, and learning models from telemetry is unsolved (the Koopman work only runs on simulations).
- **Loops that cross component boundaries.** Murat Demirbas's critique of HotOS'25: real feedback loops "cross the component boundaries", and the toy model shows no path to Kafka- or Spanner-scale systems. Farahbakhsh et al. take this compositional view but have no production tool yet.
- **Safe testing.** You can't safely push production into a state that by definition doesn't exit on its own. Facebook-style traffic shifting (Kraken) needs a guaranteed drain. Small-scale tests miss scale-dependent loop gains. Closed-loop benchmarks hide the failure.
- **Online detection.** Bronson's "characteristic metrics" (queueing delay, timeout rate, hit rate) return to normal only after recovery, but which metric matters differs per loop. Telling persistent overload from a spike is a "fundamental challenge"; the min-queue-delay-over-window (CoDel) trick is a partial answer.
- **Coordination across clients and teams.** Each client decides its own retries. Spreading health information to them "can be a new way in which a failure can have a sustaining effect" (Bronson). Organisational incentives reward optimisations that shrink hidden capacity.
- **Contested positions:**
  - **Retry vs don't retry:** clients can't tell transient faults from overload.
  - **Breaker vs bucket:** modal behaviour vs bounded load at 100% failure.
  - **LIFO vs FIFO:** fresh-first recovery vs starvation and unfairness. No primary source argues against LIFO outright, but the fairness cost is real.
  - **Client-side vs server-side throttling:** client-side saves work; Brooker shows breakers can widen outages in sharded systems.
- **LLM serving.** KV-cache preemption → recompute → longer queues, plus client retries on timeout, looks like a sustaining loop. Current work (JITServe, SCORPIO) does SLO-aware dropping, but no peer-reviewed paper frames it as metastability yet.

## 12. Lineage

```
1979  lock convoys (single-machine sustaining effect)
1984  Nagle, RFC 896: "congestion collapse ... This condition is stable"
1988  Jacobson & Karels: exponential backoff, slow start, AIMD; LBL→UCB fell 32 kbps → 40 bps (Oct '86)
1996  Mogul & Ramakrishnan: receive livelock (goodput collapse, but NOT metastable: exits when load drops)
2006  Schroeder et al.: open vs closed systems
2012  Nichols & Jacobson: CoDel
2013  Dean & Barroso, "The Tail at Scale": hedging = deliberate amplification, cap it
2013  Facebook memcache leases (NSDI); 2014 FB link-imbalance post
2015  Brooker: exponential backoff & jitter; Maurer: "Fail at Scale" (adaptive LIFO + CoDel)
2016  Google SRE book: client-side adaptive throttling, retry budgets
2019  Brooker: "bistability" (HPTS'19)
2021  Bronson, Aghayev, Charapko, Zhu: "Metastable Failures in Distributed Systems" (HotOS): the name
2022  Huang et al.: "Metastable Failures in the Wild" (OSDI): 22 incidents, theorems, reproductions
2024  Wasabi (SOSP): retry-bug finding · MSF-Model (SRDS) · TopFull (SIGCOMM)
2025  Isaacs et al. (HotOS): CTMC + DSL toolchain · Atropos (SOSP) · Rajomon (NSDI) · AWS Oct-2025 collapse
2026  Characterizing Metastable Faults (Cornell/Penn) · CSnake (EuroSys) · Koopman learning
```

## 13. Hands-on (≤ 30 min)

`metastable_sim.py` in this folder: no dependencies, runs in < 1 s.

```bash
python3 metastable_sim.py                                  # all scenarios
python3 metastable_sim.py --lam 70 --outage 10             # stuck
python3 metastable_sim.py --lam 70 --outage 1.0            # survives
python3 metastable_sim.py --lam 70 --outage 1.3            # stuck: 0.3 s more trigger
python3 metastable_sim.py --lam 30 --outage 10             # escapes, but slowly
python3 metastable_sim.py --lam 70 --outage 10 --budget 0.1
python3 metastable_sim.py --lam 70 --outage 10 --drop-expired
python3 metastable_sim.py --lam 70 --outage 10 --policy lifo
```

Things to try:

1. Find the band edge. Hold `--outage 10` and sweep `--lam` from 25 to 40. The theory says the edge is μ/(r+1) = 33. Where does recovery time go to infinity?
2. Set `--retries 5`. The band's lower edge should move to 100/6 ≈ 17.
3. Find the minimum trigger that sticks at λ = 50, 70 and 90. Compare against T·μ/λ: the outage after which the queue wait exceeds the timeout.
4. Explain why "no retries" still takes ~21 s to recover while `--drop-expired` takes ~0 s, using t_drain = B/(μ−λ).

## 14. Question ladder

**Mechanism**

1. In the sim's stuck state the server is 100% busy. Exactly what is it working on, and why does none of it count?
2. Why does the queue keep *growing* after the outage ends, instead of just staying long?
3. How does a look-aside cache create a sustaining effect without any retries?
4. Walk through Facebook's link-imbalance loop: why does an MRU pool concentrate load on the slowest link?

**Why**
5. Why is the stable region's lower edge μ/(r+1) and not μ?
6. Why do companies deliberately run in the vulnerable state?
7. Why does LIFO recover immediately when FIFO doesn't, even though both serve at the same rate?
8. Why do AWS SDKs charge more retry tokens for a timeout than for an error response?

**Counterfactual**
9. With r = ∞ (unbounded retries), what is C_stable?
10. If every client had a perfectly synchronised backoff (no jitter), what would the load look like after an outage?
11. Remove server-side deadline checks but keep a 10% retry budget. Does the system recover, and what sets how long it takes?
12. If the same service ran as a closed system (fixed clients waiting on replies), could it go metastable from retries?

**Adversarial**
13. You're an attacker who can cause brief stalls but not sustained DDoS. How would you use metastability?
14. How can a health check turn a 10% overload into a 100% outage?
15. Give a fix that looks reasonable but makes the next incident worse.

**Connection**
16. How is TCP congestion collapse (1986) the same failure, and which TCP mechanisms map to retry budgets, backoff and admission control?
17. Receive livelock causes zero goodput under overload. Why is it *not* metastable?
18. How do hedged requests from "The Tail at Scale" relate to retry storms?

**Open**
19. Can you detect that a production system is in the vulnerable band without kicking it?
20. How should retry policy be composed across a 20-service call graph owned by 10 teams?
21. Are LLM-serving systems (KV-cache preemption + client retries) metastable, and what would the sustaining effect be?

### Answers

<details><summary>1. What is a stuck server working on?</summary>
Attempts whose clients timed out long ago. With FIFO and a backlog longer than T·μ, every dequeued attempt waited more than T, so its client has already given up (and retried). The server burns full CPU producing responses nobody reads. Throughput = μ, goodput = 0, or in Brooker's words "Up, but down. Working, but broken."
</details>

<details><summary>2. Why does the queue keep growing?</summary>
Each user request now generates r+1 attempts (every attempt times out, since the queue wait > T). Arrival rate of attempts = (r+1)λ = 210/s > μ = 100/s, so the queue grows by ~110/s. The trigger isn't needed any more: the amplified load alone exceeds capacity.
</details>

<details><summary>3. Look-aside cache loop without retries?</summary>
The cache is filled by the application after a DB read. With the cache cold, most requests go to the DB, which is overloaded, so the app times out *before* writing the result to the cache. The cache never warms, so DB load stays high. The sustaining effect is capacity degradation (w*_C = 1/(1−hit rate) = 10 at 90%), not workload amplification. Bronson's fix: a permissive DB timeout, or a read-through cache that fills even after the client leaves.
</details>

<details><summary>4. MRU link imbalance?</summary>
After a burst of misses, connections on the most congested link (highest latency) are the last to return to the pool. An MRU pool hands out the most recently returned connection first, so it picks exactly those slow connections, putting more traffic on the congested link and keeping it congested. One line changing pool policy fixed it.
</details>

<details><summary>5. Why μ/(r+1)?</summary>
The collapsed state sustains itself only if its amplified load exceeds capacity: (r+1)λ > μ. Below λ = μ/(r+1), even the worst-case amplification fits within capacity, so the backlog drains and p falls back to 0. Above μ the healthy state isn't self-consistent either. In between, both are.
</details>

<details><summary>6. Why run vulnerable?</summary>
Efficiency. Staying below C_stable = C_norm/(w*_L·w*_C) means running at e.g. 50% (1 retry) or 10% (90% cache hit rate) of advertised capacity. That's very expensive, and the vulnerable band behaves perfectly on normal days. Bronson notes common-case optimisations push systems to "a larger multiple of the threshold".
</details>

<details><summary>7. LIFO vs FIFO recovery?</summary>
Under LIFO the next request served is the newest one, whose client is still waiting, so it succeeds. Its success means no retry, p drops and λ_eff falls toward λ < μ, which moves the system to the healthy fixed point. The stale backlog sits at the bottom of the stack and can be dropped. FIFO always serves the oldest (dead) request first.
</details>

<details><summary>8. Why timeouts cost more tokens?</summary>
A timeout usually means the server *did or is doing* the work and the client didn't wait. A fast error (e.g. throttling) cost the server little. Retrying after a timeout therefore adds more wasted server work, so it should drain the quota faster.
</details>

<details><summary>9. C_stable with unbounded retries?</summary>
w*_L → ∞, so C_stable → 0: no stable region. Any load can be tipped over by a long enough trigger. OSDI'22 says this explicitly.
</details>

<details><summary>10. Synchronised backoff?</summary>
All clients that failed together retry together, giving periodic spikes with quiet gaps. Each spike can re-trigger overload, so the system stays bimodal. Jitter spreads the retries out; full jitter does the least total work (Brooker 2015). Jitter still doesn't reduce total load in an open system.
</details>

<details><summary>11. Budget but no deadline checks?</summary>
In the sim, yes: it recovers at t≈64 s versus 51 s with no retries. The budget caps amplification near 1.1×, so λ_eff ≈ 77 < 100 and the backlog drains at μ − λ_eff. Recovery time is B/(μ − λ_eff), all of it spent serving dead work. Deadline checks would shrink B to only the live requests.
</details>

<details><summary>12. Closed system?</summary>
Not from load amplification in the usual sense: a fixed population of N clients each waiting on one outstanding request caps in-flight work at N, and latency rises instead of load. That's why closed benchmarks miss metastability. Capacity-degradation loops (GC thrash at fixed concurrency) could still persist in principle.
</details>

<details><summary>13. Attacker use?</summary>
Cause a short stall (e.g. 1–2 s of resource exhaustion, or a burst of expensive requests) while the target sits in its vulnerable band. The target's own retries do the rest, so a cheap kick yields a long outage that continues after the attack stops. RetryGuard (2025) treats this as a DDoS amplifier and a "Denial-of-Wallet" against autoscaling.
</details>

<details><summary>14. Health check outage?</summary>
Overloaded hosts respond slowly and fail health checks, and the load balancer removes them. The remaining hosts get their share and also fail, so capacity collapses. Mitigations: fail open when most targets are unhealthy (NLB does), limit removal velocity (AWS post-2025), and use shallow checks that don't depend on shared dependencies.
</details>

<details><summary>15. A fix that backfires?</summary>
Making servers retry a dependency indefinitely (AWS SimpleDB → DynamoDB), or adding detailed error logging (Spotify). Both increase w*_L, which shrinks C_stable and enlarges the vulnerable band.
</details>

<details><summary>16. TCP connection?</summary>
In 1986 retransmissions filled links with duplicate copies, so goodput collapsed and stayed collapsed (Nagle: "This condition is stable"). TCP's exponential RTO backoff ↔ retry backoff; the congestion window and AIMD ↔ adaptive concurrency limits; "conservation of packets" ↔ retry budgets / closed-loop admission; RED/CoDel ↔ queue-delay-based shedding.
</details>

<details><summary>17. Livelock isn't metastable?</summary>
Receive livelock wastes all capacity on interrupts under overload, but "when the input load drops sufficiently, the system leaves this state". There's no sustaining effect after the trigger load is gone. HotOS'21 excludes it explicitly.
</details>

<details><summary>18. Hedging?</summary>
Hedging sends a duplicate before the first attempt fails, which is intentional work amplification. At 10 ms hedging cut BigTable p99.9 from 1,800 ms to 74 ms for 2% more requests. Under overload, uncapped hedges behave exactly like retries; that's why gRPC throttles retries and hedges with the same token bucket.
</details>

<details><summary>19. Detecting vulnerability passively?</summary>
Open. Approaches: model-based (estimate w* from policies, compare L_norm to C_norm/w*), CTMC/simulation sweeps (Isaacs), learned spectral indicators (Koopman, simulation-only so far). The difficulty is that hidden capacity depends on behaviour in the failure state, which you don't observe while healthy.
</details>

<details><summary>20. Composing retries across a call graph?</summary>
Current best practice: retry only at the layer directly above the failure, propagate a retry counter and deadline in metadata, and return "overloaded; don't retry" upward (Google SRE). Research directions: entry-point admission (TopFull), price propagation (Rajomon), graph-wide policy control (RetryGuard). None is a settled standard.
</details>

<details><summary>21. LLM-serving metastability?</summary>
Plausible loop: memory pressure → KV-cache preemption → recompute (more GPU work per request) → longer queues → client timeouts and retries → more memory pressure. That is capacity degradation plus workload amplification. JITServe and SCORPIO do SLO-aware dropping. No peer-reviewed metastability analysis exists yet (as of research for this dive).
</details>

## 15. Go deeper next

1. **CoDel and adaptive LIFO internals**: the control law behind "minimum queue delay over an interval", and why it separates good queues from bad ones.
2. **Adaptive concurrency limits (TCP Vegas → Netflix Gradient2 → Envoy)**: congestion control turned inward onto RPC servers.
3. **Shuffle sharding and cell-based architecture**: the combinatorics of blast-radius isolation and how Route 53 gets ~730 billion shards out of 2,048 nodes.

## Sources

**Papers**

- Bronson, Aghayev, Charapko, Zhu. Metastable Failures in Distributed Systems. HotOS'21. https://sigops.org/s/conferences/hotos/2021/papers/hotos21-s11-bronson.pdf
- Huang et al. Metastable Failures in the Wild. OSDI'22. https://www.usenix.org/conference/osdi22/presentation/huang-lexiang · code https://github.com/lexiangh/Metastability
- Isaacs et al. Analyzing Metastable Failures. HotOS'25. https://sigops.org/s/conferences/hotos/2025/papers/hotos25-106.pdf · https://github.com/mpi-sws-rse/metafor
- Alvaro et al. Formal Analysis of Metastable Failures in Software Systems. arXiv 2510.03551. https://arxiv.org/abs/2510.03551
- Majumdar et al. Learning Metastable Dynamics. arXiv 2609.14712. https://arxiv.org/abs/2609.14712
- Farahbakhsh et al. Characterizing Metastable Faults and Failures. arXiv 2606.00942. https://arxiv.org/abs/2606.00942
- Qian, Tan, Zhang. CSnake. EuroSys'26. https://arxiv.org/abs/2509.26529
- Stoica et al. Wasabi. SOSP'24. https://bastoica.github.io/files/papers/2024_sosp_wasabi.pdf
- Hu et al. Atropos. SOSP'25. https://orderlab.io/paper/atropos-sosp25.pdf
- Xing et al. Rajomon. NSDI'25. https://www.usenix.org/conference/nsdi25/presentation/xing
- Park et al. TopFull. SIGCOMM'24. https://dl.acm.org/doi/10.1145/3651890.3672253
- Cho et al. Protego. NSDI'23. https://www.usenix.org/conference/nsdi23/presentation/cho-inho
- Liang et al. HoliPaxos. PVLDB 18(8), 2025. https://www.vldb.org/pvldb/vol18/p2505-charapko.pdf
- Habibi et al. MSF-Model. SRDS'24. https://arxiv.org/abs/2309.16181
- Tavori et al. RetryGuard. arXiv 2511.23278. https://arxiv.org/abs/2511.23278
- Nagle. RFC 896. https://www.rfc-editor.org/rfc/rfc896.txt
- Jacobson & Karels. Congestion Avoidance and Control. https://ee.lbl.gov/papers/congavoid.pdf
- Mogul & Ramakrishnan. Eliminating Receive Livelock. USENIX'96. https://www.usenix.org/conference/usenix-1996-annual-technical-conference/eliminating-receive-livelock-interrupt-driven
- Dean & Barroso. The Tail at Scale. CACM 2013. https://cacm.acm.org/research/the-tail-at-scale/
- Nishtala et al. Scaling Memcache at Facebook. NSDI'13. https://www.usenix.org/system/files/conference/nsdi13/nsdi13-final170_update.pdf
- Schroeder et al. Open Versus Closed: A Cautionary Tale. NSDI'06. https://www.usenix.org/conference/nsdi-06/open-versus-closed-cautionary-tale

**Code / docs**

- gRPC retry proposal A6. https://github.com/grpc/proposal/blob/master/A6-client-retries.md
- Envoy circuit breaker / retry budget. https://www.envoyproxy.io/docs/envoy/latest/api-v3/config/cluster/v3/circuit_breaker.proto
- Envoy adaptive concurrency. https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/adaptive_concurrency_filter
- Finagle RetryBudget. https://github.com/twitter/finagle/blob/develop/finagle-core/src/main/scala/com/twitter/finagle/service/RetryBudget.scala
- botocore retries. https://github.com/boto/botocore/blob/develop/botocore/retries/standard.py
- aws-sdk-go-v2 retry. https://github.com/aws/aws-sdk-go-v2/blob/main/aws/retry/standard.go
- AWS SDK retry behaviour. https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html
- Netflix concurrency-limits. https://github.com/Netflix/concurrency-limits
- HBase AdaptiveLifoCoDelCallQueue. https://hbase.apache.org/2.5/devapidocs/src-html/org/apache/hadoop/hbase/ipc/AdaptiveLifoCoDelCallQueue.html
- Go singleflight. https://pkg.go.dev/golang.org/x/sync/singleflight

**Articles / postmortems**

- Google SRE: Handling Overload. https://sre.google/sre-book/handling-overload/
- Google SRE: Addressing Cascading Failures. https://sre.google/sre-book/addressing-cascading-failures/
- AWS Builders' Library: Timeouts, retries and backoff with jitter. https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/
- AWS Builders' Library: Using load shedding to avoid overload. https://builder.aws.com/content/3Eun1EEyX6p2e3VYNyRLSJzLuMV/using-load-shedding-to-avoid-overload
- AWS Builders' Library: Avoiding insurmountable queue backlogs. https://builder.aws.com/content/3EuRcgkTP1MI0c7zM8W6HL3WIqA/avoiding-insurmountable-queue-backlogs
- AWS Builders' Library: Shuffle sharding. https://aws.amazon.com/builders-library/workload-isolation-using-shuffle-sharding/
- AWS Builders' Library: Static stability. https://aws.amazon.com/builders-library/static-stability-using-availability-zones/
- AWS cell-based architecture. https://docs.aws.amazon.com/wellarchitected/latest/reducing-scope-of-impact-with-cell-based-architecture/what-is-a-cell-based-architecture.html
- Constant work (summary). https://www.allthingsdistributed.com/2023/11/standing-on-the-shoulders-of-giants-colm-on-constant-work.html
- AWS 2026 retry update. https://aws.amazon.com/blogs/developer/announcing-updated-retry-behavior-for-aws-sdks-and-tools/
- Exponential Backoff and Jitter. https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
- Brooker: Metastability and distributed systems. https://brooker.co.za/blog/2021/05/24/metastable.html
- Brooker: Caches, modes, and unstable systems. https://brooker.co.za/blog/2021/08/27/caches.html
- Brooker: Fixing retries with token buckets and circuit breakers. https://brooker.co.za/blog/2022/02/28/retries.html
- Brooker: Will circuit breakers solve my problems? https://www.brooker.co.za/blog/2022/02/16/circuit-breakers.html
- Brooker: What is backoff for? https://brooker.co.za/blog/2022/08/11/backoff.html
- Brooker: Garbage collection and metastability. https://brooker.co.za/blog/2024/08/14/gc-metastable.html
- Brooker: Good performance for bad days. https://brooker.co.za/blog/2025/05/20/icpe.html
- Demirbas on HotOS'25. https://muratbuffalo.blogspot.com/2025/06/analyzing-metastable-failures-in.html
- Fail at Scale (summary). https://blog.acolyer.org/2015/11/19/fail-at-scale-controlling-queue-delay/
- Uber Cinnamon. https://www.uber.com/blog/cinnamon-using-century-old-tech-to-build-a-mean-load-shedder/
- FB link imbalance. https://engineering.fb.com/2014/11/14/production-engineering/solving-the-mystery-of-link-imbalance-a-metastable-failure-state-at-scale/
- AWS Oct 2025. https://aws.amazon.com/message/101925/ · Dec 2021 https://aws.amazon.com/message/12721/ · Kinesis 2020 https://aws.amazon.com/message/11201/
- Slack Jan 2021. https://slack.engineering/slacks-outage-on-january-4th-2021/ · Feb 2022 https://slack.engineering/slacks-incident-on-2-22-22/
- Google Cloud Jun 2025. https://status.cloud.google.com/incidents/ow5i3PPK96RduMcb1SsW
- Roblox Oct 2021. https://about.roblox.com/newsroom/2022/01/roblox-return-to-service-10-28-10-31-2021

*Unverified / flagged:* verbatim phrasing of the AWS 243× sentence (page is JS-rendered; arithmetic implies 3 attempts/layer); Fail at Scale's exact M/N values (ACM page blocked); 2026 arXiv items are preprints except where a venue is named.
