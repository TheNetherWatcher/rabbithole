"""Minimal CDCL SAT solver with a readable trace. ~100 lines, no watched literals
(naive propagation) so the *logic* is visible. Verified vs brute force below.

Literals: +v / -v (DIMACS). Run: python3 cdcl.py
"""
import itertools, random, sys

def solve(clauses, nvars, trace=False):
    clauses = [list(c) for c in clauses]
    val = {}            # var -> bool
    level = {}          # var -> decision level
    reason = {}         # var -> clause (list) or None for decisions
    trail = []          # literals in assignment order
    dl = 0
    act = {v: 0.0 for v in range(1, nvars + 1)}
    inc, decay = 1.0, 0.95
    phase = {v: True for v in range(1, nvars + 1)}

    def lit_val(l):
        v = val.get(abs(l))
        return None if v is None else (v if l > 0 else not v)

    def assign(l, why):
        val[abs(l)] = l > 0; level[abs(l)] = dl; reason[abs(l)] = why; trail.append(l)
        phase[abs(l)] = l > 0

    def propagate():
        changed = True
        while changed:
            changed = False
            for c in clauses:
                vals = [lit_val(l) for l in c]
                if True in vals: continue
                unassigned = [l for l, x in zip(c, vals) if x is None]
                if not unassigned: return c            # conflict
                if len(unassigned) == 1:
                    assign(unassigned[0], c); changed = True
                    if trace: print(f"  L{dl}: propagate {unassigned[0]:+d} because {c}")
        return None

    def analyze(confl):
        # 1-UIP: resolve backwards along trail until one literal of current level remains
        seen, learnt, counter, p, idx = set(), [], 0, None, len(trail) - 1
        c = confl
        while True:
            for q in c:
                if p is not None and q == p: continue
                v = abs(q)
                if v not in seen and level[v] > 0:
                    seen.add(v)
                    nonlocal_bump(v)
                    if level[v] == dl: counter += 1
                    else: learnt.append(q)
            while abs(trail[idx]) not in seen: idx -= 1
            p = trail[idx]; idx -= 1; counter -= 1
            if counter == 0: break
            c = reason[abs(p)]   # resolve on p: reason clause contains p; skipped via `q == p`
        learnt.append(-p)
        bt = max((level[abs(q)] for q in learnt[:-1]), default=0)
        return learnt, bt                               # asserting literal is last

    def nonlocal_bump(v):
        nonlocal inc
        act[v] += inc
        if act[v] > 1e100:
            for u in act: act[u] *= 1e-100
            inc *= 1e-100

    while True:
        confl = propagate()
        if confl is not None:
            if dl == 0:
                return None
            learnt, bt = analyze(confl)
            if trace: print(f"CONFLICT {confl} @L{dl} -> learn {learnt}, backjump to L{bt}")
            inc /= decay
            while trail and level[abs(trail[-1])] > bt:
                u = abs(trail.pop()); del val[u], level[u], reason[u]
            dl = bt
            clauses.append(learnt)
            assign(learnt[-1], learnt)
            if trace: print(f"  L{dl}: assert {learnt[-1]:+d} from learnt clause")
        else:
            free = [v for v in act if v not in val]
            if not free: return dict(val)
            v = max(free, key=lambda x: act[x])          # VSIDS
            dl += 1
            lit = v if phase[v] else -v                  # phase saving
            if trace: print(f"L{dl}: decide {lit:+d}")
            assign(lit, None)

def brute(clauses, n):
    for bits in itertools.product([False, True], repeat=n):
        if all(any((bits[abs(l)-1] if l > 0 else not bits[abs(l)-1]) for l in c) for c in clauses):
            return True
    return False

def check(clauses, model):
    return all(any((model[abs(l)] if l > 0 else not model[abs(l)]) for l in c) for c in clauses)

if __name__ == "__main__":
    # Hand-built example: conflict at level 3 whose 1-UIP is NOT the decision.
    # x3 -> x4 -> {x5, x6}; (-5 v -6 v -2) then conflicts. 1-UIP is x4, not the decision x3.
    F = [[-3, 4], [-4, 5], [-4, 6], [-5, -6, -2], [1, 2, 3, 7]]
    print("=== traced run ==="); m = solve(F, 7, trace=True)
    print("result:", "UNSAT" if m is None else "SAT", "\n")
    random.seed(1); bad = 0
    for t in range(2000):
        n = random.randint(3, 10); k = random.randint(2, 4 * n)
        cl = [[random.choice([-1, 1]) * v for v in random.sample(range(1, n + 1), min(n, random.randint(1, 3)))] for _ in range(k)]
        m = solve(cl, n); exp = brute(cl, n)
        if (m is not None) != exp or (m is not None and not check(cl, {**{v: False for v in range(1, n+1)}, **m})): bad += 1
    print(f"random fuzz vs brute force: 2000 instances, mismatches = {bad}")
