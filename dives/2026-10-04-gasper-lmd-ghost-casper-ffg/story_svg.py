# Generates the story SVG for sections/story.html: python3 story_svg.py prints one <svg id="story-fig">; paste it into .scrolly-fig.
# Votes are drawn at 4 px each on a 100-vote committee. Honest votes split 30 (fork A) to 31 (fork B).
W, H = 480, 420
out = []

def rng(a=None, b=None, hl=None):
    s = ''
    if a is not None: s += f' data-in="{a}"'
    if b is not None: s += f' data-out="{b}"'
    if hl: s += f' data-hl="{hl}"'
    return s

def rect(x, y, w, h, cls, a=None, b=None, hl=None, extra='', rx=4):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" class="{cls}"{extra}{rng(a, b, hl)}/>')

def text(x, y, t, cls, a=None, b=None):
    out.append(f'<text x="{x}" y="{y}" class="{cls}"{rng(a, b)}>{t}</text>')

HATCH = ' fill="url(#gsth)" stroke-width="1"'

out.append(f'<svg id="story-fig" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" '
           'aria-label="Two forks share a parent. Honest votes split 30 to 31. An attacker holds 39 votes back, '
           'releases them with no boost, then faces a 40-vote boost on the on-time block. At 39 the two forks tie, and the root name decides.">')
out.append('<defs><pattern id="gsth" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
           '<line x1="0" y1="0" x2="0" y2="6" class="s-warn" stroke-width="2" opacity=".55"/></pattern></defs>')

# captions: one per step, same spot, disjoint ranges
text(20, 28, 'Honest votes split 30 to 31.', 'sf-cap', 1, 2)
text(20, 28, 'An attacker holds 39 votes back.', 'sf-cap', 2, 3)
text(20, 28, 'Released with no boost, B takes the head.', 'sf-cap', 3, 4)
text(20, 28, 'An on-time block gets a 40-vote boost.', 'sf-cap', 4, 5)
text(20, 28, 'Attacker releases 30: A still leads.', 'sf-cap', 5, 6)
text(20, 28, 'At 39 released: a 70 to 70 tie.', 'sf-cap', 6, 7)
text(20, 28, 'The numbers behind the head rule.', 'sf-cap', 7)

# status line at the bottom, disjoint ranges
text(20, 392, 'B leads by 40 votes, and nothing answers it.', 'sf-lab', 3, 4)
text(20, 392, 'The boost is 40% of one 100-vote committee.', 'sf-lab', 4, 5)
text(20, 392, 'Boost holds: A 70, B 61.', 'sf-lab', 5, 6)
text(20, 392, 'Root name breaks the tie. From 41, B wins outright.', 'sf-lab', 6, 7)

# block tree (base, hidden at the headline step)
out.append('<path d="M110 130 C150 130 150 80 190 80" class="s-line" fill="none" stroke-width="2" data-out="7"/>')
out.append('<path d="M110 130 C150 130 150 180 190 180" class="s-line" fill="none" stroke-width="2" data-out="7"/>')
rect(20, 110, 90, 40, 'f-panel s-line', b=7, extra=' stroke-width="1.5"', rx=7)
text(30, 135, 'parent', 'sf-lab', b=7)
rect(190, 60, 120, 40, 'f-panel s-line', b=7, hl='4 5', extra=' stroke-width="1.5"', rx=7)
text(200, 85, 'fork A', 'sf-lab', b=7)
rect(190, 160, 120, 40, 'f-panel s-line', b=7, hl='3 6', extra=' stroke-width="1.5"', rx=7)
text(200, 185, 'fork B', 'sf-lab', b=7)

# vote bars: 4 px per vote
text(20, 267, 'A', 'sf-lab', b=7)
text(20, 302, 'B', 'sf-lab', b=7)
rect(50, 250, 400, 22, 'f-code', b=7)
rect(50, 285, 400, 22, 'f-code', b=7)
rect(50, 250, 120, 22, 'f-acc', b=7)             # A: 30 honest votes
rect(170, 250, 160, 22, 'f-ok', 4, 7)            # A: +40 boost, on the on-time block
rect(50, 285, 124, 22, 'f-acc2', b=7)            # B: 31 honest votes
rect(174, 285, 156, 22, 's-warn', 3, 4, extra=HATCH)   # 39 released, no boost
rect(174, 285, 120, 22, 's-warn', 5, 6, extra=HATCH)   # 30 released
rect(174, 285, 156, 22, 's-warn', 6, 7, extra=HATCH)   # 39 released

# held-back votes
for a, b, label in ((2, 3, '39 votes held back'), (4, 5, '39 votes held back'), (5, 6, '9 votes held back')):
    rect(270, 322, 190, 26, 's-warn', a, b, extra=HATCH, rx=6)
    text(280, 340, label, 'sf-lab', a, b)

# headline step: a near-opaque panel over the diagram, with five big numbers
out.append(f'<rect x="0" y="0" width="{W}" height="{H}" rx="0" class="f-bg" opacity=".97"{rng(7)}/>')
tiles = [
    (30, 86, '12 s', 'sf-num sf-a', 'per slot, one proposer'),
    (260, 86, '40%', 'sf-num sf-b', 'boost, of one committee'),
    (30, 186, '2/3', 'sf-num', 'stake to justify a checkpoint'),
    (260, 186, '1/3', 'sf-num sf-bad', 'stake to reverse finality'),
    (30, 286, '64–95', 'sf-num', 'slots to finalize today'),
]
for x, y, num, cls, label in tiles:
    text(x, y, num, cls, 7)
    text(x, y + 28, label, 'sf-lab', 7)

out.append('</svg>')
print('\n'.join(out))
