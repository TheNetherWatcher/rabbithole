# Generates the story scrolly SVG for sections/story.html: python3 story_svg.py > story.svg, then paste it into .scrolly-fig.
import sys
W, H = 480, 420
out = []

def rng(a=None, b=None, hl=None):
    s = ''
    if a: s += f' data-in="{a}"'
    if b: s += f' data-out="{b}"'
    if hl: s += f' data-hl="{hl}"'
    return s

def text(x, y, t, cls, a=None, b=None, anchor=None):
    an = f' text-anchor="{anchor}"' if anchor else ''
    out.append(f'<text x="{x}" y="{y}" class="{cls}"{an}{rng(a, b)}>{t}</text>')

ROW_Y = {1: 62, 2: 112, 3: 162}   # chip rows for decision levels 1..3
CW, CH = 58, 30
def chip_x(j): return 80 + 66 * j

def chip(level, j, label, cls, ranges):
    """One chip per visibility range, so a chip never has two texts at one spot."""
    x, y = chip_x(j), ROW_Y[level]
    for (a, b) in ranges:
        out.append(f'<g{rng(a, b)}><rect x="{x}" y="{y}" width="{CW}" height="{CH}" rx="6" class="{cls}" stroke-width="2"/>'
                   f'<text x="{x + CW / 2}" y="{y + 20}" class="sf-cell" text-anchor="middle">{label}</text></g>')

def level_label(level, a=None):
    text(20, ROW_Y[level] + 20, f'L{level}', 'sf-lab', a)

out.append(f'<svg id="story-fig" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" '
           'aria-label="A CDCL trail of decisions and forced literals. A clash is traced back to a learned clause, the solver jumps back, and the clause stays.">')

# captions: one text per phase, same spot, disjoint ranges
text(20, 26, 'Five clauses. The solver builds a trail.', 'sf-cap', 1, 2)
text(20, 26, 'Decide, then propagate: each choice forces more', 'sf-cap', 2, 4)
text(20, 26, 'A clash: one clause has every literal false', 'sf-cap', 4, 5)
text(20, 26, 'Trace the clash back to one literal', 'sf-cap', 5, 6)
text(20, 26, 'Jump back past the innocent choices', 'sf-cap', 6, 8)
text(20, 26, 'Where it still fails: pigeonhole counting', 'sf-cap', 8, 9)

# step 1: the formula, as text
for k, line in enumerate(['C1   ¬3 ∨ 4', 'C2   ¬4 ∨ 5', 'C3   ¬4 ∨ 6', 'C4   ¬5 ∨ ¬6 ∨ ¬2', 'C5   1 ∨ 2 ∨ 3 ∨ 7']):
    text(20, 92 + 24 * k, line, 'sf-lab', 1, 2)

# trail rows: background guides, shown from step 2
for lv in (1, 2, 3):
    out.append(f'<rect x="12" y="{ROW_Y[lv] - 6}" width="456" height="{CH + 12}" rx="8" class="f-panel s-line" stroke-width="1"' + rng(2) + '/>')
    level_label(lv, 2)

# level 1 and 2 decisions (step 2)
chip(1, 0, 'x1', 'f-panel s-acc', [(2, None)])
chip(2, 0, 'x2', 'f-panel s-acc', [(2, 4), (6, None)])

# level 3: decision x3, then forced x4, x5, x6 (step 3); removed by the backjump at step 6
chip(3, 0, 'x3', 'f-panel s-acc', [(3, 6)])
chip(3, 1, 'x4', 'f-panel s-acc2', [(3, 6)])
chip(3, 2, 'x5', 'f-panel s-acc2', [(3, 4)])
chip(3, 3, 'x6', 'f-panel s-acc2', [(3, 4)])

# the clash (step 4 onward): the three true literals that falsify C4
chip(2, 0, 'x2', 'f-panel s-bad', [(4, 6)])
chip(3, 2, 'x5', 'f-panel s-bad', [(4, 6)])
chip(3, 3, 'x6', 'f-panel s-bad', [(4, 6)])

# learned clause (step 5 onward)
out.append('<rect x="12" y="206" width="456" height="34" rx="8" class="f-panel s-acc2" stroke-width="2"' + rng(5) + '/>')
text(20, 228, 'learned clause:  (¬2 ∨ ¬4)', 'sf-big', 5)

# backjump (step 6): level 2 keeps x2, and ¬4 is forced by the clause
chip(2, 1, '¬4', 'f-panel s-acc2', [(6, None)])

# status line at the bottom: one text per step, same spot
status = [
    (2, 3, 'Decide x1, then x2. Nothing is forced yet.'),
    (3, 4, 'Decide x3. C1, C2, C3 force x4, x5, x6.'),
    (4, 5, 'C4 is false. Plain search undoes only x3.'),
    (5, 6, 'Learn (¬2 ∨ ¬4). Level-3 literals resolved away.'),
    (6, 7, 'Jump back to level 2. The clause is unit: ¬4.'),
    (7, 8, 'The clause stays: x2 and x4 can’t both be true.'),
    (8, 9, 'Pigeonhole, n=5: 137 conflicts. n=10: 2,657,952.'),
]
for a, b, t in status:
    text(20, 340, t, 'sf-lab', a, b)

# step 9: headline numbers over the diagram
out.append('<g' + rng(9) + '><rect x="12" y="38" width="456" height="370" rx="14" class="f-bg" opacity=".97"/>'
           '<text x="240" y="84" class="sf-cap" text-anchor="middle">What the dive measured</text>'
           '<text x="60" y="150" class="sf-num">2000</text>'
           '<text x="60" y="176" class="sf-lab">random formulas fuzzed against brute force, 0 mismatches</text>'
           '<text x="60" y="236" class="sf-num">2.66M</text>'
           '<text x="60" y="262" class="sf-lab">conflicts on pigeonhole n=10, CaDiCaL</text>'
           '<text x="60" y="322" class="sf-num">×7–8</text>'
           '<text x="60" y="348" class="sf-lab">more conflicts per extra hole</text>'
           '<text x="240" y="392" class="sf-big" text-anchor="middle">Learned clauses change speed, never the answer</text></g>')
out.append('</svg>')
sys.stdout.write('\n'.join(out) + '\n')
