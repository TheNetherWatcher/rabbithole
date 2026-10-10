# Generates the story scrolly SVG for sections/story.html: python3 story_svg.py > story.svg, then paste it into .scrolly-fig.
import sys
sys.stdout.reconfigure(encoding="utf-8")

CX = [20, 135, 250, 365]          # tile x, 104 wide
RY = [58, 134, 210]               # tile y, 68 tall
TW, TH = 104, 68
GROUP = {(0, 0), (1, 0), (0, 1), (1, 1)}   # the 2x2 group that gets a parent
out = []

def rng(a=None, b=None, hl=None):
    s = ''
    if a: s += f' data-in="{a}"'
    if b: s += f' data-out="{b}"'
    if hl: s += f' data-hl="{hl}"'
    return s

def rect(x, y, w, h, cls, rx=7, sw=1.5, a=None, b=None, extra=''):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" class="{cls}" stroke-width="{sw}"{extra}{rng(a, b)}/>')

def text(x, y, t, cls, a=None, b=None, anchor=None):
    an = f' text-anchor="{anchor}"' if anchor else ''
    out.append(f'<text x="{x}" y="{y}" class="{cls}"{an}{rng(a, b)}>{t}</text>')

out.append('<svg id="story-fig" viewBox="0 0 480 430" xmlns="http://www.w3.org/2000/svg" role="img" '
           'aria-label="Twelve clusters of one mesh. Simplifying each alone leaves cracks at the seams. '
           'Locking a group border lets one parent replace four children, and camera distance picks the cut.">')
out.append('<defs><pattern id="sth" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
           '<line x1="0" y1="0" x2="0" y2="6" class="s-warn" stroke-width="2" opacity=".55"/></pattern></defs>')

# captions: one line at the top, ranges never overlap
text(20, 26, 'One mesh, cut into 128-triangle clusters', 'sf-cap', 1, 2)
text(20, 26, 'Naive: simplify each cluster on its own', 'sf-cap', 2, 3)
text(20, 26, 'Fix: lock the border of each group', 'sf-cap', 3, 4)
text(20, 26, 'Next level: four clusters merge into one parent', 'sf-cap', 4, 5)
text(20, 26, 'Camera at 25 m: the coarse parent is enough', 'sf-cap', 5, 6)
text(20, 26, 'Camera at 12 m: the parent is too coarse', 'sf-cap', 6, 7)
text(20, 26, 'Each cut lines up with its neighbours', 'sf-cap', 7, 8)
text(20, 26, 'Trade-off: dense borders resist simplification', 'sf-cap', 8, 9)
text(20, 26, 'On disk, from Epic’s own example', 'sf-cap', 9)

# base tiles: the 12 clusters; the four in the group leave at step 4
for r in range(3):
    for c in range(4):
        x, y = CX[c], RY[r]
        rect(x, y, TW, TH, 'f-panel s-line', 7, 1.5, None, 4 if (c, r) in GROUP else None)

# step 2: naive seams (cracks in the gaps)
out.append('<path d="M244.5 62 L239 76 L248 90 L241 104 L247 118 L243 124" class="f-none s-bad" stroke-width="2.5" data-in="2" data-out="3"/>')
out.append('<path d="M24 130 L40 126 L56 134 L72 127 L88 133 L104 127 L120 131 L140 130 L160 126 L176 134 L192 127 L208 133 L224 128 L236 130" '
           'class="f-none s-bad" stroke-width="2.5" data-in="2" data-out="3"/>')

# step 3-8: locked border ring around the group
out.append('<rect x="16" y="54" width="227" height="152" rx="10" class="f-none s-ok" stroke-width="2.5" data-in="3" data-out="9"/>')

# step 4-5: the parent (one tile over the group)
rect(20, 58, 219, 144, 'f-panel s-acc', 8, 2.5, 4, 6)
text(30, 84, 'parent', 'sf-lab', 4, 6)

# step 6+: the four children drawn fine again
for (c, r) in sorted(GROUP):
    rect(CX[c], RY[r], TW, TH, 'f-acc s-acc', 7, 2, 6, 9, ' opacity=".35"')
text(30, 84, 'child 0.62 px', 'sf-lab', 6, 9)

# step 8: hatched tiles stand for parts that won't collapse
out.append('<rect x="250" y="210" width="219" height="68" rx="7" fill="url(#sth)" class="s-warn" stroke-width="1.5" data-in="8" data-out="9"/>')

# status line at the bottom, one range per message
text(20, 404, 'Each tile is one cluster of 128 triangles.', 'sf-lab', 1, 2)
text(20, 404, 'Seams no longer match, so cracks open.', 'sf-lab sf-bad', 2, 3)
text(20, 404, 'Shared border vertices never move.', 'sf-lab', 3, 4)
text(20, 404, 'Parent keeps about 50% of the triangles.', 'sf-lab', 4, 5)
text(20, 404, '25 m: parent 0.71 px, under 1 px. Draw it.', 'sf-lab', 5, 6)
text(20, 404, '12 m: parent 1.48 px is over 1. Draw children.', 'sf-lab', 6, 7)
text(20, 404, 'Same vertices on the shared edge: no cracks.', 'sf-lab', 7, 8)
text(20, 404, 'Border vertices: 30–50% of verts at level 1.', 'sf-lab', 8, 9)

# step 9: headline numbers over the diagram
out.append('<g data-in="9"><rect x="12" y="38" width="456" height="384" rx="14" class="f-bg" opacity=".97"/>')
out.append('<text x="50" y="150" class="sf-num">14.4 B</text>')
out.append('<text x="50" y="178" class="sf-lab">average on disk per input triangle (Epic)</text>')
out.append('<text x="50" y="250" class="sf-num">7.6×</text>')
out.append('<text x="50" y="278" class="sf-lab">smaller than a 4-LOD static mesh (Epic’s example)</text>')
out.append('<text x="50" y="350" class="sf-num">≈1 px</text>')
out.append('<text x="50" y="378" class="sf-lab">target projected error per cluster</text></g>')
out.append('</svg>')
sys.stdout.write('\n'.join(out))
