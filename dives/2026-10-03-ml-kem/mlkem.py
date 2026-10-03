"""
Pure-Python ML-KEM (FIPS 203), written for reading, not for production.

NOT constant-time, NOT side-channel safe. Every line maps to an algorithm
in FIPS 203 so you can follow the spec with this file open next to it.

Run:  python3 mlkem.py          -> round-trip + sizes + implicit-rejection demo
      python3 experiments.py    -> noise histogram, failure-rate intuition
"""
import hashlib
import os

Q = 3329
N = 256
ZETA = 17  # primitive 256th root of unity mod q

PARAMS = {
    #            k  eta1 eta2 du  dv
    "ML-KEM-512": (2, 3, 2, 10, 4),
    "ML-KEM-768": (3, 2, 2, 10, 4),
    "ML-KEM-1024": (4, 2, 2, 11, 5),
}


# ---------- hash / XOF wrappers (FIPS 203 §4.1) ----------
def G(b):  # SHA3-512 -> (32, 32)
    h = hashlib.sha3_512(b).digest()
    return h[:32], h[32:]


def H(b):  # SHA3-256
    return hashlib.sha3_256(b).digest()


def J(b):  # SHAKE256, 32 bytes  (implicit-rejection key)
    return hashlib.shake_256(b).digest(32)


def PRF(eta, s, b):  # SHAKE256(s || b), 64*eta bytes
    return hashlib.shake_256(s + bytes([b])).digest(64 * eta)


# ---------- NTT (FIPS 203 §4.3) ----------
def bitrev7(i):
    return int(f"{i:07b}"[::-1], 2)


ZETAS = [pow(ZETA, bitrev7(i), Q) for i in range(128)]
GAMMAS = [pow(ZETA, 2 * bitrev7(i) + 1, Q) for i in range(128)]


def ntt(f):  # Algorithm 9
    f = list(f)
    i = 1
    length = 128
    while length >= 2:
        for start in range(0, 256, 2 * length):
            z = ZETAS[i]
            i += 1
            for j in range(start, start + length):
                t = z * f[j + length] % Q
                f[j + length] = (f[j] - t) % Q
                f[j] = (f[j] + t) % Q
        length //= 2
    return f


def intt(f):  # Algorithm 10
    f = list(f)
    i = 127
    length = 2
    while length <= 128:
        for start in range(0, 256, 2 * length):
            z = ZETAS[i]
            i -= 1
            for j in range(start, start + length):
                t = f[j]
                f[j] = (t + f[j + length]) % Q
                f[j + length] = z * (f[j + length] - t) % Q
        length *= 2
    return [x * 3303 % Q for x in f]  # 3303 = 128^-1 mod q


def mul_ntt(f, g):  # Algorithms 11 + 12: 128 products in Z_q[X]/(X^2 - gamma_i)
    h = [0] * 256
    for i in range(128):
        a0, a1, b0, b1 = f[2 * i], f[2 * i + 1], g[2 * i], g[2 * i + 1]
        h[2 * i] = (a0 * b0 + a1 * b1 * GAMMAS[i]) % Q
        h[2 * i + 1] = (a0 * b1 + a1 * b0) % Q
    return h


def add(f, g):
    return [(a + b) % Q for a, b in zip(f, g)]


def sub(f, g):
    return [(a - b) % Q for a, b in zip(f, g)]


# ---------- sampling (FIPS 203 §4.2.2) ----------
def sample_ntt(seed34):  # Algorithm 7: rejection-sample uniform coeffs from SHAKE128
    xof = hashlib.shake_128(seed34).digest(840)  # 840 bytes is plenty (P(fail) ~ 2^-260 for this toy)
    out, pos = [], 0
    while len(out) < 256:
        c0, c1, c2 = xof[pos], xof[pos + 1], xof[pos + 2]
        pos += 3
        d1 = c0 + 256 * (c1 % 16)
        d2 = (c1 // 16) + 16 * c2
        if d1 < Q:
            out.append(d1)
        if d2 < Q and len(out) < 256:
            out.append(d2)
    return out


def cbd(eta, b):  # Algorithm 8: centered binomial, coeffs in [-eta, eta]
    bits = [(b[i // 8] >> (i % 8)) & 1 for i in range(len(b) * 8)]
    f = []
    for i in range(256):
        x = sum(bits[2 * i * eta + j] for j in range(eta))
        y = sum(bits[2 * i * eta + eta + j] for j in range(eta))
        f.append((x - y) % Q)
    return f


# ---------- compression + encoding (FIPS 203 §4.2.1) ----------
def compress(d, x):  # round(2^d / q * x) mod 2^d, integer-only
    return ((x << d) + Q // 2) // Q % (1 << d)


def decompress(d, y):  # round(q / 2^d * y)
    return (y * Q + (1 << (d - 1))) >> d


def byte_encode(d, f):  # Algorithm 5
    bits = []
    for a in f:
        bits += [(a >> j) & 1 for j in range(d)]
    return bytes(sum(bits[8 * i + j] << j for j in range(8)) for i in range(len(bits) // 8))


def byte_decode(d, b):  # Algorithm 6
    bits = [(b[i // 8] >> (i % 8)) & 1 for i in range(len(b) * 8)]
    m = Q if d == 12 else 1 << d
    return [sum(bits[i * d + j] << j for j in range(d)) % m for i in range(256)]


# ---------- K-PKE: the IND-CPA core (FIPS 203 §5) ----------
def gen_matrix(rho, k):  # A_hat[i][j] = SampleNTT(rho || j || i)
    return [[sample_ntt(rho + bytes([j, i])) for j in range(k)] for i in range(k)]


def kpke_keygen(d, p):  # Algorithm 13
    k, eta1, *_ = p
    rho, sigma = G(d + bytes([k]))
    A = gen_matrix(rho, k)
    s = [cbd(eta1, PRF(eta1, sigma, i)) for i in range(k)]
    e = [cbd(eta1, PRF(eta1, sigma, k + i)) for i in range(k)]
    s_hat = [ntt(x) for x in s]
    e_hat = [ntt(x) for x in e]
    t_hat = []
    for i in range(k):
        acc = e_hat[i]
        for j in range(k):
            acc = add(acc, mul_ntt(A[i][j], s_hat[j]))
        t_hat.append(acc)
    ek = b"".join(byte_encode(12, t) for t in t_hat) + rho
    dk = b"".join(byte_encode(12, x) for x in s_hat)
    return ek, dk


def kpke_encrypt(ek, m, r, p):  # Algorithm 14
    k, eta1, eta2, du, dv = p
    t_hat = [byte_decode(12, ek[384 * i: 384 * (i + 1)]) for i in range(k)]
    rho = ek[384 * k:]
    A = gen_matrix(rho, k)
    y = [cbd(eta1, PRF(eta1, r, i)) for i in range(k)]
    e1 = [cbd(eta2, PRF(eta2, r, k + i)) for i in range(k)]
    e2 = cbd(eta2, PRF(eta2, r, 2 * k))
    y_hat = [ntt(x) for x in y]
    u = []
    for i in range(k):  # u = A^T y + e1
        acc = [0] * 256
        for j in range(k):
            acc = add(acc, mul_ntt(A[j][i], y_hat[j]))
        u.append(add(intt(acc), e1[i]))
    mu = [decompress(1, b) for b in byte_decode(1, m)]  # bit -> 0 or 1665 (~q/2)
    acc = [0] * 256
    for i in range(k):
        acc = add(acc, mul_ntt(t_hat[i], y_hat[i]))
    v = add(add(intt(acc), e2), mu)  # v = t^T y + e2 + mu
    c1 = b"".join(byte_encode(du, [compress(du, x) for x in ui]) for ui in u)
    c2 = byte_encode(dv, [compress(dv, x) for x in v])
    return c1 + c2


def kpke_decrypt(dk, c, p, return_w=False):  # Algorithm 15
    k, _, _, du, dv = p
    u = [[decompress(du, y) for y in byte_decode(du, c[32 * du * i: 32 * du * (i + 1)])] for i in range(k)]
    v = [decompress(dv, y) for y in byte_decode(dv, c[32 * du * k:])]
    s_hat = [byte_decode(12, dk[384 * i: 384 * (i + 1)]) for i in range(k)]
    acc = [0] * 256
    for i in range(k):
        acc = add(acc, mul_ntt(s_hat[i], ntt(u[i])))
    w = sub(v, intt(acc))  # w = v - s^T u = mu + (small noise)
    m = byte_encode(1, [compress(1, x) for x in w])
    return (m, w) if return_w else m


# ---------- ML-KEM: FO transform with implicit rejection (FIPS 203 §6) ----------
def keygen(name="ML-KEM-768", d=None, z=None):  # Algorithms 16 + 19
    p = PARAMS[name]
    d = d or os.urandom(32)
    z = z or os.urandom(32)
    ek, dk_pke = kpke_keygen(d, p)
    dk = dk_pke + ek + H(ek) + z
    return ek, dk


def encaps(ek, name="ML-KEM-768", m=None):  # Algorithms 17 + 20
    p = PARAMS[name]
    k = p[0]
    # input check (FIPS 203 §7.2): ek coefficients must already be reduced mod q
    for i in range(k):
        chunk = ek[384 * i: 384 * (i + 1)]
        if byte_encode(12, byte_decode(12, chunk)) != chunk:
            raise ValueError("modulus check failed")
    m = m or os.urandom(32)
    K, r = G(m + H(ek))
    c = kpke_encrypt(ek, m, r, p)
    return K, c


def decaps(dk, c, name="ML-KEM-768", verbose=False):  # Algorithms 18 + 21
    p = PARAMS[name]
    k = p[0]
    dk_pke = dk[: 384 * k]
    ek = dk[384 * k: 768 * k + 32]
    h = dk[768 * k + 32: 768 * k + 64]
    z = dk[768 * k + 64:]
    m2 = kpke_decrypt(dk_pke, c, p)
    K2, r2 = G(m2 + h)
    K_bar = J(z + c)  # pseudorandom "reject" key, depends on secret z
    c2 = kpke_encrypt(ek, m2, r2, p)  # re-encrypt: the FO check
    ok = c == c2  # real code: constant-time compare + constant-time select
    if verbose:
        print(f"  re-encryption matches: {ok}")
    return K2 if ok else K_bar


if __name__ == "__main__":
    for name in PARAMS:
        ek, dk = keygen(name)
        K, c = encaps(ek, name)
        K2 = decaps(dk, c, name)
        print(f"{name}: ek={len(ek)}B dk={len(dk)}B ct={len(c)}B  shared secret match: {K == K2}")

    print("\nImplicit rejection demo (ML-KEM-768):")
    ek, dk = keygen()
    K, c = encaps(ek)
    bad = bytearray(c)
    bad[0] ^= 1  # flip one bit of the ciphertext
    K_bad = decaps(dk, bytes(bad), verbose=True)
    print(f"  honest K   = {K.hex()[:32]}...")
    print(f"  tampered K = {K_bad.hex()[:32]}...  (no error raised; looks random)")
