"""
Metastable failure simulator: one server, one FIFO queue, clients with
timeouts + retries. Inject a short outage (the trigger), remove it, and
watch whether goodput comes back.

    python3 metastable_sim.py                 # run the standard scenarios
    python3 metastable_sim.py --lam 70 --outage 10 --retries 2 --policy fifo

No dependencies. Time advances in 10 ms ticks.
"""
import argparse, collections, random

TICK = 0.01  # seconds


def simulate(lam=70.0, mu=100.0, timeout=1.0, retries=2, outage_start=20.0,
             outage=10.0, duration=120.0, policy="fifo", budget=None,
             drop_expired=False, seed=1):
    """lam: new user requests/s (Poisson). mu: server capacity req/s.
    retries: extra attempts after the first. policy: fifo | lifo.
    budget: retry budget ratio (e.g. 0.1 = retries <= 10% of first tries),
    None = unlimited. drop_expired: server skips attempts whose client
    already gave up (deadline-aware dequeue)."""
    rng = random.Random(seed)
    q = collections.deque()          # items: (send_time, req_id)
    pending = {}                     # req_id -> (attempt_no, current_deadline)
    retry_at = []                    # (time, req_id) waiting to be resent
    next_id = 0
    per_lam = lam * TICK
    serve_credit = 0.0
    tokens = 10.0                    # retry-budget bucket
    stats = collections.defaultdict(lambda: [0, 0, 0])  # sec -> [good, done, sent]
    t = 0.0
    steps = int(duration / TICK)
    for _ in range(steps):
        sec = int(t)
        # 1. new arrivals (Poisson via Bernoulli thinning, per_lam < 1 per sub-step)
        n = 0
        k = per_lam
        while k > 0:
            if rng.random() < min(k, 1.0):
                n += 1
            k -= 1.0
        for _ in range(n):
            pending[next_id] = (0, t + timeout)
            q.append((t, next_id))
            stats[sec][2] += 1
            if budget is not None:
                tokens = min(tokens + budget, 10.0 + budget * lam * 10)
            next_id += 1
        # 2. client timeouts -> retries
        expired = [rid for rid, (a, dl) in pending.items() if dl <= t]
        for rid in expired:
            a, _ = pending.pop(rid)
            if a < retries and (budget is None or tokens >= 1.0):
                if budget is not None:
                    tokens -= 1.0
                pending[rid] = (a + 1, t + timeout)
                q.append((t, rid))
                stats[sec][2] += 1
        # 3. server work (zero capacity during the outage)
        in_outage = outage_start <= t < outage_start + outage
        if not in_outage:
            serve_credit += mu * TICK
        while serve_credit >= 1.0 and q:
            send_t, rid = q.pop() if policy == "lifo" else q.popleft()
            client_waiting = rid in pending and t - send_t < timeout
            if drop_expired and not client_waiting:
                continue                     # free skip: no work burned
            serve_credit -= 1.0
            stats[sec][1] += 1
            if client_waiting:
                pending.pop(rid)
                stats[sec][0] += 1
        if not q:
            serve_credit = min(serve_credit, 1.0)
        t += TICK
    return stats, len(q)


def summarize(name, stats, qlen, duration=120):
    good = [stats[s][0] for s in range(duration)]
    done = [stats[s][1] for s in range(duration)]
    sent = [stats[s][2] for s in range(duration)]
    avg = lambda xs: sum(xs) / len(xs)
    before = avg(good[10:20]); after = avg(good[100:120])
    # first second after the trigger where goodput is back to >= 80% of normal
    back = next((s for s in range(21, duration) if good[s] >= 0.8 * before
                 and all(g >= 0.5 * before for g in good[s:s + 5])), None)
    rec = f"t={back}s" if back else "never"
    verdict = "RECOVERED" if back else "STUCK (metastable)"
    print(f"{name:<36} goodput before={before:5.1f}/s  last-20s={after:5.1f}/s  "
          f"busy={avg(done[100:120]):5.1f}/s  attempts={avg(sent[100:120]):5.1f}/s  "
          f"healthy-again={rec:>6}  -> {verdict}")
    return before, after


SCENARIOS = [
    ("baseline: lam=70, 2 retries, FIFO", dict()),
    ("lower load: lam=25 (< mu/3)", dict(lam=25)),
    ("edge of band: lam=30", dict(lam=30)),
    ("shorter trigger: outage=0.5s", dict(outage=0.5)),
    ("no retries", dict(retries=0)),
    ("retry budget 10%", dict(budget=0.1)),
    ("deadline-aware dequeue", dict(drop_expired=True)),
    ("LIFO queue", dict(policy="lifo")),
]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lam", type=float); ap.add_argument("--outage", type=float)
    ap.add_argument("--retries", type=int); ap.add_argument("--policy")
    ap.add_argument("--budget", type=float); ap.add_argument("--drop-expired", action="store_true")
    a = ap.parse_args()
    custom = {k: v for k, v in vars(a).items() if v not in (None, False)}
    if custom:
        summarize(f"custom {custom}", *simulate(**custom))
    else:
        for name, kw in SCENARIOS:
            summarize(name, *simulate(**kw))
