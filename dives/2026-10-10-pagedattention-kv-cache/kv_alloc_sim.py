"""
KV-cache allocator simulator: contiguous (max / oracle reservation) vs paged.

Models one GPU's KV pool as N token slots. Requests arrive in a queue (FCFS),
each with a prompt length and a (hidden) output length. Every step, each
running request generates one token. We measure how many requests run
concurrently and what fraction of the pool holds *real* KV.

Synthetic lengths (lognormal), not a real trace. Change SEED / distributions
and watch the gap move.

    python3 kv_alloc_sim.py
"""
import math
import random

SEED = 0
POOL_SLOTS = 32_768          # token slots in the KV pool
MAX_LEN = 2048               # model context limit (what "max" reserves)
N_REQ = 3000
STEPS = 4000


def gen_requests(rng):
    reqs = []
    for _ in range(N_REQ):
        p = min(MAX_LEN // 2, max(4, int(rng.lognormvariate(math.log(160), 0.9))))
        o = min(MAX_LEN - p, max(1, int(rng.lognormvariate(math.log(300), 0.9))))
        reqs.append((p, o))
    return reqs


class FirstFit:
    """Contiguous allocator over a linear address space (external fragmentation)."""

    def __init__(self, n):
        self.free = [(0, n)]  # sorted (start, length)

    def alloc(self, size):
        for i, (s, l) in enumerate(self.free):
            if l >= size:
                if l == size:
                    self.free.pop(i)
                else:
                    self.free[i] = (s + size, l - size)
                return s
        return None

    def release(self, start, size):
        self.free.append((start, size))
        self.free.sort()
        merged = []
        for s, l in self.free:
            if merged and merged[-1][0] + merged[-1][1] == s:
                merged[-1] = (merged[-1][0], merged[-1][1] + l)
            else:
                merged.append((s, l))
        self.free = merged

    def largest_hole(self):
        return max((l for _, l in self.free), default=0)


def run_contiguous(reqs, mode):
    ff = FirstFit(POOL_SLOTS)
    queue = list(reqs)
    running = []  # [start, reserved, prompt, out_total, generated]
    used_hist, conc_hist, frag_hist = [], [], []
    for _ in range(STEPS):
        # admit FCFS while the head fits
        while queue:
            p, o = queue[0]
            reserve = MAX_LEN if mode == "max" else p + o
            start = ff.alloc(reserve)
            if start is None:
                break
            queue.pop(0)
            running.append([start, reserve, p, o, 0])
        # decode one token each
        for r in running:
            r[4] += 1
        done = [r for r in running if r[4] >= r[3]]
        for r in done:
            ff.release(r[0], r[1])
        running = [r for r in running if r[4] < r[3]]
        real = sum(r[2] + r[4] for r in running)
        free_total = sum(l for _, l in ff.free)
        used_hist.append(real / POOL_SLOTS)
        conc_hist.append(len(running))
        # external fragmentation: free memory that is not in the largest hole
        frag_hist.append(0 if free_total == 0 else 1 - ff.largest_hole() / free_total)
        if not queue and not running:
            break
    return used_hist, conc_hist, frag_hist


def run_paged(reqs, block):
    n_blocks = POOL_SLOTS // block
    free_blocks = n_blocks
    queue = list(reqs)
    running = []  # [prompt, out_total, generated, blocks_held]
    used_hist, conc_hist, preempt = [], [], 0
    for _ in range(STEPS):
        while queue:
            p, o = queue[0]
            need = math.ceil(p / block)
            if need + 1 > free_blocks:  # keep one block of headroom
                break
            queue.pop(0)
            free_blocks -= need
            running.append([p, o, 0, need])
        # decode: a new block is needed only when the last one is full
        for r in list(running):
            length = r[0] + r[2]
            if length % block == 0:
                if free_blocks == 0:
                    # preempt newest (recompute mode): free all, requeue at front
                    victim = running.pop()
                    free_blocks += victim[3]
                    queue.insert(0, (victim[0] + victim[2], victim[1] - victim[2]))
                    preempt += 1
                    if victim is r:
                        continue
                    if free_blocks == 0:
                        continue
                free_blocks -= 1
                r[3] += 1
            r[2] += 1
        done = [r for r in running if r[2] >= r[1]]
        for r in done:
            free_blocks += r[3]
        running = [r for r in running if r[2] < r[1]]
        real = sum(r[0] + r[2] for r in running)
        used_hist.append(real / POOL_SLOTS)
        conc_hist.append(len(running))
        if not queue and not running:
            break
    return used_hist, conc_hist, preempt


def steady(x):
    """Mean over the busy middle of the run (skip warm-up and drain)."""
    a, b = len(x) // 5, 4 * len(x) // 5
    seg = x[a:b] or x
    return sum(seg) / len(seg)


def main():
    rng = random.Random(SEED)
    reqs = gen_requests(rng)
    mp = sum(p for p, _ in reqs) / len(reqs)
    mo = sum(o for _, o in reqs) / len(reqs)
    print(f"pool={POOL_SLOTS} slots, max_len={MAX_LEN}, {N_REQ} requests, "
          f"mean prompt={mp:.0f}, mean output={mo:.0f}\n")
    print(f"{'allocator':<26}{'KV util':>9}{'concurrent':>12}{'ext frag':>10}{'preempts':>10}")
    for mode in ("max", "oracle"):
        u, c, f = run_contiguous(reqs, mode)
        print(f"{'contiguous / ' + mode:<26}{steady(u):>8.1%}{steady(c):>12.1f}{steady(f):>9.1%}{'-':>10}")
    for block in (1, 16, 128, 512):
        u, c, pre = run_paged(reqs, block)
        print(f"{'paged / block=' + str(block):<26}{steady(u):>8.1%}{steady(c):>12.1f}{'0.0%':>10}{pre:>10}")


if __name__ == "__main__":
    main()
