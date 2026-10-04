"""Hands-on: CDCL (CaDiCaL via PySAT) on pigeonhole PHP(n+1 -> n); prints conflicts per size.
Pigeonhole is UNSAT, needs exponential-size resolution proofs (Haken 1985) => conflicts blow up."""
import time, itertools
from pysat.solvers import Cadical153

def php(n):  # n+1 pigeons, n holes; var p(i,j) = pigeon i in hole j
    v = lambda i, j: i * n + j + 1
    cl = [[v(i, j) for j in range(n)] for i in range(n + 1)]           # each pigeon somewhere
    for j in range(n):                                                  # no two share a hole
        for a, b in itertools.combinations(range(n + 1), 2):
            cl.append([-v(a, j), -v(b, j)])
    return cl

for n in range(5, 11):
    s = Cadical153(bootstrap_with=php(n)); t = time.time(); r = s.solve()
    st = s.accum_stats(); print(f"PHP n={n:2d} sat={r} conflicts={st['conflicts']:>9} time={time.time()-t:7.2f}s"); s.delete()
