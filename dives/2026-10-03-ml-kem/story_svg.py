# Generates the story scrolly SVG for sections/story.html: python3 story_svg.py > story.svg, then paste it into .scrolly-fig.
import sys
Q = 3329                      # ticks on the dial
X0, X1, TY = 40, 440, 220     # dial spans x 40..440 at y 220
K = (X1 - X0) / Q
out = []
def tx(t): return round(X0 + t * K, 1)
def attrs(a=None, b=None, hl=None):
    s = ''
    if a: s += f' data-in="{a}"'
    if b: s += f' data-out="{b}"'
    if hl: s += f' data-hl="{hl}"'
    return s
def text(x, y, t, cls, a=None, b=None, anchor=None):
    an = f' text-anchor="{anchor}"' if anchor else ''
    out.append(f'<text x="{x}" y="{y}" class="{cls}"{an}{attrs(a, b)}>{t}</text>')

out.append('<svg id="story-fig" viewBox="0 0 480 430" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="A clock-hand dial of 3329 ticks: a bit is hidden under smudge, the receiver removes most of it, the leftover stays far from the 832-tick edge, and a tampered box returns a pseudorandom key">')

# ---- base: the dial and the hand for bit 1 ----
out.append(f'<line x1="{X0}" y1="{TY}" x2="{X1}" y2="{TY}" class="s-line" stroke-width="4" stroke-linecap="round"/>')
text(X0, 246, '0', 'sf-lab', anchor='middle')
text(tx(1665), 246, '1665', 'sf-lab', anchor='middle')
text(X1, 246, '3329', 'sf-lab', anchor='middle')
text(tx(1665), 180, 'bit 1 hand', 'sf-lab', anchor='middle')
out.append(f'<circle cx="{tx(1665)}" cy="{TY}" r="9" class="f-acc" data-hl="1 2" stroke-width="3"/>')

# ---- step 3-4: smudge, then the receiver removes it ----
out.append(f'<rect x="{tx(1665-300)}" y="200" width="{round(600*K,1)}" height="40" rx="6" class="f-warn" opacity=".35"{attrs(3, 4)}/>')
# leftover after cleanup: sigma about 76 ticks
out.append(f'<rect x="{tx(1665-76)}" y="200" width="{round(152*K,1)}" height="40" rx="6" class="f-ok" opacity=".55"{attrs(4, 8)}/>')

# ---- step 5: the mistake edges at 832 and 2497 ----
for t in (832, 2497):
    out.append(f'<line x1="{tx(t)}" y1="178" x2="{tx(t)}" y2="262" class="s-bad" stroke-width="2" stroke-dasharray="5 4"{attrs(5, 8, "5 6")}/>')

# ---- step 6: 16 rounding levels for v ----
for k in range(16):
    x = tx(k * Q / 16)
    out.append(f'<line x1="{x}" y1="256" x2="{x}" y2="266" class="s-warn" stroke-width="2"{attrs(6, 8)}/>')
text(240, 286, '16 levels after rounding v to 4 bits', 'sf-lab', 6, 8, 'middle')

# ---- step 7: tampered box and its output key ----
out.append(f'<rect x="40" y="300" width="170" height="44" rx="7" class="f-panel s-line" stroke-width="1.5"{attrs(7, 8)}/>')
text(52, 328, 'c, one bit flipped', 'sf-lab', 7, 8)
out.append(f'<line x1="216" y1="322" x2="262" y2="322" class="s-acc" stroke-width="2"{attrs(7, 8)}/>')
out.append(f'<rect x="270" y="300" width="170" height="44" rx="7" class="f-panel s-acc" stroke-width="1.5"{attrs(7, 8)}/>')
text(282, 328, 'output: f595db36…', 'sf-lab', 7, 8)

# ---- captions (top) and status lines (bottom), ranges never overlap at the same x/y ----
text(20, 26, 'One bit, one hand on a 3,329-tick dial', 'sf-cap', 1, 3)
text(20, 26, 'Random smudge hides the hand', 'sf-cap', 3, 5)
text(20, 26, 'The mistake edge: 832 ticks away', 'sf-cap', 5, 6)
text(20, 26, 'Rounding v: the largest noise term', 'sf-cap', 6, 7)
text(20, 26, 'A tampered box: no error raised', 'sf-cap', 7, 8)

text(20, 380, 'The bit-1 hand sits at 6 o’clock, tick 1665.', 'sf-lab', 1, 2)
text(20, 380, 'With no noise, Gaussian elimination solves it.', 'sf-lab', 2, 3)
text(20, 404, 'Gaussian elimination recovers the key from it.', 'sf-lab', 2, 3)
text(20, 380, 'Smudge of a few hundred ticks hides the hand.', 'sf-lab', 3, 4)
text(20, 404, 'An eavesdropper sees only the smudge.', 'sf-lab', 3, 4)
text(20, 380, 'The receiver removes the big term and most smudge.', 'sf-lab', 4, 5)
text(20, 404, 'Leftover noise: σ ≈ 76 ticks.', 'sf-lab', 4, 5)
text(20, 380, 'The mistake edge is 832 ticks from the hand.', 'sf-lab', 5, 6)
text(20, 404, '76 of noise against 832 of room. Errors are rare.', 'sf-lab', 5, 6)
text(20, 380, 'Rounding v to 4 bits adds the most noise.', 'sf-lab', 6, 7)
text(20, 404, 'Its 16 levels add up to ±104 per coefficient.', 'sf-lab', 6, 7)
text(20, 380, 'A tampered box returns a key that looks random.', 'sf-lab', 7, 8)
text(20, 404, 'No error is raised, so there is no reject signal.', 'sf-lab', 7, 8)

# ---- step 8: headline numbers over the diagram ----
out.append(f'<rect x="10" y="10" width="460" height="410" rx="14" class="f-bg" opacity=".97"{attrs(8)}/>')
text(20, 26, 'Three numbers that matter', 'sf-cap', 8)
text(240, 120, '2<tspan dy="-9" font-size="15">-164.8</tspan>', 'sf-num', 8, anchor='middle')
text(240, 146, 'decryption failure rate, ML-KEM-768', 'sf-lab', 8, anchor='middle')
text(240, 218, '1184 B', 'sf-num', 8, anchor='middle')
text(240, 244, 'public key, ML-KEM-768', 'sf-lab', 8, anchor='middle')
text(240, 316, '±76 ticks', 'sf-num', 8, anchor='middle')
text(240, 342, 'leftover noise, against an edge at 832', 'sf-lab', 8, anchor='middle')

out.append('</svg>')
sys.stdout.write('\n'.join(out))
