#!/usr/bin/env python3
"""Toy EEVDF simulator (1 CPU, 1 ms ticks) mirroring kernel/sched/fair.c semantics:
  V = weighted avg of vruntime; eligible iff V >= v_i (exact cross-multiply, no division);
  deadline vd = ve + slice * NICE0/w ; pick = eligible task with min deadline;
  when v >= vd: new deadline. No run-to-parity, no sleep/lag (see --sleeper)."""
import argparse
from fractions import Fraction as F

NICE0 = 1024

class T:
    def __init__(s, name, w, slice_ms):
        s.name, s.w, s.slice = name, w, slice_ms
        s.v = F(0); s.vd = F(slice_ms * NICE0, w); s.ran = 0

def V(ts):
    W = sum(t.w for t in ts)
    return sum(t.w * t.v for t in ts) / W

def eligible(ts, t):
    # sum(w_j v_j) >= v_i * sum(w_j)  (same as V >= v_i, no division)
    return sum(x.w * x.v for x in ts) >= t.v * sum(x.w for x in ts)

def pick(ts):
    el = [t for t in ts if eligible(ts, t)]
    return min(el, key=lambda t: (t.vd, t.name))

def run(ts, ticks, verbose=True):
    log = []
    for now in range(ticks):
        v_avg = V(ts)
        el = [t.name for t in ts if eligible(ts, t)]
        cur = pick(ts)
        if verbose:
            print(f"t={now:2d} V={float(v_avg):7.2f} " + " ".join(
                f"{t.name}(v={float(t.v):6.2f},vd={float(t.vd):6.2f}{'*' if t.name in el else ' '})" for t in ts)
                + f" -> {cur.name}")
        cur.v += F(1 * NICE0, cur.w); cur.ran += 1
        if cur.v >= cur.vd:                      # update_deadline(): slice consumed
            cur.vd = cur.v + F(cur.slice * NICE0, cur.w)
        log.append(cur.name)
    return "".join(log)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=24)
    a = ap.parse_args()
    print("== 3 equal-weight CPU hogs: A,B slice=3ms; C slice=1ms ==")
    ts = [T("A", 1024, 3), T("B", 1024, 3), T("C", 1024, 1)]
    seq = run(ts, a.ticks); print(seq); print({t.name: t.ran for t in ts})
    print("\n== weights 2:1 (nice -3-ish vs 0): H w=2048, L w=1024, slice 3 both ==")
    ts = [T("H", 2048, 3), T("L", 1024, 3)]
    seq = run(ts, 12, verbose=False); print(seq); print({t.name: t.ran for t in ts})
