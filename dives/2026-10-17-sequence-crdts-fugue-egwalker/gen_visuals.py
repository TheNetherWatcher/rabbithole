# Generates the hero emblem, card visuals and the scroll story for this dive.
#   python3 gen_visuals.py        (run from the dive folder)
import os

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "img")
os.makedirs(IMG, exist_ok=True)


def w(path, s):
    with open(os.path.join(HERE, path), "w") as f:
        f.write(s)


# ------------------------------------------------------------------ hero
def hero():
    o = ['<svg viewBox="0 0 1200 320" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">',
         '<defs><pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" class="f-line"/></pattern></defs>',
         '<g class="layer" data-depth="0.05"><rect width="1200" height="320" fill="url(#dots)"/></g>']
    # layer 1: a Fugue-style tree (left children go down-left, right children down-right)
    nodes = {"r": (330, 92), "a": (250, 150), "b": (410, 150), "c": (200, 208), "d": (290, 208), "e": (370, 208), "f": (450, 208),
             "g": (170, 266), "h": (230, 266), "i": (480, 266)}
    edges = [("r", "a"), ("r", "b"), ("a", "c"), ("a", "d"), ("b", "e"), ("b", "f"), ("c", "g"), ("c", "h"), ("f", "i")]
    g = ['<g class="layer" data-depth="0.14">']
    for p, q in edges:
        (x1, y1), (x2, y2) = nodes[p], nodes[q]
        g.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="s-line" stroke-width="2"/>')
    for k, (x, y) in nodes.items():
        cls = "f-acc" if k in "rcdi" else ("f-acc2" if k in "bfe" else "f-panel")
        g.append(f'<circle cx="{x}" cy="{y}" r="13" class="{cls} s-line" stroke-width="2"/>')
    g.append('</g>')
    o += g
    # layer 2: woven strip resolving into two whole runs
    l2 = ['<g class="layer" data-depth="0.22">']
    for k in range(9):
        cls = "f-acc" if k % 2 == 0 else "f-acc2"
        l2.append(f'<rect x="{610 + k * 26}" y="84" width="22" height="22" rx="4" class="{cls}" opacity=".9"/>')
    l2.append('<path d="M850 95 H900" class="s-mute draw" stroke-width="2" fill="none" marker-end="url(#ah)"/>')
    l2.append('<defs><marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 z" class="f-mute"/></marker></defs>')
    for k in range(4):
        l2.append(f'<rect x="{920 + k * 26}" y="84" width="22" height="22" rx="4" class="f-acc"/>')
    for k in range(5):
        l2.append(f'<rect x="{1034 + k * 26 - 0}" y="84" width="22" height="22" rx="4" class="f-acc2"/>')
    l2.append('</g>')
    o += l2
    # layer 3: event graph, chain -> fork -> merge, one pulsing node
    l3 = ['<g class="layer" data-depth="0.32">']
    pts = {"a": (640, 250), "b": (720, 250), "c": (800, 200), "d": (880, 200), "e": (800, 290), "f": (880, 290), "g": (960, 250), "h": (1040, 250)}
    es = [("a", "b"), ("b", "c"), ("c", "d"), ("b", "e"), ("e", "f"), ("d", "g"), ("f", "g"), ("g", "h")]
    for p, q in es:
        (x1, y1), (x2, y2) = pts[p], pts[q]
        l3.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="s-mute" stroke-width="2"/>')
    for k, (x, y) in pts.items():
        cls = "f-ok" if k in "ah" else "f-panel"
        extra = ' class="f-ok pulse"' if k == "g" else f' class="{cls} s-mute"'
        l3.append(f'<circle cx="{x}" cy="{y}" r="9"{extra} stroke-width="2"/>')
    l3.append('</g>')
    o += l3
    o.append('</svg>')
    w("img/hero.svg", "\n".join(o))


# ------------------------------------------------------------------ card visuals
def cell(x, y, cls, s=14):
    return f'<rect x="{x}" y="{y}" width="{s}" height="{s}" rx="2" class="{cls}"/>'


V = {}
V["plain"] = ('<rect x="12" y="14" width="40" height="52" rx="4" class="f-panel s-line" stroke-width="1.5"/><rect x="108" y="14" width="40" height="52" rx="4" class="f-panel s-line" stroke-width="1.5"/>'
              '<path d="M20 26h24M20 36h18M20 46h22" class="s-acc" stroke-width="3" stroke-linecap="round"/><path d="M116 26h22M116 36h24M116 46h16" class="s-acc2" stroke-width="3" stroke-linecap="round"/>'
              '<path d="M52 40 L66 62M108 40 L94 62" class="s-mute flow" stroke-width="2" fill="none"/><rect x="62" y="58" width="36" height="34" rx="4" class="f-panel s-ok" stroke-width="1.5"/><path d="M68 70h24M68 80h24" class="s-ok" stroke-width="3" stroke-linecap="round"/>')
V["ctx"] = "".join(f'<circle cx="22" cy="{18 + i * 14}" r="3.5" class="f-acc"/><rect x="34" y="{15 + i * 14}" width="{70 + (i * 17) % 40}" height="6" rx="3" class="f-line"/>' for i in range(6))
V["world"] = "".join(f'<rect x="{14 + (i % 2) * 70}" y="{12 + (i // 2) * 44}" width="62" height="36" rx="5" class="f-panel s-line" stroke-width="1.5"/><circle cx="{30 + (i % 2) * 70}" cy="{30 + (i // 2) * 44}" r="5" class="{["f-acc","f-acc2","f-ok","f-warn"][i]}"/><rect x="{42 + (i % 2) * 70}" y="{27 + (i // 2) * 44}" width="26" height="6" rx="3" class="f-line"/>' for i in range(4))
V["onel"] = ('<rect x="14" y="30" width="42" height="40" rx="6" class="f-panel s-acc" stroke-width="2"/><text x="35" y="56" text-anchor="middle" class="t-ink">o4</text>'
             '<path d="M60 50 H92" class="s-mute" stroke-width="2" fill="none"/><path d="M90 44 l8 6 l-8 6" class="s-mute" stroke-width="2" fill="none"/><rect x="104" y="30" width="42" height="40" rx="6" class="f-panel s-acc2" stroke-width="2"/><text x="125" y="56" text-anchor="middle" class="t-ink">!</text>'
             '<text x="80" y="90" text-anchor="middle" class="t-mute">insert after o4</text>')
V["problem"] = (cell(14, 24, "f-code s-line") + cell(32, 24, "f-code s-line") + cell(50, 24, "f-code s-line") + cell(68, 24, "f-code s-line") + '<text x="48" y="58" text-anchor="middle" class="t-mute">Helo</text>'
                '<rect x="86" y="24" width="14" height="14" rx="2" class="f-ok"/><text x="120" y="52" class="t-mute">idx 4</text><path d="M93 40 V70" class="s-bad" stroke-width="2"/>'
                '<text x="14" y="86" class="t-mute">Hell!o</text><path d="M62 82 l10 0" class="s-bad" stroke-width="2"/><text x="78" y="86" class="t-ink" style="fill:var(--bad)">≠ Hello!</text>')
V["model"] = "".join(f'<rect x="{12 + i * 18}" y="{30 - (i % 3) * 4}" width="14" height="{54 + (i % 3) * 4}" rx="2" class="{["f-acc","f-acc2","f-ok","f-warn"][i % 4]}"/>' for i in range(8)) + '<rect x="12" y="86" width="140" height="4" class="f-line"/><path d="M150 14 v14" class="s-mute" stroke-width="2"/>'
V["mech"] = ('<circle cx="80" cy="18" r="8" class="f-panel s-line" stroke-width="1.5"/><circle cx="48" cy="48" r="8" class="f-acc"/><circle cx="112" cy="48" r="8" class="f-acc2"/><circle cx="30" cy="80" r="8" class="f-panel s-line" stroke-width="1.5"/><circle cx="66" cy="80" r="8" class="f-acc"/>'
             '<path d="M75 24 L53 42M85 24 L107 42M43 55 L33 73M53 55 L63 73" class="s-line" stroke-width="2"/>')
V["math"] = ('<path d="M12 80 L40 30 L68 56 L96 20 L124 44 L148 70" class="s-acc draw" fill="none" stroke-width="3"/><text x="14" y="94" class="t-mute">k=1</text><text x="116" y="94" class="t-mute">k=n</text><text x="46" y="26" class="t-mute">(k+m) log</text>')
V["why"] = "".join(f'<rect x="{18 + i * 44}" y="{20 + (i == 1) * 20}" width="30" height="{60 - (i == 1) * 20}" rx="4" class="{["f-acc","f-bad","f-ok"][i]}" opacity="{1 if i != 1 else .55}"/>' for i in range(3)) + '<path d="M40 96 h82" class="s-line" stroke-width="2"/>'
V["knobs"] = "".join(f'<path d="M16 {24 + i * 24} H144" class="s-line" stroke-width="3"/><circle cx="{[48, 100, 70][i]}" cy="{24 + i * 24}" r="8" class="f-acc"/>' for i in range(3))
V["breaks"] = "".join(cell(10 + i * 15, 36, "f-acc" if i % 2 == 0 else "f-acc2", 12) for i in range(9)) + '<text x="80" y="72" text-anchor="middle" class="t-ink" style="fill:var(--bad)">ebgrgesad</text>'
V["wild"] = "".join(f'<rect x="{12 + (i % 3) * 48}" y="{14 + (i // 3) * 40}" width="40" height="30" rx="5" class="f-panel s-line" stroke-width="1.5"/><circle cx="{32 + (i % 3) * 48}" cy="{29 + (i // 3) * 40}" r="5" class="{["f-acc","f-acc2","f-ok","f-warn","f-bad","f-mute"][i]}"/>' for i in range(6))
V["frontier"] = '<path d="M12 60 H148" class="s-line" stroke-width="3"/>' + "".join(f'<circle cx="{x}" cy="60" r="7" class="{c}"/><text x="{x}" y="{40 if i % 2 == 0 else 86}" text-anchor="middle" class="t-mute">{y}</text>' for i, (x, y, c) in enumerate([(26, "2022", "f-mute"), (62, "2023", "f-acc"), (98, "2024", "f-acc2"), (134, "2025", "f-ok")]))
V["open"] = '<text x="80" y="76" text-anchor="middle" style="font:700 64px var(--serif);fill:var(--acc)">?</text>'
V["lineage"] = "".join(f'<circle cx="{18 + i * 31}" cy="50" r="8" class="{["f-mute","f-mute","f-acc","f-acc2","f-ok"][i]}"/>' + (f'<path d="M{28 + i * 31} 50 H{39 + i * 31}" class="s-mute" stroke-width="2"/>' if i < 4 else "") for i in range(5))
V["hands"] = '<rect x="10" y="12" width="140" height="76" rx="6" class="f-code s-line" stroke-width="1.5"/><text x="20" y="36" class="t-ink">$ python3 sim.py</text><text x="20" y="54" class="t-mute">RGA   xaybzc</text><text x="20" y="72" class="t-mute">Fugue abcxyz</text>'
V["quiz"] = '<circle cx="80" cy="50" r="30" class="f-none s-line" stroke-width="7"/><path d="M80 20 A30 30 0 1 1 52 62" class="f-none s-acc draw" stroke-width="7" stroke-linecap="round"/><path d="M68 50 l9 9 l16 -18" class="f-none s-ok" stroke-width="5" stroke-linecap="round"/>'
V["next"] = "".join(f'<path d="M20 {24 + i * 26} H116" class="s-line" stroke-width="3"/><path d="M110 {17 + i * 26} l10 7 l-10 7" class="s-acc" stroke-width="3" fill="none"/><circle cx="14" cy="{24 + i * 26}" r="4" class="f-acc"/>' for i in range(3))
V["sources"] = "".join(f'<rect x="20" y="{14 + i * 18}" width="{100 + (i * 23) % 30}" height="9" rx="3" class="{"f-acc" if i == 0 else "f-line"}"/>' for i in range(5))
for k, body in V.items():
    w(f"img/{k}.svg", f'<svg viewBox="0 0 160 100" xmlns="http://www.w3.org/2000/svg">{body}</svg>')


# ------------------------------------------------------------------ scroll story
S = []


def rng(a=None, b=None, hl=None):
    s = ""
    if a:
        s += f' data-in="{a}"'
    if b:
        s += f' data-out="{b}"'
    if hl:
        s += f' data-hl="{hl}"'
    return s


def T(x, y, t, cls, a=None, b=None, anchor=None):
    an = f' text-anchor="{anchor}"' if anchor else ""
    S.append(f'<text x="{x}" y="{y}" class="{cls}"{an}{rng(a, b)}>{t}</text>')


def R(x, y, wd, h, cls, a=None, b=None, rx=6, hl=None, extra=""):
    S.append(f'<rect x="{x}" y="{y}" width="{wd}" height="{h}" rx="{rx}" class="{cls}"{rng(a, b, hl)}{extra}/>')


def L(x1, y1, x2, y2, cls, a=None, b=None, sw=2, hl=None):
    S.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="{cls}" stroke-width="{sw}"{rng(a, b, hl)}/>')


def C(x, y, r, cls, a=None, b=None, hl=None):
    S.append(f'<circle cx="{x}" cy="{y}" r="{r}" class="{cls}" stroke-width="2"{rng(a, b, hl)}/>')


# captions (top)
T(20, 28, "Two people, one note, no server", "sf-cap", 1, 2)
T(20, 28, "Edits by position break when they cross", "sf-cap", 2, 3)
T(20, 28, "Fix: give every character a name", "sf-cap", 3, 4)
T(20, 28, "New problem: two words, one spot", "sf-cap", 4, 5)
T(20, 28, "A bad tie-break weaves the words", "sf-cap", 5, 6)
T(20, 28, "Fugue keeps each run whole", "sf-cap", 6, 7)
T(20, 28, "The price: nothing is ever forgotten", "sf-cap", 7, 8)
T(20, 28, "Eg-walker: keep a log, not a CRDT", "sf-cap", 8, 9)
T(20, 28, "Same trace, same result, far cheaper", "sf-cap", 9)

# ---- panel A (steps 1-3): "Helo"
for x, who in ((20, "User 1"), (250, "User 2")):
    R(x, 50, 210, 300, "f-panel s-line", 1, 4, hl=None, extra=' stroke-width="1.5"')
    T(x + 14, 76, who, "sf-id", 1, 4)
T(125, 130, "Helo", "sf-doc", 1, 2, "middle")
T(355, 130, "Helo", "sf-doc", 1, 2, "middle")
T(125, 130, "Hello", "sf-doc", 2, 3, "middle")
T(355, 130, "Helo!", "sf-doc", 2, 3, "middle")
T(125, 160, "Insert(3,'l')", "sf-op sf-a", 2, 3, "middle")
T(355, 160, "Insert(4,'!')", "sf-op sf-b", 2, 3, "middle")
T(125, 230, "Hell!o", "sf-doc sf-bad", 2, 3, "middle")
T(355, 230, "Hello!", "sf-doc", 2, 3, "middle")
T(240, 382, "same edits, different text", "sf-lab sf-bad", 2, 3, "middle")
T(240, 364, "after swapping edits as-is:", "sf-id", 2, 3, "middle")
# step 3: ids
for i, ch in enumerate("Helo"):
    for x0 in (60, 290):
        x = x0 + i * 30
        R(x, 100, 26, 34, "f-code s-line", 3, 4, 4, extra=' stroke-width="1.5"')
        T(x + 13, 123, ch, "sf-cell", 3, 4, "middle")
        T(x + 13, 150, f"{ch.lower()}{i + 1}", "sf-id", 3, 4, "middle")
T(125, 200, "insert '!' after o4", "sf-op sf-b", 3, 4, "middle")
T(355, 200, "insert 'l' after l3", "sf-op sf-a", 3, 4, "middle")
T(125, 262, "Hello!", "sf-doc sf-ok", 3, 4, "middle")
T(355, 262, "Hello!", "sf-doc sf-ok", 3, 4, "middle")
T(240, 382, "an ID means the same on every copy", "sf-lab", 3, 4, "middle")

# ---- panel B (steps 4-6): eggs / bread
T(240, 78, "milk¶", "sf-doc", 4, 7, "middle")
for i, ch in enumerate("eggs"):
    R(30 + i * 36, 130, 32, 36, "f-acc", 4, 5, 5)
    T(46 + i * 36, 155, ch, "sf-cell sf-inv", 4, 5, "middle")
for i, ch in enumerate("bread"):
    R(250 + i * 36, 130, 32, 36, "f-acc2", 4, 5, 5)
    T(266 + i * 36, 155, ch, "sf-cell sf-inv", 4, 5, "middle")
T(100, 195, "User A types", "sf-op", 4, 5, "middle")
T(340, 195, "User B types", "sf-op", 4, 5, "middle")
L(240, 90, 100, 124, "s-mute", 4, 5, 2)
L(240, 90, 340, 124, "s-mute", 4, 5, 2)
T(240, 260, "both insert right after the same character", "sf-lab", 4, 5, "middle")
weave = [("e", "f-acc"), ("b", "f-acc2"), ("g", "f-acc"), ("r", "f-acc2"), ("g", "f-acc"), ("e", "f-acc2"), ("s", "f-acc"), ("a", "f-acc2"), ("d", "f-acc2")]
for i, (ch, cls) in enumerate(weave):
    R(24 + i * 48, 130, 42, 44, cls, 5, 6, 5)
    T(45 + i * 48, 160, ch, "sf-cell sf-inv", 5, 6, "middle")
T(240, 230, "ebgrgesad", "sf-doc sf-bad", 5, 6, "middle")
T(240, 262, "every copy agrees, nobody can read it", "sf-lab", 5, 6, "middle")
for i, ch in enumerate("eggs"):
    R(24 + i * 44, 130, 40, 44, "f-acc", 6, 7, 5)
    T(44 + i * 44, 160, ch, "sf-cell sf-inv", 6, 7, "middle")
for i, ch in enumerate("bread"):
    R(220 + i * 44, 130, 40, 44, "f-acc2", 6, 7, 5)
    T(240 + i * 44, 160, ch, "sf-cell sf-inv", 6, 7, "middle")
S.append('<path d="M24 188 q86 18 172 0" class="s-acc" fill="none" stroke-width="2" ' + rng(6, 7) + '/>')
S.append('<path d="M220 188 q108 18 216 0" class="s-acc2" fill="none" stroke-width="2" ' + rng(6, 7) + '/>')
T(240, 250, "each run stays whole (either order)", "sf-lab", 6, 7, "middle")
T(240, 280, "a tree of characters: a run is a subtree", "sf-id", 6, 7, "middle")

# ---- step 7: size bars (Fugue paper Table II: 105 kB text, Yjs 160 kB, Fugue 168 kB)
for y, lab, wd, cls, val in ((110, "plain text", 105, "f-mute", "105 kB"), (180, "Yjs file", 160, "f-acc2", "160 kB"), (250, "Fugue file", 168, "f-acc", "168 kB")):
    T(20, y - 10, lab, "sf-lab", 7, 8)
    R(20, y, wd * 1.9, 36, cls, 7, 8, 5)
    T(26 + wd * 1.9, y + 24, val, "sf-big", 7, 8)
T(20, 330, "metadata ≈ 60% of the text", "sf-lab", 7, 8)
T(20, 352, "saved doc, 105 kB of typed text", "sf-id", 7, 8)

# ---- step 8: event graph with the concurrent stretch boxed
R(100, 160, 280, 190, "f-none s-acc", 8, 9, 10, extra=' stroke-dasharray="6 5" stroke-width="2"')
nodes = {"a": (240, 70), "b": (240, 120), "c": (170, 205), "d": (170, 255), "e": (310, 205), "f": (310, 255), "g": (310, 305), "h": (240, 375)}
edges = [("a", "b"), ("b", "c"), ("c", "d"), ("b", "e"), ("e", "f"), ("f", "g"), ("d", "h"), ("g", "h")]
for p, q in edges:
    (x1, y1), (x2, y2) = nodes[p], nodes[q]
    L(x1, y1, x2, y2, "s-mute", 8, 9, 2)
for k, (x, y) in nodes.items():
    C(x, y, 11, "f-ok s-ink" if k in "abh" else "f-panel s-ink", 8, 9)
T(266, 76, "straight line: no CRDT needed", "sf-id", 8, 9)
T(266, 126, "critical version", "sf-id", 8, 9)
T(110, 185, "only this part is replayed", "sf-id sf-a", 8, 9)
T(266, 380, "merge", "sf-id", 8, 9)

# ---- step 9: big numbers
R(0, 40, 480, 380, "f-bg", 9, None, 0, extra=' opacity=".97"')
T(240, 100, "merge a long offline branch", "sf-lab", 9, None, "middle")
T(240, 150, "61.1 min → 23.5 ms", "sf-num", 9, None, "middle")
T(240, 176, "textbook OT vs Eg-walker, same real trace", "sf-id", 9, None, "middle")
T(240, 240, "while merging, RAM", "sf-lab", 9, None, "middle")
T(240, 290, "271 MiB → 8 MiB", "sf-num", 9, None, "middle")
T(240, 316, "Automerge vs Eg-walker peak (432 KiB steady)", "sf-id", 9, None, "middle")
T(240, 376, "all numbers: Eg-walker paper, Figs 8 and 10", "sf-id", 9, None, "middle")

svg = "\n".join(S)
STEPS = [
    '<p class="dropcap">Two people hold the same note, <b>Helo</b>, and edit it offline. No server decides who goes first. When they reconnect, both copies must end up identical.</p>',
    "<p><b>The obvious way: positions.</b> User 1 inserts an <i>l</i> at index 3. User 2 adds <i>!</i> at index 4. Swap the edits as-is and User 1 gets <b>Hell!o</b> while User 2 gets Hello!. Same edits, different documents.</p>",
    "<p><b>The CRDT fix: names, not numbers.</b> Give every character a permanent ID and say &ldquo;insert after <i>o4</i>&rdquo;. That sentence means the same on every copy, so both land on Hello!.</p>",
    "<p><b>A new problem.</b> Now two people each type a whole word right after the same character. &ldquo;After <i>milk</i>&rdquo; no longer names a unique spot, so the algorithm needs a tie-break rule.</p>",
    "<p><b>A tie-break can wreck the text.</b> If ties are broken character by character, the two words weave into <b>ebgrgesad</b> (the example from the Fugue paper). Every copy agrees. Nobody can read it.</p>",
    "<p><b>Fugue's rule.</b> Hang characters in a tree so that a typed run becomes a subtree, and runs stay whole. In a simulation I ran for this dive, plain RGA wove two backward-typed words into <i>xaybzc</i>; Fugue kept them whole.</p>",
    "<p><b>The price: nothing is forgotten.</b> A deleted character must stay as a tombstone, because a concurrent edit may still point at it. In the Fugue paper's benchmark a 105 kB document saves to 168 kB (Yjs: 160 kB).</p>",
    "<p><b>Eg-walker's trick.</b> Keep only the log of edits (an <i>event graph</i>). Most history is a straight line, where no CRDT is needed. Build one temporarily for the stretch where people really overlapped, then throw it away.</p>",
    "<p><b>The payoff.</b> On a real trace of two weeks of offline editing, merging took 61.1 minutes with textbook OT and 23.5 ms with Eg-walker. Peak merge memory was 8 MiB against Automerge's 271 MiB.</p>",
]
style = """<style>
#story-fig .sf-cap{fill:var(--ink);font:700 17px var(--serif)}
#story-fig .sf-id{fill:var(--mute);font:600 12px var(--mono)}
#story-fig .sf-lab{fill:var(--ink);font:15px system-ui,sans-serif}
#story-fig .sf-big{fill:var(--ink);font:700 16px system-ui,sans-serif}
#story-fig .sf-doc{fill:var(--ink);font:700 26px var(--mono)}
#story-fig .sf-op{fill:var(--ink);font:600 14px var(--mono)}
#story-fig .sf-cell{fill:var(--ink);font:700 18px var(--mono)}
#story-fig .sf-inv{fill:var(--bg)}
#story-fig .sf-a{fill:var(--accent)}#story-fig .sf-b{fill:var(--accent2)}#story-fig .sf-bad{fill:var(--bad)}#story-fig .sf-ok{fill:var(--ok)}
#story-fig .sf-num{fill:var(--ink);font:700 28px var(--serif)}
</style>"""
html = (style + '\n<div class="scrolly">\n<div class="scrolly-fig"><svg id="story-fig" viewBox="0 0 480 430" xmlns="http://www.w3.org/2000/svg" role="img" '
        'aria-label="Two copies of a note edited offline: positions break, IDs fix it, tie-breaks can weave words, Fugue keeps runs whole, tombstones cost space, and Eg-walker replays only the concurrent stretch">\n'
        + svg + '\n</svg></div>\n<div class="scrolly-steps">\n' + "\n".join(f'<div class="step">{s}</div>' for s in STEPS) + "\n</div>\n</div>\n")
w("sections/story.html", html)
hero()
print("ok", len(html))
