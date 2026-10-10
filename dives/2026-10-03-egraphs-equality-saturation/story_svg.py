# Generates the story scrolly SVG for sections/story.html: python3 story_svg.py > story.svg, then paste it into .scrolly-fig.
import sys

out = []


def T(x, y, s, cls, a=None, b=None, anchor=None):
    an = f' text-anchor="{anchor}"' if anchor else ''
    rg = (f' data-in="{a}"' if a else '') + (f' data-out="{b}"' if b else '')
    out.append(f'<text x="{x}" y="{y}" class="{cls}"{an}{rg}>{s}</text>')


def R(x, y, w, h, cls, a=None, b=None, hl=None, rx=6, extra=''):
    rg = (f' data-in="{a}"' if a else '') + (f' data-out="{b}"' if b else '') + (f' data-hl="{hl}"' if hl else '')
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" class="{cls}"{extra}{rg}/>')


out.append('<svg id="story-fig" viewBox="0 0 480 430" xmlns="http://www.w3.org/2000/svg" role="img" '
           'aria-label="The term (a times 2) divided by 2 as e-classes. A rewrite adds forms to classes instead of replacing them, '
           'extraction keeps the cheapest form, and the total e-node count grows under commutativity until a limit stops it.">')

# ---- captions (top line, one per step) ----
caps = [
    'The term (a × 2) ÷ 2, one class per subterm',
    'Rewrite first, ask later: a × 2 becomes a ≪ 1',
    'Keep both: the new form joins the same class',
    'div-assoc adds a second form to the root class',
    'div-same: 2 ÷ 2 is 1, so class e6 holds 1',
    'mul-one: a × 1 = a, so the root merges with e0',
    'Extraction: keep the cheapest form in each class',
    'Add one commutativity rule and it never stops',
]
for k, s in enumerate(caps, start=1):
    T(20, 26, s, 'sf-cap', k, k + 1)

# ---- row 1 classes: e0 e1 e2 e3 ----
R(20, 44, 104, 96, 'f-panel s-line sf-blk', rx=7, extra=' stroke-width="1.5"')
R(132, 44, 104, 96, 'f-panel s-line sf-blk', rx=7, extra=' stroke-width="1.5"')
R(244, 44, 104, 96, 'f-panel s-line sf-blk', rx=7, extra=' stroke-width="1.5"', hl='3')
R(356, 44, 104, 96, 'f-panel s-line sf-blk', rx=7, extra=' stroke-width="1.5"')
T(26, 60, 'e0', 'sf-id')
T(138, 60, 'e1', 'sf-id')
T(250, 60, 'e2', 'sf-id')
T(362, 60, 'e3', 'sf-id')

# e0: a, then a × 1 once mul-one fires (step 6)
T(28, 86, 'a', 'sf-node')
T(28, 106, 'a × 1', 'sf-node', 6)
# e1: the constant 2
T(140, 86, '2', 'sf-node')
# e2: a × 2 is overwritten by the naive rewrite (step 2), restored in step 3 with a ≪ 1 beside it
T(252, 86, 'a × 2', 'sf-node', None, 2)
T(252, 86, 'a ≪ 1', 'sf-node', 2, 3)
T(252, 86, 'a × 2', 'sf-node', 3)
T(252, 106, 'a ≪ 1', 'sf-node', 3)
# e3: the root
T(364, 86, '(a × 2) ÷ 2', 'sf-node')
T(364, 106, 'a × (2 ÷ 2)', 'sf-node', 4)
T(364, 126, 'merged: e0', 'sf-node', 6)

# ---- row 2: e6 holds 2 ÷ 2, then 1 ----
R(132, 156, 104, 84, 'f-panel s-line sf-blk', 4, None, hl='5', rx=7, extra=' stroke-width="1.5"')
T(138, 172, 'e6', 'sf-id', 4)
T(140, 192, '2 ÷ 2', 'sf-node', 4)
T(140, 212, '1', 'sf-node', 5)

# ---- middle panel: one explanation per step ----
mid = {
    2: ('Rewrite a × 2 to a ≪ 1 in place, first:', 'the ÷ rule can no longer match, so a is gone.'),
    3: ('e2 keeps its old form and gains the new one.', 'Nothing is thrown away until extraction.'),
    4: ('e3 gets a second form: a × (2 ÷ 2).', '2 ÷ 2 sits in its own class, e6.'),
    5: ('e6 now holds 1 as well.', 'Rebuilding fixes the keys of nodes that point at e6.'),
    6: ('mul-one: a × 1 = a, so e0 gains a × 1.', 'a × 1 points back into e0. That is a cycle.'),
    7: ('Extraction walks each class bottom-up.', 'It keeps the cheapest node in each class.'),
    8: ('e-nodes per round: 9, 12, 13, 20, 28, 39, 52,', '67, 84, 103, and then the iteration limit.'),
}
for k, (l1, l2) in mid.items():
    T(20, 280, l1, 'sf-lab', k, k + 1)
    T(20, 302, l2, 'sf-lab', k, k + 1)

# ---- status line (bottom, one per step 1-8) ----
status = [
    'The 2 is stored once, even though it appears twice.',
    'The ÷ rule now finds no a × _. a has been lost.',
    'a × 2 and a ≪ 1 now sit side by side in e2.',
    'div-assoc adds a × (2 ÷ 2). Nothing is removed.',
    'div-same: 2 ÷ 2 joins the class holding 1.',
    'e3 merges into e0. e0 now points back to itself.',
    'Cost: a is 1, (a × 2) ÷ 2 is 5. The result is a.',
    'Commutativity keeps adding nodes until a limit hits.',
]
for k, s in enumerate(status, start=1):
    T(20, 400, s, 'sf-lab', k, k + 1)

# ---- step 9: headline numbers over the diagram ----
R(12, 38, 456, 384, 'f-bg', 9, None, rx=14, extra=' opacity=".97"')
T(240, 84, 'Keeping every form has a price', 'sf-cap', 9, None, 'middle')
T(60, 128, 'Round trip through the e-graph, zero rewrites', 'sf-lab', 9)
R(60, 136, 400, 28, 'f-code s-line', 9)
R(60, 136, 230, 28, 'f-bad', 9)
T(300, 162, '23%', 'sf-num', 9)
T(60, 206, 'Budget for the whole optimizer', 'sf-lab', 9)
R(60, 214, 400, 28, 'f-code s-line', 9)
R(60, 214, 100, 28, 'f-ok', 9)
T(170, 240, 'about 10%', 'sf-num', 9)
T(240, 304, 'A rewrite that changes nothing still costs time.', 'sf-big', 9, None, 'middle')
T(240, 328, "Cranelift's average e-class holds 1.13 nodes.", 'sf-lab', 9, None, 'middle')
T(240, 352, 'So its mid-end keeps only a few eager rules.', 'sf-lab', 9, None, 'middle')
T(240, 392, 'The cards below cover the limits and the fixes.', 'sf-lab', 9, None, 'middle')

out.append('</svg>')
sys.stdout.write('\n'.join(out))
