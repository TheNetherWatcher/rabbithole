# Generates the story scrolly SVG for sections/story.html: python3 story_svg.py > story.svg, then paste it into .scrolly-fig.
import sys

OUT = []
STAGES = ['Receive', 'Parse', 'Book', 'Strategy', 'Risk', 'Send']
SX, SY, SW_, SH_, SG = 20, 130, 68, 56, 8  # stage row: x0, y, box width, box height, gap


def rng(a=None, b=None):
    s = ''
    if a is not None:
        s += f' data-in="{a}"'
    if b is not None:
        s += f' data-out="{b}"'
    return s


def rect(x, y, w, h, cls, a=None, b=None, extra=''):
    OUT.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" class="{cls}"{extra}{rng(a, b)}/>')


def text(x, y, t, cls, a=None, b=None, anchor=None):
    an = f' text-anchor="{anchor}"' if anchor else ''
    OUT.append(f'<text x="{x}" y="{y}" class="{cls}"{an}{rng(a, b)}>{t}</text>')


OUT.append('<svg id="story-fig" viewBox="0 0 480 420" xmlns="http://www.w3.org/2000/svg" role="img" '
           'aria-label="A trading hot path kept warm: a cold run is 6.5 times slower at the median, one packet '
           'walks six stages, and a shared cache line costs 23 times more.">')

# captions: one line at the top, one range per caption
text(20, 26, 'Most of the time, the hot path sits idle.', 'sf-cap', 1, 2)
text(20, 26, 'Cold: the path pays for cache misses', 'sf-cap', 2, 3)
text(20, 26, 'Warm: a dummy tick keeps code and data hot', 'sf-cap', 3, 4)
text(20, 26, 'One packet, no syscalls, no allocation', 'sf-cap', 4, 6)
text(20, 26, 'Budget: about 2.5 µs for the whole box', 'sf-cap', 6, 7)
text(20, 26, 'Shared line: false sharing', 'sf-cap', 7, 8)
text(20, 26, 'Speed is worthless without blocking risk gates', 'sf-cap', 8, 9)

# step 1: the duty cycle
rect(20, 140, 440, 24, 'f-code', 1, 2)
rect(20, 140, 2, 24, 'f-acc', 1, 2)
text(240, 200, '0.01%', 'sf-num', 1, 2, 'middle')
text(240, 226, 'of the time the hot path runs', 'sf-lab', 1, 2, 'middle')

# step 2: cold vs warm median, drawn to scale (542 ns and 84 ns)
text(20, 104, 'Cold (after cache trash): p50 542 ns', 'sf-lab', 2, 3)
rect(20, 112, 420, 30, 'f-bad', 2, 3)
text(20, 166, 'Warm (after a warm-up call): p50 84 ns', 'sf-lab', 2, 3)
rect(20, 174, round(420 * 84 / 542, 1), 30, 'f-ok', 2, 3)
text(20, 240, '6.5× slower at the median', 'sf-big', 2, 3)

# steps 3-6: the stage row, lit in two passes
for i, name in enumerate(STAGES):
    x = SX + i * (SW_ + SG)
    rect(x, SY, SW_, SH_, 'f-panel s-line sf-blk', 3, 7, ' rx="7" stroke-width="1.5"')
    text(x + SW_ / 2, SY + 33, name, 'sf-stg', 3, 7, 'middle')
for i in range(3):
    x = SX + i * (SW_ + SG)
    rect(x, SY, SW_, SH_, 'f-acc', 4, 5, ' rx="7" opacity=".45"')
for i in range(3, 6):
    x = SX + i * (SW_ + SG)
    rect(x, SY, SW_, SH_, 'f-acc', 5, 6, ' rx="7" opacity=".45"')
text(20, 215, 'Warm-up tick: same code, dry_run, no order', 'sf-lab', 3, 4)
text(20, 215, 'Receive, parse, then book update in place', 'sf-lab', 4, 5)
text(20, 215, 'Strategy, risk check, then send', 'sf-lab', 5, 6)

# step 6: the budget, drawn to scale (2.5 µs against about 90 µs)
text(20, 262, 'Software budget, wire to wire: about 2.5 µs', 'sf-lab', 6, 7)
rect(20, 270, round(440 * 2.5 / 90, 1), 20, 'f-ok', 6, 7)
text(20, 308, 'One deep core C6 exit: about 90 µs', 'sf-lab', 6, 7)
rect(20, 316, 440, 20, 'f-bad', 6, 7)

# step 7: two counters on one cache line
rect(40, 262, 400, 44, 'f-none s-warn', 7, 8, ' rx="8" stroke-width="2"')
text(60, 289, 'counter A', 'sf-lab', 7, 8)
text(270, 289, 'counter B', 'sf-lab', 7, 8)
text(240, 326, 'each write moves the line to the other core', 'sf-lab', 7, 8, 'middle')
text(240, 358, '23× slower than padded, in our lab', 'sf-big', 7, 8, 'middle')

# step 8: the failure mode that speed does not fix
text(240, 268, '45 minutes', 'sf-num', 8, 9, 'middle')
text(240, 302, 'over $460M lost', 'sf-big sf-bad', 8, 9, 'middle')
text(240, 330, 'One reused flag, on one of eight servers', 'sf-lab', 8, 9, 'middle')

# step 9: headline numbers over the diagram
OUT.append('<g data-in="9">')
rect(12, 38, 456, 370, 'f-bg', None, None, ' rx="14" opacity=".97"')
text(240, 80, 'The whole idea, in four numbers', 'sf-cap', None, None, 'middle')
rows = [
    ('cold vs warm hot path, median', '6.5×'),
    ('two counters on one cache line', '23×'),
    ('reversed vector vs std::map, book', '1.55×'),
    ('software budget, wire to wire', '2.5 µs'),
]
for k, (lab, num) in enumerate(rows):
    y = 134 + k * 58
    text(40, y, lab, 'sf-lab')
    text(440, y + 8, num, 'sf-num', None, None, 'end')
text(240, 388, 'Each number has a card below.', 'sf-big', None, None, 'middle')
OUT.append('</g>')

OUT.append('</svg>')
sys.stdout.write('\n'.join(OUT) + '\n')
