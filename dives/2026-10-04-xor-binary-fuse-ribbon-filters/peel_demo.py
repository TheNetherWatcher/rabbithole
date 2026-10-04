"""Hands-on: watch hypergraph peeling succeed/fail around the 1.23 threshold,
then build a real 8-bit XOR filter and measure its false-positive rate.

Run: python3 peel_demo.py
"""
import random

M64 = (1 << 64) - 1


def mix(x, seed):
    # splitmix64-style finalizer
    x = (x + seed + 0x9E3779B97F4A7C15) & M64
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & M64
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & M64
    return x ^ (x >> 31)


def positions(key, seed, block):
    h = mix(key, seed)
    # three independent-ish slices of one 64-bit hash, one block each
    return (h % block,
            block + ((h >> 21) % block),
            2 * block + ((h >> 42) % block))


def peel(keys, seed, block):
    return peel_generic(keys, lambda k: positions(k, seed, block), 3 * block)


def peel_generic(keys, posfn, nverts):
    """Return (order, ok, pos). order = [(key, vertex_that_was_degree_1)] in peel order."""
    cnt = [0] * nverts
    xr = [0] * nverts               # XOR of keys incident to each vertex
    pos = {}
    for k in keys:
        p = posfn(k)
        pos[k] = p
        for v in p:
            cnt[v] += 1
            xr[v] ^= k
    stack = [v for v in range(nverts) if cnt[v] == 1]
    order = []
    while stack:
        v = stack.pop()
        if cnt[v] != 1:
            continue
        k = xr[v]                    # the single remaining key at v
        order.append((k, v))
        for u in pos[k]:
            cnt[u] -= 1
            xr[u] ^= k
            if cnt[u] == 1:
                stack.append(u)
    return order, len(order) == len(keys), pos


def peel_success_rate(n, factor, trials=40):
    block = max(1, int(factor * n / 3) + 1)
    ok = 0
    for t in range(trials):
        keys = random.sample(range(1 << 40), n)
        ok += peel(keys, t * 7919, block)[1]
    return ok / trials


def build_xor8(keys):
    n = len(keys)
    block = int(1.23 * n / 3) + 11
    for seed in range(100):
        order, ok, pos = peel(keys, seed, block)
        if ok:
            break
    else:
        raise RuntimeError("no seed worked (duplicate keys?)")
    B = [0] * (3 * block)
    fp = lambda k: mix(k, seed ^ 0xABCDEF) & 0xFF
    for k, v in reversed(order):     # assign in reverse peel order
        a, b, c = pos[k]
        B[v] = fp(k) ^ B[a] ^ B[b] ^ B[c] ^ B[v]  # B[v] is 0 yet, so it cancels
    def contains(k):
        a, b, c = positions(k, seed, block)
        return fp(k) == B[a] ^ B[b] ^ B[c]
    return contains, 3 * block, seed


if __name__ == "__main__":
    random.seed(1)
    n = 20000
    print("peeling success vs size factor (n=%d, 3 blocks):" % n)
    for f in (1.10, 1.18, 1.21, 1.23, 1.25, 1.30):
        print("  factor %.2f -> success %.0f%%" % (f, 100 * peel_success_rate(n, f)))

    keys = random.sample(range(1 << 40), n)
    contains, slots, seed = build_xor8(keys)
    assert all(contains(k) for k in keys), "false negative!"
    others = random.sample(range(1 << 40, 1 << 41), 200000)
    fpr = sum(contains(k) for k in others) / len(others)
    print("\nxor8: %d slots for %d keys = %.3f bits/key, seed=%d" % (slots, n, 8 * slots / n, seed))
    print("false positives: %.4f%%  (theory 1/256 = %.4f%%)" % (100 * fpr, 100 / 256))
