"""1-D toy of Nanite's cluster DAG: a polyline stands in for a mesh.

  * cluster  = run of <= C consecutive segments
  * group    = G consecutive clusters; simplified with its two END POINTS LOCKED
               (the 1-D analogue of "locked group border edges"), then re-split
  * grouping offset alternates by level, so old borders become interior later
  * error is made monotone (max with children), bounds are made nested (hull)
  * LOD cut test per cluster:   proj(self) <= tau  <  proj(parent)

Checks: for random cameras / thresholds the selected clusters must tile
[0, N] exactly (no crack = gap, no overlap).  Then ablate the two monotone
rules and watch it break.  Run: python3 cluster_dag_1d.py
"""
import math, random

N, C, G = 2048, 8, 4
random.seed(7)
Y = [math.sin(i * 0.013) * 40 + math.sin(i * 0.11) * 6 + random.uniform(-1, 1)
     for i in range(N + 1)]


def interp_err(pts, a, b):
    """max |orig - piecewise-linear(pts)| over original indices a..b."""
    worst = 0.0
    for p, q in zip(pts, pts[1:]):
        for i in range(p, q + 1):
            t = (i - p) / (q - p)
            worst = max(worst, abs(Y[i] - (Y[p] * (1 - t) + Y[q] * t)))
    return worst


def simplify(pts, target_segs):
    """greedy interior-point removal; pts[0], pts[-1] are locked."""
    pts = list(pts)
    while len(pts) - 1 > target_segs and len(pts) > 2:
        best, bi = None, None
        for k in range(1, len(pts) - 1):
            p, m, q = pts[k - 1], pts[k], pts[k + 1]
            t = (m - p) / (q - p)
            e = abs(Y[m] - (Y[p] * (1 - t) + Y[q] * t))
            if best is None or e < best:
                best, bi = e, k
        del pts[bi]
    return pts


class Cl:
    def __init__(s, pts, lvl, self_err, self_bnd):
        s.pts, s.lvl = pts, lvl
        s.a, s.b = pts[0], pts[-1]          # covered interval [a, b]
        s.self_err, s.self_bnd = self_err, self_bnd
        s.parent_err, s.parent_bnd = math.inf, None


def split(pts, lvl, err, bnd):
    out = []
    for i in range(0, len(pts) - 1, C):
        out.append(Cl(pts[i:i + C + 1], lvl, err, bnd))
    return out


def build(monotone=True):
    level = split(list(range(N + 1)), 0, 0.0, (0, N))
    allc = list(level)
    lvl = 0
    while len(level) > 1:
        lvl += 1
        off = (G // 2) if lvl % 2 else 0
        cuts = ([0, off] if off else [0]) + list(range(off + G, len(level), G)) + [len(level)]
        cuts = sorted(set(c for c in cuts if c <= len(level)))
        nxt = []
        for s, e in zip(cuts, cuts[1:]):
            grp = level[s:e]
            pts = [grp[0].pts[0]]
            for c in grp:
                pts += c.pts[1:]
            segs = len(pts) - 1
            sp = simplify(pts, max(1, math.ceil(segs / 2)))
            err = interp_err(sp, pts[0], pts[-1])
            lo, hi = grp[0].a, grp[-1].b
            if monotone:
                err = max([err] + [c.self_err for c in grp])
                lo = min([lo] + [c.self_bnd[0] for c in grp])
                hi = max([hi] + [c.self_bnd[1] for c in grp])
            bnd = (lo, hi)
            for c in grp:                       # all members share parent err+bounds
                c.parent_err, c.parent_bnd = err, bnd
            nxt += split(sp, lvl, err, bnd)
        allc += nxt
        level = nxt
    return allc


def dist(bnd, cam):
    lo, hi = bnd
    d = 0 if lo <= cam <= hi else min(abs(cam - lo), abs(cam - hi))
    return max(d, 1.0)                          # "camera distance to bounds"


def select(clusters, cam, tau, K=2000.0):
    sel = []
    for c in clusters:
        ps = c.self_err * K / dist(c.self_bnd, cam)
        pp = math.inf if c.parent_bnd is None else c.parent_err * K / dist(c.parent_bnd, cam)
        if ps <= tau < pp:
            sel.append(c)
    return sel


def tiles(sel):
    sel = sorted(sel, key=lambda c: c.a)
    pos = 0
    for c in sel:
        if c.a != pos:
            return False
        pos = c.b
    return pos == N


def trial(clusters, n=3000):
    bad = 0
    for _ in range(n):
        cam = random.uniform(-300, N + 300)
        tau = 10 ** random.uniform(-1.5, 1.5)
        bad += not tiles(select(clusters, cam, tau))
    return bad, n


if __name__ == "__main__":
    good = build(True)
    print(f"DAG: {len(good)} clusters, root err {max(c.self_err for c in good):.3f}")
    print("monotone err + nested bounds : tiling failures %d / %d" % trial(good))
    bad = build(False)
    print("ablate monotone rules        : tiling failures %d / %d" % trial(bad))
    for tau in (0.5, 4, 20):
        s = select(good, cam=-500, tau=tau)
        by = {}
        for c in s:
            by[c.lvl] = by.get(c.lvl, 0) + 1
        print(f"cut cam=-500 tau={tau:<4}: {len(s):3d} clusters, per level {dict(sorted(by.items()))}")
