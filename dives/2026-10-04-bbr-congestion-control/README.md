# BBR congestion control: modeling the pipe instead of waiting for loss (v1 → v3)

**Subject:** Computer science · **Domain:** Networking/protocols · **Topic:** BBR: BtlBw/RTprop model, pacing-gain state machine, v2/v3 loss + ECN bounds, coexistence with CUBIC · **Depth:** hard · **Date:** 2026-10-04

---

## 0b. Plain-English first

### Explain it simply

Picture a highway with a toll booth that can let through exactly 100 cars per minute. Behind the booth is a parking lot where cars wait when they arrive too fast. The old way of driving onto this highway (Reno, CUBIC) is: keep sending more and more cars until the lot is so full that a car gets turned away, then cut back by about a third, and creep up again. It works, but the parking lot is almost always full, so every car waits a long time. With a huge lot, a trip that should take 40 ms can take half a second. That's "bufferbloat".

BBR does something else. It watches two things: how fast cars actually come out the far side of the booth (the most it has ever seen recently is the booth's speed), and the shortest trip time it has ever seen (that's the trip with an empty lot). Multiply them and you know exactly how many cars should be on the road at once to keep the booth busy without anyone waiting. BBR sends cars at that pace. Now and then it sends a few extra to check whether the booth got faster, then a few fewer to clear out any line it caused. Every few seconds it nearly stops for a moment to re-measure the empty-lot trip time.

### Everyday example

You upload a video from a café. The link out to the internet carries 12 megabits per second and the round trip to the server takes 40 ms when nothing is queued. The café router has a big buffer. With the old method your upload fills that buffer: your ping jumps to around 220 ms and your friend's video call at the next table starts to stutter. With BBR, your laptop ramps up for about half a second and sees the delivery rate stop growing at 12 Mbit/s. It notes that the best round trip was 40 ms, so "12 Mbit/s × 40 ms ≈ 40 packets" is the right amount to have in flight. It drains the short line it built while ramping up, then holds about 40 packets in flight. Upload speed is the same 12 Mbit/s, but your ping stays near 55 ms, and your friend's call is fine.

**Now the same thing, technically.**

---

## 1. Bare-minimum context

- **cwnd (congestion window):** the cap on unacknowledged bytes in flight, set by the sender. [RFC 5681](https://www.rfc-editor.org/rfc/rfc5681)
- **Loss-based CC:** Reno/CUBIC grow cwnd until a packet drops, then multiply it by β (0.5 for Reno, 0.7 for CUBIC). [RFC 9438 (CUBIC)](https://www.rfc-editor.org/rfc/rfc9438)
- **BDP (bandwidth-delay product):** bottleneck rate × base RTT, the number of bytes needed to keep the pipe full. [ACM Queue BBR paper](https://queue.acm.org/detail.cfm?id=3022184)
- **Bufferbloat:** oversized FIFO buffers that loss-based CC fills, which adds hundreds of ms of queueing delay. [bufferbloat.net](https://www.bufferbloat.net/)
- **Pacing:** spacing packets out at a target rate instead of sending a burst whenever cwnd opens. Linux does it in the `fq` qdisc or inside TCP. [fasterdata BBR notes](https://fasterdata.es.net/host-tuning/linux/recent-tcp-enhancements/bbr-tcp/)
- **ECN:** routers set a CE bit instead of dropping. The receiver echoes it back. [RFC 3168](https://www.rfc-editor.org/rfc/rfc3168)

## 1b. Real-world context

**What it is.** BBR (Bottleneck Bandwidth and Round-trip propagation time) is a sender-side congestion control algorithm from Google (Cardwell, Cheng, Gunn, Hassas Yeganeh, Jacobson, 2016). It keeps an explicit model of the path, made of a max-filtered delivery rate and a min-filtered RTT. It sets a **pacing rate** from that model and uses cwnd only as a safety cap. It does not use loss as the main signal.

**Why it exists.** Loss-based CC has two problems at the ends of the buffer range. With **deep buffers** it fills them, so a 40 ms path becomes hundreds of ms or seconds. With **shallow buffers or random loss** it reads a 1% non-congestive loss rate as congestion and collapses. Google's B4 WAN ran into the second problem: BBR's throughput was **2–25× CUBIC's** there, and on one US–Europe path BBR sustained 2 Gbit/s where CUBIC got 15 Mbit/s (**133×**). On YouTube, BBR cut **median RTT by 53% globally and >80% in the developing world** ([ACM Queue 2016](https://web.stanford.edu/class/cs244/papers/bbr.pdf)).

**Where it's used.**

| System | Role |
|---|---|
| Google B4 WAN | All B4 TCP traffic on BBR since 2016. BBRv3 is now CC for all Google-internal WAN traffic ([IETF 119 slides](https://datatracker.ietf.org/meeting/119/materials/slides-119-ccwg-bbrv3-overview-and-google-deployment-00)) |
| google.com + YouTube | BBRv3 is the TCP CC for all public-Internet traffic. QUIC v3 was in A/B tests as of March 2024 (same slides) |
| Linux kernel | `tcp_bbr.c` (BBRv1) mainline since 4.9 (2016). v3 lives out of tree in [google/bbr `v3`](https://github.com/google/bbr/blob/v3/README.md) |
| AWS CloudFront | BBR rolled out March–April 2019. Up to 22% higher aggregate throughput ([AWS blog](https://aws.amazon.com/blogs/networking-and-content-delivery/tcp-bbr-congestion-control-with-amazon-cloudfront/)) |
| Dropbox edge | Measured BBRv2 vs v1 vs CUBIC. v2 had 4× lower loss than v1 but still ~2× CUBIC's ([Dropbox tech blog, 2019](https://dropbox.tech/infrastructure/evaluating-bbrv2-on-the-dropbox-edge-network)) |
| QUIC stacks | Google QUICHE (Chromium/Envoy), Meta mvfst and Cloudflare quiche all ship BBR variants in user space |
| Verizon Media CDN | Client-facing gain of 6–8%, but **~50% regression on PoP-to-PoP** links from RTT unfairness. Kept CUBIC inside the DC ([APNIC 2019](https://blog.apnic.net/2019/11/01/bbr-evaluation-at-a-large-cdn/)) |

**How it's used.**

```bash
# system-wide (Linux ≥ 4.9; ≥ 4.13 paces inside TCP if fq absent)
sysctl -w net.core.default_qdisc=fq
sysctl -w net.ipv4.tcp_congestion_control=bbr

# per socket
setsockopt(fd, IPPROTO_TCP, TCP_CONGESTION, "bbr", 3);

# inspect live model
ss -tin dst :443
#  ... bbr:(bw:160Mbps,mrtt:0.073,pacing_gain:2.88672,cwnd_gain:2.88672) ...
```

`bw` is the BtlBw estimate and `mrtt` is the RTprop estimate. A `pacing_gain` of 2.88672 (= 2/ln2) means the flow is still in Startup. There are no tunables in mainline. The constants are in the source.

<table><tr><th>Use it</th><th>Skip it / be careful</th></tr><tr><td>
Server → Internet clients, especially long RTT, lossy (cellular, Wi-Fi, intercontinental), or deep-buffered last miles. Bulk transfer over a WAN with some random loss. Latency-sensitive services co-hosted with bulk traffic on a bloated link.
</td><td>
Intra-DC or PoP-to-PoP fabric where flows with very different RTTs share a shallow switch buffer (v1 RTT unfairness). Shallow buffers where you care about other tenants' retransmits (v1 ignores loss). Links behind token-bucket policers or heavy ACK aggregation, unless you test first.
</td></tr></table>

**Who should care.** Edge/CDN and video infra engineers (it decides QoE). Backend people debugging p99 on long-haul links. Network ops seeing their CUBIC customers starved. QUIC implementers, since BBR lives in user space there. Researchers in CC fairness.

## 2. The one-liner — and what it hides

> "BBR measures bottleneck bandwidth and min RTT and sends at that rate instead of waiting for packet loss."

What this hides:

1. **You can't measure both at once.** Seeing max bandwidth needs a full pipe, which means a queue. Seeing min RTT needs an empty queue, which means less than full bandwidth. So BBR has to alternate between them, and that is the reason the state machine exists.
2. **"Sends at that rate" needs gains above and below 1.** At gain 1.0 BBR can never learn that bandwidth went up. At gain >1 it builds a queue. So the 1.25/0.75 (v1) or UP/DOWN (v3) cycle is required by the design.
3. **cwnd still matters.** It caps inflight at 2×BDP, and in competition with CUBIC that cap, not the rate, decides BBR's share (Ware et al., IMC 2019).
4. **v1 really did ignore loss**, and that is why it caused 10× the retransmits of CUBIC in shallow buffers. v2/v3 added a 2% loss bound and ECN, which changed what BBR is.
5. **The model assumes non-congestive delay is zero.** Jitter from ACK aggregation, Wi-Fi or scheduling breaks the min-RTT and max-bw filters. There is a theorem saying no delay-bounding CCA can avoid starvation if jitter is large enough.

## 3. The problem

Any path has one slowest link, the bottleneck, with rate **BtlBw**, and a propagation RTT **RTprop**. There are three operating regions as inflight grows:

```
delivery rate                          RTT
   ^        ┌────────────── BtlBw        ^                    /  slope 1/BtlBw
   │       /                             │                   /
   │      /  app-  │ bw-   │ buffer-     │ RTprop __________/
   │     /  limited│limited│ limited     │                  │
   │    /          │       │ (loss)      │                  │
   └───/───────────┴───────┴────► inflight└──────────────────┴────────► inflight
              BDP=BtlBw·RTprop   BDP+BufSize            BDP
                  ▲ Kleinrock optimum         ▲ loss-based CC operates here
```

- Below BDP, delivery rate = inflight / RTprop and RTT = RTprop.
- Between BDP and BDP + buffer, delivery rate = BtlBw and RTT grows linearly (queueing).
- Above BDP + buffer, drops.

Loss-based CC finds the right edge of the middle region, where loss starts. Kleinrock (1979) showed the optimum for each connection is the **left** edge: max throughput at min delay. Jaffe (1981) showed no distributed algorithm can converge to that point exactly, because a single measurement can't tell BtlBw and RTprop apart. BBR's answer is to estimate them **at different times** and combine them.

Size of the gap: a 12 Mbit/s, 40 ms path has BDP = 40 packets of 1500 B. Home routers often buffer hundreds of packets. At 320 packets (8 BDP), Reno's steady-state queue delay averages in the hundreds of ms. Our toy sim gives a **221 ms median RTT for Reno vs 55.5 ms for BBR at the same 11.9 Mbit/s goodput** (§13).

## 4. Mental model

**A garden hose of unknown diameter and length.** You want the hose full of water but no puddle at the tap. Two gauges:
- an **outflow meter** at the nozzle, whose peak reading is the hose diameter (BtlBw);
- a **dye-transit timer**, whose fastest reading is the hose length (RTprop).

Water in the hose = diameter × length. You turn the tap to the peak outflow rate. Sometimes you open it 25% wider to see if the hose got wider, then close it to 75% to drain the puddle you just made. Sometimes you nearly shut it so the dye timer can get a clean reading.

**Where the analogy breaks.**

- The hose is **shared**. Other taps make outflow look smaller (your share) and transit look longer (their puddle). A max filter of your own delivery rate measures your current share, not capacity, so the model has no idea of a "fair share".
- Real hoses don't spit water in **clumps**. Wi-Fi and cellular deliver ACKs in bursts, so the outflow meter shows short spikes far above the true rate.
- Some hoses have a **valve that slams shut** once you've used your allowance (token-bucket policers). Delivery rate then drops suddenly with heavy loss, and that is not the bottleneck model at all.

## 5. The mechanism, traced

One BBRv1-style flow, 12 Mbit/s bottleneck, RTprop 40 ms, buffer 320 packets. These are output lines from `bbr_sim.py --trace` (state every 100 ms):

```
t=0.0s STARTUP   queue=  0  btlbw= 0.00 Mbit/s
t=0.1s STARTUP   queue=  1  btlbw= 2.96      ← exponential growth, gain 2.885
t=0.2s STARTUP   queue= 72  btlbw=11.43      ← overshoot: pacing > bottleneck
t=0.3s STARTUP   queue= 78  btlbw=12.09      ← bw stopped growing
t=0.4s STARTUP   queue= 78  btlbw=12.09      ← 3 rounds <25% growth → exit
t=0.5s DRAIN     queue= 71  btlbw=12.09      ← gain 0.347 drains queue
t=0.6s PROBE_BW  queue=  1  btlbw=12.09      ← inflight ≤ BDP → cruise
t=0.9s PROBE_BW  queue=  9  btlbw=12.09      ← the 1.25 probe phase
t=1.0s PROBE_BW  queue=  3                    ← the 0.75 phase drains it
```

### Step 1 — one ACK → one delivery-rate sample

Each packet carries a snapshot taken at send time: `(delivered, delivered_time, first_sent_time, is_app_limited)`. When its ACK arrives at time `now`:

```
send_elapsed = P.sent_time  - P.first_sent_time
ack_elapsed  = now          - P.delivered_time
interval     = max(send_elapsed, ack_elapsed)        # guards against ACK compression
delivery_rate = (C.delivered - P.delivered) / interval
if interval < min_rtt: discard sample                 # too short to trust
```

Concrete numbers. Packet P was sent when `C.delivered = 120` packets and `delivered_time = 0.210 s`. Its ACK arrives at 0.252 s, when `C.delivered = 160`. Then `ack_elapsed = 42 ms` and the rate = 40 / 0.042 = 952 pkt/s ≈ **11.4 Mbit/s**. That's one sample, and it is a lower bound on BtlBw.

Taking `max(send_elapsed, ack_elapsed)` matters. If ACKs were compressed (arriving in a clump), `ack_elapsed` is too short and inflates the rate. The send-side interval can't be compressed by the network, so the max of the two is the honest choice. ([draft-ietf-ccwg-bbr-06 §4.1](https://datatracker.ietf.org/doc/html/draft-ietf-ccwg-bbr-06))

### Step 2 — update the model

```
max_bw  = windowed_max(delivery_rate, window = 10 round trips (v1) / 2 ProbeBW cycles (v3))
min_rtt = windowed_min(rtt_sample,    window = 10 s)
BDP     = max_bw × min_rtt     = 12 Mbit/s × 0.040 s = 480 kbit = 40 packets
```

Samples marked **app-limited** (the app had nothing to send, so the pipe wasn't full) can only *raise* max_bw, never lower it. Otherwise a video player pausing would teach BBR that the network got slow.

### Step 3 — turn model into control

```
pacing_rate = pacing_gain × max_bw
cwnd        = cwnd_gain   × BDP   (+ extra_acked allowance for ACK aggregation)
```

### Step 4 — the state machine

```
            ┌──────────┐ bw plateau 3 rounds  ┌───────┐ inflight ≤ BDP ┌──────────────────────────────┐
  start ──► │ STARTUP  │ ───────────────────► │ DRAIN │ ─────────────► │ PROBE_BW                     │
            │ g=2.77   │  (v3: or loss>2%     │ g=0.5 │                │ v1: 8-phase cycle            │
            │ cg=2     │   / ECN)             └───────┘                │   1.25,0.75,1,1,1,1,1,1      │
            └──────────┘                                               │ v3: DOWN 0.9 → CRUISE 1.0 →  │
                 ▲                                                     │     REFILL 1.0 → UP 1.25     │
                 │            min_rtt not refreshed for 5 s (v3) / 10 s (v1)                         │
                 │                       ┌───────────┐ ◄─────────────────┘
                 └─(if pipe not full)────┤ PROBE_RTT │  v1: cwnd = 4 pkts, ≥200 ms + 1 round
                                         │           │  v3: cwnd = 0.5 × BDP, ≥200 ms
                                         └───────────┘
```

Constants from the current spec ([draft-ietf-ccwg-bbr-06](https://datatracker.ietf.org/doc/html/draft-ietf-ccwg-bbr-06), July 2026):

| State | pacing_gain | cwnd_gain | notes |
|---|---|---|---|
| Startup | 2.77 (4 ln 2) | 2 | v1 used 2/ln2 = 2.885 for both |
| Drain | 0.5 | 2 | v1 used ln2/2 = 0.347 |
| ProbeBW_DOWN | 0.90 | 2 | v1's 0.75 phase |
| ProbeBW_CRUISE | 1.0 | 2 | inflight ≤ 0.85·inflight_longterm |
| ProbeBW_REFILL | 1.0 | 2 | one round to refill the pipe |
| ProbeBW_UP | 1.25 | 2.25 | ends on loss >2% or bw plateau |
| ProbeRTT | 1.0 | 0.5 | ≥200 ms, at most every 5 s |

Other constants: `LossThresh = 2%`, `Beta = 0.7` (multiplicative cut on loss), `Headroom = 0.15`, `MinPipeCwnd = 4·SMSS`, `MinRTTFilterLen = 10 s`, `StartupFullLossCnt = 6`.

### Step 5 — what v2/v3 add: inflight bounds

v1 had one model, (bw, rtt). v2/v3 add **long-term and short-term bounds**:

- `inflight_longterm` (previously `inflight_hi`) is the largest inflight that did *not* cause loss >2% or ECN above threshold. It is learned in ProbeBW_UP.
- `bw_shortterm` / `inflight_shortterm` (previously `*_lo`) are cut by β = 0.7 per round with loss and recover in REFILL/UP.

So in CRUISE, v3 deliberately keeps inflight at 85% of the known-safe ceiling (`Headroom = 0.15`) to leave room for other flows.

### Step 6 — when to probe again

v3 doesn't probe on a fixed 8-RTT cycle. It waits `T_probe = min(T_bbr, T_reno)`:

- `T_bbr` is random in **2–3 s** wall clock;
- `T_reno = min(BDP in packets, 62 or 63)` round trips, chosen randomly between 62 and 63.

So on a small-BDP path BBR probes about as often as Reno's sawtooth would. On a huge-BDP path it probes every 2–3 s, which is much faster than Reno, whose cycle there takes minutes. (Draft §5.3.3.8.)

## 6. The math

### 6.1 The two-region model

Let `x` = inflight (bytes), `B` = BtlBw, `R` = RTprop, `Q` = buffer size.

```
delivery_rate(x) = min(x / R, B)
RTT(x)           = max(R, x / B)            for x ≤ B·R + Q
```

→ in plain terms: below the BDP, data is limited by how much you sent per round trip. Above it, the pipe is full and every extra byte just waits in line.

Kleinrock's *power* metric is throughput / delay:

```
P(x) = delivery_rate(x) / RTT(x)
     = (x/R)/R = x/R²        for x ≤ BR   (increasing)
     = B / (x/B) = B²/x      for x ≥ BR   (decreasing)
```

→ in plain terms: power peaks exactly at x = B·R = BDP. Below it you waste bandwidth. Above it you only add delay. BBR's target is this kink.

**Why both filters, and why max/min.** Any queueing *adds* to RTT, so every RTT sample ≥ R and `min` converges to R from above. Any competing traffic or under-utilization *reduces* the delivery rate, so every sample ≤ B and `max` converges to B from below. Each filter is biased only toward the truth, never past it, as long as there is no measurement noise. That condition is exactly what jitter and ACK aggregation break.

### 6.2 Why the Startup gain is 4 ln 2 ≈ 2.77

*(This is my reconstruction. It reproduces the draft's value, which the draft calls "the minimum gain value that will allow the sending rate to double each round".)*

You want the sending rate to double every round trip `R`: `r(t) = r₀·2^{t/R}`. BBR can't see `r(t)` directly. It sees the delivery rate of data acknowledged now, and that data was sent over the previous round and is reported one round late. Model the estimate as the average send rate over `[t−2R, t−R]`:

```
b(t) = (1/R) ∫_{t−2R}^{t−R} r₀ 2^{s/R} ds
     = r(t) · (2^{-1} − 2^{-2}) / ln 2
     = r(t) / (4 ln 2)
```

To send at `r(t)` while only knowing `b(t)`, the gain must be `g = r(t)/b(t) = 4 ln 2 ≈ 2.77`.

→ in plain terms: your bandwidth estimate is always about one-and-a-half rounds stale and averaged, so to double you must multiply it by ~2.77, not by 2. BBRv1's 2/ln2 ≈ 2.885 came from a slightly different model of the lag (the paper only states "2/ln2 … discovers BtlBw in log₂BDP RTTs"). The difference is about 4%. Startup still finds BtlBw in roughly **log₂(BDP)** rounds: about 5–6 rounds for our 40-packet BDP from a 10-packet initial window, and that matches the trace (exit at ~0.4 s ≈ 10 RTTs including the 3 plateau rounds).

Overshoot cost: when Startup exits, inflight ≈ 2·BDP (cwnd_gain 2), so roughly one BDP sits in the queue. Drain removes it. With v1's Drain gain `ln2/2 = 0.347` (the inverse of the Startup gain), the queue empties in about one round.

### 6.3 Why ProbeBW is 1.25 then 0.75 (v1) / 0.9 (v3)

Pacing at `1.25·B` for one RTprop sends `0.25·B·R` = 0.25 BDP more than the bottleneck can drain. If no new bandwidth exists, that becomes a 0.25 BDP queue. Pacing at `0.75·B` for the next RTprop under-sends by exactly 0.25 BDP, which drains it. The average gain over 8 phases is `(1.25 + 0.75 + 6·1)/8 = 1.0`.

→ in plain terms: probe up, then pay it back, so the average rate stays at the estimate and the average queue stays near zero.

If bandwidth *did* increase, the 1.25 phase measures higher delivery, `max_bw` rises, and the new bandwidth is taken within a few cycles. Growth is multiplicative, about 1.25× per 8 rounds.

v3's DOWN is 0.90, not 0.75. The draft says it is "the minimum pacing_gain value that allows bandwidth-based convergence to approximate fairness". The intuition is that a gentler down phase lets a *larger* flow's max filter stay elevated less, so flows move toward equal shares through their bandwidth estimates rather than all draining equally.

### 6.4 Loss response and the 62-round magic number

In v3 steady state, a round with loss rate `p` cuts the sending rate by `p`, so after `N` lossy CRUISE rounds the rate is `(1−p)^N`. REFILL + UP can then double cwnd twice (×4). The draft picks the Reno-timescale bound so that a flow facing 1% loss still recovers fully:

```
(1 − 0.01)^N · 2² ≥ 1   ⇒   N ≤ ln 4 / −ln 0.99 ≈ 137.9
```

→ in plain terms: if BBR waits ≤ ~137 rounds between probes, it can tolerate 1% random loss and still hold its rate. The lower limit of ~62 rounds comes from the other side: wait less than about 60 rounds and Reno/CUBIC sharing the link can't sustain 4K video. So they picked 62–63.

The wall-clock lower bound of 2 s comes from a Reno flow at RTT 30 ms needing 25 Mbit/s. Its sawtooth from BDP to 2·BDP at +1 MSS/RTT takes `BDP·RTT = (25e6·0.03/12112 bits)·0.03 ≈ 1.9 s`, so BBR shouldn't cause loss more often than that.

### 6.5 Cost of ProbeRTT

v1: cwnd = 4 packets for ≥ 200 ms every 10 s → at most `200 ms / 10 s ≈ 2%` throughput lost (paper). v3 halves inflight instead (`0.5·BDP`) and does it every 5 s. The cost per episode is smaller and the RTprop estimate is fresher, so it reacts faster to route changes that *raise* RTprop. The min filter can never notice a raise until the old minimum ages out.

### 6.6 Why BBRv1 takes a fixed share against CUBIC

When BBR competes with a buffer-filling CUBIC flow, the queue never drains. BBR's ProbeRTT dips briefly, but `min_rtt` still ends up close to R, and the RTT BBR actually sees is `R + q`. BBR's inflight is capped at `2·max_bw·min_rtt`. Its throughput is therefore `inflight / RTT = 2·max_bw·R / (R + q)`, which is bounded by its *cap*, not by any loss signal. Ware et al. model this cap and predict BBR's share against CUBIC within **5% median error** (8% vs Reno). The headline result: **a single BBR flow takes a fixed ~40% of the link, whether it competes with 1 or 16 CUBIC flows** ([IMC 2019 abstract](https://www.cs.cmu.edu/~srini/papers/2019-Ware-imc)). Adding more CUBIC flows only splits the remaining 60% among them.

### 6.7 Starvation theorem (sketch)

Arun, Alizadeh and Balakrishnan (SIGCOMM 2022): suppose a CCA converges, on an ideal path, to an equilibrium delay range of width δ that depends on its rate. Then if non-congestive delay variation (ACK aggregation, end-host scheduling) can exceed **2δ**, there are paths where two flows of that CCA end up with arbitrarily unequal throughput, i.e. starvation. The reason is that the CCA *encodes its rate in the delay it sees*. Jitter of more than 2δ lets one flow see a delay that "means" a much lower rate. BBR, PCC Vivace and Copa were all shown to starve in emulation ([paper](https://web.stanford.edu/class/cs244/papers/venkat_starvation.pdf)).

## 7. Why it works

**Core insight:** the two quantities that define the optimum change on different timescales and can each be filtered with a one-sided estimator. Bandwidth changes from competition, so it gets a short max window. Propagation delay changes from routing, so it gets a long min window. Pacing, not cwnd, is the control output, so BBR sends at the rate it believes the bottleneck drains, and that is what prevents the queue.

Ablations:

- **Remove pacing (cwnd only):** cwnd opens in ACK-clocked bursts, line-rate bursts build queues at the bottleneck, and the RTT samples get inflated. This is why early BBR needed `fq`.
- **Remove the 1.25 phase:** BBR can never discover added capacity. A flow that starts while another is active stays at its initial share forever.
- **Remove the 0.75/0.9 phase:** each probe leaves 0.25 BDP behind. After a few cycles a standing queue forms and min_rtt samples stop appearing.
- **Remove ProbeRTT:** with ≥2 BBR flows each keeping some queue, nobody ever sees R again. min_rtt is never refreshed, and if a route change raises R, BBR's BDP estimate is permanently too low.
- **Remove the cwnd cap (pure rate):** if ACKs stop (a delay spike), a pure pacer keeps sending at max_bw into a black hole. cwnd = 2·BDP bounds the damage to about 1 BDP of queue.
- **Remove v2/v3 loss bounds (= v1):** in buffers smaller than ~1.5 BDP, the 2·BDP cwnd plus probing overflow the buffer every cycle. Our sim at 0.5 BDP buffer: **324 drops for BBRv1-like vs 8 for Reno** in 12 s.
- **Remove app-limited marking:** every idle period would pull `max_bw` down and slow the next burst.

## 8. Design knobs & alternatives

| Knob | v1 | v3 | Tradeoff |
|---|---|---|---|
| BtlBw window | 10 rounds | 2 ProbeBW cycles | longer → stickier to stale bandwidth after capacity drops |
| RTprop window | 10 s | 10 s (ProbeRTT every 5 s) | shorter → more ProbeRTT dips; longer → slow to see route changes |
| ProbeBW down gain | 0.75 | 0.90 | lower drains faster; higher converges to fairness better (draft) |
| ProbeRTT inflight | 4 pkts | 0.5·BDP | 4 pkts gets a cleaner min_rtt but a 2% throughput hit and big sawtooth |
| Loss threshold | none | 2%/round | lower is more CUBIC-friendly; higher tolerates random loss |
| Inter-probe time | 8 RTprop | min(2–3 s, 62–63 rounds) | shorter grabs freed bandwidth faster but hurts Reno |
| ECN | ignored | DCTCP/L4S-style shallow-threshold response | stronger signal, but classic-ECN AQMs make it collapse CUBIC (§9) |

Alternatives:

- **CUBIC + HyStart++** is the default almost everywhere, well understood and fair to itself, but bufferbloat-prone and loss-fragile.
- **Delay-based (Vegas, Copa)** have a low standing queue but lose to buffer-fillers. Copa switches modes to compete, and both are subject to the starvation theorem.
- **Online-learning (PCC Vivace, Sage, Astraea, Orca)** optimize a utility function from experiments or traces. They're good in benchmarks, but deployment needs fairness and compute guarantees ([Learning vs human-derived CC, 2025](https://arxiv.org/abs/2510.25105)).
- **L4S / TCP Prague with DualPQ AQM** move the problem into the network. Routers give immediate fine-grained ECN, and the sender runs a scalable (DCTCP-like) response. With an L4S AQM you get the latency without guessing.
- **Receiver/in-network** (DCTCP, HPCC, Swift in DCs) use explicit signals. Inside Google's DC the CC is BBR.Swift, which uses network_RTT excluding receiver delay ([IETF 119](https://datatracker.ietf.org/meeting/119/materials/slides-119-ccwg-bbrv3-overview-and-google-deployment-00)).

BBR won where you control only the sender and serve the open Internet. It lost, or needs care, where everyone shares a shallow buffer with legacy CC.

## 9. Where it breaks

> **Misconception: "BBR is delay-based."** It isn't. Vegas reacts to RTT *rising*. BBR uses *min* RTT as a constant of the path and doesn't back off when RTT rises. That's why v1 kept going under CUBIC's standing queue.

> **Misconception: "BBR ignores loss."** True only of v1, which looks at loss only for policer detection and recovery. v2/v3 cap the loss rate at 2% per round and cut by β = 0.7.

> **Misconception: "BBR needs the fq qdisc."** True before Linux 4.13. Since then TCP paces internally via a high-resolution timer. `fq` is still more efficient with many flows.

**Failure modes**

1. **Shallow buffers (v1).** cwnd = 2·BDP with buffer < BDP means constant overflow. Hock, Bless and Zitterbart (ICNP 2017) saw massive loss and unfairness. Our sim shows 324 vs 8 drops.
2. **Deep buffers vs CUBIC (v1).** BBR gets a fixed ~40% share regardless of the number of CUBIC flows (Ware 2019). In very deep buffers CUBIC wins, because BBR's inflight cap uses a min_rtt that excludes the standing queue.
3. **RTT unfairness.** A longer-RTprop flow has a larger BDP, hence a larger inflight cap and a larger slice of the shared queue. PAM 2024 finds this bias **persists in v3 and grows with RTT disparity**. This is what bit Verizon's PoP-to-PoP traffic.
4. **ACK aggregation (Wi-Fi, DOCSIS, cellular).** ACKs arrive in bursts, so a short interval and an inflated max_bw. Or cwnd = 2·BDP stalls the sender during ACK gaps. The fix is `extra_acked`, a 10-round max filter of "ACKed more than expected", added to cwnd ([APNIC 2018](https://blog.apnic.net/2018/04/30/bbr-patches-for-higher-wifi-throughput-and-lower-queuing-delays/)).
5. **Token-bucket policers.** The bucket gives a burst at line rate, so the max filter sees line rate and then hits ~20% loss at the policed rate. v1 added a separate long-term bandwidth model (`lt_bw`) to detect this ([IETF 97 policing slides](https://www.ietf.org/proceedings/97/slides/slides-97-maprg-traffic-policing-in-the-internet-yuchung-cheng-and-neal-cardwell-00.pdf)).
6. **ECN + CUBIC.** With ECN enabled, **one BBRv3 flow takes ~99% of bandwidth against five CUBIC flows** (Zeynali et al., ANRW 2024). The paper also says that using RFC-3168 classic marking instead of DCTCP-style shallow marking changes the picture. ECN makes v3 *more* unfair to CUBIC, not less.
7. **Non-congestive jitter → starvation** (§6.7). This one can't be patched away with constants.
8. **Bandwidth drops.** The max filter keeps the old peak for its whole window, so BBR overshoots the new capacity until the sample ages out. v1 lost heavily in that window. v2/v3's `bw_shortterm` cut on loss shortens it.

## 10. In the wild

- **Linux mainline `tcp_bbr.c`** is still **BBRv1** (plus later tweaks like `extra_acked`). Google's plan since IETF 119 (March 2024) is to replace it in place with v3 because "throughput within 1% of v1 on YouTube" with lower loss. As of the latest public info it has not landed; check upstream for status.
- **Google production** deviates from the paper: v3, not v1, everywhere public. Inside DCs it runs **BBR.Swift**, which uses network_RTT (excluding receiver delay) as the primary signal.
- **QUIC stacks** run BBR in user space. Pacing precision depends on the event loop timer (Cloudflare quiche issue #514 notes libev/libuv timer accuracy was insufficient for BBR pacing). ACK frequency is under the receiver's control (QUIC ACK-delay), which changes the delivery-rate sampling.
- **Dropbox (2019, v2 on Linux 5.3 patches):** 4× lower loss and 3× lower inflight than v1, but still about 2× CUBIC's loss. Throughput comparable to CUBIC on slow links.
- **Verizon Media/Edgecast:** BBR on client-facing traffic only. Kept CUBIC inside the DC after a ~50% PoP-to-PoP regression.
- **CloudFront (2019):** up to 22% aggregate throughput. Third-party Tutela data saw ~28% in Asia for a 2 MB object.

## 11. Frontier (what's new)

| Year · venue | Paper | Contribution |
|---|---|---|
| 2024 · PAM | [Promises and Potential of BBRv3](https://pam2024.cs.northwestern.edu/pdfs/paper-59.pdf) (Zeynali, Weyulu, Fathalli, Chandrasekaran, Feldmann) | First independent v3 study. "BBRv3's throughput unfairness towards … Cubic is nearly identical to BBRv1's behavior and is exacerbated in shallow buffers". Long-RTT bias persists. v3 converges faster than v1/v2 among BBR flows but has more retransmits than v2 in shallow buffers |
| 2024 · ANRW | [BBRv3 in the public Internet: a boon or a bane?](https://balakrishnanc.github.io/papers/zeynali-anrw2024.pdf) | Adds ECN: one BBRv3 flow gets >~99% vs 5 CUBIC flows. JFI tables show CUBIC at ~0.5–1.6% share |
| 2025 · IFIP Networking | [BBR's Sharing Behavior with CUBIC and Reno](https://arxiv.org/abs/2505.07741) (Sarpkaya, Srivastava, Fund, Panwar) | Validates the Ware steady-state and the IMC'22 fluid models on FABRIC. They fit v1 and partly v2, but **v3 shows "clear discrepancies"**, so we lack a working analytical model for v3 |
| 2025 · PERFORMANCE | [A Control-Theoretic Perspective on BBR/CUBIC Competition](https://arxiv.org/abs/2510.22773) | Treats the BBR–CUBIC interaction as a feedback system to explain the coexistence dynamics |
| 2025 · PAM | [To Adopt or Not to Adopt L4S-Compatible CC?](https://arxiv.org/abs/2411.10952) | Measures partial L4S deployment where Prague / L4S-BBR coexist with CUBIC/BBR. The incentive question for ECN-based low latency |
| 2026 · NSDI | [FRCC: Towards Provably Fair and Robust CC](https://www.usenix.org/conference/nsdi26/presentation/agarwal-anup) (Agarwal, Arun, Seshan) | "First CCA that provably bounds unfairness (avoids starvation) even under network jitter". Separates flow-count signaling from capacity estimation |
| 2026 · arXiv | [Unveiling TCP BBR Dominance in Starlink Internet](https://arxiv.org/abs/2607.07133) | Measures BBR (v1 and v3) against CUBIC over Starlink, where handovers every ~15 s reshuffle RTT and capacity |
| 2026 · IETF | [draft-ietf-ccwg-bbr-06](https://datatracker.ietf.org/doc/html/draft-ietf-ccwg-bbr-06) (Cardwell, Swett, Beshay) | BBRv3 as a CCWG working-group document (editors from Google and Meta), Experimental track. Renamed `inflight_hi/lo` → `inflight_longterm/shortterm` and specifies the 2–3 s / 62–63-round probe timing |
| 2025 · arXiv | [Learning-Based vs Human-Derived CC](https://arxiv.org/abs/2510.25105) | Side-by-side test of Sage/Astraea/Orca vs BBRv3/CUBIC. Learning-based schemes still carry overhead and generalization gaps |

**What changed in the last two years:** v3 replaced v1 as Google's default, BBR became an IETF WG draft, independent measurements showed v3's fairness problems largely survived, ECN made things worse against classic CC, and the theory side moved from "model BBR" to "build provably starvation-free CC" (FRCC).

## 11b. Open problems

1. **What does "fair" even mean between different CCAs?** Jain's index treats every unequal split as equally bad and ignores how long it lasts. Ware et al. (HotNets 2019, "Beyond Jain's Fairness Index") argue for *harm*-based metrics: how much worse off am I because you showed up? Nobody agrees on the target, so nobody can say v3 is "done".
2. **Coexistence with CUBIC in shallow buffers.** Any rate-based scheme that probes above its estimate overflows a sub-BDP buffer. A loss bound (v3's 2%) helps, but CUBIC halves at *any* loss, so the two respond on different scales. PAM 2024 shows the v3 gap ≈ v1's.
3. **Jitter-robust delay signals.** The starvation theorem says a delay-convergent CCA must oscillate by at least jitter/2. That conflicts with the low-delay goal. FRCC is one exit, but it isn't deployed and hasn't been evaluated at Internet scale.
4. **No validated analytical model of v3.** The 2025 IFIP paper finds existing models diverge for v3. Without one, every tuning change needs a testbed campaign.
5. **ECN semantics.** v3 treats CE as a DCTCP/L4S-style signal. Classic RFC 3168 AQMs mark like loss. With mixed deployment the same bit means two different things, and CUBIC gets crushed (ANRW 2024). L4S's dual-queue isolation is the proposed fix but isn't widely deployed yet.
6. **LEO and 5G.** Capacity and RTT change every few seconds (Starlink reconfigures roughly every 15 s). A 10 s min filter and 2–3 s probe cadence are too slow, so you get overshoot or underuse ([HotNets 2024 LEO mobility](https://conferences.sigcomm.org/hotnets/2024/papers/hotnets24-79.pdf)).
7. **Multipath QUIC coupling.** Coupled BBR across subflows that may share a bottleneck has no standard. Reno-style coupled CC (LIA/OLIA) doesn't translate to rate-based control.

## 12. Lineage

- **1979** Kleinrock: power metric, the optimum at BDP.
- **1981** Jaffe: a distributed algorithm can't converge to it with a single signal.
- **1988** Jacobson: TCP congestion avoidance (Tahoe/Reno), loss as the signal, ACK clocking.
- **1994** Vegas: delay-based, loses to Reno.
- **2008** CUBIC: RTT-independent cubic growth, became the Linux default.
- **2011–13** bufferbloat recognized; CoDel/fq_codel AQMs.
- **2014–15** PCC (online learning), Sprout/Remy (learned).
- **2016** **BBRv1**: ACM Queue paper, Linux 4.9, B4 + YouTube.
- **2017** Linux 4.13 internal pacing; ICNP shallow-buffer critique.
- **2018** Copa (NSDI); BBR Wi-Fi ACK-aggregation patches.
- **2019** **BBRv2** (alpha): loss + ECN, inflight_hi/lo. Ware IMC model; Dropbox eval.
- **2022** Starvation theorem; IMC fluid model (Scherrer et al.).
- **2023** **BBRv3** released (July); Sage (SIGCOMM).
- **2024** BBRv3 default for google.com + YouTube; PAM/ANRW critiques; IETF CCWG adoption.
- **2026** draft-ietf-ccwg-bbr-06; FRCC (NSDI).

## 13. Hands-on (≤30 min)

`bbr_sim.py` in this folder is a toy packet-level simulator: one bottleneck, a Reno-like sender and a BBRv1-like sender (max/min filters, Startup/Drain/ProbeBW/ProbeRTT, pacing). It's deliberately simple: drops are detected instantly and there are no SACK or RTO details.

```bash
python3 bbr_sim.py --trace       # 12 Mbit/s, 40 ms, buffer 8×BDP, print BBR states
python3 bbr_sim.py --buf 0.5     # shallow buffer
python3 bbr_sim.py --buf 32      # bloated buffer
```

Actual output on this machine:

```
# --buf 8
reno  bdp=40.0pkt buf=320pkt  goodput=11.91Mbit/s median_rtt=221.0ms drops=1
bbr   bdp=40.0pkt buf=320pkt  goodput=11.89Mbit/s median_rtt=55.5ms  drops=0
# --buf 0.5
reno  bdp=40.0pkt buf=20pkt   goodput=11.32Mbit/s median_rtt=49.0ms  drops=8
bbr   bdp=40.0pkt buf=20pkt   goodput=11.89Mbit/s median_rtt=49.5ms  drops=324
# --buf 32
reno  bdp=40.0pkt buf=1280pkt goodput=11.91Mbit/s median_rtt=670.0ms drops=1
bbr   bdp=40.0pkt buf=1280pkt goodput=11.89Mbit/s median_rtt=55.5ms  drops=0
```

Read it this way: Reno's RTT tracks *buffer size* (221 → 670 ms), while BBR's stays at about RTprop + ~0.4 BDP of probe queue whatever the buffer. In the shallow buffer BBRv1 gets 5% more goodput by blasting through 40× more drops. That is the v1 retransmit problem in miniature.

Try next:

1. Set the Drain gain to 1.0 and watch the Startup queue never drain.
2. Remove the 0.75 phase (`gains = [1.25, 1, 1, ...]`) and watch the median RTT creep up.
3. On a real Linux box: `tc qdisc add dev lo root netem delay 20ms rate 50mbit limit 1000`, run `iperf3 -C bbr` vs `-C cubic`, and watch `ss -tin` show `bw`, `mrtt` and `pacing_gain` cycling through 1.25/0.75.

## 14. Question ladder

**Mechanism**

1. When an ACK arrives, exactly which two intervals does BBR compare to compute a delivery-rate sample, and why the max of the two?
2. What happens to `max_bw` when the application goes idle for 2 s, then resumes?
3. Walk through what ProbeBW_UP does in v3 if loss reaches 3% halfway through the phase.
4. Why does ProbeRTT trigger on "min_rtt not refreshed" rather than on a fixed timer?

**Why**

5. Why is the Startup gain ~2.77–2.89 and not 2?
6. Why does BBR need a cwnd at all if it paces?
7. Why does v3 use 0.9 in DOWN instead of v1's 0.75?
8. Why 62–63 rounds for T_reno and not, say, 200?

**Counterfactual**

9. If you made the RTprop filter 60 s instead of 10 s, what breaks?
10. If cwnd_gain were 1 instead of 2, what would happen on a Wi-Fi link with ACK aggregation?
11. What if every flow on the Internet ran BBRv1, so there is no CUBIC at all? Does bufferbloat vanish?

**Adversarial**

12. How could an on-path middlebox make a BBR sender wildly overestimate bandwidth?
13. Construct a scenario where two BBR flows on the same bottleneck get a 10:1 split.
14. Why does enabling ECN on a classic-AQM router make BBRv3 *more* unfair to CUBIC?

**Connection**

15. How does BBR's delivery-rate estimator relate to TCP's ACK clock from Jacobson '88?
16. How is BBR's "probe up, pay back" related to CUBIC's concave/convex window curve around W_max?
17. How does L4S change the problem BBR is trying to solve?

**Open**

18. Can any sender-only CCA be both starvation-free under jitter and low-delay?
19. What fairness metric should the IETF use to judge whether BBRv3 is "safe to deploy"?

### Answers

<details><summary>1. Two intervals</summary>

`send_elapsed = P.sent_time − P.first_sent_time` (how long the sender took to send the flight) and `ack_elapsed = now − P.delivered_time` (how long the ACKs for it took to come back). The rate is `Δdelivered / max(send_elapsed, ack_elapsed)`. ACK compression or aggregation can make `ack_elapsed` artificially short, and a sender burst can make `send_elapsed` short. The bottleneck can't deliver faster than either one, so the larger interval gives the conservative, unbiased-low estimate.
</details>

<details><summary>2. Idle then resume</summary>

During idle, any samples are marked app-limited and can't lower `max_bw`. If the idle lasts longer than the filter window (10 rounds in v1), the old peak expires only when it is replaced. Implementations keep the last max because app-limited samples are ignored unless they're higher. On restart BBR paces at the old `max_bw`, not slow-start. Linux also has a "restart from idle" path that paces at `pacing_gain=1·bw` so it doesn't dump a burst.
</details>

<details><summary>3. Loss in UP</summary>

The loss rate for the round crosses `LossThresh = 2%`. BBR sets `inflight_longterm` to the inflight at which loss crossed the threshold (with a correction to estimate where it crossed 2%), sets `prev_probe_too_high`, exits UP to DOWN, and cuts the short-term bounds by β = 0.7. The next UP is a short "precautionary" probe until it shows no excess loss.
</details>

<details><summary>4. Stale-triggered ProbeRTT</summary>

If the flow naturally observed a new minimum (e.g. the app was idle and the queue emptied, or another flow left), there's no need to dip. Triggering only when `min_rtt` hasn't been refreshed for `ProbeRTTInterval` (5 s in v3) avoids the throughput cost for flows that see the true RTprop for free. It also tends to synchronize competing BBR flows: they all see the same queue, so they all go stale and dip together, and that dip empties the queue for everyone.
</details>

<details><summary>5. Startup gain</summary>

The bandwidth estimate lags: it's the delivery rate of data sent about a round ago, averaged over a round, and reported a round later. For the send rate to double each round, the gain must correct for that lag. Integrating an exponential `r₀2^{t/R}` over `[t−2R, t−R]` gives `r(t)/(4 ln 2)`, so g = 4 ln 2 ≈ 2.77. Gain 2 would grow more slowly than 2× per round, roughly 1.4–1.5×, and take many more rounds to find BtlBw.
</details>

<details><summary>6. Why cwnd</summary>

Pacing is open-loop between ACKs. If the path stalls (ACK loss, a delay spike, ACK aggregation gaps) a pure pacer keeps sending at `max_bw` with no feedback. cwnd = 2·BDP bounds inflight so that stall costs at most one extra BDP of queue. Against CUBIC, that cap is what sets BBRv1's share.
</details>

<details><summary>7. 0.9 vs 0.75</summary>

The draft calls 0.9 "the minimum pacing_gain that allows bandwidth-based convergence to approximate fairness", given UP = 1.25. It also gives up less throughput during DOWN. v3 no longer depends on DOWN to empty the queue fully. It uses inflight bounds and `Headroom` (CRUISE at 0.85 × inflight_longterm) to keep queues low.
</details>

<details><summary>8. 62–63 rounds</summary>

Two constraints. With much fewer than ~60 rounds between probes (each probe may cause loss), Reno/CUBIC flows can't regrow enough to carry 4K video. With too many rounds, BBR can't tolerate 1% random loss: `(0.99)^N · 4 ≥ 1` requires N ≤ ~137. 62–63 satisfies both, and the randomization avoids synchronization.
</details>

<details><summary>9. 60 s RTprop window</summary>

ProbeRTT would happen much less often (good for throughput), but a route change that *raises* propagation delay would go unnoticed for up to 60 s. BDP would be underestimated and BBR would be cwnd-limited below capacity. Competing BBR flows would also stay on standing-queue-inflated estimates longer, and multi-flow queue drains would be rarer.
</details>

<details><summary>10. cwnd_gain 1 with ACK aggregation</summary>

ACKs arrive in clumps separated by gaps. With cwnd = 1·BDP, the sender exhausts cwnd during a gap and idles until the next clump, so throughput drops well below BtlBw. That is exactly the problem behind the Wi-Fi patches. Gain 2 plus `extra_acked` gives enough headroom to keep sending through gaps.
</details>

<details><summary>11. All-BBRv1 Internet</summary>

The standing queue would mostly vanish: each flow paces near its share and probes ±25%. But not entirely. Multiple v1 flows each overestimate their share by a bit, and studies found BBR-vs-BBR queues of about 1–2 BDP in deep buffers, plus RTT unfairness and massive loss in shallow buffers. v2/v3 bounds fix much of that.
</details>

<details><summary>12. Middlebox overestimate</summary>

Hold ACKs and release them in a burst (ACK compression / aggregation) so a short `ack_elapsed` interval inflates samples. Or ACK data optimistically before it is delivered (a split-TCP or ACK-spoofing proxy). `max(send_elapsed, ack_elapsed)` and `extra_acked` bound but don't eliminate the first. The second fools every CC.
</details>

<details><summary>13. 10:1 split</summary>

Give the flows very different RTprops on a deep-buffer bottleneck: say 10 ms vs 200 ms. Each caps inflight at 2·its own BDP. The long-RTT flow's cap is 20× larger, so it holds most of the queue, and its delivery rate wins in the max filter. PAM 2024 reports this persists in v3. Alternatively, add non-congestive jitter > 2× the equilibrium delay oscillation to one flow's path (the starvation construction).
</details>

<details><summary>14. ECN makes v3 more unfair</summary>

v3 reacts to CE like DCTCP: proportionally to the fraction marked. CUBIC reacts to *any* CE like a loss, so it cuts its window by 30%. A classic AQM marks well before dropping, so CUBIC keeps backing off on marks while v3 trims only a little. Zeynali et al. (ANRW 2024) measured one v3 flow taking >~99% vs five CUBIC flows with ECN on.
</details>

<details><summary>15. ACK clock</summary>

Jacobson's ACK clock says ACK arrivals are paced by the bottleneck, so sending one packet per ACK self-clocks to the bottleneck rate. BBR measures that clock explicitly (Δdelivered/Δt), filters it with a max, and replaces ACK-clocked sending with timer-driven pacing at that rate. That's why it survives ACK compression better than pure ACK clocking.
</details>

<details><summary>16. CUBIC analogy</summary>

CUBIC grows concavely toward the last W_max (cautious near the known ceiling), then convexly beyond it (probing for more). v3's CRUISE at 85% of `inflight_longterm` then REFILL/UP is the same "stay below the known-safe ceiling, then periodically probe above it" idea, with the ceiling learned from loss/ECN rather than from the last drop.
</details>

<details><summary>17. L4S</summary>

L4S AQMs mark CE at a very shallow queue threshold with a scalable signal and isolate L4S traffic in its own queue. The sender no longer needs to infer the queue from RTT or probe for bandwidth by overshooting. The network tells it. The BBR question becomes "how to respond to a scalable ECN signal while sharing with non-L4S flows", and that is why v3 adopted DCTCP-style ECN.
</details>

<details><summary>18. Starvation-free + low delay</summary>

Unsettled. Arun et al. show delay-convergent CCAs must oscillate by at least half the jitter to avoid starvation, which means some delay floor. FRCC (NSDI 2026) claims provable fairness under jitter by separating flow-count estimation from capacity estimation. Whether that also gives low delay on real Internet paths, and how it coexists with CUBIC, is open.
</details>

<details><summary>19. Fairness metric</summary>

Candidates: Jain's index (simple, ignores duration and harm), max-min fairness (needs to know demand), and "harm" (Ware et al. 2019: compare a flow's performance with and without the newcomer, so it's acceptable if you harm others no more than CUBIC harms them). The IETF hasn't standardized one. BBRv3 is on the *Experimental* track partly for this reason.
</details>

## 15. Go deeper next

1. **L4S and DualPI2:** how a coupled dual-queue AQM gives scalable ECN flows sub-ms queues while protecting classic flows (RFC 9330–9332).
2. **Delivery-rate estimation and ACK frequency in QUIC:** how ACK-delay, ACK decimation and GRO/LRO distort BBR's samples, and the `extra_acked` math.
3. **Swift / HPCC datacenter CC:** delay targets and in-band telemetry instead of model inference. Why Google runs BBR.Swift in the DC.

## Sources

**Papers & specs**

- Cardwell et al., "BBR: Congestion-Based Congestion Control", ACM Queue 14(5), 2016 — https://queue.acm.org/detail.cfm?id=3022184 · PDF https://web.stanford.edu/class/cs244/papers/bbr.pdf
- draft-ietf-ccwg-bbr-06 (July 2026) — https://datatracker.ietf.org/doc/html/draft-ietf-ccwg-bbr-06
- draft-cardwell-iccrg-bbr-congestion-control — https://datatracker.ietf.org/doc/html/draft-cardwell-iccrg-bbr-congestion-control-02
- Ware et al., "Modeling BBR's Interactions with Loss-Based Congestion Control", IMC 2019 — https://www.cs.cmu.edu/~srini/papers/2019-Ware-imc · https://blog.apnic.net/2020/01/24/modelling-bbrs-interactions-with-loss-based-congestion-control/
- Hock, Bless, Zitterbart, "Experimental Evaluation of BBR Congestion Control", ICNP 2017 — https://datatracker.ietf.org/meeting/100/materials/slides-100-iccrg-an-experimental-evaluation-of-bbr-congestion-control-00
- Arun, Alizadeh, Balakrishnan, "Starvation in End-to-End Congestion Control", SIGCOMM 2022 — https://web.stanford.edu/class/cs244/papers/venkat_starvation.pdf
- Scherrer et al., "Model-Based Insights on the Performance, Fairness, and Stability of BBR", IMC 2022 — https://netsec.ethz.ch/publications/papers/scherrer_bbr_imc22.pdf
- Zeynali et al., "Promises and Potential of BBRv3", PAM 2024 — https://pam2024.cs.northwestern.edu/pdfs/paper-59.pdf
- Zeynali et al., "BBRv3 in the public Internet: a boon or a bane?", ANRW 2024 — https://balakrishnanc.github.io/papers/zeynali-anrw2024.pdf
- Sarpkaya et al., "BBR's Sharing Behavior with CUBIC and Reno", IFIP Networking 2025 — https://arxiv.org/abs/2505.07741
- "A Control-Theoretic Perspective on BBR/CUBIC Congestion-Control Competition", PERFORMANCE 2025 — https://arxiv.org/abs/2510.22773
- "To Adopt or Not to Adopt L4S-Compatible Congestion Control?", PAM 2025 — https://arxiv.org/abs/2411.10952
- Agarwal, Arun, Seshan, "FRCC: Towards Provably Fair and Robust Congestion Control", NSDI 2026 — https://www.usenix.org/conference/nsdi26/presentation/agarwal-anup
- "Unveiling TCP BBR Dominance in Starlink Internet", arXiv 2026 — https://arxiv.org/abs/2607.07133
- "Learning-Based vs Human-Derived Congestion Control", arXiv 2025 — https://arxiv.org/abs/2510.25105
- "Mind the Misleading Effects of LEO Mobility on End-to-End CC", HotNets 2024 — https://conferences.sigcomm.org/hotnets/2024/papers/hotnets24-79.pdf

**Code & docs**

- Google BBR repo (v3 branch) — https://github.com/google/bbr/blob/v3/README.md
- Linux `tcp_bbr.c` — https://codebrowser.dev/linux/linux/net/ipv4/tcp_bbr.c.html
- IETF 119 BBRv3 overview & Google deployment — https://datatracker.ietf.org/meeting/119/materials/slides-119-ccwg-bbrv3-overview-and-google-deployment-00
- IETF 97 traffic policing slides — https://www.ietf.org/proceedings/97/slides/slides-97-maprg-traffic-policing-in-the-internet-yuchung-cheng-and-neal-cardwell-00.pdf
- ESnet fasterdata BBR — https://fasterdata.es.net/host-tuning/linux/recent-tcp-enhancements/bbr-tcp/
- Cloudflare quiche BBR pacing issue — https://github.com/cloudflare/quiche/issues/514

**Articles / deployment reports**

- AWS CloudFront BBR — https://aws.amazon.com/blogs/networking-and-content-delivery/tcp-bbr-congestion-control-with-amazon-cloudfront/
- Dropbox, Evaluating BBRv2 — https://dropbox.tech/infrastructure/evaluating-bbrv2-on-the-dropbox-edge-network
- APNIC, BBR evaluation at a large CDN — https://blog.apnic.net/2019/11/01/bbr-evaluation-at-a-large-cdn/
- APNIC, BBR patches for Wi-Fi — https://blog.apnic.net/2018/04/30/bbr-patches-for-higher-wifi-throughput-and-lower-queuing-delays/
