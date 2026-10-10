# Generates the story scrolly SVG for sections/story.html: python3 story_svg.py > story.svg, then paste it into .scrolly-fig.
import sys
out = []
def rng(a=None, b=None, hl=None):
    s = ''
    if a: s += f' data-in="{a}"'
    if b: s += f' data-out="{b}"'
    if hl: s += f' data-hl="{hl}"'
    return s
def rect(x, y, w, h, cls, a=None, b=None, extra='', rx=4):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" class="{cls}"{extra}{rng(a,b)}/>')
def text(x, y, t, cls, a=None, b=None, anchor=None):
    an = f' text-anchor="{anchor}"' if anchor else ''
    out.append(f'<text x="{x}" y="{y}" class="{cls}"{an}{rng(a,b)}>{t}</text>')

# grid of 8 x 8 cells (the picture as tokens); origin and pitch
GX, GY, P, S = 30, 70, 26, 22
GW = 7 * P + S  # 204
def cell(i):
    return GX + (i % 8) * P, GY + (i // 8) * P

out.append('<svg id="story-fig" viewBox="0 0 480 430" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="One denoiser step: a noisy grid of tiles becomes a grid of latent patch tokens, text tokens join, 19 double-stream and 38 single-stream blocks run, the output drives an Euler step repeated 28 to 50 times, and attention takes over the layer cost at video length">')
out.append('<defs><pattern id="sth" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" class="s-warn" stroke-width="2" opacity=".55"/></pattern></defs>')

# captions (top line, one per step, same spot)
text(20, 26, 'One denoiser call on a noisy grid', 'sf-cap', 1, 2)
text(20, 26, 'Naive: treat every pixel as a token', 'sf-cap', 2, 3)
text(20, 26, 'Latent space, then 2×2 patches', 'sf-cap', 3, 4)
text(20, 26, 'Text joins the same sequence', 'sf-cap', 4, 5)
text(20, 26, 'Double-stream: two lanes, one attention', 'sf-cap', 5, 6)
text(20, 26, 'Single-stream: one merged lane', 'sf-cap', 6, 7)
text(20, 26, 'The output drives a loop', 'sf-cap', 7, 8)
text(20, 26, 'The catch: attention grows fastest', 'sf-cap', 8, 9)
text(20, 26, 'The headline numbers', 'sf-cap', 9)

# step 1-2: noisy grid (static), hatched in step 2 as "too many tokens"
for i in range(64):
    x, y = cell(i)
    op = 0.25 + 0.5 * ((i * 37) % 7) / 6
    out.append(f'<rect x="{x}" y="{y}" width="{S}" height="{S}" rx="3" class="f-mute" opacity="{op:.2f}"{rng(1,3)}/>')
rect(GX - 2, GY - 2, GW + 4, GW + 4, 'sf-hatch', 2, 3, ' fill="url(#sth)"', rx=6)

# step 3+: latent patches become tokens
for i in range(64):
    x, y = cell(i)
    out.append(f'<rect x="{x}" y="{y}" width="{S}" height="{S}" rx="3" class="f-acc" opacity="{0.45 + 0.4 * ((i * 11) % 5) / 4:.2f}"{rng(3,10)}/>')
# loop outline (steps 7-8)
out.append(f'<rect x="{GX-8}" y="{GY-8}" width="{GW+16}" height="{GW+26}" rx="10" class="f-none s-ok" stroke-width="2" stroke-dasharray="6 4"{rng(7,9)}/>')
text(GX, GY + GW + 28, 'repeat 28–50 times', 'sf-lab sf-ok', 7, 9)

# step 4: text tokens
rect(262, 76, 190, 40, 'f-acc2', 4, 6, ' stroke-width="0"')
text(272, 101, '512 text tokens', 'sf-lab', 4, 6)

# step 5: double-stream lanes with shared attention
rect(262, 76, 190, 26, 'f-acc s-acc', 5, 6, ' stroke-width="1.5"', rx=6)
text(272, 93, 'image lane', 'sf-lab', 5, 6)
rect(262, 110, 190, 26, 'f-acc2 s-acc2', 5, 6, ' stroke-width="1.5"', rx=6)
text(272, 127, 'text lane', 'sf-lab', 5, 6)
rect(262, 150, 190, 22, 'f-warn', 5, 6, ' data-hl="5"', rx=6)
text(272, 165, 'shared attention', 'sf-lab', 5, 6)

# step 6+: single merged lane
rect(262, 76, 190, 96, 'f-ok s-ok', 6, 8, ' stroke-width="2" data-hl="6 7"', rx=8)
text(272, 128, 'one set of weights', 'sf-lab', 6, 8)

# step 8: attention share bars
text(262, 86, 'Attention share of one layer', 'sf-lab', 8, 9)
rect(262, 118, 190, 16, 'f-code', 8, 9, '', rx=4)
rect(262, 118, round(190 * 0.20, 1), 16, 'f-acc', 8, 9, '', rx=4)
text(262, 112, '1024² image: 20%', 'sf-lab', 8, 9)
rect(262, 166, 190, 16, 'f-code', 8, 9, '', rx=4)
rect(262, 166, round(190 * 0.87, 1), 16, 'f-bad', 8, 9, '', rx=4)
text(262, 160, '720p video: 87%', 'sf-lab', 8, 9)

# status lines (bottom), two per step, distinct spots
text(20, 318, 'Start: static. The grid is noise.', 'sf-lab', 1, 2)
text(20, 318, 'Attention over every pixel at 256²:', 'sf-lab', 2, 3)
text(20, 344, '65,536 tokens. ADM costs 1120 GFLOPs.', 'sf-lab sf-bad', 2, 3)
text(20, 318, 'Latent 16×128×128, cut into patches.', 'sf-lab', 3, 4)
text(20, 344, 'A 1024² image is 4,096 tokens.', 'sf-lab', 3, 4)
text(20, 318, '4,096 image + 512 text = 4,608 tokens.', 'sf-lab', 4, 5)
text(20, 318, '19 double-stream blocks.', 'sf-lab', 5, 6)
text(20, 344, 'Separate weights, one shared attention.', 'sf-lab', 5, 6)
text(20, 318, '38 single-stream blocks.', 'sf-lab', 6, 7)
text(20, 344, 'One sequence, one set of weights.', 'sf-lab', 6, 7)
text(20, 318, 'Output: a velocity. One small Euler step.', 'sf-lab', 7, 8)
text(20, 344, 'The static moves towards a picture.', 'sf-lab', 7, 8)
text(20, 318, 'Attention cost grows with tokens squared.', 'sf-lab', 8, 9)
text(20, 344, 'Past T = 6d, attention takes over.', 'sf-lab sf-bad', 8, 9)

# step 9: headline overlay
out.append('<g data-in="9"><rect x="12" y="38" width="456" height="384" rx="14" class="f-bg" opacity=".97"/>'
           '<text x="60" y="120" class="sf-num">−0.93</text>'
           '<text x="60" y="144" class="sf-lab">correlation of DiT Gflops with FID</text>'
           '<text x="60" y="214" class="sf-num">1120 → 118.6</text>'
           '<text x="60" y="238" class="sf-lab">Gflops: pixel U-Net ADM vs latent DiT-XL/2</text>'
           '<text x="60" y="308" class="sf-num">12B</text>'
           '<text x="60" y="332" class="sf-lab">parameters in FLUX.1</text></g>')
out.append('</svg>')
sys.stdout.write('\n'.join(out))
