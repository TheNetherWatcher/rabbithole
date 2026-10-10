# Generates the story scrolly SVG for sections/story.html (python3 story_svg.py prints it; story.html embeds the output).
import sys
out = []

def rng(a=None, b=None, hl=None):
    s = ''
    if a: s += f' data-in="{a}"'
    if b: s += f' data-out="{b}"'
    if hl: s += f' data-hl="{hl}"'
    return s

def text(x, y, t, cls, a=None, b=None, anchor=None):
    an = f' text-anchor="{anchor}"' if anchor else ''
    out.append(f'<text x="{x}" y="{y}" class="{cls}"{an}{rng(a, b)}>{t}</text>')

def rect(x, y, w, h, cls, a=None, b=None, extra=''):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" class="{cls}"{extra}{rng(a, b)}/>')

out.append('<svg id="story-fig" viewBox="0 0 480 430" xmlns="http://www.w3.org/2000/svg" role="img" '
           'aria-label="One server at 100 requests a second, a 10-second stall, a queue that keeps growing with dead requests, and the fix that drains it">')

# captions (top): one per step, same spot, ranges never overlap
text(20, 26, 'Normal: 70 req/s in, 100 req/s capacity', 'sf-cap', 1, 2)
text(20, 26, 'Trigger: the server stalls for 10 s', 'sf-cap', 2, 3)
text(20, 26, 'Every timeout sends another attempt', 'sf-cap', 3, 4)
text(20, 26, 'Stall over. Server is back at 100/s.', 'sf-cap', 4, 5)
text(20, 26, 'Queue grows, though the trigger is gone', 'sf-cap', 5, 6)
text(20, 26, 'Still stuck, with 0/s goodput', 'sf-cap', 6, 7)
text(20, 26, 'Skip dead requests, or serve newest first', 'sf-cap', 7, 8)
text(20, 26, 'Or cut the retries, or cap them with a budget', 'sf-cap', 8, 9)

# users -> queue -> server
rect(20, 44, 120, 34, 'f-panel s-line', extra=' stroke-width="1.5"')
text(80, 66, 'users 70/s', 'sf-lab', anchor='middle')
out.append('<rect x="340" y="44" width="120" height="34" rx="4" class="f-panel s-line" stroke-width="1.5" data-hl="2 3"/>')
text(400, 66, 'server 100/s', 'sf-lab', anchor='middle')
out.append('<rect x="336" y="40" width="128" height="42" rx="7" class="f-none s-bad" stroke-width="2.5" stroke-dasharray="6 4" data-in="2" data-out="4"/>')
out.append('<line x1="80" y1="78" x2="80" y2="110" class="s-mute" stroke-width="2"/>')
out.append('<line x1="400" y1="110" x2="400" y2="78" class="s-mute" stroke-width="2"/>')

# queue track and queue depth (bar widths scale 440 px = 11,826 requests)
out.append('<rect x="20" y="112" width="440" height="30" rx="6" class="f-code s-line" stroke-width="1"/>')
out.append('<rect x="22" y="115" width="4" height="24" rx="2" class="f-ok"/>')
out.append('<rect x="22" y="115" width="70" height="24" rx="2" class="f-warn" data-in="2" data-out="4"/>')
out.append('<rect x="22" y="115" width="111" height="24" rx="2" class="f-warn" data-in="4" data-out="5"/>')
out.append('<rect x="22" y="115" width="193" height="24" rx="2" class="f-warn" data-in="5" data-out="6"/>')
out.append('<rect x="22" y="115" width="436" height="24" rx="2" class="f-bad" data-in="6" data-out="7"/>')
text(20, 170, 'queue ~2', 'sf-lab', 1, 2)
text(20, 170, 'queue 1,870 when the stall ends', 'sf-lab', 2, 4)
text(20, 170, 'queue 2,971 at t = 40 s', 'sf-lab', 4, 5)
text(20, 170, 'queue 5,191 at t = 60 s', 'sf-lab', 5, 6)
text(20, 170, 'queue 11,826 at t = 120 s', 'sf-lab', 6, 7)
text(20, 170, 'queue drains at once', 'sf-lab', 7, 9)

# arrivals (scale: 440 px = 210 req/s)
text(20, 204, 'in: 70/s', 'sf-lab', 1, 3)
text(20, 204, 'in: 210/s, every user sends 3 attempts', 'sf-lab', 3, 7)
text(20, 204, 'in: 70/s, retries stop', 'sf-lab', 7, 9)
out.append('<rect x="20" y="210" width="440" height="18" rx="4" class="f-code s-line" stroke-width="1"/>')
out.append('<rect x="20" y="210" width="147" height="18" rx="4" class="f-acc" data-in="1" data-out="3"/>')
out.append('<rect x="20" y="210" width="440" height="18" rx="4" class="f-bad" data-in="3" data-out="7"/>')
out.append('<rect x="20" y="210" width="147" height="18" rx="4" class="f-acc" data-in="7" data-out="9"/>')

# goodput
text(20, 254, 'goodput: 70/s', 'sf-lab', 1, 2)
text(20, 254, 'goodput: 0/s', 'sf-lab', 2, 7)
text(20, 254, 'goodput: 70/s', 'sf-lab', 7, 9)
out.append('<rect x="20" y="260" width="440" height="18" rx="4" class="f-code s-line" stroke-width="1"/>')
out.append('<rect x="20" y="260" width="147" height="18" rx="4" class="f-ok" data-in="1" data-out="2"/>')
out.append('<rect x="20" y="260" width="147" height="18" rx="4" class="f-ok" data-in="7" data-out="9"/>')

# status line (bottom of the chart)
text(20, 318, 'Every request is served within its 1 s timeout.', 'sf-lab', 1, 2)
text(20, 318, 'Requests wait; nothing is served.', 'sf-lab sf-bad', 2, 3)
text(20, 318, '3 attempts per user: 210/s into 100/s.', 'sf-lab', 3, 4)
text(20, 318, 'Each served attempt is work nobody reads.', 'sf-lab', 4, 5)
text(20, 318, 'Queue grows by about 110/s, trigger gone.', 'sf-lab', 5, 6)
text(20, 318, 'Goodput stays 0/s, server 100% busy.', 'sf-lab sf-bad', 6, 7)
text(20, 318, 'Goodput back to 70/s at t = 30 s.', 'sf-lab', 7, 8)
text(20, 318, 'No retries also recovers, at t = 51 s.', 'sf-lab', 8, 9)

# request tiles: 19 queued requests; live = client still waiting, dead = client gone
for i in range(19):
    x = 20 + i * 23.5
    out.append(f'<rect x="{x:.1f}" y="338" width="18" height="24" rx="4" class="f-ok" data-in="1" data-out="3"/>')
    out.append(f'<rect x="{x:.1f}" y="338" width="18" height="24" rx="4" class="f-bad" data-in="3" data-out="7"/>')
    out.append(f'<rect x="{x:.1f}" y="338" width="18" height="24" rx="4" class="f-ok" data-in="7" data-out="9"/>')
text(20, 386, 'live: the client is still waiting', 'sf-lab', 1, 3)
text(20, 386, 'dead: the client has already left', 'sf-lab sf-bad', 3, 7)
text(20, 386, 'live: the remaining requests still wait', 'sf-lab', 7, 9)

# result overlay (step 9)
out.append('<g data-in="9"><rect x="12" y="38" width="456" height="384" rx="14" class="f-bg" opacity=".97"/>'
           '<text x="240" y="100" class="sf-cap" text-anchor="middle">What the loop costs</text>'
           '<text x="60" y="160" class="sf-lab">attempts per user request (2 retries)</text>'
           '<text x="420" y="160" class="sf-num" text-anchor="end">3×</text>'
           '<text x="60" y="240" class="sf-lab">stable band, req/s</text>'
           '<text x="420" y="240" class="sf-num" text-anchor="end">33–100</text>'
           '<rect x="60" y="252" width="360" height="14" rx="4" class="f-code s-line" stroke-width="1"/>'
           '<rect x="178.8" y="252" width="241.2" height="14" rx="4" class="f-warn"/>'
           '<text x="60" y="320" class="sf-lab">goodput while stuck</text>'
           '<text x="420" y="320" class="sf-num" text-anchor="end">0/s</text>'
           '<text x="240" y="380" class="sf-big" text-anchor="middle">The loop, not the trigger, keeps it down.</text></g>')
out.append('</svg>')
sys.stdout.write('\n'.join(out))
