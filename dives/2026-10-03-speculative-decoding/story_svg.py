# Generates the story scrolly SVG for sections/story.html: python3 story_svg.py > story.svg, then paste it into .scrolly-fig.
import sys

out = []


def rng(a=None, b=None, hl=None):
    s = ''
    if a: s += f' data-in="{a}"'
    if b: s += f' data-out="{b}"'
    if hl: s += f' data-hl="{hl}"'
    return s


def rect(x, y, w, h, cls, a=None, b=None, hl=None, extra=''):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" class="{cls}"{extra}{rng(a, b, hl)}/>')


def text(x, y, t, cls, a=None, b=None, anchor=None):
    an = f' text-anchor="{anchor}"' if anchor else ''
    out.append(f'<text x="{x}" y="{y}" class="{cls}"{an}{rng(a, b)}>{t}</text>')


def word(x, y, w, h, t, cls, a=None, b=None, box_cls='f-acc2'):
    """A token box with its label centred in it."""
    rect(x, y, w, h, box_cls, a, b)
    text(x + w / 2, y + h / 2 + 5, t, cls, a, b, 'middle')


out.append('<svg id="story-fig" viewBox="0 0 480 430" xmlns="http://www.w3.org/2000/svg" role="img" '
           'aria-label="A target model writes one token per pass. A drafter guesses three tokens, the target checks them in one pass, keeps the first match, resamples one, and at high batch the gain falls to 1.01x.">')

# ---- captions: one per phase, same spot, disjoint ranges ----
text(20, 26, 'Plain decoding: one pass per token', 'sf-cap', 1, 3)
text(20, 26, 'Speculative: guess 3, then check in one pass', 'sf-cap', 3, 5)
text(20, 26, 'Keep the matches, resample at the first miss', 'sf-cap', 5, 8)
text(20, 26, 'Batch grows, and the spare compute runs out', 'sf-cap', 8, 9)

# ---- prefix row (always visible) and the accepted continuation ----
for i, w_ in enumerate(['The', 'cat', 'sat', 'on', 'the']):
    word(20 + i * 50, 50, 44, 30, w_, 'sf-cell', box_cls='f-panel s-line')
word(270, 50, 44, 30, 'mat', 'sf-cell', 7, None, box_cls='f-ok')
word(320, 50, 44, 30, '.', 'sf-cell', 7, None, box_cls='f-ok')

# ---- target model (always visible) ----
rect(20, 150, 440, 44, 'f-panel s-line', hl=None, extra=' stroke-width="1.5"')
out[-1] = out[-1].replace('/>', ' data-hl="4"/>')
text(32, 177, 'Target model: big, slow, exact', 'sf-lab')

# ---- steps 1-2: one pass per token ----
for i in range(3):
    rect(20 + i * 151, 214, 138, 28, 'f-panel s-line', 2, 3)
    text(20 + i * 151 + 69, 233, f'pass {i + 1}: 1 token', 'sf-lab', 2, 3, 'middle')

# ---- steps 3-7: drafter guesses, target checks ----
text(20, 120, 'drafter guesses', 'sf-lab', 3, 7)
text(20, 120, 'one target pass gave 2 tokens', 'sf-lab sf-ok', 7, 9)
word(288, 100, 58, 30, 'mat', 'sf-cell', 3, 5, box_cls='f-acc2')
word(350, 100, 58, 30, 'and', 'sf-cell', 3, 5, box_cls='f-acc2')
word(412, 100, 58, 30, 'purred', 'sf-cell', 3, 5, box_cls='f-acc2')
# step 5: 'mat' kept, 'and' rejected, 'purred' dropped with it
word(288, 100, 58, 30, 'mat', 'sf-cell', 5, 9, box_cls='f-ok')
word(350, 100, 58, 30, 'and', 'sf-cell', 5, 6, box_cls='f-bad')
word(412, 100, 58, 30, 'purred', 'sf-mute', 5, 9, box_cls='f-none s-mute')
# step 6+: the resampled token replaces 'and'
word(350, 100, 58, 30, '.', 'sf-cell', 6, 9, box_cls='f-warn')

# ---- step 8: the gain at two batch sizes ----
text(20, 226, 'batch 2', 'sf-lab', 8, 9)
rect(100, 212, 175, 20, 'f-ok', 8, 9)
text(282, 228, '1.75×', 'sf-lab', 8, 9)
text(20, 266, 'batch 56', 'sf-lab', 8, 9)
rect(100, 252, 101, 20, 'f-warn', 8, 9)
text(208, 268, '1.01×', 'sf-lab', 8, 9)

# ---- status line at the bottom: one per step ----
status = [
    (1, 'Chinchilla 70B on 16 TPU v4: 14.1 ms per token.'),
    (2, 'Tokens come one after another, one pass each.'),
    (3, 'A small drafter writes 3 guesses, cheaply.'),
    (4, 'The target scores all 3 positions in one pass.'),
    (5, "'mat' is kept. 'and' is rejected, so 'purred' goes."),
    (6, "'and' is replaced from the leftover mass."),
    (7, 'Two new tokens for one target pass.'),
    (8, "At batch 56, EAGLE-3's gain falls to 1.01×."),
]
for s, t in status:
    text(20, 400, t, 'sf-lab', s, s + 1)

# ---- step 9: headline numbers over the diagram (overlay last, so it sits on top) ----
out.append('<g data-in="9">'
           '<rect x="12" y="38" width="456" height="384" rx="14" class="f-bg" opacity=".97"/>'
           '<text x="240" y="100" class="sf-cap" text-anchor="middle">Speedup from speculative decoding</text>'
           '<text x="60" y="150" class="sf-lab">Google, T5-XXL 11B, 60M drafter</text>'
           '<text x="420" y="152" class="sf-num" text-anchor="end">~3×</text>'
           '<text x="60" y="194" class="sf-lab">EAGLE-3, 8B, batch 2</text>'
           '<text x="420" y="196" class="sf-num" text-anchor="end">1.75×</text>'
           '<text x="60" y="238" class="sf-lab">EAGLE-3, 8B, batch 56</text>'
           '<text x="420" y="240" class="sf-num" text-anchor="end">1.01×</text>'
           '<text x="240" y="308" class="sf-big" text-anchor="middle">Same output distribution, in exact arithmetic</text>'
           '<text x="240" y="346" class="sf-lab" text-anchor="middle">The cards below cover the proof, the knobs and the failure cases.</text>'
           '</g>')
out.append('</svg>')
sys.stdout.write('\n'.join(out))
