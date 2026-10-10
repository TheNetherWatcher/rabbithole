#!/usr/bin/env python3
"""Build rabbithole pages.

  python3 build.py dives/<date>-<slug>      # dive.json + sections/ + img/  ->  index.html (single self-contained file)
  python3 build.py --hub dives              # every dive  ->  dives/index.html (visual index with progress badges)

Inputs per dive folder (see SKILL.md, "Step 4"):
  dive.json            meta, tldr, stats, hero, ordered card list, questions
  sections/*.html      one HTML fragment per card: the in-depth content (may contain <style>/<script>)
  img/*                hero + card visuals. .svg is inlined raw (theme-aware), .txt is ASCII art,
                       raster images become data: URIs. <img src="img/..."> inside sections is inlined too.
"""
import base64
import hashlib
import html
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
TPL = HERE / "template"
RASTER = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
WPM = 180  # technical prose; each interactive .widget adds a minute


def read(p):
    return pathlib.Path(p).read_text(encoding="utf-8")


def esc(s):
    return html.escape(str(s), quote=True)


def svg_inline(path):
    s = read(path)
    s = re.sub(r"<\?xml[^>]*\?>|<!DOCTYPE[^>]*>|<!--.*?-->", "", s, flags=re.S)
    return s.strip()


def visual(dive, ref, cls=""):
    """Render a hero/card visual reference as inline markup."""
    if not ref:
        return ""
    p = dive / ref
    if not p.exists():
        sys.exit(f"missing visual: {p}")
    if p.suffix == ".svg":
        return svg_inline(p)
    if p.suffix == ".txt":
        return f'<pre class="ascii-hero {cls}" aria-hidden="true">{esc(read(p).rstrip())}</pre>'
    if p.suffix in RASTER:
        b64 = base64.b64encode(p.read_bytes()).decode()
        return f'<img src="data:{RASTER[p.suffix]};base64,{b64}" alt="" style="width:100%;height:100%;object-fit:cover">'
    sys.exit(f"unsupported visual type: {p}")


def inline_imgs(dive, frag):
    """<img src="img/x.png"> inside section fragments -> data: URI so the page stays one file."""
    def sub(m):
        src = m.group(2)
        p = dive / src
        if src.startswith(("http:", "https:", "data:")) or not p.exists():
            return m.group(0)
        mime = RASTER.get(p.suffix, "image/svg+xml" if p.suffix == ".svg" else None)
        if not mime:
            return m.group(0)
        return f'{m.group(1)}data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}{m.group(3)}'
    return re.sub(r'(<img\b[^>]*\bsrc=")([^"]+)(")', sub, frag)


def words(frag):
    txt = re.sub(r"<(script|style)\b.*?</\1>", " ", frag, flags=re.S)
    txt = re.sub(r"<[^>]+>", " ", txt)
    return len(txt.split())


def minutes(n):
    return max(1, round(n / WPM))


def fill(tpl, repl):
    """Single-pass placeholder substitution, so content containing '{{X}}' is never re-expanded."""
    return re.sub(r"\{\{[A-Z]+\}\}", lambda m: repl.get(m.group(0), m.group(0)), tpl)


OPEN_LICENSES = ("CC BY", "CC BY-SA", "CC0", "Public domain", "Apache-2.0", "MIT", "BSD")


def check_figure(fid, f, dive):
    for k in ("file", "caption", "license"):
        if not f.get(k):
            sys.exit(f"figure '{fid}': missing '{k}'")
    src = f.get("source") or {}
    if not src.get("cite") or not src.get("url"):
        sys.exit(f"figure '{fid}': source needs 'cite' and 'url'")
    lic = f["license"]
    if "ND" in lic.replace("-", " ").split():
        sys.exit(f"figure '{fid}': {lic} forbids modified copies; link to it or redraw as your own SVG instead")
    if not lic.startswith(OPEN_LICENSES):
        sys.exit(f"figure '{fid}': license '{lic}' is not an open license; link to the figure or redraw it "
                 f"as your own SVG ('adapted from ...') instead of embedding it")
    if "NC" in lic:
        print(f"warning: figure '{fid}' is {lic}: fine in the private repo, must not go into blog posts", file=sys.stderr)
    p = dive / f["file"]
    if not p.exists():
        sys.exit(f"figure '{fid}': missing file {p}")
    head = p.read_bytes()[:12]
    ok = head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8") or head[8:12] == b"WEBP" or head.startswith(b"GIF8") \
        or (p.suffix == ".svg" and b"<svg" in p.read_bytes()[:2000])
    if not ok:
        sys.exit(f"figure '{fid}': {p.name} is not a PNG/JPEG/WebP/GIF/SVG image")
    kb = p.stat().st_size // 1024
    if kb > 400:
        print(f"warning: figure '{fid}' is {kb} KB; run fig.py with a smaller --max", file=sys.stderr)


class Figures:
    """Expands <figure data-fig="id"></figure> placeholders, numbers them in page order, collects credits."""

    def __init__(self, dive, figs):
        self.dive, self.figs, self.order = dive, figs, []
        for fid, f in figs.items():
            check_figure(fid, f, dive)

    def expand(self, frag):
        def sub(m):
            fid = m.group(1)
            if fid not in self.figs:
                sys.exit(f"section references unknown figure '{fid}'")
            f = self.figs[fid]
            if fid not in self.order:
                self.order.append(fid)
            n = self.order.index(fid) + 1
            p = self.dive / f["file"]
            mime = RASTER.get(p.suffix, "image/svg+xml")
            data = base64.b64encode(p.read_bytes()).decode()
            src = f["source"]
            lic = f'<a href="{esc(f["license_url"])}" target="_blank" rel="noopener">{esc(f["license"])}</a>' \
                if f.get("license_url") else esc(f["license"])
            mod = f' · {esc(f["modified"])}' if f.get("modified") else ""
            return (f'<figure class="fig" id="fig-{esc(fid)}"><button class="fig-zoom" type="button" aria-label="Enlarge figure {n}">'
                    f'<img src="data:{mime};base64,{data}" alt="{esc(f.get("alt", f["caption"]))}" loading="lazy"></button>'
                    f'<figcaption><b>Figure {n}.</b> {f["caption"]}<span class="fig-cite">Source: '
                    f'<a href="{esc(src["url"])}" target="_blank" rel="noopener">{esc(src["cite"])}</a>'
                    f'{" · " + esc(src["figure"]) if src.get("figure") else ""} · {lic}{mod}</span></figcaption></figure>')
        return re.sub(r'<figure\s+data-fig="([^"]+)"\s*>\s*</figure>', sub, frag)

    def count(self, frag):
        return len(re.findall(r'<figure\s+data-fig="', frag))

    def credits(self):
        if not self.order:
            return ""
        items = []
        for n, fid in enumerate(self.order, 1):
            f, src = self.figs[fid], self.figs[fid]["source"]
            lic = f'<a href="{esc(f["license_url"])}" target="_blank" rel="noopener">{esc(f["license"])}</a>' \
                if f.get("license_url") else esc(f["license"])
            items.append(f'<li><a href="#fig-{esc(fid)}">Figure {n}</a>: <a href="{esc(src["url"])}" target="_blank" rel="noopener">'
                         f'{esc(src["cite"])}</a>{", " + esc(src["figure"]) if src.get("figure") else ""}. {lic}.'
                         f'{" " + esc(f["modified"]).capitalize() + "." if f.get("modified") else ""}</li>')
        return ('<h3 id="figure-credits">Figure credits</h3><p class="mini">Reproduced under their open licenses; '
                'changes limited to what is noted.</p><ol class="credits">' + "".join(items) + "</ol>")


CHECK_SVG = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5l3.2 3L13 4.5"/></svg>'


def render_quiz(questions):
    groups, out = [], []
    for i, q in enumerate(questions):
        g = q.get("type", "Questions")
        if g not in groups:
            groups.append(g)
    for g in groups:
        out.append(f'<div class="qgroup">{esc(g)}</div>')
        for i, q in enumerate(questions):
            if q.get("type", "Questions") != g:
                continue
            sec = f'<a class="sec mini" href="#c-{esc(q["sec"])}">→ related card</a>' if q.get("sec") else ""
            out.append(
                f'<div class="q" data-i="{i}"><div class="qq">{i + 1}. {q["q"]}</div>'
                f'<div class="qa"><div><p>{q["a"]}</p></div></div>'
                f'<div class="qrow"><button class="qbtn qshow" type="button" aria-expanded="false">Show answer</button>'
                f'<button class="qbtn y" type="button" aria-pressed="false">✓ Knew it</button>'
                f'<button class="qbtn n" type="button" aria-pressed="false">✗ Didn\'t</button>{sec}</div></div>'
            )
    head = ('<p class="mini">Answer in your head first, then reveal and mark yourself honestly. '
            'Marks are saved in this browser and feed the progress ring.</p>'
            '<p><button class="btn" id="reveal-all" type="button" aria-pressed="false">Reveal all answers</button> '
            '<button class="btn" id="quiz-reset" type="button">Reset marks</button></p>')
    return head + "\n".join(out)


def build_dive(dive):
    dive = pathlib.Path(dive).resolve()
    D = json.loads(read(dive / "dive.json"))
    m = D["meta"]
    slug = dive.name
    cards_html, dots, data_cards = [], [], []
    deep_words = 0
    skim_words = words(D.get("tldr", "")) + words(D.get("why", ""))
    last_group = None
    figs = Figures(dive, D.get("figures", {}))
    credits_id = next((c["id"] for c in D["cards"] if c.get("credits")),
                      "sources" if any(c["id"] == "sources" for c in D["cards"]) else D["cards"][-1]["id"])
    deeps = {}
    for c in D["cards"]:  # expand figures in card order so numbering follows the page
        deeps[c["id"]] = render_quiz(D.get("questions", [])) if c.get("builtin") == "quiz" \
            else inline_imgs(dive, read(dive / c["file"]))
        deeps[c["id"]] = (figs.count(deeps[c["id"]]), figs.expand(deeps[c["id"]]))
    deeps[credits_id] = (deeps[credits_id][0], deeps[credits_id][1] + figs.credits())
    unused = set(figs.figs) - set(figs.order)
    if unused:
        print(f"warning: figures defined but never placed: {', '.join(sorted(unused))}", file=sys.stderr)
    for idx, c in enumerate(D["cards"]):
        cid = c["id"]
        if c.get("group") and c["group"] != last_group:
            cards_html.append(f'<div class="group rv">{esc(c["group"])}</div>')
            last_group = c["group"]
        nfig, deep = deeps[cid]
        w = words(deep) + WPM * deep.count('class="widget') + WPM // 3 * nfig
        deep_words += w
        skim_words += words(c["brief"])
        brief = c["brief"]
        if c.get("builtin") == "quiz":
            brief += '<p class="score" id="quiz-score"></p>'
        cls = "card rv" + (" plain" if c.get("tone") == "plain" else "")
        opened = " data-open" if c.get("open") else ""
        vis = visual(dive, c.get("visual"))
        vis_html = f'<div class="card-vis" aria-hidden="true">{vis}</div>' if vis else '<div class="card-vis" aria-hidden="true"></div>'
        kicker = esc(c.get("kicker", ""))
        cards_html.append(f'''<article class="{cls}" id="c-{esc(cid)}" data-id="{esc(cid)}"{opened}>
<div class="card-head">{vis_html}
<div class="card-body"><div class="kicker">{kicker}</div><h2>{esc(c["title"])}</h2>
<div class="brief">{brief}</div>
<div class="card-actions"><button class="deeper" type="button" aria-expanded="false" aria-controls="d-{esc(cid)}">Go deeper <span class="chev">▸</span> <small>{minutes(w)} min{f" · {nfig} fig" if nfig else ""}</small></button>
<label class="got"><input type="checkbox"><span class="box">{CHECK_SVG}</span><span>Got it</span></label></div></div></div>
<div class="deep" id="d-{esc(cid)}"><div class="deep-inner"><div class="deep-content">
{deep}
</div><div class="deep-foot"><button class="collapse" type="button">Collapse ▴</button></div></div></div>
</article>''')
        dots.append(f'<a href="#c-{esc(cid)}" data-id="{esc(cid)}" aria-label="{esc(c["title"])}"><span>{esc(c["title"])}</span></a>')
        data_cards.append(cid)

    stats = "".join(
        f'<div class="stat rv" style="--i:{i}"><div class="v">{esc(s["v"])}</div><div class="l">{s["l"]}</div></div>'
        for i, s in enumerate(D.get("stats", []))
    )
    chips = "".join(f'<span class="chip">{esc(x)}</span>' for x in
                    [m.get("subject"), m.get("domain"), "Depth: " + m.get("depth", "hard"), m.get("date")] if x)
    data = json.dumps({"slug": slug, "cards": data_cards, "questions": len(D.get("questions", []))})
    page = read(TPL / "dive.html")
    repl = {
        "{{TITLE}}": esc(m["title"]),
        "{{SHORT}}": esc(m.get("short", m["title"])),
        "{{DESC}}": esc(re.sub(r"<[^>]+>", "", D.get("tldr", ""))[:300]),
        "{{CSS}}": read(TPL / "app.css"),
        "{{JS}}": read(TPL / "app.js"),
        "{{HERO}}": visual(dive, D.get("hero")),
        "{{CHIPS}}": chips,
        "{{TLDR}}": D.get("tldr", ""),
        "{{WHY}}": D.get("why", ""),
        "{{STATS}}": stats,
        "{{NCARDS}}": str(len(data_cards)),
        "{{SKIM}}": str(minutes(skim_words)),
        "{{DEEP}}": str(minutes(deep_words)),
        "{{CARDS}}": "\n".join(cards_html),
        "{{DOTS}}": "".join(dots),
        "{{DATA}}": data.replace("</", "<\\/"),
    }
    page = fill(page, repl)
    out = dive / "index.html"
    out.write_text(page, encoding="utf-8")
    print(f"built {out.relative_to(dive.parent.parent) if dive.parent.parent in out.parents else out} "
          f"({len(page) // 1024} KB, {len(data_cards)} cards, skim ~{minutes(skim_words)} min, deep ~{minutes(deep_words)} min)")


# ---------------- hub ----------------

def emblem_fallback(slug):
    """Deterministic abstract emblem for dives built before the card format."""
    h = hashlib.sha256(slug.encode()).digest()
    cells = []
    for i in range(36):
        x, y = 40 + (i % 12) * 95, 30 + (i // 12) * 85
        b = h[i % 32]
        if b % 3 == 0:
            cells.append(f'<rect x="{x}" y="{y}" width="70" height="56" rx="8" class="f-code s-line" stroke-width="2"/>')
        elif b % 3 == 1:
            cells.append(f'<circle cx="{x + 35}" cy="{y + 28}" r="{8 + b % 14}" class="f-none s-acc2" stroke-width="2" opacity=".6"/>')
        if b % 7 == 0:
            cells.append(f'<rect x="{x}" y="{y}" width="70" height="56" rx="8" class="f-acc" opacity=".8"/>')
    return f'<svg viewBox="0 0 1200 300" preserveAspectRatio="xMidYMid slice" aria-hidden="true">{"".join(cells)}</svg>'


def history_rows(dives_dir):
    rows = {}
    hist = dives_dir.parent / "history.md"
    if not hist.exists():
        return rows
    for line in read(hist).splitlines():
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) < 5:
            continue
        mm = re.search(r"\(dives/([^/)]+)/?\)", cols[4])
        if mm:
            rows[mm.group(1)] = {"date": cols[0], "domain": cols[1], "topic": cols[2], "depth": cols[3]}
    return rows


def scope_ids(svg, prefix):
    """Prefix SVG ids (and their url(#..)/href refs) so many emblems can share one page."""
    pre = re.sub(r"[^a-zA-Z0-9]", "", prefix)[-12:]
    for i in set(re.findall(r'\sid="([^"]+)"', svg)):
        svg = re.sub(rf'(\sid="|url\(#|href="#){re.escape(i)}(["\)])', rf"\g<1>{pre}-{i}\g<2>", svg)
    return svg


def build_hub(dives_dir):
    dives_dir = pathlib.Path(dives_dir).resolve()
    hist = history_rows(dives_dir)
    tiles, domains = [], []
    for d in sorted([p for p in dives_dir.iterdir() if p.is_dir()], reverse=True):
        slug = d.name
        if (d / "dive.json").exists():
            D = json.loads(read(d / "dive.json"))
            m = D["meta"]
            title, domain, date = m.get("short", m["title"]), m.get("domain", ""), m.get("date", slug[:10])
            art = visual(d, D.get("hero")) or emblem_fallback(slug)
            fmt = "cards"
        else:
            h = hist.get(slug, {})
            readme = d / "README.md"
            title = read(readme).splitlines()[0].lstrip("# ") if readme.exists() else h.get("topic", slug)
            if ":" in title and len(title.split(":")[0]) >= 8:
                title = title.split(":")[0]
            domain, date = h.get("domain", ""), h.get("date", slug[:10])
            art = emblem_fallback(slug)
            fmt = "classic"
        if domain and domain not in domains:
            domains.append(domain)
        art = scope_ids(art, slug)
        tiles.append(f'''<a class="tile rv" href="{esc(slug)}/index.html" data-slug="{esc(slug)}" data-domain="{esc(domain)}" data-q="{esc((title + " " + domain).lower())}">
<div class="tile-art hero-art-mini">{art}</div>
<div class="tile-body"><h3>{esc(title)}</h3>
<div class="bar"><i></i></div>
<div class="tile-meta"><span class="badge" data-s="new">New</span><span>{esc(domain)}</span><span>· {esc(date)}</span>{'<span>· classic</span>' if fmt == 'classic' else ''}</div></div></a>''')
    chips = "".join(f'<button class="tb-btn" type="button" data-f="{esc(x)}" aria-pressed="false">{esc(x)}</button>' for x in domains)
    page = read(TPL / "hub.html")
    page = fill(page, {"{{CSS}}": read(TPL / "app.css"), "{{TILES}}": "\n".join(tiles),
                       "{{FILTERS}}": chips, "{{N}}": str(len(tiles))})
    out = dives_dir / "index.html"
    out.write_text(page, encoding="utf-8")
    print(f"built {out} ({len(tiles)} dives)")


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "--hub":
        build_hub(a[1])
    elif len(a) == 1 and not a[0].startswith("-"):
        build_dive(a[0])
    else:
        sys.exit(__doc__)
