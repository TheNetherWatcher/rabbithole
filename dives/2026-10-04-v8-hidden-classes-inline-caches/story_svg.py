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
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{6 if h < 40 else 8}" class="{cls}"{extra}{rng(a, b, hl)}/>')


def text(x, y, t, cls, a=None, b=None, anchor=None):
    an = f' text-anchor="{anchor}"' if anchor else ''
    out.append(f'<text x="{x}" y="{y}" class="{cls}"{an}{rng(a, b)}>{t}</text>')


def obj(x, mapname, fields, hdr_cls, a=None, b=None, hl_hdr=None, hl_field=None):
    """Object box: outer panel, map header, two field rows."""
    out.append(f'<g{rng(a, b)}>')
    out.append(f'<rect x="{x}" y="56" width="140" height="96" rx="8" class="f-panel s-line" stroke-width="1.5"/>')
    rect(x + 6, 62, 128, 22, hdr_cls, hl=hl_hdr)
    text(x + 12, 78, f'map {mapname}', 'sf-hdr')
    for j, (name, val) in enumerate(fields):
        fy = 90 + j * 28
        rect(x + 6, fy, 128, 22, 'f-code', hl=(hl_field if (hl_field and j == 0) else None))
        text(x + 12, fy + 16, f'{name} = {val}', 'sf-cell')
    out.append('</g>')


out.append('<svg id="story-fig" viewBox="0 0 480 430" xmlns="http://www.w3.org/2000/svg" role="img" '
           'aria-label="One V8 read site o.x over four object shapes: a naive search, then an inline cache that remembers the Map, a deopt to a polymorphic slot, and the headline timings">')

# ---- captions: one line at the top, swapped per step ----
text(20, 26, 'An object is a tag plus its fields.', 'sf-cap', 1, 2)
text(20, 26, 'Naive read: search the keys every time.', 'sf-cap', 2, 3)
text(20, 26, 'Key idea: each read site remembers one Map.', 'sf-cap', 3, 4)
text(20, 26, 'First call misses, then stores the answer.', 'sf-cap', 4, 5)
text(20, 26, 'Next call hits: compare the Map, load.', 'sf-cap', 5, 6)
text(20, 26, 'Hot code bets on M2: one compare, one load.', 'sf-cap', 6, 7)
text(20, 26, 'The bet loses: deopt, then the IC goes poly.', 'sf-cap', 7, 8)
text(20, 26, 'Every extra shape adds a cost. Cap: 4.', 'sf-cap', 8, 9)
text(20, 26, 'Headline numbers, one site, one run.', 'sf-cap', 9)

# ---- objects ----
obj(20, 'M2', [('x', 1), ('y', 2)], 'f-acc', hl_hdr=None, hl_field='2 3')
obj(170, 'M2', [('x', 3), ('y', 4)], 'f-acc', hl_hdr='5 6')
obj(320, 'M3', [('y', 5), ('x', 6)], 'f-acc2', a=7, hl_hdr='7 8')

# ---- step 1 / 2 / 3 / 4 / 5 / 6 / 7 / 8 middle line (y 205) ----
text(20, 205, 'Objects built the same way share M2.', 'sf-lab', 1, 2)
text(20, 205, 'Search: compare key names until x turns up.', 'sf-lab', 2, 3)
text(20, 205, 'Remember: slot 3 keeps the last Map seen.', 'sf-lab', 3, 4)
text(20, 205, 'Miss: look up x once, then store the answer.', 'sf-lab', 4, 5)
text(20, 205, 'Hit: the Map matches, so load +12 at once.', 'sf-lab', 5, 6)
text(20, 205, 'The compiler reads the slot while it builds code.', 'sf-lab', 6, 7)
text(20, 205, 'Object with M3 arrives: CheckMaps fails.', 'sf-lab', 7, 8)
text(20, 205, 'Poly: one compare per Map, at most 4 of them.', 'sf-lab', 8, 9)

# ---- inline cache slot (y 236-296) ----
rect(20, 236, 440, 60, 'f-panel s-line', a=3, b=None, hl='4 5 6 7', extra=' stroke-width="2"')
text(30, 252, 'read site o.x, feedback slot 3', 'sf-sm', 3)
text(30, 284, 'UNINITIALIZED', 'sf-big', 3, 4)
text(30, 284, 'MONO: (M2, field at +12)', 'sf-big', 4, 7)
text(30, 284, 'POLY: [M2, M3]', 'sf-big sf-bad', 7, 8)
text(30, 284, 'MEGA: global stub cache', 'sf-big sf-bad', 8, 9)

# ---- optimized code (y 306-362) ----
rect(20, 306, 440, 56, 'f-code s-line', a=6, b=8)
text(30, 326, 'cmp map, M2     jne deopt', 'sf-code', 6, 7)
text(30, 326, 'deopt: back to Ignition', 'sf-code sf-bad', 7, 8)
text(30, 348, 'mov r, [o+12]', 'sf-code', 6, 8)

# ---- bottom status lines (y 372, 400) ----
text(20, 372, 'Each object carries its Map, a layout tag.', 'sf-lab', 1, 2)
text(20, 400, 'Objects built the same way share one Map.', 'sf-lab', 1, 2)
text(20, 372, 'Search costs several dependent loads.', 'sf-lab', 2, 3)
text(20, 400, 'Tens of nanoseconds per access, every object.', 'sf-lab', 2, 3)
text(20, 372, 'The read site keeps one slot for its last Map.', 'sf-lab', 3, 4)
text(20, 400, 'Empty at first: UNINITIALIZED.', 'sf-lab', 3, 4)
text(20, 372, 'The slot now holds M2 and the offset of x.', 'sf-lab', 4, 5)
text(20, 400, 'The next read with M2 skips the search.', 'sf-lab', 4, 5)
text(20, 372, 'One compare, one load, no descriptor lookup.', 'sf-lab', 5, 6)
text(20, 400, 'Same Map, same fixed offset, every time.', 'sf-lab', 5, 6)
text(20, 372, 'Optimized code: one compare, one load.', 'sf-lab', 6, 7)
text(20, 400, 'It also depends on M2 staying stable.', 'sf-lab', 6, 7)
text(20, 372, 'The IC keeps M2 and adds M3. Now POLY.', 'sf-lab', 7, 8)
text(20, 400, 'Two checks, still no search. Never goes back.', 'sf-lab', 7, 8)
text(20, 372, 'Past 4 Maps the site uses a global stub cache.', 'sf-lab', 8, 9)
text(20, 400, 'In my run: 4.06 ns at 4 shapes, 4.90 at 8.', 'sf-lab', 8, 9)

# ---- step 9: headline numbers over the diagram ----
out.append('<g data-in="9">'
           '<rect x="12" y="38" width="456" height="384" rx="14" class="f-bg" opacity=".97"/>'
           '<text x="240" y="82" class="sf-cap" text-anchor="middle">One read site, ns per read (one run)</text>'
           # row 1: mono
           '<text x="60" y="130" class="sf-lab">1 shape (mono)</text>'
           '<text x="420" y="130" class="sf-big" text-anchor="end">0.99 ns</text>'
           '<rect x="60" y="136" width="360" height="22" rx="6" class="f-code s-line"/>'
           '<rect x="60" y="136" width="73" height="22" rx="6" class="f-ok"/>'
           # row 2: poly
           '<text x="60" y="192" class="sf-lab">4 shapes (poly)</text>'
           '<text x="420" y="192" class="sf-big" text-anchor="end">4.06 ns</text>'
           '<rect x="60" y="198" width="360" height="22" rx="6" class="f-code s-line"/>'
           '<rect x="60" y="198" width="298" height="22" rx="6" class="f-warn"/>'
           # row 3: mega
           '<text x="60" y="254" class="sf-lab">8 shapes (mega)</text>'
           '<text x="420" y="254" class="sf-big" text-anchor="end">4.90 ns</text>'
           '<rect x="60" y="260" width="360" height="22" rx="6" class="f-code s-line"/>'
           '<rect x="60" y="260" width="360" height="22" rx="6" class="f-bad"/>'
           '<text x="240" y="332" class="sf-num" text-anchor="middle">4.1× slower at 4 shapes</text>'
           '<text x="240" y="362" class="sf-lab" text-anchor="middle">Self: a point took 10 words without maps, 3 with.</text>'
           '<text x="240" y="390" class="sf-lab" text-anchor="middle">Mega costs about the same at 8 and 64 shapes.</text>'
           '</g>')

out.append('</svg>')
sys.stdout.write('\n'.join(out))
