"""Toy loss-free balancing (Wang et al. 2024 / DeepSeek-V3 style).
Frozen skewed router, bias b_i added ONLY for top-k selection, gate uses unbiased sigmoid score.
Update: b_i += u * sign(mean_load - load_i). Measures MaxVio = (max load - mean) / mean."""
import numpy as np

def run(u, steps=400, N=16, k=2, T=4096, d=32, seed=0):
    rng = np.random.default_rng(seed)
    W = rng.normal(size=(d, N)) / np.sqrt(d)
    W[:, 0] += 0.0
    skew = rng.normal(size=N) * 0.8            # persistent per-expert popularity (the "rich")
    b = np.zeros(N)
    hist = []
    for t in range(steps):
        x = rng.normal(size=(T, d))
        s = 1 / (1 + np.exp(-(x @ W + skew)))   # sigmoid affinity, unbiased
        top = np.argpartition(-(s + b), k, axis=1)[:, :k]   # selection uses biased score
        load = np.bincount(top.ravel(), minlength=N).astype(float)
        mean = load.mean()
        hist.append((load.max() - mean) / mean)
        b += u * np.sign(mean - load)           # overloaded -> bias down
    return np.array(hist), b

for u in [0.0, 0.001, 0.01, 0.05]:
    h, b = run(u)
    print(f"u={u:<6} MaxVio step0={h[0]:.3f}  step100={h[100]:.3f}  mean(last100)={h[-100:].mean():.3f}  |b|max={np.abs(b).max():.3f}")
