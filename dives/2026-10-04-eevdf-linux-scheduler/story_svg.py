# Generates the story scrolly SVG for sections/story.html: python3 story_svg.py, then paste its output into .scrolly-fig.
import sys

VX, SC = 285, 100                      # x of V (weighted average), px per unit of (vruntime - V)
ROW = {'A': 62, 'B': 92, 'C': 122}     # ledger rows
CLS = {'A': 'f-acc', 'B': 'f-acc2', 'C': 'f-ok'}
TRACE = 'CABCABABCCABCABABCCABCAB'     # from eevdf_sim.py, 1 ms per letter
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

def dot(t, cx, a, b, hl=None):
    out.append(f'<circle cx="{cx}" cy="{ROW[t]}" r="8" class="{CLS[t]} s-ink" stroke-width="1.5"{rng(a, b, hl)}/>')

out.append('<svg id="story-fig" viewBox="0 0 480 430" xmlns="http://www.w3.org/2000/svg" role="img" '
           'aria-label="One CPU with three tasks. Ledger dots show each task against the average V. Then the schedule runs one millisecond at a time, '
           'with 8 ms each in 24 ms, a 2 to 1 weight ratio, and headline numbers.">')

# ---- captions: one per step, same spot ----
caps = [(1, 2, 'One CPU, three runnable tasks'),
        (2, 3, 'Old rule: serve the least-served task'),
        (3, 4, 'Eligible means not ahead of V'),
        (4, 5, 'Pick the earliest virtual deadline'),
        (5, 6, 'Working: one millisecond per turn'),
        (6, 7, 'Over 24 ms, every task gets 8 ms'),
        (7, 8, 'Weight sets the share'),
        (8, 9, 'The cost is switches, not share'),
        (9, None, 'The numbers behind the rule')]
for a, b, t in caps:
    text(20, 26, t, 'sf-cap', a, b)

# ---- ledger (steps 1-4) ----
out.append(f'<line x1="{VX}" y1="44" x2="{VX}" y2="136" class="s-ink" stroke-width="1.5" stroke-dasharray="4 4" data-out="5"/>')
text(VX, 152, 'V, the weighted average', 'sf-lab', None, 5, 'middle')
for t, lab in (('A', 'A  3 ms'), ('B', 'B  3 ms'), ('C', 'C  1 ms')):
    y = ROW[t]
    out.append(f'<rect x="110" y="{y-10}" width="350" height="20" rx="4" class="f-code s-line" stroke-width="1" data-out="5"/>')
    text(20, y + 5, lab, 'sf-lab', None, 5)
# steps 1-2: all square on V
for t in 'ABC': dot(t, VX, 1, 3)
# step 3: C ran 1 ms (vruntime 1.00 vs V 0.33): ahead, not eligible; A and B behind
dot('A', VX - 33, 3, 4); dot('B', VX - 33, 3, 4); dot('C', VX + 67, 3, 4, hl=3)
# step 4: all square at t = 3 ms
for t in 'ABC': dot(t, VX, 4, 5)

# status line (bottom), one per step
stat = [(1, 2, 'C asks for 1 ms turns. A and B ask for 3 ms.'),
        (2, 3, 'CFS is fair over time, but takes no turn length.'),
        (3, 4, 'C ran, so it is ahead of V: not eligible.'),
        (4, 5, 'All square again. C has deadline 2, A and B 3.'),
        (5, 6, 'Each millisecond goes to one eligible task.'),
        (6, 7, 'Over 24 ms: A 8, B 8, C 8. Equal shares.'),
        (7, 8, 'Weight 2048 vs 1024: H gets 8 ms, L gets 4.'),
        (8, 9, 'Short turns mean more switches. Share unchanged.')]
for a, b, t in stat:
    text(20, 400, t, 'sf-lab', a, b)

# ---- timeline: steps 5-6 show the ABC trace, step 7-8 the weight trace ----
def cells(row_y, seq, a, b, cls_map, start=0, n=12):
    for j, ch in enumerate(seq):
        x = 24 + j * 36
        out.append(f'<g{rng(a, b)}><rect x="{x}" y="{row_y}" width="30" height="30" rx="5" class="{cls_map[ch]}"/>'
                   f'<text x="{x+15}" y="{row_y+20}" class="sf-cell" text-anchor="middle">{ch}</text></g>')

ABC = {'A': 'f-acc', 'B': 'f-acc2', 'C': 'f-ok'}
HL = {'H': 'f-acc', 'L': 'f-acc2'}
text(24, 170, 'ms 0 to 11', 'sf-lab', 5, 7)
cells(178, TRACE[:12], 5, 7, ABC)
text(24, 228, 'ms 12 to 23', 'sf-lab', 6, 7)
cells(236, TRACE[12:], 6, 7, ABC)
text(24, 170, 'H: weight 2048 · L: weight 1024', 'sf-lab', 7, 9)
cells(178, 'HLHHLHHLHHLH', 7, 9, HL)
text(24, 290, 'Each change of task is a context switch.', 'sf-lab', 8, 9)

# ---- step 9: headline numbers over the diagram ----
out.append('<g data-in="9"><rect x="12" y="38" width="456" height="384" rx="14" class="f-bg" opacity=".97"/>')
rows = [('0.7–2.8 ms', 'default base slice, from 1 CPU to 8 or more'),
        ('8 / 8 / 8', 'ms of CPU each task gets in 24 ms, slices unequal'),
        ('2 : 1', 'CPU share for weight 2048 against 1024'),
        ('6.6', 'first mainline kernel with EEVDF, Oct 2023')]
for i, (num, lab) in enumerate(rows):
    y = 110 + i * 74
    out.append(f'<text x="40" y="{y}" class="sf-num">{num}</text>')
    out.append(f'<text x="40" y="{y+24}" class="sf-lab">{lab}</text>')
out.append('<text x="40" y="404" class="sf-big">The cards below take each piece apart.</text></g>')
out.append('</svg>')
sys.stdout.write('\n'.join(out) + '\n')
