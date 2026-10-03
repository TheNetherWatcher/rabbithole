"""Tiny e-graph + equality saturation (~150 lines, stdlib only).

Mirrors egg's design: union-find over e-class ids, hashcons from canonical
e-node -> e-class, deferred congruence repair ("rebuild"), top-down e-matching,
greedy bottom-up extraction with AstSize cost.

Run:  python3 mini_egraph.py
"""
from collections import defaultdict
import itertools

# ---------- terms ----------
# A term is either a str leaf ("a", "2") or a tuple (op, child, child...).
def parse(s):
    toks = s.replace("(", " ( ").replace(")", " ) ").split()
    def go(i):
        if toks[i] == "(":
            op, i = toks[i + 1], i + 2
            kids = []
            while toks[i] != ")":
                k, i = go(i); kids.append(k)
            return (op, *kids), i + 1
        return toks[i], i + 1
    return go(0)[0]

def show(t):
    return t if isinstance(t, str) else "(" + " ".join([t[0]] + [show(k) for k in t[1:]]) + ")"

# ---------- e-graph ----------
class EGraph:
    def __init__(self):
        self.parent = []                 # union-find
        self.memo = {}                   # canonical e-node -> e-class id (hashcons)
        self.classes = defaultdict(set)  # e-class id -> set of e-nodes
        self.parents = defaultdict(list) # e-class id -> [(e-node, e-class)] users
        self.pending = []                # worklist of merged classes (deferred repair)

    def find(self, a):
        while self.parent[a] != a:
            self.parent[a] = self.parent[self.parent[a]]  # path halving
            a = self.parent[a]
        return a

    def canon(self, node):               # node = (op, child_id, ...)
        return (node[0], *[self.find(c) for c in node[1:]])

    def add_node(self, node):
        node = self.canon(node)
        if node in self.memo:            # hashcons hit: structural sharing
            return self.find(self.memo[node])
        cid = len(self.parent); self.parent.append(cid)
        self.memo[node] = cid
        self.classes[cid].add(node)
        for c in node[1:]:
            self.parents[c].append((node, cid))
        return cid

    def add(self, term):
        if isinstance(term, str):
            return self.add_node((term,))
        return self.add_node((term[0], *[self.add(k) for k in term[1:]]))

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a == b:
            return False
        if len(self.parents[a]) < len(self.parents[b]):
            a, b = b, a                  # keep the class with more users as root
        self.parent[b] = a
        self.classes[a] |= self.classes.pop(b)
        self.parents[a] += self.parents.pop(b)
        self.pending.append(a)           # congruence NOT restored yet
        return True

    def rebuild(self):
        """Restore invariants: memo holds canonical nodes, congruent nodes share a class."""
        while self.pending:
            todo = {self.find(c) for c in self.pending}; self.pending = []
            for c in todo:
                self.repair(c)

    def repair(self, cid):
        for node, owner in self.parents[cid]:
            self.memo.pop(node, None)    # stale key: children may have changed ids
        seen = {}
        for node, owner in self.parents[cid]:
            n = self.canon(node)
            if n in seen:                # congruence: same op, same canonical kids
                self.union(owner, seen[n])
            seen[n] = self.find(owner)
            self.memo[n] = self.find(owner)
        self.parents[self.find(cid)] = list(seen.items())
        for k in list(self.classes):     # re-canonicalize node sets (slow but simple)
            self.classes[k] = {self.canon(n) for n in self.classes[k]}

    def size(self):
        return len(self.classes), sum(len(v) for v in self.classes.values())

# ---------- e-matching (top-down backtracking) ----------
# Pattern: "?x" is a variable; otherwise same shape as a term.
def ematch(eg, pat, cid, subst):
    cid = eg.find(cid)
    if isinstance(pat, str) and pat.startswith("?"):
        if pat in subst:
            if eg.find(subst[pat]) == cid: yield subst
            return
        yield {**subst, pat: cid}; return
    op, kids = (pat, ()) if isinstance(pat, str) else (pat[0], pat[1:])
    for node in list(eg.classes[cid]):
        if node[0] != op or len(node) - 1 != len(kids):
            continue
        def go(i, s):
            if i == len(kids):
                yield s; return
            for s2 in ematch(eg, kids[i], node[1 + i], s):
                yield from go(i + 1, s2)
        yield from go(0, subst)

def instantiate(eg, pat, subst):
    if isinstance(pat, str):
        return subst[pat] if pat.startswith("?") else eg.add_node((pat,))
    return eg.add_node((pat[0], *[instantiate(eg, k, subst) for k in pat[1:]]))

# ---------- equality saturation loop ----------
def saturate(eg, rules, iters=10, node_limit=5000, log=True):
    for it in range(iters):
        matches = []                     # 1) read phase: search all rules
        for name, lhs, rhs in rules:
            for cid in list(eg.classes):
                for s in ematch(eg, lhs, cid, {}):
                    matches.append((name, cid, rhs, s))
        changed = False                  # 2) write phase: apply all matches
        for name, cid, rhs, s in matches:
            changed |= eg.union(cid, instantiate(eg, rhs, s))
        eg.rebuild()                     # 3) restore invariants once per iteration
        if log:
            print(f"iter {it}: {len(matches):4d} matches -> e-classes, e-nodes = {eg.size()}")
        if not changed:
            print("saturated: no rule adds new information"); return True
        if eg.size()[1] > node_limit:
            print("node limit hit: stopping (result depends on schedule!)"); return False
    print("iter limit hit"); return False

# ---------- extraction (greedy bottom-up, AstSize) ----------
def extract(eg, root):
    best = {}                            # class -> (cost, term)
    changed = True
    while changed:                       # fixpoint: costs only decrease
        changed = False
        for cid, nodes in eg.classes.items():
            for n in nodes:
                kids = [best.get(eg.find(c)) for c in n[1:]]
                if any(k is None for k in kids): continue
                cost = 1 + sum(k[0] for k in kids)
                if cid not in best or cost < best[cid][0]:
                    term = n[0] if len(n) == 1 else (n[0], *[k[1] for k in kids])
                    best[cid] = (cost, term); changed = True
    return best[eg.find(root)]

r = lambda name, l, rr: (name, parse(l), parse(rr))
RULES = [
    r("mul-comm",  "(* ?a ?b)", "(* ?b ?a)"),
    r("mul-two",   "(* ?a 2)", "(<< ?a 1)"),
    r("div-assoc", "(/ (* ?a ?b) ?c)", "(* ?a (/ ?b ?c))"),
    r("div-same",  "(/ ?a ?a)", "1"),     # UNSOUND when ?a = 0; fine for the demo
    r("mul-one",   "(* ?a 1)", "?a"),
]

if __name__ == "__main__":
    print("--- (a*2)/2 with the egg-paper rules (no commutativity) ---")
    eg = EGraph()
    root = eg.add(parse("(/ (* a 2) 2)"))
    print("start  :", eg.size(), "(e-classes, e-nodes)")
    saturate(eg, [x for x in RULES if x[0] != "mul-comm"])
    cost, term = extract(eg, root)
    print("best   :", show(term), "cost", cost)
    print("root class holds:", sorted(show(n) if len(n) == 1 else n[0] for n in eg.classes[eg.find(root)]))

    print("\n--- same term, same rules + mul-comm: never saturates ---")
    eg = EGraph()
    root = eg.add(parse("(/ (* a 2) 2)"))
    saturate(eg, RULES)                  # (* 2 a)/2 -> (* 2 (/ a 2)) -> a/4, a/8, ...
    print("best   :", show(extract(eg, root)[1]), "(still found, before the limit)")

    print("\n--- blowup: associativity + commutativity on a sum of n leaves ---")
    AC = [r("add-comm", "(+ ?a ?b)", "(+ ?b ?a)"),
          r("add-assoc", "(+ ?a (+ ?b ?c))", "(+ (+ ?a ?b) ?c)"),
          r("add-assoc2", "(+ (+ ?a ?b) ?c)", "(+ ?a (+ ?b ?c))")]
    for n in range(2, 7):
        eg2 = EGraph()
        t = "x0"
        for i in range(1, n): t = f"(+ {t} x{i})"
        eg2.add(parse(t))
        saturate(eg2, AC, iters=50, node_limit=10**6, log=False)
        c, nn = eg2.size()
        print(f"n={n}: e-classes={c:4d} (2^n-1={2**n-1:4d})  e-nodes={nn:5d}")
