# Generates the story scrolly SVG for sections/story.html: python3 story_svg.py > story.svg, then paste it into .scrolly-fig.
CX = [85, 185, 285, 385]   # expert column centres
BASE, SCALE, BW = 300, 0.2, 50  # bar baseline y, px per token, bar width
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

def bars(loads, classes, a, b, labels=True, hot_hl=None):
    for i, v in enumerate(loads):
        h = round(v * SCALE, 1)
        hl = hot_hl if (hot_hl and i == 0) else None
        out.append(f'<rect x="{CX[i] - BW // 2}" y="{round(BASE - h, 1)}" width="{BW}" height="{h}" rx="4" '
                   f'class="{classes[i]}"{rng(a, b, hl)}/>')
        if labels:
            text(CX[i], round(BASE - h - 7, 1), f'{v:,}', 'sf-cell', a, b, 'middle')

out.append('<svg id="story-fig" viewBox="0 0 480 420" xmlns="http://www.w3.org/2000/svg" role="img" '
           'aria-label="Four experts receive 2,000 picks. Without balancing one expert takes 820. A per-expert bias '
           'steers picks until loads settle near the fair share of 500.">')

# ---- base: expert frames, fair-share line, expert ids ----
for i in range(4):
    out.append(f'<rect x="{CX[i] - 40}" y="120" width="80" height="180" rx="8" class="f-panel s-line" stroke-width="1.5"/>')
    text(CX[i], 322, f'E{i}', 'sf-lab', None, None, 'middle')
out.append('<line x1="30" y1="200" x2="450" y2="200" class="s-mute" stroke-width="1.5" stroke-dasharray="5 4"/>')

# ---- captions (top, one per step, disjoint ranges) ----
text(20, 28, '1,000 tokens, top 2 each: fair share 500', 'sf-cap', 1, 2)
text(20, 28, 'No balancing: expert 0 takes 820', 'sf-cap', 2, 3)
text(20, 28, 'A bias per expert steers selection', 'sf-cap', 3, 4)
text(20, 28, 'This token picks experts 3 and 1', 'sf-cap', 4, 5)
text(20, 28, 'After the batch, the bias moves', 'sf-cap', 5, 6)
text(20, 28, 'Keep going: loads settle near 500', 'sf-cap', 6, 7)
text(20, 28, 'Step too big: it jitters, never settles', 'sf-cap', 7, 8)

# ---- status line (bottom, one per step, disjoint ranges) ----
text(20, 396, 'Toy run, u = 0: MaxVio stays at 2.57', 'sf-lab', 2, 3)
text(20, 396, 'Bias changes selection, not the gate', 'sf-lab', 3, 4)
text(20, 396, 'Gate weights use raw scores 0.599 and 0.711', 'sf-lab', 4, 5)
text(20, 396, 'One batch: b moves 0.001 per step, sign only', 'sf-lab', 5, 6)
text(20, 396, 'Toy run, u = 0.001: MaxVio 0.084 over last 100', 'sf-lab', 6, 7)
text(20, 396, 'Toy run, u = 0.05: MaxVio 0.492, no settling', 'sf-lab', 7, 8)

# ---- step 1 has no bars; step 2-5: one traced batch (2,000 picks) ----
bars([820, 430, 300, 450], ['f-warn', 'f-acc', 'f-acc', 'f-acc'], 2, 6, True, hot_hl='2 3')

# ---- step 3-4: bias chips before the update ----
for i, t in enumerate(['b -0.20', 'b +0.05', 'b +0.12', 'b 0.00']):
    text(CX[i], 346, t, 'sf-cell', 3, 5, 'middle')

# ---- step 4: the two experts the token picks ----
for i in (1, 3):
    out.append(f'<rect x="{CX[i] - 44}" y="116" width="88" height="190" rx="10" class="f-none s-acc" '
               f'stroke-width="2.5"{rng(4, 5)}/>')

# ---- step 5: chips after the batch ----
for i, t in enumerate(['b -0.201', 'b +0.051', 'b +0.121', 'b +0.001']):
    text(CX[i], 346, t, 'sf-cell', 5, 6, 'middle')

# ---- step 6+: loads settle near the fair share ----
out.append('<g' + rng(6) + '>')
for i in range(4):
    out.append(f'<rect x="{CX[i] - BW // 2}" y="{BASE - 100}" width="{BW}" height="100" rx="4" class="f-ok"/>')
out.append('</g>')

# ---- step 8: headline numbers over the diagram ----
out.append('<rect x="10" y="10" width="460" height="400" rx="12" class="f-bg" opacity="0.97"' + rng(8) + '/>')
text(20, 110, '2.57 → 0.084', 'sf-num', 8)
text(20, 134, 'Toy run MaxVio: no balancing, then bias at u = 0.001', 'sf-lab', 8)
text(20, 200, '0.52 → 0.04', 'sf-num', 8)
text(20, 224, '3B model MaxVio: aux loss, then loss-free bias', 'sf-lab', 8)
text(20, 300, 'The bias gets no gradient. The gate ignores it.', 'sf-big', 8)

out.append('</svg>')
print('\n'.join(out))
