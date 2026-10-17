#!/usr/bin/env python3
"""Replay the three classic concurrent-marking races under five write barriers.

The mutator and the collector interleave in a fixed, hand-scheduled order.
An object is "lost" if it is still reachable at the end but was never marked.
Run: python3 barrier_sim.py          (prints a table, then a trace of S1 + hybrid)
"""

WHITE, GREY, BLACK = "white", "grey", "black"


class Heap:
    def __init__(self, barrier, edges, roots_global, stack_refs):
        self.barrier = barrier
        self.color = {}
        self.edges = {}
        for src, dst in edges:
            self.edges.setdefault(src, []).append(dst)
            for o in (src, dst):
                self.color.setdefault(o, WHITE)
        for o in list(self.color):
            self.edges.setdefault(o, [])
        self.globals = list(roots_global)
        self.stack = list(stack_refs)           # goroutine stack: no write barrier
        for o in self.stack:
            self.color.setdefault(o, WHITE)
            self.edges.setdefault(o, [])
        self.stack_color = GREY                 # unscanned stack == grey
        self.grey = []
        self.log = []

    # ---- collector side
    def shade(self, o, why=""):
        if o is not None and self.color[o] == WHITE:
            self.color[o] = GREY
            self.grey.append(o)
            self.log.append(f"    shade({o})  {why}")

    def scan_globals(self):
        for g in self.globals:
            self.shade(g, "global root")
        self.log.append("  GC: scanned globals")

    def scan_stack(self):
        for o in self.stack:
            self.shade(o, "from stack scan")
        self.stack_color = BLACK
        self.log.append(f"  GC: scanned stack {self.stack} -> stack is now black")

    def scan_object(self, o):
        assert self.color[o] == GREY, f"{o} not grey"
        for c in self.edges[o]:
            self.shade(c, f"child of {o}")
        self.color[o] = BLACK
        self.grey.remove(o)
        self.log.append(f"  GC: scanned {o} -> black")

    def drain(self):
        while self.grey:
            self.scan_object(self.grey[0])

    # ---- mutator side
    def stack_load(self, holder, field_idx):
        o = self.edges[holder][field_idx]
        self.stack.append(o)
        self.log.append(f"  MUT: stack <- {holder}.f{field_idx} (= {o}); stack writes have no barrier")

    def stack_drop(self, o):
        self.stack.remove(o)
        self.log.append(f"  MUT: stack drops {o}")

    def heap_store(self, holder, idx, new):
        old = self.edges[holder][idx] if idx < len(self.edges[holder]) else None
        b = self.barrier
        stack_grey = self.stack_color == GREY
        if b == "yuasa":
            self.shade(old, "deletion")
        elif b == "dijkstra":
            self.shade(new, "insertion")
        elif b == "hybrid":
            self.shade(old, "deletion")
            if stack_grey:
                self.shade(new, "insertion (stack is grey)")
        elif b == "hybrid-always":  # what the runtime's buffer effectively does
            self.shade(old, "deletion")
            self.shade(new, "insertion")
        if idx < len(self.edges[holder]):
            if new is None:
                self.edges[holder].pop(idx)
            else:
                self.edges[holder][idx] = new
        else:
            self.edges[holder].append(new)
        self.log.append(f"  MUT: {holder}.f{idx} = {new}   (old = {old}, barrier = {b})")

    # ---- result
    def reachable(self):
        seen, todo = set(), list(self.globals) + list(self.stack)
        while todo:
            o = todo.pop()
            if o in seen:
                continue
            seen.add(o)
            todo.extend(self.edges[o])
        return seen

    def lost(self):
        return sorted(o for o in self.reachable() if self.color[o] == WHITE)


def s1(barrier):
    """Hide behind a scanned (black) stack: load C onto the stack, then unlink it from the heap."""
    h = Heap(barrier, [("B", "C")], ["B"], [])
    h.scan_globals()           # B grey
    h.scan_stack()             # empty stack, now black
    h.stack_load("B", 0)       # t = B.f0 (C)
    h.heap_store("B", 0, None)  # B.f0 = nil
    h.drain()
    return h


def s2(barrier):
    """Hide in a black heap object: stack holds C alone and is still grey; store C into black A."""
    h = Heap(barrier, [("A", "A0")], ["A"], ["C"])
    h.scan_globals()           # A grey
    h.drain()                  # A black, A0 black
    h.heap_store("A", 0, "C")  # A.f0 = C
    h.stack_drop("C")
    h.scan_stack()             # stack now empty
    h.drain()
    return h


def s3(barrier):
    """Stack already scanned and holds D (shaded at scan); store D into black heap object A."""
    h = Heap(barrier, [("A", "A0")], ["A"], ["D"])
    h.scan_globals()
    h.scan_stack()             # shades D
    h.drain()                  # A, A0, D black
    h.heap_store("A", 0, "D")
    h.stack_drop("D")
    h.drain()
    return h


SCENARIOS = [("S1 load-then-unlink (black stack)", s1),
             ("S2 stack-to-black-heap (grey stack)", s2),
             ("S3 black stack shares shaded D", s3)]
BARRIERS = ["none", "yuasa", "dijkstra", "hybrid", "hybrid-always"]

if __name__ == "__main__":
    print(f"{'scenario':38}" + "".join(f"{b:>15}" for b in BARRIERS))
    for name, fn in SCENARIOS:
        row = []
        for b in BARRIERS:
            lost = fn(b).lost()
            row.append("LOST " + ",".join(lost) if lost else "ok")
        print(f"{name:38}" + "".join(f"{c:>15}" for c in row))
    print("\n--- trace: S1 under the hybrid barrier ---")
    print("\n".join(s1("hybrid").log))
    print("\n--- trace: S1 with no barrier ---")
    h = s1("none")
    print("\n".join(h.log))
    print("  END: lost =", h.lost())
