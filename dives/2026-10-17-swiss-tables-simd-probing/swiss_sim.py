"""Swiss-table probe simulator. Measures groups probed, H2 false matches, and tombstone churn.
Run: python3 swiss_sim.py
Model: capacity = G groups of W slots (G power of two), ctrl bytes EMPTY/DELETED/h2, triangular probe over groups.
"""
import random

MASK = (1 << 64) - 1
EMPTY, DELETED = -128, -2

class Swiss:
    def __init__(self, groups=1 << 12, W=16, never_full_rule=True, seed=1):
        self.G, self.W = groups, W
        self.cap = groups * W
        self.ctrl = [EMPTY] * self.cap
        self.keys = [None] * self.cap
        self.rule = never_full_rule
        self.n = 0
        self.rng = random.Random(seed)

    def _h(self, key):
        # splitmix64 finalizer: Python's tuple hash has weak low/top bits and str hashes are randomized per run
        z = ((key[1] * 0x2545F4914F6CDD1D) ^ (ord(key[0][0]) << 40)) + 0x9E3779B97F4A7C15 & MASK  # deterministic across runs
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK
        h = z ^ (z >> 31)
        return h, h >> 57  # h1 = full hash (low bits pick the group), h2 = top 7 bits

    def _probe(self, h1):
        g, step = h1 % self.G, 0
        while True:
            yield g
            step += 1
            g = (g + step) % self.G  # triangular over groups

    def find(self, key):
        """returns (found, groups_probed, h2_false_matches)"""
        h1, h2 = self._h(key)
        probed = fm = 0
        for g in self._probe(h1):
            probed += 1
            base = g * self.W
            grp = self.ctrl[base:base + self.W]
            for i, c in enumerate(grp):
                if c == h2:
                    if self.keys[base + i] == key:
                        return True, probed, fm
                    fm += 1
            if EMPTY in grp:
                return False, probed, fm
            if probed > self.G:
                return False, probed, fm

    def insert(self, key):
        h1, h2 = self._h(key)
        for g in self._probe(h1):
            base = g * self.W
            for i in range(self.W):
                if self.ctrl[base + i] < -1:  # empty or deleted
                    self.ctrl[base + i] = h2
                    self.keys[base + i] = key
                    self.n += 1
                    return

    def _was_never_full(self, idx):
        g = idx // self.W
        # simplification: group g never forced a probe past it iff it holds an EMPTY now
        # (exact Abseil test also checks the neighbouring window; see notes)
        base = g * self.W
        return EMPTY in self.ctrl[base:base + self.W]

    def erase(self, key):
        h1, h2 = self._h(key)
        for g in self._probe(h1):
            base = g * self.W
            for i in range(self.W):
                if self.ctrl[base + i] == h2 and self.keys[base + i] == key:
                    idx = base + i
                    self.ctrl[idx] = EMPTY if (self.rule and self._was_never_full(idx)) else DELETED
                    self.keys[idx] = None
                    self.n -= 1
                    return
            if EMPTY in self.ctrl[base:base + self.W]:
                return

def lookup_stats(load, W, trials=20000):
    t = Swiss(groups=(1 << 14) // (W // 8) , W=W)
    n = int(load * t.cap)
    for k in range(n):
        t.insert(("k", k))
    hit_p = sum(t.find(("k", random.randrange(n)))[1] for _ in range(trials)) / trials
    miss = [t.find(("miss", k)) for k in range(trials)]
    miss_p = sum(m[1] for m in miss) / trials
    miss_fm = sum(m[2] for m in miss) / trials
    return hit_p, miss_p, miss_fm

def full_group_fraction(load, W):
    t = Swiss(groups=(1 << 14) // (W // 8), W=W)
    for k in range(int(load * t.cap)):
        t.insert(("f", k))
    full = sum(1 for g in range(t.G) if EMPTY not in t.ctrl[g * W:(g + 1) * W])
    return full / t.G

def poisson_tail(mean, W):
    """P(X >= W) for X ~ Poisson(mean): groups that would overflow if keys landed independently"""
    import math
    cdf = sum(math.exp(-mean) * mean ** i / math.factorial(i) for i in range(W))
    return 1 - cdf

def rehash_in_place(t, live):
    """Abseil-style: when empties + tombstones budget (7/8 of capacity) is spent, clear tombstones."""
    t.ctrl = [EMPTY] * t.cap
    t.keys = [None] * t.cap
    t.n = 0
    for k in live:
        t.insert(("c", k))

def churn(rule, load=0.80, rounds=60000, W=16):
    t = Swiss(groups=1 << 10, W=W, never_full_rule=rule)
    n = int(load * t.cap)
    live = list(range(n))
    for k in live:
        t.insert(("c", k))
    nxt, rehashes, probe_sum, samples = n, 0, 0.0, 0
    rng = random.Random(7)
    budget = int(t.cap * 7 / 8)  # live + tombstones may not exceed this
    for r in range(rounds):
        i = rng.randrange(len(live))
        t.erase(("c", live[i]))
        live[i] = nxt
        occupied = sum(1 for c in t.ctrl if c != EMPTY) if r % 500 == 0 else None
        t.insert(("c", nxt))
        nxt += 1
        if r % 500 == 0:
            if occupied is not None and occupied >= budget:
                rehash_in_place(t, live); rehashes += 1
            probe_sum += sum(t.find(("m", k))[1] for k in range(200)) / 200; samples += 1
    tomb = sum(1 for c in t.ctrl if c == DELETED)
    return tomb / t.cap, rehashes, probe_sum / samples

if __name__ == "__main__":
    random.seed(3)
    print("load  W   hit_groups  miss_groups  miss_h2_false  | theory miss_groups 1/(1-a^W)")
    for load in (0.50, 0.75, 0.875, 0.95):
        for W in (8, 16):
            h, m, f = lookup_stats(load, W)
            print(f"{load:.3f} {W:>2}  {h:9.3f}  {m:10.3f}  {f:12.3f}  | {1/(1-load**W):.3f}")
    print("\nshare of groups with no EMPTY slot (a miss must hop past them)")
    for load in (0.50, 0.75, 0.875):
        for W in (8, 16):
            print(f"load {load:.3f} W={W:>2}  measured {full_group_fraction(load, W):.3f}  poisson-before-overflow {poisson_tail(load * W, W):.3f}")
    print("\nchurn at 80% load, 60k delete+insert rounds, W=16")
    for rule in (False, True):
        tomb, rh, mg = churn(rule)
        print(f"never_full_rule={rule!s:5}  final_tombstones={tomb:.1%}  rehashes={rh}  avg_miss_groups={mg:.2f}")
