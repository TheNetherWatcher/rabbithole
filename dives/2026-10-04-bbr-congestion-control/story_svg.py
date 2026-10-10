# Generates the story scrolly SVG for sections/story.html: python3 story_svg.py > story.svg, then paste it into .scrolly-fig.
import sys
COLS, ROWS, CW, CH, GAP = 16, 5, 24, 24, 3   # 80 cells; one cell = 4 packets, grid = 320-packet buffer (8 x BDP)
X0, Y0, STEP = 20, 70, 27
out = []
def cx(c): return X0 + c * STEP
def cy(r): return Y0 + r * STEP
def rng(a=None, b=None, hl=None):
    s = ''
    if a: s += f' data-in="{a}"'
    if b: s += f' data-out="{b}"'
    if hl: s += f' data-hl="{hl}"'
    return s
def cell(c, r, cls, a=None, b=None, hl=None):
    out.append(f'<rect x="{cx(c)}" y="{cy(r)}" width="{CW}" height="{CH}" rx="3" class="{cls}"{rng(a, b, hl)}/>')
def text(x, y, t, cls, a=None, b=None, anchor=None):
    an = f' text-anchor="{anchor}"' if anchor else ''
    out.append(f'<text x="{x}" y="{y}" class="{cls}"{an}{rng(a, b)}>{t}</text>')

out.append('<svg id="story-fig" viewBox="0 0 480 430" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="A router buffer grid of 80 cells. Loss-based senders fill every cell until packets drop. BBR keeps about 10 cells, one BDP, in flight and the queue stays near empty.">')
out.append('<defs><pattern id="sbh" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" class="s-warn" stroke-width="2" opacity=".55"/></pattern></defs>')

# captions (same spot, disjoint ranges)
text(20, 26, 'A 12 Mbit/s link, empty round trip 40 ms', 'sf-cap', 1, 2)
text(20, 26, 'Loss-based: keep sending until a drop', 'sf-cap', 2, 3)
text(20, 26, 'BBR target: BtlBw × RTprop', 'sf-cap', 3, 4)
text(20, 26, 'BBR cruises: probe up, then drain', 'sf-cap', 4, 7)
text(20, 26, 'The cost: shallow buffers and fairness', 'sf-cap', 7, 9)

# base panel and grid
out.append('<rect x="14" y="62" width="452" height="148" rx="8" class="f-panel s-line" stroke-width="1.5"/>')
for r in range(ROWS):
    for c in range(COLS):
        cell(c, r, 'f-code')
text(20, 232, 'Router buffer: 320 packets, 8 × BDP', 'sf-lab', None, 9)

# loss-based fill (steps 2-2): whole buffer full
for r in range(ROWS):
    for c in range(COLS):
        cell(c, r, 'f-warn', 2, 3)

# BDP outline (step 3-4): first 10 cells = 40 packets
out.append(f'<rect x="{X0-4}" y="{cy(0)-4}" width="{10*STEP-3+8}" height="{CH+8}" rx="6" class="f-none s-ok" stroke-width="2"{rng(3, 5)}/>')

# BBR in flight (from step 4): 10 cells
for c in range(10):
    cell(c, 0, 'f-ok', 4)
# probe (steps 5-6): two more cells, accent outline
cell(10, 0, 'f-acc2', 5, 6, '5 6')
cell(11, 0, 'f-acc2', 5, 6, '5 6')

# shallow buffer drops (steps 7-8): hatched cells in the last row
for c in range(5):
    out.append(f'<rect x="{cx(c)}" y="{cy(4)}" width="{CW}" height="{CH}" rx="3" fill="url(#sbh)" class="s-warn" stroke-width="1"{rng(7, 9)}/>')

# status line (bottom), disjoint ranges
text(20, 400, 'Each cell = 4 packets. The grid is the router buffer.', 'sf-lab', 1, 2)
text(20, 400, 'Median RTT 221 ms, against 40 ms with an empty queue.', 'sf-lab', 2, 3)
text(20, 400, '12 Mbit/s × 40 ms = 40 packets = 10 cells.', 'sf-lab', 3, 4)
text(20, 400, 'Queue stays near empty. Median RTT 55.5 ms.', 'sf-lab', 4, 5)
text(20, 400, 'Probe: pacing gain 1.25 sends 25% more for a round.', 'sf-lab', 5, 6)
text(20, 400, 'Back down: gain 0.75 drains what the probe added.', 'sf-lab', 6, 7)
text(20, 400, 'Shallow buffer: BBRv1 drops 324 packets. Reno: 8.', 'sf-lab sf-bad', 7, 8)
text(20, 400, 'Against CUBIC, BBR takes a fixed ~40% share.', 'sf-lab', 8, 9)

# result overlay (step 9)
bar = 360 * 55.5 / 221
out.append(f'<g{rng(9)}><rect x="12" y="38" width="456" height="384" rx="14" class="f-bg" opacity=".97"/>'
           '<text x="240" y="96" class="sf-cap" text-anchor="middle">Same 12 Mbit/s link, same 40 ms path</text>'
           '<text x="60" y="146" class="sf-lab">Loss-based (Reno)</text>'
           '<text x="420" y="146" class="sf-num" text-anchor="end">221 ms</text>'
           '<rect x="60" y="156" width="360" height="30" rx="8" class="f-code s-line"/>'
           '<rect x="60" y="156" width="360" height="30" rx="8" class="f-warn"/>'
           '<text x="60" y="236" class="sf-lab">BBR (BBRv1-like)</text>'
           '<text x="420" y="236" class="sf-num" text-anchor="end">55.5 ms</text>'
           '<rect x="60" y="246" width="360" height="30" rx="8" class="f-code s-line"/>'
           f'<rect x="60" y="246" width="{bar:.1f}" height="30" rx="8" class="f-ok"/>'
           '<text x="240" y="330" class="sf-big" text-anchor="middle">About 40 packets in flight, queue near empty</text>'
           '<text x="240" y="356" class="sf-lab" text-anchor="middle">Its weak spots: shallow buffers and CUBIC</text>'
           '<text x="240" y="392" class="sf-lab" text-anchor="middle">The cards below cover each piece.</text></g>')
out.append('</svg>')
sys.stdout.write('\n'.join(out))
