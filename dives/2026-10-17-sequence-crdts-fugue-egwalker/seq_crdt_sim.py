"""Two replicas type concurrently at the same spot. Compare RGA and Fugue.

    python3 seq_crdt_sim.py

Each case: both replicas start from the shared text "XZ", edit offline,
then exchange operations. We print the merged text from each replica's point
of view (they must match) and whether the two runs stayed contiguous.
"""


# ---------------------------------------------------------------- RGA
class RGA:
    """Replicated Growable Array. Element = (id, value, prev_id); id = (lamport, replica)."""

    def __init__(self, rid):
        self.rid, self.clock = rid, 0
        self.seq = []  # [(id, value, prev_id)] in document order (no tombstones needed here)

    def _pos(self, eid):
        return -1 if eid is None else next(i for i, e in enumerate(self.seq) if e[0] == eid)

    def integrate(self, el):
        eid, _, prev = el
        i = self._pos(prev) + 1
        while i < len(self.seq) and self.seq[i][0] > eid:  # skip concurrent inserts with newer ids
            i += 1
        self.seq.insert(i, el)
        self.clock = max(self.clock, eid[0])

    def insert(self, index, value):
        prev = self.seq[index - 1][0] if index > 0 else None
        el = ((self.clock + 1, self.rid), value, prev)
        self.integrate(el)
        return el

    def text(self):
        return "".join(e[1] for e in self.seq)


# ---------------------------------------------------------------- Fugue
class Fugue:
    """Tree of characters. Node = id -> (parent_id, side, value). Root id is None."""

    def __init__(self, rid):
        self.rid, self.n = rid, 0
        self.nodes = {}

    def _kids(self, pid, side):
        return sorted(i for i, (p, s, _) in self.nodes.items() if p == pid and s == side)

    def _walk(self, pid=None):  # in-order: left children, node, right children
        for k in self._kids(pid, "L"):
            yield from self._walk(k)
        if pid is not None:
            yield pid
        for k in self._kids(pid, "R"):
            yield from self._walk(k)

    def insert(self, index, value):
        order = list(self._walk())
        visible = [i for i in order if self.nodes[i][2] is not None]
        left = visible[index - 1] if index > 0 else None
        if not self._kids(left, "R"):
            parent, side = left, "R"
        else:  # left origin already has a right child: become left child of the next node
            nxt = order[order.index(left) + 1] if left is not None else order[0]
            parent, side = nxt, "L"
        self.n += 1
        nid = (self.rid, self.n)
        self.nodes[nid] = (parent, side, value)
        return (nid, parent, side, value)

    def integrate(self, op):
        nid, parent, side, value = op
        self.nodes[nid] = (parent, side, value)

    def text(self):
        return "".join(self.nodes[i][2] for i in self._walk() if self.nodes[i][2] is not None)


# ---------------------------------------------------------------- scenarios
def run(cls, name, typing):
    """typing(replica, word) -> list of ops. Shared base 'XZ' made by replica O."""
    base = cls("O")
    ops = [base.insert(0, "X"), base.insert(1, "Z")]
    a, b = cls("A"), cls("B")
    for r in (a, b):
        for op in ops:
            r.integrate(op)
        r.clock = 2 if cls is RGA else 0
    ops_a = typing(a, "abc")
    ops_b = typing(b, "xyz")
    for op in ops_b:
        a.integrate(op)
    for op in ops_a:
        b.integrate(op)
    assert a.text() == b.text(), "replicas diverged"
    t = a.text()
    contiguous = "abc" in t and "xyz" in t
    print(f"  {name:6s} -> {t}   {'runs stay whole' if contiguous else 'INTERLEAVED'}")


def forward(r, word):  # type the word left to right
    return [r.insert(1 + k, ch) for k, ch in enumerate(word)]


def backward(r, word):  # type the word right to left, always at index 1
    return [r.insert(1, ch) for ch in reversed(word)]


if __name__ == "__main__":
    for title, fn in (("forward typing (a, b, c)", forward), ("backward typing (c, b, a)", backward)):
        print(title)
        for cls in (RGA, Fugue):
            run(cls, cls.__name__, fn)
