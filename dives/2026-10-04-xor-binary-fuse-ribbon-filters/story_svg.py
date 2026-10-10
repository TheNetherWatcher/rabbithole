# Generates the story scrolly SVG for sections/story.html: python3 story_svg.py, then paste its output into .scrolly-fig.
import sys

out = []
BX = {'A0': 52, 'A1': 112, 'B0': 184, 'B1': 244, 'C0': 316, 'C1': 376}
BY, BS = 96, 52


def rng(a=None, b=None, hl=None):
    s = ''
    if a is not None:
        s += f' data-in="{a}"'
    if b is not None:
        s += f' data-out="{b}"'
    if hl is not None:
        s += f' data-hl="{hl}"'
    return s


def text(x, y, t, cls, a=None, b=None, anchor=None):
    an = f' text-anchor="{anchor}"' if anchor else ''
    out.append(f'<text x="{x}" y="{y}" class="{cls}"{an}{rng(a, b)}>{t}</text>')


out.append('<svg id="story-fig" viewBox="0 0 480 430" xmlns="http://www.w3.org/2000/svg" role="img" '
           'aria-label="Three guests and six slots. Each guest is peeled onto a stack through a slot only it touches, then the slots are filled in reverse.">')

# captions (top): one per phase, same spot, disjoint ranges
text(20, 26, 'Three guests, six slots, one XOR check each', 'sf-cap', 1, 2)
text(20, 26, 'Random guesses pass each guest 1 time in 8', 'sf-cap', 2, 3)
text(20, 26, 'Peel: park a guest who owns a slot alone', 'sf-cap', 3, 6)
text(20, 26, 'Fill in reverse: last parked goes first', 'sf-cap', 6, 8)
text(20, 26, 'Check every guest against its code', 'sf-cap', 8, 9)

# board: six slots, base layer
for name, x in BX.items():
    hl = {'C0': '3 7', 'A1': '4 7', 'A0': '5 6', 'B1': '6', 'C1': '6'}.get(name)
    out.append(f'<rect x="{x}" y="{BY}" width="{BS}" height="{BS}" rx="6" class="f-panel s-line sf-blk" stroke-width="1.5"'
               + (rng(hl=hl) if hl else '') + '/>')
    text(x + 6, BY + 15, name, 'sf-id')

# slot values, written in the fill phase (the last-parked guest first)
for name, v, a in (('A0', '3', 6), ('B0', '0', 6), ('B1', '0', 6), ('C1', '0', 6), ('A1', '6', 7), ('C0', '6', 7)):
    text(BX[name] + BS / 2, BY + 36, v, 'sf-cell', a, 9, 'middle')

# guest equations, always visible until the overlay
text(52, 180, 'Ana: A0 ⊕ B0 ⊕ C0 = 5', 'sf-lab', 1, 9)
text(52, 204, 'Ben: A0 ⊕ B1 ⊕ C1 = 3', 'sf-lab', 1, 9)
text(52, 228, 'Cy: A1 ⊕ B0 ⊕ C1 = 6', 'sf-lab', 1, 9)

# the stack, bottom to top: Ana (3), Cy (4), Ben (5)
text(52, 256, 'Stack, bottom to top', 'sf-lab', 3, 9)
for k, (x, lab, a) in enumerate(((52, '1st: Ana via C0', 3), (190, '2nd: Cy via A1', 4), (328, '3rd: Ben via A0', 5))):
    out.append(f'<g{rng(a, 9)}><rect x="{x}" y="262" width="134" height="34" rx="6" class="f-panel s-ok" stroke-width="1.5"/>'
           f'<text x="{x + 10}" y="284" class="sf-lab">{lab}</text></g>')

# status lines (bottom): two lines per step, one range each
status = [
    (1, 'Ana, Ben and Cy each need three slots to XOR', 'to their code. Solve all three at once.'),
    (2, 'Guess values at random and each guest passes 1 time in 8.', 'Setting one guest’s slots breaks another’s.'),
    (3, 'C0 is touched by Ana alone. Park Ana.', 'Her code is set later, from the slots the others leave.'),
    (4, 'A1 is touched by Cy alone. Park Cy.', 'Ben is left. Nothing unparked touches his slots.'),
    (5, 'Park Ben too. All three guests are on the stack.', 'The stack gives the order, so the table exists.'),
    (6, 'Pop Ben first: A0 = 3. B0, B1 and C1 stay 0.', 'His slots now XOR to his code, 3.'),
    (7, 'Pop Cy: A1 = 6. Then Ana: C0 = 6.', 'Each slot is set once, so earlier guests stay correct.'),
    (8, 'Check Ana: 3 ⊕ 0 ⊕ 6 = 5. Ben and Cy pass too.', 'A stranger passes by luck 1 time in 256 (8 bits).'),
]
for s, l1, l2 in status:
    text(20, 392, l1, 'sf-lab', s, s + 1)
    text(20, 414, l2, 'sf-lab', s, s + 1)

# result overlay (step 9)
out.append(
    f'<g{rng(9)}><rect x="12" y="38" width="456" height="384" rx="14" class="f-bg" opacity=".97"/>'
    '<text x="240" y="100" class="sf-cap" text-anchor="middle">What the peel costs</text>'
    '<text x="60" y="160" class="sf-num">1.23</text>'
    '<text x="60" y="186" class="sf-lab">slots per key, XOR filter (peeling threshold)</text>'
    '<text x="60" y="246" class="sf-num">1.125</text>'
    '<text x="60" y="272" class="sf-lab">slots per key, binary fuse (3-wise windows)</text>'
    '<text x="60" y="332" class="sf-num">0.39%</text>'
    '<text x="60" y="358" class="sf-lab">false positives with an 8-bit fingerprint</text>'
    '<text x="40" y="398" class="sf-big">Below 1.22 slots per key the peel stalls. Retry.</text></g>'
)
out.append('</svg>')
sys.stdout.write('\n'.join(out))
