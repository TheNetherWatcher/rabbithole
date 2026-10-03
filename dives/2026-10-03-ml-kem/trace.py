"""Print the intermediate values of one ML-KEM-768 encaps/decaps with fixed seeds (used in section 5)."""
import mlkem
from mlkem import *

def c(x): x%=Q; return x-Q if x>Q//2 else x
p = PARAMS["ML-KEM-768"]; k = 3
d, z, m = bytes(32), bytes([1]) * 32, bytes([0xA5]) + bytes(31)
rho, sigma = G(d + bytes([k]))
print("rho   =", rho.hex()[:16], "... sigma =", sigma.hex()[:16], "...")
A = gen_matrix(rho, k)
print("A_hat[0][0][:4] =", A[0][0][:4])
s0 = cbd(2, PRF(2, sigma, 0)); e0 = cbd(2, PRF(2, sigma, 3))
print("s[0][:8] =", [c(x) for x in s0[:8]], " e[0][:8] =", [c(x) for x in e0[:8]])
ek, dk = keygen("ML-KEM-768", d, z)
print("t_hat[0][:4] =", byte_decode(12, ek[:384])[:4], " len ek =", len(ek), " len dk =", len(dk))
hek = H(ek); K, r = G(m + hek)
print("H(ek) =", hek.hex()[:16], "...  K =", K.hex()[:16], "...  r =", r.hex()[:16], "...")
ct = kpke_encrypt(ek, m, r, p)
print("ct len =", len(ct), " c1 first bytes", ct[:6].hex(), " c2 first bytes", ct[960:966].hex())
_, w = kpke_decrypt(dk[:1152], ct, p, return_w=True)
bits = [(m[i // 8] >> (i % 8)) & 1 for i in range(16)]
print("m bits[:8]  =", bits[:8])
print("w[:8]       =", w[:8])
print("noise[:8]   =", [c(w[i] - bits[i] * 1665) for i in range(8)])
print("decoded[:8] =", [compress(1, x) for x in w[:8]])
K2 = decaps(dk, ct); print("decaps K == encaps K:", K2 == K)
bad = bytearray(ct); bad[0] ^= 1
print("tampered -> K_bar = J(z||c') =", decaps(dk, bytes(bad)).hex()[:16], "...")
