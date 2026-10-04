"""Hands-on part 2: (a) fuse-style windowed hypergraph beats the 1.23 xor factor,
(b) a tiny standard Ribbon (banded GF(2) system, on-the-fly Gaussian elimination).

Run: python3 fuse_ribbon_demo.py
"""
import random
from peel_demo import mix, peel_generic

M64 = (1 << 64) - 1


# ---------- (a) fuse-style: 3 consecutive segments, key picks a window ----------
def fuse_positions(key, seed, seglen, nseg):
    h = mix(key, seed)
    s = (h >> 40) % nseg                       # window start segment
    return (s * seglen + (h % seglen),
            (s + 1) * seglen + ((h >> 14) % seglen),
            (s + 2) * seglen + ((h >> 27) % seglen))


def fuse_success(n, seglen, factor, trials=12):
    nseg = max(1, round(factor * n / seglen) - 2)
    ok = 0
    for t in range(trials):
        keys = random.sample(range(1 << 40), n)
        _, good, _ = peel_generic(keys, lambda k, _t=t: fuse_positions(k, _t * 104729, seglen, nseg),
                                  (nseg + 2) * seglen)
        ok += good
    return ok / trials, (nseg + 2) * seglen / n


# ---------- (b) tiny standard Ribbon: w-wide band over GF(2), r solution bits ----------
W = 64


def ribbon_build(keys, m, r, seed):
    """Insert equations (start, coeff-bitvector, r-bit fingerprint) with on-the-fly
    banded Gaussian elimination. Return (rows, ok)."""
    rc = [0] * m            # stored coefficient word per pivot row (0 = empty)
    rb = [0] * m            # stored rhs
    for k in keys:
        h = mix(k, seed)
        s = h % (m - W + 1)
        c = (mix(k, seed ^ 0x5555) | 1) & M64        # bit0 set: row starts at s
        b = mix(k, seed ^ 0xAAAA) & ((1 << r) - 1)
        i = s
        while True:
            if rc[i] == 0:                            # empty pivot -> store
                rc[i], rb[i] = c, b
                break
            c ^= rc[i]; b ^= rb[i]                    # eliminate against existing pivot
            if c == 0:
                if b == 0: break                      # redundant
                return None, False                    # inconsistent -> new seed
            j = (c & -c).bit_length() - 1             # trailing zeros -> next pivot offset
            c >>= j; i += j
            if i >= m: return None, False
    # back substitution: Z[i] = b_i ^ XOR_{j>0, bit j of c_i} Z[i+j]
    Z = [0] * (m + W)
    for i in range(m - 1, -1, -1):
        if rc[i] == 0: continue
        v, c = rb[i], rc[i] >> 1
        j = 1
        while c:
            if c & 1: v ^= Z[i + j]
            c >>= 1; j += 1
        Z[i] = v
    return Z, True


def ribbon_contains(k, Z, m, r, seed):
    h = mix(k, seed); s = h % (m - W + 1)
    c = (mix(k, seed ^ 0x5555) | 1) & M64
    b = mix(k, seed ^ 0xAAAA) & ((1 << r) - 1)
    v, j = 0, 0
    while c:
        if c & 1: v ^= Z[s + j]
        c >>= 1; j += 1
    return v == b


if __name__ == "__main__":
    random.seed(7)
    n = 100000
    print("fuse-style windows, n=%d, segment length 2048:" % n)
    for f in (1.10, 1.15, 1.19, 1.23):
        rate, real = fuse_success(n, 2048, f)
        print("  array/n = %.3f -> peel success %.0f%%" % (real, 100 * rate))

    print("\nstandard Ribbon, w=64, r=8, n=20000:")
    n = 20000
    keys = random.sample(range(1 << 40), n)
    for eps in (0.02, 0.05, 0.10, 0.15):
        m = int(n * (1 + eps))
        okc = 0
        for sd in range(10):
            Z, ok = ribbon_build(keys, m, 8, sd * 31 + 1)
            okc += ok
        print("  m/n = %.2f -> build success %d/10" % (m / n, okc))
    m = int(n * 1.10)
    for sd in range(50):
        Z, ok = ribbon_build(keys, m, 8, sd + 1)
        if ok: break
    assert all(ribbon_contains(k, Z, m, 8, sd + 1) for k in keys)
    others = random.sample(range(1 << 40, 1 << 41), 100000)
    fpr = sum(ribbon_contains(k, Z, m, 8, sd + 1) for k in others) / len(others)
    print("  built at m/n=1.10 (seed %d): %.2f bits/key, FPR %.3f%% (1/256 = 0.391%%)"
          % (sd + 1, 8 * m / n, 100 * fpr))
