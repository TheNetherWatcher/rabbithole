"""
Back-of-envelope cost model for diffusion transformer backbones.

Per transformer layer (forward multiply-accumulates, MACs):
  QKV + output projection : 4 * T * d^2
  attention scores + AV   : 2 * T^2 * d
  MLP (4x expansion)      : 8 * T * d^2
  total                   : 12*T*d^2 + 2*T^2*d

Checks this against the Gflops DiT reports (Peebles & Xie, Table 4),
then uses it to show why token count, not parameter count, drives cost.
No GPU or dependencies needed: `python3 backbone_flops.py`
"""

DIT = {  # name: (layers, width)
    "S": (12, 384), "B": (12, 768), "L": (24, 1024), "XL": (28, 1152),
}
REPORTED = {  # DiT paper, 256x256 (32x32x4 latent), Gflops
    ("S", 8): 0.36, ("S", 4): 1.41, ("S", 2): 6.06,
    ("B", 8): 1.42, ("B", 4): 5.56, ("B", 2): 23.01,
    ("L", 8): 5.01, ("L", 4): 19.70, ("L", 2): 80.71,
    ("XL", 8): 7.39, ("XL", 4): 29.05, ("XL", 2): 118.64,
}


def layer_macs(T, d):
    return 12 * T * d * d + 2 * T * T * d


def model_gmacs(N, d, T):
    return N * layer_macs(T, d) / 1e9


print("1) Formula vs DiT's reported Gflops (latent 32x32)")
print(f"{'model':8}{'p':>3}{'T':>6}{'ours':>10}{'paper':>9}{'err%':>7}{'attn share':>12}")
for (name, p), rep in REPORTED.items():
    N, d = DIT[name]
    T = (32 // p) ** 2
    ours = model_gmacs(N, d, T)
    attn = 2 * T * T * d / layer_macs(T, d)
    print(f"DiT-{name:4}{p:>3}{T:>6}{ours:>10.2f}{rep:>9.2f}{100*(ours-rep)/rep:>7.1f}{100*attn:>11.1f}%")
print("  -> matches to within a few %: DiT's 'Gflops' behave like forward GMACs.\n")

print("2) Same DiT-XL weights, different patch size: params constant, cost explodes")
N, d = DIT["XL"]
for p in (8, 4, 2, 1):
    T = (32 // p) ** 2
    print(f"  p={p}: T={T:5d} tokens -> {model_gmacs(N, d, T):8.1f} GMACs")
print()

print("3) Token counts in production (latent / patch arithmetic)")
cases = [
    # name, pixels H, W, frames, spatial f, temporal f, patch
    ("SD1.5 U-Net 512^2 (no tokens; latent grid)", 512, 512, 1, 8, 1, 1),
    ("DiT-XL/2 ImageNet 256", 256, 256, 1, 8, 1, 2),
    ("Flux.1 1024^2 (f8, 2x2 pack)", 1024, 1024, 1, 8, 1, 2),
    ("SANA 1024^2 (DC-AE f32, p1)", 1024, 1024, 1, 32, 1, 1),
    ("Video 720p, 129 frames (f8, t4, 1x2x2)", 720, 1280, 129, 8, 4, 2),
]
for name, H, W, F, fs, ft, p in cases:
    t_lat = 1 + (F - 1) // ft if F > 1 else 1
    T = t_lat * (H // fs // p) * (W // fs // p)
    print(f"  {name:45} {T:>8,d} tokens")
print()

print("4) Where attention starts to dominate a d=3072 layer (Flux width)")
d = 3072
for T in (256, 1024, 4096, 4608, 16384, 118800):
    share = 2 * T * T * d / layer_macs(T, d)
    print(f"  T={T:>7,d}: attention = {100*share:5.1f}% of layer MACs")
print("  crossover (attn == linear) at T = 6d =", 6 * d)
