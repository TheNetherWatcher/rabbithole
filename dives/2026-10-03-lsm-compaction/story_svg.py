# Generates the scroll-story SVG for sections/story.html: python3 story_svg.py > story.svg, then paste it into .scrolly-fig.
# Two lanes, leveling (top) and tiering (bottom), T = 3, traced flush by flush as in sections/05-mechanism.html.
# Final step draws the simulator's measured write amplification at T = 10, L = 3 (sections/13-hands-on.html).
out = []
def rng(a=None, b=None, hl=None):
    s = ''
    if a: s += f' data-in="{a}"'
    if b: s += f' data-out="{b}"'
    if hl: s += f' data-hl="{hl}"'
    return s
def rect(x, y, w, h, cls, a=None, b=None, hl=None, rx=7, sw=1.5):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" class="{cls}" stroke-width="{sw}"{rng(a, b, hl)}/>')
def text(x, y, t, cls, a=None, b=None, anchor=None):
    an = f' text-anchor="{anchor}"' if anchor else ''
    out.append(f'<text x="{x}" y="{y}" class="{cls}"{an}{rng(a, b)}>{t}</text>')
def chip(x, y, n, cls, a, b, hl=None):
    rect(x, y, 40, 30, f'f-code {cls}', a, b, hl, rx=4, sw=1.5)
    text(x + 20, y + 20, n, 'sf-cell', a, b, 'middle')

out.append('<svg id="story-fig" viewBox="0 0 480 430" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Two lanes of LSM runs traced over nine steps: leveling re-merges one run per level, tiering stacks T runs and merges them once, and a final panel shows the simulator write amplification for leveling, lazy leveling and tiering.">')

# captions (top line, one range each)
text(20, 26, 'Each flush lands as one sorted run (T = 3)', 'sf-cap', 1, 2)
text(20, 26, 'Leveling: one run per level', 'sf-cap', 2, 7)
text(20, 26, 'Tiering: up to T runs per level', 'sf-cap', 7, 9)
text(20, 26, 'Simulator, T = 10, 3 levels: write amp', 'sf-cap', 9)

# lanes (always visible)
text(20, 100, 'Leveling', 'sf-lab')
text(20, 220, 'Tiering', 'sf-lab')
rect(110, 72, 150, 50, 'f-panel s-line')
rect(290, 72, 170, 50, 'f-panel s-line')
text(110, 66, 'L0', 'sf-id')
text(290, 66, 'L1', 'sf-id')
rect(110, 192, 150, 50, 'f-panel s-line')
rect(290, 192, 170, 50, 'f-panel s-line')
text(110, 186, 'L0', 'sf-id')
text(290, 186, 'L1', 'sf-id')

# leveling: one run on L0 at a time, re-merged on every flush
chip(118, 80, '1', 's-acc', 2, 3)
chip(118, 80, '2', 's-acc', 3, 4)
chip(118, 80, '3', 's-acc', 4, 5)
text(110, 146, 'flush 2 rewrote 1', 'sf-lab', 3, 4)
text(110, 146, 'flush 3 rewrote 2', 'sf-lab', 4, 5)
text(110, 146, 'flush 4 pushed down, rewrote 3', 'sf-lab', 5, 6)
chip(298, 80, '4', 's-acc', 5, 7, hl=5)

# tiering: three runs stack on L0, then merge once into L1
chip(118, 200, '1', 's-ok', 7, 8)
chip(162, 200, '1', 's-ok', 7, 8)
chip(206, 200, '1', 's-ok', 7, 8)
chip(298, 200, '3', 's-ok', 8, 9)
text(110, 262, 'three runs merged once into L1', 'sf-lab', 8, 9)

# bottom status line, one range each
text(20, 412, 'Each arrival merges into the resident run.', 'sf-lab', 2, 7)
text(20, 412, 'Runs wait until T = 3 of them arrive.', 'sf-lab', 7, 8)
text(20, 412, 'Then they merge once into the next level.', 'sf-lab', 8, 9)

# final step: headline numbers over the diagram
out.append('<rect x="20" y="40" width="440" height="352" rx="10" class="f-bg" opacity=".97" data-in="9"/>')
bars = [('17.09×', 'leveling', 17.09, 'f-acc', 95),
        ('8.40×', 'lazy leveling', 8.40, 'f-acc2', 240),
        ('4.00×', 'tiering', 4.00, 'f-ok', 385)]
for val, name, v, cls, cx in bars:
    h = round(v * 8.4, 1)
    top = round(350 - h, 1)
    rect(cx - 32, top, 64, h, cls, 9, None, rx=4, sw=0)
    text(cx, round(top - 8, 1), val, 'sf-num', 9, None, 'middle')
    text(cx, 372, name, 'sf-lab', 9, None, 'middle')

out.append('</svg>')
print('\n'.join(out))
