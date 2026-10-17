# Original diagrams for this dive (palette classes only).  python3 gen_figs.py
import os

HERE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(HERE, "img", "fig"), exist_ok=True)


def out(name, w, h, body):
    with open(os.path.join(HERE, "img", "fig", name), "w") as f:
        f.write(f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" role="img">{body}</svg>')


def node(x, y, label, cls, r=18, sub=None):
    s = f'<circle cx="{x}" cy="{y}" r="{r}" class="{cls} s-ink" stroke-width="2"/><text x="{x}" y="{y + 5}" text-anchor="middle" class="t-ink" style="font:700 16px var(--mono)">{label}</text>'
    if sub:
        s += f'<text x="{x}" y="{y + r + 15}" text-anchor="middle" class="t-mute" style="font:12px var(--mono)">{sub}</text>'
    return s


def edge(x1, y1, x2, y2, lab, dash=False):
    d = ' stroke-dasharray="5 4"' if dash else ""
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="s-mute" stroke-width="2"{d}/>'
            f'<text x="{mx + (8 if lab == "R" else -8)}" y="{my}" text-anchor="{"start" if lab == "R" else "end"}" class="t-mute" style="font:700 13px var(--mono)">{lab}</text>')


# ------------------------------------------------------------ Fugue tree after backward typing
b = []
b.append(node(360, 40, "X", "f-panel", sub="(root's right child)"))
b.append(edge(360, 58, 440, 118, "R"))
b.append(node(450, 130, "Z", "f-panel"))
# A's chain (left children): Z <- c <- b <- a ; B's chain: Z <- z <- y <- x
b.append(edge(436, 144, 330, 198, "L"))
b.append(node(320, 210, "c", "f-acc", sub="A, 1st"))
b.append(edge(306, 224, 250, 268, "L"))
b.append(node(240, 280, "b", "f-acc", sub="A, 2nd"))
b.append(edge(226, 294, 170, 338, "L"))
b.append(node(160, 350, "a", "f-acc", sub="A, 3rd"))
b.append(edge(464, 144, 570, 198, "L"))
b.append(node(580, 210, "z", "f-acc2", sub="B, 1st"))
b.append(edge(594, 224, 650, 268, "L"))
b.append(node(660, 280, "y", "f-acc2", sub="B, 2nd"))
b.append(edge(674, 294, 730, 338, "L"))
b.append(node(740, 350, "x", "f-acc2", sub="B, 3rd"))
b.append('<text x="40" y="40" class="t-mute" style="font:600 14px system-ui">Fugue tree (L = left child, R = right child)</text>')
b.append('<text x="40" y="76" class="t-mute" style="font:13px system-ui">Siblings c and z share a parent and side,</text>')
b.append('<text x="40" y="94" class="t-mute" style="font:13px system-ui">so they sort by ID: A’s subtree first.</text>')
b.append('<text x="450" y="410" text-anchor="middle" class="t-ink" style="font:700 15px system-ui">in-order walk: a b c x y z (left kids, node, right kids) ... X a b c x y z Z</text>')
out("own-fugue-tree.svg", 820, 430, "".join(b))

# ------------------------------------------------------------ RGA vs Fugue result rows
o = []


def row(y, title, seq, bad):
    s = f'<text x="20" y="{y - 14}" class="t-ink" style="font:700 15px system-ui">{title}</text>'
    x = 20
    for ch, who in seq:
        cls = {"A": "f-acc", "B": "f-acc2", "-": "f-line"}[who]
        s += f'<rect x="{x}" y="{y}" width="40" height="44" rx="6" class="{cls}"/><text x="{x + 20}" y="{y + 29}" text-anchor="middle" class="{"t-ink" if who == "-" else ""}" style="font:700 20px var(--mono);fill:{"var(--ink)" if who == "-" else "var(--bg)"}">{ch}</text>'
        x += 46
    s += f'<text x="{x + 12}" y="{y + 29}" style="font:700 15px system-ui;fill:{"var(--bad)" if bad else "var(--ok)"}">{"interleaved" if bad else "runs stay whole"}</text>'
    return s


o.append(row(50, "RGA, backward typing (sim output XxaybzcZ)", [("X", "-"), ("x", "B"), ("a", "A"), ("y", "B"), ("b", "A"), ("z", "B"), ("c", "A"), ("Z", "-")], True))
o.append(row(150, "Fugue, same operations (sim output XabcxyzZ)", [("X", "-"), ("a", "A"), ("b", "A"), ("c", "A"), ("x", "B"), ("y", "B"), ("z", "B"), ("Z", "-")], False))
o.append('<text x="20" y="232" class="t-mute" style="font:13px system-ui">A typed c, b, a at index 1; B typed z, y, x at index 1; both started from "XZ".</text>')
o.append('<text x="20" y="252" class="t-mute" style="font:13px system-ui">Both replicas print the same text, so the difference is the tie-break rule.</text>')
out("own-interleave.svg", 640, 268, "".join(o))

# ------------------------------------------------------------ event graph (adapted from Eg-walker Fig. 4)
g = []
ev = {
    "e1": (330, 36, "e1 Insert(0,'h')", "f-ok"),
    "e2": (330, 92, "e2 Insert(1,'i')", "f-ok"),
    "e3": (150, 168, "e3 Insert(0,'H')", "f-acc"),
    "e4": (150, 224, "e4 Delete(1)", "f-acc"),
    "e5": (510, 168, "e5 Delete(1)", "f-acc2"),
    "e6": (510, 224, "e6 Insert(1,'e')", "f-acc2"),
    "e7": (510, 280, "e7 Insert(2,'y')", "f-acc2"),
    "e8": (330, 350, "e8 Insert(3,'!')", "f-ok"),
}
g.append('<rect x="40" y="136" width="560" height="176" rx="12" class="f-none s-acc" stroke-width="2" stroke-dasharray="7 5"/>')
g.append('<text x="52" y="156" class="t-mute" style="font:600 13px system-ui">concurrent region: replayed with a temporary CRDT</text>')
for a, bq in (("e1", "e2"), ("e2", "e3"), ("e3", "e4"), ("e2", "e5"), ("e5", "e6"), ("e6", "e7"), ("e4", "e8"), ("e7", "e8")):
    x1, y1, _, _ = ev[a]
    x2, y2, _, _ = ev[bq]
    g.append(f'<line x1="{x1}" y1="{y1 + 14}" x2="{x2}" y2="{y2 - 14}" class="s-mute" stroke-width="2"/>')
for k, (x, y, lab, cls) in ev.items():
    g.append(f'<rect x="{x - 78}" y="{y - 15}" width="156" height="30" rx="8" class="{cls} s-ink" stroke-width="1.5"/><text x="{x}" y="{y + 5}" text-anchor="middle" style="font:600 13px var(--mono);fill:var(--bg)">{lab}</text>')
g.append('<text x="622" y="97" class="t-mute" style="font:12px system-ui">critical version</text>')
g.append('<text x="622" y="333" class="t-mute" style="font:12px system-ui">critical version</text>')
g.append('<text x="40" y="22" class="t-mute" style="font:600 13px system-ui">“hi” becomes “hey” while someone capitalises the H; result “Hey!”</text>')
out("own-event-graph.svg", 740, 380, "".join(g))
print("ok")
