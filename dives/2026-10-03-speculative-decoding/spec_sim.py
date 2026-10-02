"""Toy speculative sampling: verify exactness, alpha = sum(min(p,q)), and speedup model.
Run: python spec_sim.py   (numpy only, ~2s)
"""
import numpy as np

rng = np.random.default_rng(0)
V = 8

def softmax(z, T=1.0):
    z = z / T
    e = np.exp(z - z.max())
    return e / e.sum()

logits = rng.normal(size=V) * 2
p = softmax(logits)                              # target
q = softmax(logits + rng.normal(size=V) * 1.0)   # draft = noisy copy

def spec_step(p, q, rng):
    """One-position speculative sampling (Leviathan Alg. 1, gamma=1 view)."""
    x = rng.choice(V, p=q)
    if rng.random() < min(1.0, p[x] / q[x]):
        return x, True
    resid = np.maximum(p - q, 0)
    return rng.choice(V, p=resid / resid.sum()), False

N = 200_000
out = np.empty(N, dtype=int); acc = 0
for i in range(N):
    out[i], a = spec_step(p, q, rng); acc += a
emp = np.bincount(out, minlength=V) / N

print("target p   :", np.round(p, 4))
print("empirical  :", np.round(emp, 4))
print("max |diff| :", np.abs(emp - p).max(), "(should be ~1/sqrt(N) =", round(1/np.sqrt(N), 4), ")")
alpha = np.minimum(p, q).sum()
tv = 0.5 * np.abs(p - q).sum()
print(f"alpha theory = sum min(p,q) = {alpha:.4f} = 1-TV = {1-tv:.4f}; measured = {acc/N:.4f}")
print(f"sample-and-match acceptance = sum p*q = {(p*q).sum():.4f}  (lower: why llama.cpp default path accepts less)")

# Temperature sweep: same logits, both models at temperature T
print("\nT     alpha")
for T in [0.01, 0.5, 1.0, 1.5, 2.0]:
    pT = softmax(logits, T)
    qT = softmax(np.log(q), T)  # draft logits = log q, same temperature
    print(f"{T:<5} {np.minimum(pT, qT).sum():.3f}")

# Speedup model (Theorem 3.8): (1 - a^(g+1)) / ((1-a)(g*c + 1))
def speedup(a, g, c):
    return (1 - a ** (g + 1)) / ((1 - a) * (g * c + 1))

print("\nbest gamma / speedup")
print("c\\alpha " + "".join(f"{a:>12}" for a in [0.6, 0.7, 0.8, 0.9]))
for c in [0.01, 0.05, 0.10]:
    row = []
    for a in [0.6, 0.7, 0.8, 0.9]:
        g = max(range(1, 64), key=lambda g: speedup(a, g, c))
        row.append(f"g={g},{speedup(a, g, c):.2f}x")
    print(f"{c:<8}" + "".join(f"{r:>12}" for r in row))
