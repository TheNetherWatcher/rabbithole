"""
Three small experiments on top of mlkem.py.

1. Noise budget: decrypt many ciphertexts and measure how far w = v - s^T u
   lands from the encoded message bit (0 or ~q/2). Decryption fails only if
   that distance reaches q/4 = 832.
2. The KyberSlash line: Compress_1 divides a secret-dependent value by q.
   Show the division-free replacement gives identical output for every input.
3. Implicit vs explicit rejection: what a decapsulator leaks if it returns an
   error instead of a pseudorandom key.
"""
import os
from collections import Counter

import mlkem
from mlkem import Q, PARAMS


def centered(x):
    x %= Q
    return x - Q if x > Q // 2 else x


def noise_budget(name="ML-KEM-768", trials=200):
    p = PARAMS[name]
    ek, dk = mlkem.keygen(name)
    dk_pke = dk[: 384 * p[0]]
    worst, hist = 0, Counter()
    for _ in range(trials):
        m = os.urandom(32)
        c = mlkem.kpke_encrypt(ek, m, os.urandom(32), p)
        m2, w = mlkem.kpke_decrypt(dk_pke, c, p, return_w=True)
        assert m2 == m
        bits = [(m[i // 8] >> (i % 8)) & 1 for i in range(256)]
        for b, wi in zip(bits, w):
            noise = centered(wi - b * 1665)
            worst = max(worst, abs(noise))
            hist[noise // 50 * 50] += 1
    total = sum(hist.values())
    print(f"[1] {name}: {total} coefficients, worst |noise| = {worst}  (fails at >= {Q // 4})")
    for lo in sorted(hist):
        bar = "#" * max(1, round(60 * hist[lo] / max(hist.values())))
        print(f"    [{lo:5d},{lo + 49:5d}] {hist[lo]:6d} {bar}")


def kyberslash_fix():
    # Reference code before Jan 2024 (poly_tomsg):  t = ((x << 1) + Q/2) / Q & 1
    # The compiler emits a DIV whose latency on many CPUs depends on the operands.
    # Fixed code: multiply by a precomputed reciprocal and shift. No division.
    def slow(x):
        return (((x << 1) + Q // 2) // Q) & 1

    def fixed(x):
        t = (x << 1) + 1665
        t *= 80635          # 80635 ~= 2^28 / 3329
        t >>= 28
        return t & 1

    bad = [x for x in range(Q) if slow(x) != fixed(x)]
    print(f"[2] division-free Compress_1 differs from x/q version on {len(bad)} of {Q} inputs")


def rejection_styles(name="ML-KEM-768"):
    ek, dk = mlkem.keygen(name)
    K, c = mlkem.encaps(ek, name)
    bad = bytearray(c)
    bad[-1] ^= 0x10
    K1 = mlkem.decaps(dk, bytes(bad), name)
    K2 = mlkem.decaps(dk, bytes(bad), name)
    print("[3] tampered ciphertext -> implicit rejection key")
    print(f"    same tampered ct twice gives same key: {K1 == K2}  (deterministic: J(z || c))")
    print(f"    differs from honest key:               {K1 != K}")
    print("    an explicit 'decaps failed' error would instead hand the attacker a 1-bit oracle per query")


if __name__ == "__main__":
    noise_budget()
    kyberslash_fix()
    rejection_styles()
