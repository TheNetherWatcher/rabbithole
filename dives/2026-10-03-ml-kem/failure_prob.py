"""
Estimate ML-KEM's per-ciphertext decryption-failure probability by exact
convolution of the noise terms (same method as the Kyber team's script,
simplified: assumes coefficients of the products are independent sums).

noise = e^T y + e2 + dv_err  -  s^T (e1 + du_err)
Decryption of one bit fails when |noise| >= q/4.
"""
import math
import numpy as np

Q = 3329


def cbd(eta):
    c = np.array([math.comb(2 * eta, i) for i in range(2 * eta + 1)], float)
    return {i - eta: p for i, p in zip(range(2 * eta + 1), c / c.sum())}


def compress_err(d):
    # error introduced by Decompress(Compress(x)) - x over uniform x in Z_q
    out = {}
    for x in range(Q):
        y = ((x << d) + Q // 2) // Q % (1 << d)
        xr = (y * Q + (1 << (d - 1))) >> d
        e = (xr - x + Q // 2) % Q - Q // 2
        out[e] = out.get(e, 0) + 1 / Q
    return out


def to_arr(dist):
    lo, hi = min(dist), max(dist)
    a = np.zeros(hi - lo + 1)
    for k, v in dist.items():
        a[k - lo] = v
    return a, lo


def conv(a, b):
    (x, lx), (y, ly) = a, b
    return np.convolve(x, y), lx + ly


def product(a, b):
    out = {}
    for i, p in a.items():
        for j, r in b.items():
            out[i * j] = out.get(i * j, 0) + p * r
    return out


def power(dist, n):  # sum of n iid copies, via repeated squaring
    result, base = (np.array([1.0]), 0), to_arr(dist)
    while n:
        if n & 1:
            result = conv(result, base)
        base = conv(base, base)
        n >>= 1
        result = (result[0] / result[0].sum(), result[1])
    return result


def add_dists(a, b):
    out = {}
    for i, p in a.items():
        for j, r in b.items():
            out[i + j] = out.get(i + j, 0) + p * r
    return out


def failure(k, eta1, eta2, du, dv):
    n = 256
    ey = power(product(cbd(eta1), cbd(eta1)), k * n)            # e^T y
    s_e1 = power(product(cbd(eta1), add_dists(cbd(eta2), compress_err(du))), k * n)
    tail = to_arr(add_dists(cbd(eta2), compress_err(dv)))      # e2 + dv error
    tot = conv(conv(ey, s_e1), tail)
    arr, lo = tot
    idx = np.arange(len(arr)) + lo
    p_bit = arr[np.abs(idx) >= Q // 4].sum()
    std = math.sqrt((arr * idx**2).sum())
    return std, p_bit, min(1.0, n * p_bit)


if __name__ == "__main__":
    for name, p in {"ML-KEM-512": (2, 3, 2, 10, 4), "ML-KEM-768": (3, 2, 2, 10, 4),
                    "ML-KEM-1024": (4, 2, 2, 11, 5)}.items():
        std, pb, pc = failure(*p)
        gauss = 256 * math.erfc((Q // 4) / std / math.sqrt(2))
        print(f"{name}: sigma={std:6.1f}  P(fail)/ct ~ 2^{math.log2(pc):7.1f}"
              f"   (Gaussian approx would say 2^{math.log2(gauss):6.1f})")
