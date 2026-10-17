"""Generates sections/story.html: the scroll story's sticky SVG (4 groups x 8 slots) plus its 7 steps."""
TAGS = [
    ["3F", "--", "5A", "B2", "5A", "--", "91", "C7"],
    ["22", "7D", "E0", "14", "8B", "A6", "3C", "F1"],
    ["0D", "--", "66", "--", "9E", "41", "--", "D3"],
    ["58", "2A", "--", "B7", "--", "6C", "19", "--"],
]
X0, CW, CH, GAP = 64, 47, 36, 5
def y(g): return 62 + g * 66
def cell(g, i):
    return X0 + i * CW, y(g)

o = []
o.append('''<style>
#story-fig .sf-cap{fill:var(--ink);font:700 17px var(--serif)}
#story-fig .sf-id{fill:var(--mute);font:600 12px var(--mono)}
#story-fig .sf-lab{fill:var(--ink);font:15px system-ui,sans-serif}
#story-fig .sf-big{fill:var(--ink);font:700 16px system-ui,sans-serif}
#story-fig .sf-tag{fill:var(--ink);font:700 14px var(--mono)}
#story-fig .sf-mask{fill:var(--accent);font:700 14px var(--mono)}
#story-fig .sf-num{fill:var(--ink);font:700 26px var(--serif)}
#story-fig .sf-node{fill:var(--panel);stroke:var(--line);stroke-width:1.5}
</style>
<div class="scrolly">
<div class="scrolly-fig"><svg id="story-fig" viewBox="0 0 480 430" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Four groups of eight hash-table slots with a tag byte per slot, probed by comparing a whole group at once">''')
caps = [
    (1, 2, "Chaining: every lookup chases pointers"),
    (2, 3, "Open addressing: items live in the slots"),
    (3, 4, "Add a 1-byte tag to every slot"),
    (4, 5, "Compare a whole group in one instruction"),
    (5, 6, "A full group sends the probe onward"),
    (6, 7, "Erase: tombstone only if a probe passed here"),
    (7, 8, "Swiss table, in four numbers"),
]
for a, b, t in caps:
    o.append(f'<text x="20" y="28" class="sf-cap" data-in="{a}" data-out="{b}">{t}</text>')
# step 1: chain picture
o.append('<g data-in="1" data-out="2">')
for k in range(4):
    yy = 62 + k * 62
    o.append(f'<rect x="30" y="{yy}" width="46" height="34" rx="5" class="sf-node"/><text x="40" y="{yy+22}" class="sf-id">b{k}</text>')
chains = [2, 1, 3, 1]
for k, n in enumerate(chains):
    yy = 62 + k * 62
    for j in range(n):
        x = 130 + j * 110
        o.append(f'<line x1="{x-52 if j else 76}" y1="{yy+17}" x2="{x}" y2="{yy+17}" class="s-acc2" stroke-width="2"/>')
        o.append(f'<rect x="{x}" y="{yy}" width="70" height="34" rx="5" class="sf-node"/><text x="{x+8}" y="{yy+22}" class="sf-id">key+val</text>')
o.append('<text x="30" y="330" class="sf-lab">Each hop is a pointer: a likely cache miss.</text>')
o.append('<text x="30" y="352" class="sf-lab">8 bytes of pointer per entry, plus a heap node.</text>')
o.append('</g>')
# grid
for g in range(4):
    o.append(f'<text x="22" y="{y(g)+24}" class="sf-id" data-in="2">G{g}</text>')
    for i in range(8):
        x, yy = cell(g, i)
        t = TAGS[g][i]
        occ = t != "--"
        cls = "f-panel" if occ else "f-code"
        o.append(f'<rect x="{x}" y="{yy}" width="{CW-GAP}" height="{CH}" rx="5" class="{cls} s-line" stroke-width="1.5" data-in="2"/>')
for g in range(4):
    for i in range(8):
        x, yy = cell(g, i)
        t = TAGS[g][i]
        # erased cells swap their tag at step 6
        out = ' data-out="6"' if (g, i) in ((1, 3), (3, 3)) else ""
        if t != "--":
            o.append(f'<text x="{x+(CW-GAP)/2}" y="{yy+23}" text-anchor="middle" class="sf-tag"{out} data-in="3">{t}</text>')
        else:
            o.append(f'<text x="{x+(CW-GAP)/2}" y="{yy+23}" text-anchor="middle" class="sf-id" data-in="3">--</text>')
# step 4 highlights: G0 cells 2 and 4
for i in (2, 4):
    x, yy = cell(0, i)
    o.append(f'<rect x="{x-2}" y="{yy-2}" width="{CW-GAP+4}" height="{CH+4}" rx="7" fill="none" class="s-acc" stroke-width="3" data-hl="4" data-in="4" data-out="5"/>')
o.append(f'<text x="{X0}" y="{y(0)-8}" class="sf-mask" data-in="4" data-out="5">tag 5A vs 8 bytes → mask 00101000</text>')
o.append(f'<text x="{X0}" y="320" class="sf-lab" data-in="4" data-out="5">One true hit, one false match: the full key decides.</text>')
# step 5: probe from G1 -> G2
x1, y1 = cell(1, 7)
o.append(f'<rect x="{X0-3}" y="{y(1)-3}" width="{8*CW-GAP+6}" height="{CH+6}" rx="8" fill="none" class="s-warn" stroke-width="3" data-in="5" data-out="6"/>')
o.append(f'<path d="M {X0+8*CW-GAP+8} {y(1)+18} h 12 v {66} h -12" fill="none" class="s-acc2" stroke-width="2.5" data-in="5" data-out="6"/>')
o.append(f'<path d="M {X0+8*CW-GAP+2} {y(2)+12} l 7 6 l -7 6" fill="none" class="s-acc2" stroke-width="2.5" data-in="5" data-out="6"/>')
o.append(f'<text x="{X0}" y="320" class="sf-lab" data-in="5" data-out="6">G1 has no empty slot: hop +1 group to G2.</text>')
o.append(f'<text x="{X0}" y="342" class="sf-lab" data-in="5" data-out="6">G2 has an empty: the key is absent. Stop.</text>')
# step 6: erase
x, yy = cell(1, 3)
o.append(f'<text x="{x+(CW-GAP)/2}" y="{yy+25}" text-anchor="middle" class="sf-big" style="fill:var(--bad)" data-in="6" data-out="7">X</text>')
x, yy = cell(3, 3)
o.append(f'<text x="{x+(CW-GAP)/2}" y="{yy+23}" text-anchor="middle" class="sf-id" data-in="6" data-out="7">--</text>')
o.append(f'<rect x="{cell(1,3)[0]-2}" y="{cell(1,3)[1]-2}" width="{CW-GAP+4}" height="{CH+4}" rx="7" fill="none" class="s-bad" stroke-width="3" data-hl="6" data-in="6" data-out="7"/>')
o.append(f'<rect x="{cell(3,3)[0]-2}" y="{cell(3,3)[1]-2}" width="{CW-GAP+4}" height="{CH+4}" rx="7" fill="none" class="s-ok" stroke-width="3" data-hl="6" data-in="6" data-out="7"/>')
o.append(f'<text x="{X0}" y="320" class="sf-lab" data-in="6" data-out="7">G1 was full: erasing writes a tombstone (X).</text>')
o.append(f'<text x="{X0}" y="342" class="sf-lab" data-in="6" data-out="7">G3 had empties: erasing just writes empty.</text>')
# step 7 overlay
o.append('<rect x="0" y="0" width="480" height="430" class="f-bg" opacity=".97" data-in="7"/>')
for k, (n, l) in enumerate([("7/8", "max load factor"), ("1 byte", "metadata per slot"), ("16", "slots compared per SSE2 op"), ("~2.1", "groups probed per miss at 7/8 (my sim)")]):
    yy = 90 + k * 82
    o.append(f'<text x="30" y="{yy+26}" class="sf-num" data-in="7">{n}</text><text x="170" y="{yy+24}" class="sf-lab" data-in="7">{l}</text>')
o.append('</svg></div>')
steps = [
    '<p class="dropcap">A hash table has to answer "where is this key?" fast. The classic answer, chaining, hashes to a bucket and walks a linked list. It works, but every hop is a pointer to a separately allocated node, so a lookup is a string of likely cache misses and every entry pays for a pointer.</p>',
    '<p><b>Open addressing</b> drops the lists. Keys and values sit directly in one flat array of slots, grouped here in rows of 8 (Abseil uses 16). A key hashes to a home group and goes in the first free slot it finds. No pointers, no per-entry allocation. The price: a lookup now has to check slots, and a full key comparison per slot is expensive.</p>',
    '<p><b>The trick: a tag per slot.</b> Next to the slots, keep a separate array with one byte per slot. A full slot stores 7 bits of the key\'s hash. An empty slot stores a special "empty" value. The tag is a cheap fingerprint: slots whose tag differs cannot hold the key.</p>',
    '<p><b>One instruction checks a whole group.</b> Load the group\'s tag bytes into a SIMD register, compare all of them to the key\'s tag at once, and get back a bitmask of candidates. Here two slots match 5A. Only those get a real key comparison. A wrong tag matches roughly 1 slot in 128, so false matches are rare.</p>',
    '<p><b>Empty is the stop sign.</b> If the group holds no match and at least one empty slot, the key cannot be further along, because inserts always fill the earliest free slot on the probe path. If the group is completely full, the probe hops to another group, +1 then +2 then +3 groups (triangular steps), and repeats.</p>',
    '<p><b>Deleting needs care.</b> Emptying a slot in a full group could cut a probe path that once passed through it, so such a slot gets a tombstone marker that says "keep going". If the group already has an empty slot, no probe ever passed it, and plain empty is safe. That check keeps tombstones rare.</p>',
    '<p><b>The result.</b> Tables run at up to 7/8 full, spend one byte of metadata per slot and scan 16 slots per instruction. Rust\'s HashMap, Go\'s built-in map since 1.24 and Google\'s Abseil all use this layout. The cost: values move when the table grows, and tombstones can pile up until a rehash.</p>',
]
o.append('<div class="scrolly-steps">')
for s in steps:
    o.append(f'<div class="step">{s}</div>')
o.append('</div></div>')
open("sections/story.html", "w").write("\n".join(o))
print("story.html", sum(len(x) for x in o), "bytes")
