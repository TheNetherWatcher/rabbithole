#!/usr/bin/env python3
"""Generates hero, card visuals, original figures and the story scrolly for this dive.

Run from the dive folder:  python3 gen_svgs.py
Writes img/*.svg, img/fig/own-*.svg and sections/story.html. Palette classes only, no hex colors.
"""
import math
import pathlib
import random

HERE = pathlib.Path(__file__).parent
IMG = HERE / "img"
FIG = IMG / "fig"
IMG.mkdir(exist_ok=True)
FIG.mkdir(exist_ok=True)


def w(path, s):
    path.write_text(s)


def arrow(x1, y1, x2, y2, cls="s-acc2", sw=2, head=9, extra=""):
    """Line with a drawn arrowhead (no <marker> ids)."""
    a = math.atan2(y2 - y1, x2 - x1)
    bx, by = x2 - head * math.cos(a), y2 - head * math.sin(a)
    px, py = -math.sin(a) * head * 0.5, math.cos(a) * head * 0.5
    return (f'<path d="M{x1:.1f} {y1:.1f} L{bx:.1f} {by:.1f}" class="f-none {cls}" stroke-width="{sw}" {extra}/>'
            f'<path d="M{x2:.1f} {y2:.1f} L{bx+px:.1f} {by+py:.1f} L{bx-px:.1f} {by-py:.1f} Z" class="{cls.replace("s-", "f-")}" {extra}/>')


NODE = {  # state -> (fill class, stroke class, extra)
    "w": ("f-panel", "s-mute", ' stroke-dasharray="5 4"'),
    "g": ("f-hl", "s-warn", ""),
    "k": ("f-ink", "s-ink", ""),
}


def node(cx, cy, r, st, extra=""):
    f, s, d = NODE[st]
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" class="{f} {s}" stroke-width="2.5"{d} {extra}/>'


# ------------------------------------------------------------------ card visuals (160 x 100)
V = {}
V["plain"] = ('<svg viewBox="0 0 160 100" xmlns="http://www.w3.org/2000/svg">'
              + node(36, 30, 14, "w") + node(80, 30, 14, "g") + node(124, 30, 14, "k")
              + arrow(52, 30, 64, 30, "s-mute", 1.6, 6) + arrow(96, 30, 108, 30, "s-mute", 1.6, 6)
              + '<rect x="30" y="62" width="100" height="22" rx="5" class="f-code s-line" stroke-width="1.5"/>'
              + '<rect x="36" y="68" width="14" height="10" rx="2" class="f-warn"/><rect x="56" y="68" width="14" height="10" rx="2" class="f-ok"/>'
              + '<rect x="76" y="68" width="14" height="10" rx="2" class="f-acc2"/><rect x="96" y="68" width="14" height="10" rx="2" class="f-line"/></svg>')
V["ctx"] = ('<svg viewBox="0 0 160 100" xmlns="http://www.w3.org/2000/svg">'
            + arrow(40, 50, 76, 26, "s-mute", 1.5, 6) + arrow(40, 50, 76, 74, "s-mute", 1.5, 6)
            + arrow(96, 26, 126, 26, "s-mute", 1.5, 6)
            + node(28, 50, 12, "k") + node(86, 26, 12, "g") + node(86, 74, 12, "w") + node(140, 26, 12, "w")
            + '<path d="M104 78 l14 -10 M118 78 l-14 -10" class="f-none s-bad" stroke-width="2.5"/></svg>')
V["world"] = ('<svg viewBox="0 0 160 100" xmlns="http://www.w3.org/2000/svg">'
              '<rect x="12" y="40" width="136" height="18" rx="4" class="f-line"/>'
              '<rect x="12" y="40" width="58" height="18" rx="4" class="f-acc2"/>'
              '<rect x="70" y="40" width="46" height="18" class="f-hl"/>'
              '<path d="M116 30 V68" class="f-none s-warn" stroke-width="2"/><path d="M148 30 V68" class="f-none s-bad" stroke-width="2"/>'
              '<text x="100" y="82" class="t-mute">trigger</text><text x="126" y="24" class="t-mute">goal</text>'
              '<text x="16" y="82" class="t-mute">live</text></svg>')
V["onel"] = ('<svg viewBox="0 0 160 100" xmlns="http://www.w3.org/2000/svg">'
             + arrow(18, 22, 66, 46, "s-acc2", 2, 8) + arrow(18, 78, 66, 54, "s-acc", 2, 8)
             + node(84, 50, 16, "g")
             + '<text x="10" y="14" class="t-mute">old</text><text x="10" y="94" class="t-mute">new</text>'
             + arrow(102, 50, 144, 50, "s-ok", 2, 8) + '</svg>')
V["problem"] = ('<svg viewBox="0 0 160 100" xmlns="http://www.w3.org/2000/svg">'
                '<rect x="14" y="18" width="40" height="34" rx="5" class="f-ink"/>'
                '<path d="M30 70 a14 14 0 1 1 6 10" class="f-none s-bad draw" stroke-width="2.5"/>'
                '<path d="M30 80 l-6 -2 l2 -7" class="f-none s-bad" stroke-width="2.5"/>'
                '<rect x="70" y="26" width="76" height="14" rx="3" class="f-line"/><rect x="70" y="26" width="76" height="14" rx="3" class="f-bad" opacity=".75"/>'
                '<text x="72" y="58" class="t-mute">STW rescan</text>'
                '<rect x="70" y="72" width="3" height="14" class="f-ok"/><text x="80" y="83" class="t-mute">&lt;50 us</text></svg>')
V["model"] = ('<svg viewBox="0 0 160 100" xmlns="http://www.w3.org/2000/svg">'
              '<rect x="14" y="30" width="60" height="8" class="f-line"/><rect x="14" y="60" width="60" height="8" class="f-line"/>'
              '<rect x="24" y="16" width="16" height="14" rx="2" class="f-hl s-warn" stroke-width="1.5"/>'
              '<rect x="44" y="46" width="16" height="14" rx="2" class="f-panel s-mute" stroke-width="1.5" stroke-dasharray="3 2"/>'
              '<circle cx="116" cy="28" r="9" class="f-panel s-ink" stroke-width="2"/><path d="M116 37 V62 M116 46 L98 54 M116 46 L134 54 M116 62 L104 84 M116 62 L128 84" class="f-none s-ink" stroke-width="2"/>'
              '<rect x="92" y="52" width="14" height="12" rx="2" class="f-hl s-warn" stroke-width="1.5"/></svg>')
V["mech"] = ('<svg viewBox="0 0 160 100" xmlns="http://www.w3.org/2000/svg">'
             + "".join(f'<rect x="{12 + i * 17}" y="34" width="14" height="22" rx="2" class="{"f-acc2" if i < 6 else "f-line"}"/>' for i in range(8))
             + '<path d="M12 70 H148" class="f-none s-mute" stroke-width="1.5"/><path d="M114 62 V78" class="f-none s-acc" stroke-width="2.5" class="blink"/>'
             + arrow(80, 24, 80, 14, "s-ok", 2, 6)
             + '<text x="14" y="90" class="t-mute">wbBuf</text><text x="104" y="90" class="t-mute">next</text></svg>')
V["math"] = ('<svg viewBox="0 0 160 100" xmlns="http://www.w3.org/2000/svg">'
             '<rect x="14" y="34" width="52" height="24" rx="3" class="f-acc2"/><rect x="66" y="34" width="12" height="24" class="f-warn"/>'
             '<rect x="78" y="34" width="64" height="24" rx="3" class="f-hl s-warn" stroke-width="1.5" stroke-dasharray="4 3"/>'
             '<text x="18" y="50" class="t-ink" style="fill:var(--panel)">live</text><text x="84" y="50" class="t-ink">x GOGC</text>'
             '<text x="14" y="78" class="t-mute">goal = live + (live + roots) x GOGC/100</text></svg>')
V["why"] = ('<svg viewBox="0 0 160 100" xmlns="http://www.w3.org/2000/svg">'
            '<rect x="24" y="22" width="48" height="40" rx="6" class="f-ink"/>'
            '<path d="M38 42 l8 8 l14 -16" class="f-none s-ok draw" stroke-width="3.5" style="stroke:var(--ok)"/>'
            '<path d="M92 30 a14 14 0 1 1 6 22" class="f-none s-mute" stroke-width="2.5" stroke-dasharray="3 4"/>'
            '<path d="M88 24 L128 64" class="f-none s-bad" stroke-width="3"/>'
            '<text x="26" y="82" class="t-mute">scanned once</text></svg>')
V["knobs"] = ('<svg viewBox="0 0 160 100" xmlns="http://www.w3.org/2000/svg">'
              '<path d="M16 26 H144 M16 50 H144 M16 74 H144" class="f-none s-line" stroke-width="3"/>'
              '<circle cx="96" cy="26" r="7" class="f-acc"/><circle cx="52" cy="50" r="7" class="f-acc2"/><circle cx="118" cy="74" r="7" class="f-warn"/></svg>')
V["breaks"] = ('<svg viewBox="0 0 160 100" xmlns="http://www.w3.org/2000/svg">'
               + node(34, 40, 14, "k") + arrow(48, 40, 80, 40, "s-mute", 1.5, 6) + node(96, 40, 14, "w")
               + '<path d="M84 28 l24 24 M108 28 l-24 24" class="f-none s-bad" stroke-width="3"/>'
               + '<text x="12" y="82" class="t-mute">lost object</text>'
               + '<path d="M120 76 h28" class="f-none s-warn" stroke-width="3"/></svg>')
V["wild"] = ('<svg viewBox="0 0 160 100" xmlns="http://www.w3.org/2000/svg">'
             '<rect x="12" y="16" width="56" height="28" rx="4" class="f-panel s-line" stroke-width="1.5"/>'
             '<rect x="92" y="16" width="56" height="28" rx="4" class="f-hl s-warn" stroke-width="1.5"/>'
             + arrow(70, 30, 90, 30, "s-mute", 1.5, 6)
             + "".join(f'<rect x="{92 + i * 7}" y="62" width="5" height="16" class="f-acc2"/>' for i in range(8))
             + '<text x="14" y="62" class="t-mute">paper</text><text x="14" y="76" class="t-mute">runtime</text></svg>')
V["frontier"] = ('<svg viewBox="0 0 160 100" xmlns="http://www.w3.org/2000/svg">'
                 '<path d="M12 62 H148" class="f-none s-line" stroke-width="2"/>'
                 '<circle cx="30" cy="62" r="6" class="f-mute"/><circle cx="76" cy="62" r="6" class="f-acc2"/><circle cx="124" cy="62" r="7" class="f-ok pulse"/>'
                 '<text x="14" y="46" class="t-mute">1.19</text><text x="62" y="46" class="t-mute">1.25</text><text x="106" y="46" class="t-mute">1.26</text>'
                 '<text x="86" y="86" class="t-mute">Green Tea</text></svg>')
V["open"] = ('<svg viewBox="0 0 160 100" xmlns="http://www.w3.org/2000/svg">'
             '<path d="M62 36 a18 18 0 1 1 28 14 q-10 8 -10 18" class="f-none s-acc draw" stroke-width="4"/><circle cx="80" cy="84" r="4" class="f-acc"/></svg>')
V["lineage"] = ('<svg viewBox="0 0 160 100" xmlns="http://www.w3.org/2000/svg">'
                + arrow(22, 60, 138, 60, "s-mute", 2, 8)
                + '<circle cx="28" cy="60" r="6" class="f-mute"/><circle cx="64" cy="60" r="6" class="f-mute"/><circle cx="104" cy="60" r="7" class="f-acc"/>'
                + '<text x="14" y="44" class="t-mute">1978</text><text x="50" y="44" class="t-mute">1990</text><text x="92" y="44" class="t-mute">2017</text></svg>')
V["hands"] = ('<svg viewBox="0 0 160 100" xmlns="http://www.w3.org/2000/svg">'
              '<rect x="14" y="14" width="132" height="72" rx="6" class="f-code s-line" stroke-width="1.5"/>'
              '<text x="24" y="38" class="t-ink">$ go run gcdemo.go</text><text x="24" y="56" class="t-mute">max STW pause=104us</text>'
              '<rect x="24" y="64" width="8" height="12" class="f-acc blink"/></svg>')
V["quiz"] = (HERE.parent / "2026-10-10-pagedattention-kv-cache/img/quiz.svg").read_text() \
    if (HERE.parent / "2026-10-10-pagedattention-kv-cache/img/quiz.svg").exists() else '<svg viewBox="0 0 160 100" xmlns="http://www.w3.org/2000/svg"><path d="M50 20 H110 M50 50 H110 M50 80 H110" class="f-none s-mute" stroke-width="2"/></svg>'
V["next"] = ('<svg viewBox="0 0 160 100" xmlns="http://www.w3.org/2000/svg">'
             + node(28, 50, 12, "k")
             + arrow(42, 46, 106, 20, "s-acc2", 2, 8) + arrow(42, 50, 106, 50, "s-acc2", 2, 8) + arrow(42, 54, 106, 80, "s-acc2", 2, 8)
             + '<circle cx="124" cy="18" r="9" class="f-panel s-acc2" stroke-width="2"/><circle cx="124" cy="50" r="9" class="f-panel s-acc2" stroke-width="2"/><circle cx="124" cy="82" r="9" class="f-panel s-acc2" stroke-width="2"/></svg>')
V["sources"] = ('<svg viewBox="0 0 160 100" xmlns="http://www.w3.org/2000/svg">'
                '<rect x="40" y="10" width="80" height="80" rx="6" class="f-panel s-line" stroke-width="1.5"/>'
                '<path d="M52 28 H108 M52 42 H108 M52 56 H96 M52 70 H100" class="f-none s-mute" stroke-width="3"/></svg>')
for k, s in V.items():
    w(IMG / f"{k}.svg", s)

# ------------------------------------------------------------------ hero (1200 x 320)
rnd = random.Random(8)
cols, rows = 14, 4
pts = {}
for c in range(cols):
    for r in range(rows):
        pts[(c, r)] = (330 + c * 60 + rnd.uniform(-14, 14), 78 + r * 56 + rnd.uniform(-14, 14))
FRONT = 7


def st(c):
    return "k" if c < FRONT - 1 else ("g" if c <= FRONT else "w")


edges = []
for (c, r), (x, y) in pts.items():
    for dc, dr in ((1, 0), (0, 1), (1, 1)):
        o = (c + dc, r + dr)
        if o in pts and rnd.random() < 0.55:
            edges.append(((c, r), o))
hero = ['<svg viewBox="0 0 1200 320" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">',
        '<defs><pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" class="f-line"/></pattern></defs>',
        '<g class="layer" data-depth="0.05"><rect width="1200" height="320" fill="url(#dots)"/></g>']
hero.append('<g class="layer" data-depth="0.12">')
for a, b in edges:
    (x1, y1), (x2, y2) = pts[a], pts[b]
    both_black = st(a[0]) == "k" and st(b[0]) == "k"
    hero.append(f'<path d="M{x1:.0f} {y1:.0f} L{x2:.0f} {y2:.0f}" class="f-none {"s-ink" if both_black else "s-line"}" stroke-width="{2 if both_black else 1.5}"/>')
hero.append('</g><g class="layer" data-depth="0.2">')
for (c, r), (x, y) in pts.items():
    s = st(c)
    extra = ' class="pulse f-hl s-warn"' if (c, r) == (FRONT, 1) else None
    if extra:
        hero.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="11"{extra} stroke-width="2.5"/>')
    else:
        hero.append(node(f"{x:.0f}", f"{y:.0f}", 10 if s != "g" else 11, s))
hero.append('</g><g class="layer" data-depth="0.3">')
# the stack column on the left: scanned blocks turn black top to bottom
for i in range(6):
    cls = "f-ink" if i < 4 else ("f-hl s-warn" if i == 4 else "f-panel s-mute")
    hero.append(f'<rect x="130" y="{70 + i * 34}" width="110" height="26" rx="5" class="{cls}" stroke-width="2"/>')
# write buffer strip, bottom right
for i in range(16):
    hero.append(f'<rect x="{800 + i * 22}" y="{272}" width="18" height="22" rx="3" class="{"f-acc2" if i < 10 else "f-line"}"{" " if i != 10 else " "}/>')
hero.append('<path d="M1000 262 V300" class="f-none s-acc blink" stroke-width="3"/>')
hero.append(arrow(560, 130, 800, 270, "s-acc2 flow", 2, 9, 'opacity=".7"'))
hero.append('</g></svg>')
w(IMG / "hero.svg", "\n".join(hero))

# ------------------------------------------------------------------ original figures
T = 'style="font-size:13px"'
TT = 'style="font-size:15px;font-weight:700"'
# races
fig = ['<svg viewBox="0 0 860 330" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Two races: a black stack hides an object loaded from the heap, and a grey stack stores its only pointer into a black heap object">']
fig.append(f'<text x="30" y="34" class="t-ink" {TT}>S1 · black stack hides C</text>')
fig.append(f'<text x="470" y="34" class="t-ink" {TT}>S2 · grey stack feeds black A</text>')
fig.append(node(100, 110, 28, "g") + node(310, 110, 28, "w")
           + '<text x="100" y="116" class="t-ink" style="font-size:16px;text-anchor:middle">B</text>'
           + '<text x="310" y="116" class="t-ink" style="font-size:16px;text-anchor:middle">C</text>')
fig.append(arrow(128, 110, 280, 110, "s-mute", 2, 9, 'opacity=".5"'))
fig.append('<path d="M180 94 l36 32 M216 94 l-36 32" class="f-none s-bad" stroke-width="3.5"/>')
fig.append(f'<text x="150" y="82" class="t-mute" {T}>② B.f = nil</text>')
fig.append('<rect x="170" y="220" width="170" height="64" rx="8" class="f-ink"/>')
fig.append(f'<text x="255" y="248" class="t-ink" style="fill:var(--bg);font-size:14px;text-anchor:middle">stack S (black)</text>'
           f'<text x="255" y="268" class="t-ink" style="fill:var(--bg);font-size:13px;text-anchor:middle">holds t = C</text>')
fig.append(arrow(300, 220, 312, 144, "s-acc", 2.5, 10))
fig.append(f'<text x="330" y="190" class="t-mute" {T}>① t := B.f</text>')
fig.append(f'<text x="30" y="318" class="t-mute" {T}>Fix: shade(old = C). Without it C stays white while S holds it.</text>')
fig.append(node(540, 110, 28, "k") + node(750, 110, 28, "w")
           + '<text x="540" y="116" class="t-ink" style="fill:var(--bg);font-size:16px;text-anchor:middle">A</text>'
           + '<text x="750" y="116" class="t-ink" style="font-size:16px;text-anchor:middle">C</text>')
fig.append(arrow(568, 110, 720, 110, "s-acc", 2.5, 10))
fig.append(f'<text x="560" y="82" class="t-mute" {T}>① A.f = C</text>')
fig.append('<rect x="620" y="220" width="190" height="64" rx="8" class="f-hl s-warn" stroke-width="2.5"/>')
fig.append(f'<text x="715" y="248" class="t-ink" style="font-size:14px;text-anchor:middle">stack S (grey)</text>'
           f'<text x="715" y="268" class="t-ink" style="font-size:13px;text-anchor:middle">only holder of C</text>')
fig.append(arrow(745, 220, 750, 144, "s-mute", 2, 10, 'opacity=".5"'))
fig.append('<path d="M770 176 l30 24 M800 176 l-30 24" class="f-none s-bad" stroke-width="3.5"/>')
fig.append(f'<text x="810" y="178" class="t-mute" {T}>② S drops C</text>')
fig.append(f'<text x="470" y="318" class="t-mute" {T}>Fix: shade(new = C). Without it C hides inside black A.</text>')
fig.append('</svg>')
w(FIG / "own-races.svg", "\n".join(fig))

# write-barrier buffer
fig = ['<svg viewBox="0 0 860 296" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Store, enabled check, buffer reserve, per-P buffer, flush">']
bx = [20, 220, 430, 640]
labels = [("*slot = ptr", "heap pointer store"), ("writeBarrier", "enabled? (only during mark)"), ("gcWriteBarrier2", "reserve 16 B, store old + new"), ("wbBufFlush", "when the buffer is full")]
for x, (a, b) in zip(bx, labels):
    fig.append(f'<rect x="{x}" y="40" width="190" height="64" rx="8" class="f-panel s-line" stroke-width="2"/>')
    fig.append(f'<text x="{x + 95}" y="68" class="t-ink" style="font-size:14px;text-anchor:middle">{a}</text>')
    fig.append(f'<text x="{x + 95}" y="90" class="t-mute" style="font-size:12px;text-anchor:middle">{b}</text>')
for i in range(3):
    fig.append(arrow(bx[i] + 192, 72, bx[i + 1] - 2, 72, "s-acc2", 2.5, 9))
fig.append(f'<text x="20" y="150" class="t-ink" {TT}>per-P write-barrier buffer: 512 pointers (4 KiB)</text>')
for i in range(32):
    cls = "f-acc2" if i < 21 else "f-line"
    fig.append(f'<rect x="{20 + i * 25}" y="164" width="21" height="34" rx="3" class="{cls}"/>')
fig.append('<path d="M545 156 V206" class="f-none s-acc" stroke-width="3.5"/>')
fig.append(f'<text x="533" y="224" class="t-mute" style="font-size:12px;text-anchor:middle">next</text>')
fig.append('<path d="M820 156 V206" class="f-none s-bad" stroke-width="3.5"/>')
fig.append(f'<text x="800" y="224" class="t-mute" style="font-size:12px;text-anchor:middle">end</text>')
fig.append(f'<text x="20" y="258" class="t-mute" {T}>Fast path: bump next by 16 B and store both pointers.</text>')
fig.append(f'<text x="20" y="278" class="t-mute" {T}>Slow path: flush every entry, mark the object, queue it grey. Marking happens in batches.</text>')
fig.append('</svg>')
w(FIG / "own-wbbuf.svg", "\n".join(fig))

# GC cycle sawtooth with trigger and goal (worked example: live 100 MB, goal 203 MB)
fig = ['<svg viewBox="0 0 860 330" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Heap size over time with live heap, trigger band, heap goal, and the barrier-on window">']
X0, X1, YB, YT = 70, 830, 280, 40


def hy(mb):
    return YB - (mb - 90) / (215 - 90) * (YB - YT)


for mb, lab, cls in ((100, "heapMarked 100 MB", "s-mute"), (203, "goal 203 MB", "s-bad")):
    fig.append(f'<path d="M{X0} {hy(mb):.0f} H{X1}" class="f-none {cls}" stroke-width="1.5" stroke-dasharray="6 5"/>')
    fig.append(f'<text x="{X1 - 4}" y="{hy(mb) - 6:.0f}" class="t-mute" style="font-size:12px;text-anchor:end">{lab}</text>')
fig.append(f'<rect x="{X0}" y="{hy(198):.0f}" width="{X1 - X0}" height="{hy(172) - hy(198):.0f}" class="f-hl" opacity=".55"/>')
fig.append(f'<text x="{X0 + 8}" y="{hy(185) + 4:.0f}" class="t-ink" style="font-size:12px">trigger lands in 172–198 MB</text>')
# two cycles
cyc = [(70, 140, 185, 330, 203), (330, 400, 185, 590, 203)]
pts = []
x = X0
path = f"M{x} {hy(100):.0f}"
for (sx, tx, trig, ex, peak) in [(X0, 270, 185, 300, 203), (300, 500, 185, 530, 203), (530, 730, 185, 760, 203)]:
    path += f" L{tx} {hy(trig):.0f} L{ex} {hy(peak):.0f} L{ex} {hy(100):.0f}"
fig.append(f'<path d="{path}" class="f-none s-acc2" stroke-width="3"/>')
for (tx, ex) in ((270, 300), (500, 530), (730, 760)):
    fig.append(f'<rect x="{tx}" y="{YT - 6}" width="{ex - tx}" height="{YB - YT + 12}" class="f-warn" opacity=".28"/>')
fig.append(f'<text x="300" y="{YT - 12}" class="t-ink" style="font-size:12px;text-anchor:middle">barrier on · mark assists if behind</text>')
fig.append(f'<text x="{X0}" y="{YB + 30}" class="t-mute" style="font-size:12px">time →  (heap grows by allocation, drops when sweep frees the dead)</text>')
fig.append('</svg>')
w(FIG / "own-cycle.svg", "\n".join(fig))

# tri-color invariant graph
fig = ['<svg viewBox="0 0 780 280" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Black, grey and white objects; the weak invariant allows black to white only when a grey object protects it">']
P = {"K1": (80, 70), "K2": (80, 200), "G": (280, 70), "W1": (480, 120), "W2": (480, 230)}
fig.append(arrow(108, 70, 252, 70, "s-ink", 2.5, 10))
fig.append(arrow(308, 76, 452, 112, "s-mute", 2.5, 10))
fig.append(arrow(106, 190, 454, 130, "s-ok", 2.5, 10, 'stroke-dasharray="7 5"'))
fig.append(arrow(106, 210, 452, 228, "s-bad", 2.5, 10, 'stroke-dasharray="7 5"'))
fig.append('<path d="M240 232 l26 26 M266 232 l-26 26" class="f-none s-bad" stroke-width="3.5"/>')
fig.append(node(*P["K1"], 26, "k") + node(*P["K2"], 26, "k") + node(*P["G"], 26, "g") + node(*P["W1"], 26, "w") + node(*P["W2"], 26, "w"))
for n, (x, y) in P.items():
    fill = "var(--bg)" if n.startswith("K") else "var(--ink)"
    fig.append(f'<text x="{x}" y="{y + 5}" class="t-ink" style="fill:{fill};font-size:14px;text-anchor:middle">{n}</text>')
fig.append('<text x="500" y="46" class="t-mute" style="font-size:13px">grey G still has a white path to W1</text>')
fig.append('<text x="500" y="64" class="t-mute" style="font-size:13px">so K2 → W1 is allowed (weak invariant)</text>')
fig.append('<text x="520" y="214" class="t-mute" style="font-size:13px">K2 → W2: no grey path to W2,</text>')
fig.append('<text x="520" y="232" class="t-mute" style="font-size:13px">W2 would be freed while reachable</text>')
fig.append('</svg>')
w(FIG / "own-tricolor.svg", "\n".join(fig))

# ------------------------------------------------------------------ story scrolly
out = []


def rng(a=None, b=None, hl=None):
    s = ""
    if a:
        s += f' data-in="{a}"'
    if b:
        s += f' data-out="{b}"'
    if hl:
        s += f' data-hl="{hl}"'
    return s


def snode(cx, cy, r, states, label, lab_cls):
    """states: [(state, first_step, last_step)] ; label colour flips on black."""
    for s, a, b in states:
        f, sc, d = NODE[s]
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" class="{f} {sc}" stroke-width="2.5"{d}{rng(a, b + 1)}/>')
        out.append(f'<text x="{cx}" y="{cy + 6}" class="{"sf-nk" if s == "k" else "sf-nl"}" text-anchor="middle"{rng(a, b + 1)}>{label}</text>')


def stk(states):
    for s, a, b in states:
        f, sc, d = NODE[s]
        out.append(f'<rect x="290" y="206" width="170" height="64" rx="9" class="{f} {sc}" stroke-width="2.5"{d}{rng(a, b + 1)}/>')
        out.append(f'<text x="375" y="234" class="{"sf-nk" if s == "k" else "sf-nl"}" text-anchor="middle"{rng(a, b + 1)}>goroutine stack S</text>')
        out.append(f'<text x="375" y="256" class="{"sf-nk2" if s == "k" else "sf-nm"}" text-anchor="middle"{rng(a, b + 1)}>{"scanned" if s == "k" else "unscanned"}</text>')


def cap(t, a, b):
    out.append(f'<text x="20" y="28" class="sf-cap"{rng(a, b + 1)}>{t}</text>')


def note(x, y, t, a, b, cls="sf-lab", anchor="start"):
    out.append(f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}"{rng(a, b + 1)}>{t}</text>')


out.append('<svg id="story-fig" viewBox="0 0 480 430" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Objects B and C and goroutine stacks colored white, grey and black as write barriers keep the collector from losing an object">')
cap("Mark phase: find everything reachable", 1, 1)
cap("Go 1.5: shade the new pointer on heap stores", 2, 2)
cap("Go 1.7: a scanned stack goes stale", 3, 3)
cap("Hybrid: also shade the overwritten pointer", 4, 4)
cap("…and the new pointer, while a stack is grey", 5, 5)
cap("A scanned stack stays black", 6, 6)
cap("What ships: a buffer, not a function call", 7, 7)
# heap graph
note(26, 100, "global", 1, 6, "sf-nm")
out.append(f'<path d="M64 112 H116" class="f-none s-mute" stroke-width="2.5"{rng(1, 7)}/>')
snode(150, 112, 30, [("w", 1, 1), ("g", 2, 3), ("k", 4, 6)], "B", "")
out.append(f'<path d="M182 112 H296" class="f-none s-acc2" stroke-width="2.5"{rng(1, 4)}/>')
out.append(f'<path d="M182 112 H296" class="f-none s-bad" stroke-width="2.5" stroke-dasharray="5 5"{rng(4, 5)}/>')
snode(330, 112, 30, [("w", 1, 3), ("g", 4, 5), ("k", 6, 6)], "C", "")
stk([("g", 1, 2), ("k", 3, 4), ("g", 5, 5), ("k", 6, 6)])
# S holds C (steps 4-6)
out.append(arrow(340, 206, 336, 146, "s-acc", 3, 10, rng(4, 7)))
note(352, 182, "t = C", 4, 6, "sf-nm")
# step 2 labels
note(20, 176, "heap store → shade(new)", 2, 2, "sf-lab")
note(20, 202, "stack write → no barrier", 2, 2, "sf-bad")
# step 3
out.append(f'<rect x="20" y="296" width="440" height="52" rx="8" class="f-panel s-bad" stroke-width="2.5"{rng(3, 4)}/>')
note(240, 318, "STOP THE WORLD: re-scan every stack", 3, 3, "sf-bad", "middle")
note(240, 338, "that ran since its scan · 10s–100s ms", 3, 3, "sf-lab", "middle")
note(20, 176, "↻ the goroutine runs again →", 3, 3, "sf-bad")
note(20, 202, "S may hold a white pointer: grey again", 3, 3, "sf-bad")
# step 4
note(20, 176, "B.f = nil → shade(old = C)", 4, 4, "sf-lab")
note(20, 202, "C grey: the stack can't hide it", 4, 4, "sf-nm")
# step 5: second race
out.append(f'<circle cx="150" cy="226" r="26" class="f-ink s-ink" stroke-width="2.5"{rng(5, 6)}/>')
out.append(f'<text x="150" y="232" class="sf-nk" text-anchor="middle"{rng(5, 6)}>A</text>')
out.append(arrow(176, 218, 302, 140, "s-acc", 3, 10, rng(5, 6)))
note(20, 176, "A.f = C → shade(new)", 5, 5, "sf-lab")
note(20, 290, "S still unscanned = grey,", 5, 5, "sf-nm")
note(20, 310, "so the insertion shade is required", 5, 5, "sf-nm")
# step 6
note(20, 176, "S is black, C already shaded:", 6, 6, "sf-lab")
note(20, 202, "no rescan, no pause", 6, 6, "sf-ok")
# step 7: buffer overlay
out.append(f'<rect x="0" y="0" width="480" height="430" class="f-bg" opacity=".94"{rng(7, 8)}/>')
note(20, 28, "What ships: a buffer, not a function call", 7, 7, "sf-cap")
note(20, 76, "per-P write-barrier buffer", 7, 7, "sf-lab")
for i in range(16):
    out.append(f'<rect x="{20 + i * 27}" y="92" width="23" height="36" rx="3" class="{"f-acc2" if i < 11 else "f-line"}"{rng(7, 8)}/>')
out.append(f'<path d="M{20 + 11 * 27 + 11} 84 V136" class="f-none s-acc" stroke-width="3"{rng(7, 8)}/>')
note(20, 168, "512 pointers · 4 KiB", 7, 7, "sf-big")
note(20, 200, "1. barrier off outside mark: just a flag test", 7, 7, "sf-lab")
note(20, 226, "2. barrier on: bump next, store old + new", 7, 7, "sf-lab")
note(20, 252, "3. buffer full: flush, mark, queue grey", 7, 7, "sf-lab")
note(20, 296, "Both pointers recorded every time,", 7, 7, "sf-nm")
note(20, 316, "not only while the stack is grey.", 7, 7, "sf-nm")
# step 8 headline overlay
out.append(f'<rect x="0" y="0" width="480" height="430" class="f-bg" opacity=".97"{rng(8)}/>')
note(240, 70, "The whole trade", 8, 8, "sf-cap", "middle")
for i, (big, lab) in enumerate((("< 50 µs", "worst-case STW target in the design doc"), ("512", "pointers buffered per P"), ("25%", "CPU the pacer gives background marking"))):
    y = 150 + i * 92
    out.append(f'<text x="240" y="{y}" class="sf-num" text-anchor="middle"{rng(8)}>{big}</text>')
    out.append(f'<text x="240" y="{y + 26}" class="sf-lab" text-anchor="middle"{rng(8)}>{lab}</text>')
out.append("</svg>")

STEPS = [
    '<p class="dropcap">A garbage collector has to find everything a program can still reach, and Go does it <em>while the program runs</em>. It tags objects <b>white</b> (not seen), <b>grey</b> (seen, contents not yet read) and <b>black</b> (fully read). Whatever is still white at the end is freed. Goroutine stacks count as roots.</p>',
    '<p><b>The Go 1.5 way.</b> Every time the program stores a pointer into the heap, a small <em>write barrier</em> shades the new pointer so a black object can never hold a white one. But stack writes get no barrier, because they are the most common operation in any program.</p>',
    '<p><b>The catch (Go 1.7).</b> A scanned stack turns black, but as soon as its goroutine runs it can pick up a white pointer, so it is grey again. The collector had to <em>stop the world and re-scan every stack that ran</em>. The design doc says that took 10s to 100s of milliseconds with many goroutines.</p>',
    '<p><b>The new idea (Go 1.8).</b> Also shade the pointer being <em>overwritten</em>. Now if a scanned stack loads C and the heap link to C is cut, the cut itself shades C. The stack can no longer hide anything the collector hasn\'t seen.</p>',
    '<p><b>The other half.</b> If a stack is <em>not yet scanned</em>, it may hold the only pointer to C, and it can store C into an already-black object. So while the current stack is grey, the new pointer gets shaded too. (Simulated: either shade alone loses C in one of the two races.)</p>',
    '<p><b>The payoff.</b> After a stack is scanned, everything on it was shaded and the deletion shade stops it hiding more. It stays black for the rest of the cycle. No re-scan list, no stop-the-world re-scan.</p>',
    '<p><b>What actually ships.</b> The runtime does not call a function per store. The compiler tests a flag, and when marking is on it writes the old and new pointer into a 512-entry per-P buffer, flushed in batches. It records <em>both</em> unconditionally, which the design doc says costs about twice the conditional form.</p>',
    '<p><b>The trade.</b> A tiny worst-case pause, paid for by a barrier that runs on every pointer store during the mark phase, and a pacer that keeps marking near 25% of CPU and bills allocating goroutines when it falls behind.</p>',
]
html = ['''<style>
#story-fig .sf-cap{fill:var(--ink);font:700 17px var(--serif)}
#story-fig .sf-lab{fill:var(--ink);font:15px system-ui,sans-serif}
#story-fig .sf-nm{fill:var(--mute);font:14px system-ui,sans-serif}
#story-fig .sf-bad{fill:var(--bad);font:700 15px system-ui,sans-serif}
#story-fig .sf-ok{fill:var(--ok);font:700 15px system-ui,sans-serif}
#story-fig .sf-big{fill:var(--ink);font:700 22px var(--serif)}
#story-fig .sf-nl{fill:var(--ink);font:700 16px var(--mono)}
#story-fig .sf-nk{fill:var(--bg);font:700 16px var(--mono)}
#story-fig .sf-nk2{fill:var(--bg);font:14px system-ui,sans-serif;opacity:.85}
#story-fig .sf-num{fill:var(--ink);font:700 34px var(--serif)}
</style>
<div class="scrolly">
<div class="scrolly-fig">''']
html += out
html.append('</div>\n<div class="scrolly-steps">')
for s in STEPS:
    html.append(f'<div class="step">{s}</div>')
html.append("</div>\n</div>")
w(HERE / "sections" / "story.html", "\n".join(html))
print("ok:", len(V), "card visuals,", "hero,", "4 figures, story with", len(STEPS), "steps")
