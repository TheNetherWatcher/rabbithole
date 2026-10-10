# Generates the story scrolly SVG for sections/story.html: python3 story_svg.py, then paste it into .scrolly-fig.
import sys
out = []
def text(x, y, t, cls, a=None, b=None, anchor=None):
    an = f' text-anchor="{anchor}"' if anchor else ''
    rg = (f' data-in="{a}"' if a else '') + (f' data-out="{b}"' if b else '')
    out.append(f'<text x="{x}" y="{y}" class="{cls}"{an}{rg}>{t}</text>')

CW, CH, CG = 48, 36, 8          # ring cell width, height, gap
def cx(i): return 20 + i * (CW + CG)

out.append('<svg id="story-fig" viewBox="0 0 480 430" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Two shared rings between app and kernel. Old aio path, then batched submission, inline completion, poll wait and io-wq fallback, then the cost and the measured gains">')

# captions: top line, one per step, consecutive ranges so they never overlap
text(20, 26, 'One ring pair, shared by app and kernel', 'sf-cap', 1, 2)
text(20, 26, 'Old way: one request, wait, then the next', 'sf-cap', 2, 3)
text(20, 26, 'Why it fails: buffered reads still block', 'sf-cap', 3, 4)
text(20, 26, 'Key idea: queue many, enter once', 'sf-cap', 4, 5)
text(20, 26, 'Cached reads finish inline, with no thread', 'sf-cap', 5, 6)
text(20, 26, 'A socket with no data waits on a poll list', 'sf-cap', 6, 7)
text(20, 26, 'Buffered file reads go to a worker thread', 'sf-cap', 7, 8)
text(20, 26, 'The cost: a syscall filter sees only enter', 'sf-cap', 8, 9)

# base rings (always visible)
text(20, 62, 'SQ: app writes requests', 'sf-lab')
text(20, 142, 'CQ: kernel posts results', 'sf-lab')
for i in range(8):
    out.append(f'<rect x="{cx(i)}" y="70" width="{CW}" height="{CH}" rx="5" class="f-code s-line" stroke-width="1"/>')
    out.append(f'<rect x="{cx(i)}" y="150" width="{CW}" height="{CH}" rx="5" class="f-code s-line" stroke-width="1"/>')

# step 2-3: old way, one aio request in the SQ
out.append(f'<rect x="{cx(0)}" y="70" width="{CW}" height="{CH}" rx="5" class="f-warn" data-in="2" data-out="4"/>')
# step 4-8: eight requests queued, one enter call
for i in range(8):
    out.append(f'<rect x="{cx(i)}" y="70" width="{CW}" height="{CH}" rx="5" class="f-acc" data-in="4" data-out="9"/>')
# step 5-9: inline completion lands in CQ slot 0; step 7-9: io-wq completion in CQ slot 1
out.append(f'<rect x="{cx(0)}" y="150" width="{CW}" height="{CH}" rx="5" class="f-ok" data-in="5" data-out="9"/>')
out.append(f'<rect x="{cx(1)}" y="150" width="{CW}" height="{CH}" rx="5" class="f-ok" data-in="7" data-out="9"/>')
# step 8: the dashed watch line around the ring that a syscall filter cannot read
out.append('<rect x="14" y="64" width="452" height="50" rx="10" class="f-none s-bad" stroke-width="2" stroke-dasharray="6 4" data-in="8" data-out="9"/>')

# kernel band with fixed label, and a badge during step 4
out.append('<rect x="20" y="200" width="440" height="44" rx="8" class="f-panel s-line" stroke-width="1.5"/>')
text(32, 228, 'kernel: try inline, else park or punt', 'sf-lab')
text(330, 228, 'one enter call', 'sf-lab sf-a', 4, 5)

# three outcome boxes, highlighted in turn
boxes = [
    (20, 'Inline', 'cache hit', 5),
    (170, 'Socket', 'no data yet', 6),
    (320, 'File', 'buffered read', 7),
]
for x, head, sub, hl in boxes:
    out.append(f'<rect x="{x}" y="262" width="140" height="76" rx="8" class="f-panel s-line" stroke-width="1.5" data-hl="{hl}"/>')
    text(x + 12, 292, head, 'sf-big')
    text(x + 12, 318, sub, 'sf-lab')

# status line at the bottom, one per step
text(20, 404, 'Requests and results are plain memory writes.', 'sf-lab', 1, 2)
text(20, 404, 'aio: 104 bytes copied, 2+ syscalls per I/O.', 'sf-lab sf-bad', 2, 3)
text(20, 404, 'Buffered reads block, so apps add thread pools.', 'sf-lab sf-bad', 3, 4)
text(20, 404, 'One io_uring_enter submits all eight at once.', 'sf-lab', 4, 5)
text(20, 404, 'Cached read: result posted before enter returns.', 'sf-lab', 5, 6)
text(20, 404, 'No data yet: the request sleeps, no thread does.', 'sf-lab', 6, 7)
text(20, 404, 'Only the slow fallback uses an iou-wrk thread.', 'sf-lab', 7, 8)
text(20, 404, 'seccomp sees io_uring_enter, not OPENAT or READ.', 'sf-lab sf-bad', 8, 9)

# result overlay (step 9)
out.append('<g data-in="9">'
           '<rect x="12" y="38" width="456" height="384" rx="14" class="f-bg" opacity=".97"/>'
           '<text x="240" y="100" class="sf-cap" text-anchor="middle">What the numbers say</text>'
           '<text x="60" y="150" class="sf-lab">buffer manager, naive libaio-to-io_uring swap</text>'
           '<text x="60" y="184" class="sf-num">1.06×</text>'
           '<text x="60" y="224" class="sf-lab">same buffer manager, after redesign</text>'
           '<text x="60" y="258" class="sf-num">2.05×</text>'
           '<text x="60" y="298" class="sf-lab">transactions/s, io_uring vs sync POSIX</text>'
           '<text x="60" y="332" class="sf-num">376K vs 16.5K</text>'
           '<text x="240" y="384" class="sf-big" text-anchor="middle">The gain comes from the redesign, not a swap.</text>'
           '</g>')
out.append('</svg>')
sys.stdout.write('\n'.join(out))
