# Generates the story scrolly SVG for sections/story.html: python3 story_svg.py > story.svg, then paste it into .scrolly-fig.
import sys
X0, Y0, BW, BH, GX, GY = 20, 46, 104, 50, 8, 10
SW, SH = 22, 22
out = []
def bx(i): return X0 + (i % 4) * (BW + GX)
def by(i): return Y0 + (i // 4) * (BH + GY)
def rng(a=None, b=None, hl=None):
    s = ''
    if a: s += f' data-in="{a}"'
    if b: s += f' data-out="{b}"'
    if hl: s += f' data-hl="{hl}"'
    return s
def slot(i, k): return bx(i) + 6 + k * (SW + 2.5), by(i) + 22
def fill(i, ks, cls, a=None, b=None):
    for k in ks:
        x, y = slot(i, k)
        out.append(f'<rect x="{x:.1f}" y="{y}" width="{SW}" height="{SH}" rx="3" class="{cls}"{rng(a,b)}/>')
def hatch(i, ks, a=None, b=None):
    for k in ks:
        x, y = slot(i, k)
        out.append(f'<rect x="{x:.1f}" y="{y}" width="{SW}" height="{SH}" rx="3" fill="url(#sth)" class="s-warn" stroke-width="1"{rng(a,b)}/>')
def text(x, y, t, cls, a=None, b=None, anchor=None):
    an = f' text-anchor="{anchor}"' if anchor else ''
    out.append(f'<text x="{x}" y="{y}" class="{cls}"{an}{rng(a,b)}>{t}</text>')

out.append('<svg id="story-fig" viewBox="0 0 480 430" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="A GPU KV pool of 16 blocks, filled first by contiguous reservation and then by paging">')
out.append('<defs><pattern id="sth" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" class="s-warn" stroke-width="2" opacity=".55"/></pattern></defs>')
# captions per phase
text(20, 26, 'GPU KV memory: 16 blocks × 4 token slots', 'sf-cap', 1, 2)
text(20, 26, 'Contiguous: one max-length slab per request', 'sf-cap', 2, 4)
text(20, 26, 'Paged: any free block, tracked by a table', 'sf-cap', 4, 10)
# base grid
for i in range(16):
    x, y = bx(i), by(i)
    out.append(f'<rect x="{x}" y="{y}" width="{BW}" height="{BH}" rx="7" class="f-panel s-line sf-blk" stroke-width="1.5"' +
               (rng(hl={3:'5',10:'8',14:'8',7:'6'}[i]) if i in (3,10,14,7) else '') + '/>')
    text(x + 6, y + 15, f'#{i}', 'sf-id')
    for k in range(4):
        sx, sy = slot(i, k)
        out.append(f'<rect x="{sx:.1f}" y="{sy}" width="{SW}" height="{SH}" rx="3" class="f-code"/>')

# ---- contiguous (steps 2-3) ----
fill(0, range(4), 'f-acc', 2, 4); fill(1, range(3), 'f-acc', 2, 4)
hatch(1, [3], 2, 4)
for i in range(2, 8): hatch(i, range(4), 2, 4)
out.append(f'<rect x="{X0-4}" y="{Y0-4}" width="{4*BW+3*GX+8}" height="{2*BH+GY+8}" rx="10" class="f-none s-acc" stroke-width="2.5"{rng(2,4)}/>')
text(20, 318, 'A’s slab: 7 tokens used, 25 slots reserved', 'sf-big sf-a', 2, 4)
# C slab 11-13
fill(11, range(4), 'f-mute', 3, 4); fill(12, range(3), 'f-mute', 3, 4); hatch(12, [3], 3, 4); hatch(13, range(4), 3, 4)
out.append(f'<rect x="{bx(11)-4}" y="{by(11)-4}" width="{BW+8}" height="{BH+8}" rx="10" class="f-none s-mute" stroke-width="2"{rng(3,4)}/>')
out.append(f'<rect x="{bx(12)-4}" y="{by(12)-4}" width="{2*BW+GX+8}" height="{BH+8}" rx="10" class="f-none s-mute" stroke-width="2"{rng(3,4)}/>')
for (i, n) in ((8, 3), (14, 2)):
    out.append(f'<rect x="{bx(i)-3}" y="{by(i)-3}" width="{n*BW+(n-1)*GX+6}" height="{BH+6}" rx="9" class="f-none s-ok" stroke-width="2" stroke-dasharray="6 4"{rng(3,4)}/>')
text(20, 348, 'B needs 4 adjacent blocks. 5 are free,', 'sf-lab', 3, 4)
text(20, 372, 'but the largest gap is only 3.', 'sf-lab', 3, 4)
text(20, 400, 'B waits, though memory is free.', 'sf-big sf-bad', 3, 4)

# ---- paged (steps 4+) ----
A, Bc, D, E = 'f-acc', 'f-acc2', 'f-ok', 'f-warn'
fill(7, range(4), A, 4); fill(1, range(3), A, 4)
fill(1, [3], A, 5); fill(3, [0], A, 5)
fill(3, [1, 2, 3], A, 7)
fill(10, [0], A, 8)
# B shares #7, owns 10 and 14 (steps 6-7)
fill(10, range(4), Bc, 6, 8); fill(14, [0], Bc, 6, 8)
out.append(f'<g{rng(6,8)}><rect x="{bx(7)+BW-34}" y="{by(7)+4}" width="30" height="16" rx="8" class="f-acc2"/><text x="{bx(7)+BW-19}" y="{by(7)+16}" class="sf-badge" text-anchor="middle">×2</text></g>')
# D and E fill the rest at step 7
for i in (0, 2, 4, 5): fill(i, range(4), D, 7)
fill(6, [0, 1], D, 7)
for i in (8, 9, 11, 12, 13): fill(i, range(4), E, 7)
fill(15, [0], E, 7)
# preempted ghost on 14 at step 8
out.append(f'<rect x="{bx(14)+2}" y="{by(14)+2}" width="{BW-4}" height="{BH-4}" rx="6" class="f-none s-bad" stroke-width="2" stroke-dasharray="5 4"{rng(8,10)}/>')
text(bx(14) + BW - 6, by(14) + 15, 'freed', 'sf-lab sf-bad', 8, 10, 'end')

# ---- block tables ----
def table(row_y, label, cells, cls, lab_cls):
    text(20, row_y + 21, label, 'sf-lab ' + lab_cls, cells[0][1], cells[0][2])
    for j, (v, a, b) in enumerate(cells):
        x = 104 + j * 50
        out.append(f'<g{rng(a,b)}><rect x="{x}" y="{row_y}" width="44" height="30" rx="6" class="f-panel {cls}" stroke-width="2"/>'
                   f'<text x="{x+22}" y="{row_y+20}" class="sf-cell" text-anchor="middle">{v}</text></g>')
table(300, 'A’s table', [('7', 4, None), ('1', 4, None), ('3', 5, None), ('10', 8, None)], 's-acc', 'sf-a')
table(342, 'B’s table', [('7', 6, 8), ('10', 6, 8), ('14', 6, 8)], 's-acc2', 'sf-b')
text(20, 363, 'B: preempted whole, recomputed later', 'sf-lab sf-bad', 8, 9)
text(20, 400, 'Waste: at most one part-filled block per request', 'sf-lab', 5, 6)
text(20, 400, 'Block #7 computed once, read by both', 'sf-lab', 6, 7)
text(20, 400, 'Pool full. A has filled #3 and needs one more block.', 'sf-lab sf-bad', 7, 8)
text(20, 400, 'Newest request (B) evicted; A takes #10', 'sf-lab', 8, 9)

# ---- result overlay (step 9) ----
out.append(f'<g{rng(9)}><rect x="12" y="38" width="456" height="384" rx="14" class="f-bg" opacity=".97"/>'
           '<text x="240" y="110" class="sf-cap" text-anchor="middle">Share of KV memory holding real tokens</text>'
           '<rect x="60" y="140" width="360" height="34" rx="8" class="f-code s-line"/><rect x="60" y="140" width="104" height="34" rx="8" class="f-warn"/>'
           '<text x="60" y="198" class="sf-lab">contiguous (Orca)</text><text x="420" y="198" class="sf-num" text-anchor="end">20–38%</text>'
           '<rect x="60" y="230" width="360" height="34" rx="8" class="f-code s-line"/><rect x="60" y="230" width="347" height="34" rx="8" class="f-ok"/>'
           '<text x="60" y="288" class="sf-lab">paged (vLLM)</text><text x="420" y="288" class="sf-num" text-anchor="end">96.3%</text>'
           '<text x="240" y="352" class="sf-big" text-anchor="middle">→ 2–4× more throughput, same GPU</text></g>')
out.append('</svg>')
sys.stdout.write('\n'.join(out))
