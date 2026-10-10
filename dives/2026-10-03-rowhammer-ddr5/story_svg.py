# Generates the story scrolly SVG for sections/story.html: python3 story_svg.py > story.svg, then paste it into .scrolly-fig.
import sys
out = []

def rng(a=None, b=None, hl=None):
    s = ''
    if a: s += f' data-in="{a}"'
    if b: s += f' data-out="{b}"'
    if hl: s += f' data-hl="{hl}"'
    return s

def rect(x, y, w, h, cls, a=None, b=None, hl=None, rx=6, sw=None, dash=None):
    extra = (f' stroke-width="{sw}"' if sw else '') + (f' stroke-dasharray="{dash}"' if dash else '')
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" class="{cls}"{extra}{rng(a, b, hl)}/>')

def text(x, y, s, cls, a=None, b=None, anchor=None):
    an = f' text-anchor="{anchor}"' if anchor else ''
    out.append(f'<text x="{x}" y="{y}" class="{cls}"{an}{rng(a, b)}>{s}</text>')

def line(x1, y1, x2, y2, cls, a=None, b=None, dash=None, sw=2):
    d = f' stroke-dasharray="{dash}"' if dash else ''
    out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="{cls}" stroke-width="{sw}"{d}{rng(a, b)}/>')

out.append('<svg id="story-fig" viewBox="0 0 480 420" xmlns="http://www.w3.org/2000/svg" role="img" '
           'aria-label="One DRAM bank: hammering two rows drains a victim row to the sense point and flips it. '
           'Then TRR tracks only a few rows, PRAC counts every row, and the headline numbers.">')
out.append('<defs></defs>')

# ---- steps 1-5: one bank, victim V drains ----
ROW_Y = [50, 100, 150, 200, 250]
LABELS = ['V−2', 'A1 (V−1)', 'V (victim)', 'A2 (V+1)', 'V+2']
# V charge fills: (width, in, out, class)
V_FILLS = [(170, 1, 2, 'f-ok'), (150, 2, 3, 'f-ok'), (115, 3, 4, 'f-ok'), (85, 4, 5, 'f-ok'), (30, 5, 6, 'f-bad')]
for i, (y, lab) in enumerate(zip(ROW_Y, LABELS)):
    hl = '2 3 4 5' if i in (1, 3) else None
    rect(20, y, 300, 40, 'f-panel s-line', None, 6, hl, rx=7, sw=1.5)
    text(32, y + 25, lab, 'sf-lab', None, 6)
    rect(130, y + 13, 170, 14, 'f-code', None, 6, rx=3)
    if i != 2:
        rect(130, y + 13, 170, 14, 'f-ok', None, 6, rx=3)
for (w, a, b, c) in V_FILLS:
    rect(130, ROW_Y[2] + 13, w, 14, c, a, b, rx=3)
# decision (sense) point at half charge
line(215, 44, 215, 294, 's-mute', None, 6, dash='4 4')
text(215, 312, 'sense point', 'sf-lab', 1, 6, 'middle')
text(340, 175, 'bit = 1', 'sf-lab', 1, 5)
text(340, 175, 'bit = 0', 'sf-lab sf-bad', 5, 6)

# ---- steps 6-8: TRR tracker, then the bypass, then PRAC counters ----
rect(20, 60, 440, 110, 'f-panel s-line', 6, 8, rx=8, sw=1.5)
text(32, 80, 'TRR tracker: 4 entries', 'sf-lab', 6, 8)
for i, lab in enumerate(['A1', 'A2', 'A3', 'A4']):
    x = 32 + i * 108
    rect(x, 94, 96, 46, 'f-code s-acc', 6, 8, rx=6, sw=2)
    text(x + 48, 123, lab, 'sf-cell', 6, 8, 'middle')
text(20, 274, 'victim V', 'sf-lab', 6, 8)
rect(100, 260, 350, 18, 'f-code', 6, 8, rx=3)
rect(100, 260, 350, 18, 'f-ok', 6, 7, rx=3)
rect(100, 260, 110, 18, 'f-bad', 7, 8, rx=3)
rect(20, 182, 440, 40, 'f-none s-bad', 7, 8, rx=8, sw=2, dash='6 4')
text(32, 207, 'A5: not in the tracker, never refreshed', 'sf-lab sf-bad', 7, 8)

# ---- step 8-9: PRAC exact counters ----
COUNT = [('A1', 300, 'f-bad', 66), ('A2', 200, 'f-acc', 106), ('V+2', 40, 'f-ok', 146)]
for lab, w, c, y in COUNT:
    text(20, y + 16, lab, 'sf-lab', 8, 9)
    rect(110, y, 330, 22, 'f-code', 8, 9, rx=4)
    rect(110, y, w, 22, c, 8, 9, rx=4)
text(374, 50, 'threshold', 'sf-lab', 8, 9, 'middle')
line(374, 56, 374, 172, 's-bad', 8, 9, dash='4 4')

# ---- step 9: headline overlay ----
out.append(f'<g{rng(9)}>')
out.append('<rect x="12" y="38" width="456" height="360" rx="14" class="f-bg" opacity=".97"/>')
out.append('<text x="240" y="74" class="sf-cap" text-anchor="middle">The numbers in this dive</text>')
text(60, 114, 'DDR3 modules with bit flips, 2014', 'sf-lab', 9)
rect(60, 124, 360, 18, 'f-code', 9, None, rx=4)
rect(60, 124, 307, 18, 'f-warn', 9, None, rx=4)
text(60, 166, '110 of 129', 'sf-num', 9)
text(60, 214, 'SK Hynix DDR5 DIMMs flipped by Phoenix, 2026', 'sf-lab', 9)
rect(60, 224, 360, 18, 'f-code', 9, None, rx=4)
rect(60, 224, 360, 18, 'f-bad', 9, None, rx=4)
text(60, 266, '15 of 15', 'sf-num', 9)
text(60, 304, 'PRAC latency cost, as reported (up to)', 'sf-lab', 9)
rect(60, 314, 360, 18, 'f-code', 9, None, rx=4)
rect(60, 314, 65, 18, 'f-acc2', 9, None, rx=4)
text(60, 356, '10–18%', 'sf-num', 9)
text(240, 388, 'Details in the cards below', 'sf-lab', 9, None, 'middle')
out.append('</g>')

# ---- captions (top) and status lines (bottom), each with its own range ----
text(20, 26, 'One DRAM bank: a bit is a little charge', 'sf-cap', 1, 2)
text(20, 26, 'Hammer the rows beside victim V', 'sf-cap', 2, 6)
text(20, 26, 'Defense 1, TRR: a short list of hot rows', 'sf-cap', 6, 8)
text(20, 26, 'Defense 2, PRAC: an exact count per row', 'sf-cap', 8, 9)

text(20, 396, 'Refresh tops every row up within 64 ms.', 'sf-lab', 1, 2)
text(20, 396, 'A1 and A2 are read. V is never opened.', 'sf-lab', 2, 3)
text(20, 396, "Each hammer bleeds a sliver of V's charge.", 'sf-lab', 3, 4)
text(20, 396, '~9.6K total hammers: V reaches the sense point.', 'sf-lab', 4, 5)
text(20, 396, 'Read V: it returns 0, and V was never opened.', 'sf-lab sf-bad', 5, 6)
text(20, 396, 'Tracker: 4 rows. Their neighbours get refreshed.', 'sf-lab', 6, 7)
text(20, 396, 'Untracked aggressor: 13 of 42 DDR4 DIMMs flipped.', 'sf-lab sf-bad', 7, 8)
text(20, 396, 'Count crosses the threshold, so V is refreshed.', 'sf-lab', 8, 9)

out.append('</svg>')
sys.stdout.write('\n'.join(out))
