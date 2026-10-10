/* rabbithole dive template runtime — cards, progress, quiz, motion. Shared by every dive page. */
(function () {
  var root = document.documentElement;
  root.classList.add('js');
  var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var $ = function (s, el) { return (el || document).querySelector(s); };
  var $$ = function (s, el) { return [].slice.call((el || document).querySelectorAll(s)); };

  // ---- storage (never required: page works without it) ----
  function load(k, d) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } }
  function save(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }

  // ---- theme ----
  var theme = load('rh:theme', null);
  if (theme) root.setAttribute('data-theme', theme);
  var tb = $('#theme');
  if (tb) tb.onclick = function () {
    var dark = root.getAttribute('data-theme') ? root.getAttribute('data-theme') === 'dark'
      : matchMedia('(prefers-color-scheme: dark)').matches;
    theme = dark ? 'light' : 'dark';
    root.setAttribute('data-theme', theme); save('rh:theme', theme);
  };

  // ---- copy buttons ----
  $$('pre').forEach(function (p) {
    var c = p.querySelector('code'); if (!c) return;
    var b = document.createElement('button'); b.className = 'copy'; b.type = 'button'; b.textContent = 'Copy';
    b.onclick = function () {
      (navigator.clipboard ? navigator.clipboard.writeText(c.innerText) : Promise.reject())
        .then(function () { b.textContent = 'Copied'; }, function () { b.textContent = 'Select + copy'; });
      setTimeout(function () { b.textContent = 'Copy'; }, 1400);
    };
    p.appendChild(b);
  });

  // ---- SVG stroke draw-in: normalise path length ----
  $$('.draw').forEach(function (e) { e.setAttribute('pathLength', '1'); });

  // ---- hero layers: stagger intro, parallax ----
  var layers = $$('.hero-art .layer');
  layers.forEach(function (g, i) { g.style.setProperty('--i', i); });
  var bar = $('.topbar');
  var ticking = false;
  function onScroll() {
    if (ticking) return; ticking = true;
    requestAnimationFrame(function () {
      var y = window.scrollY;
      if (bar) bar.classList.toggle('scrolled', y > 40);
      if (!reduce && y < 700) layers.forEach(function (g) {
        g.style.translate = '0 ' + (y * (+g.getAttribute('data-depth') || 0)).toFixed(1) + 'px';
      });
      ticking = false;
    });
  }
  window.addEventListener('scroll', onScroll, { passive: true }); onScroll();
  var heroArt = $('.hero-art');
  if (heroArt) requestAnimationFrame(function () { requestAnimationFrame(function () { heroArt.classList.add('in-view'); }); });

  // ---- ASCII hero: scramble then resolve ----
  var ascii = $('.hero-art .ascii-hero');
  if (ascii && !reduce) {
    var target = ascii.textContent, glyphs = '01#*+=-:.<>/\\|[]{}', t0 = performance.now();
    (function frame(now) {
      var k = Math.min(1, (now - t0) / 1400), out = '';
      for (var i = 0; i < target.length; i++) {
        var ch = target[i];
        out += (ch === '\n' || ch === ' ' || Math.random() < k * 1.15) ? ch : glyphs[(Math.random() * glyphs.length) | 0];
      }
      ascii.textContent = out;
      if (k < 1) requestAnimationFrame(frame); else ascii.textContent = target;
    })(t0);
  }

  // ---- stat count-up ----
  function countUp(el) {
    var m = /^(\d+(?:\.\d+)?)(.*)$/.exec(el.textContent.trim());
    if (!m || reduce) return;
    if (el.dataset.counted) return; el.dataset.counted = 1;
    var final = el.textContent, end = parseFloat(m[1]), dec = (m[1].split('.')[1] || '').length, rest = m[2], t0 = performance.now();
    (function f() {
      var k = Math.min(1, Math.max(0, (performance.now() - t0) / 900)), e = 1 - Math.pow(1 - k, 3);
      el.textContent = k < 1 ? (end * e).toFixed(dec) + rest : final;
      if (k < 1) requestAnimationFrame(f);
    })();
    setTimeout(function () { el.textContent = final; }, 1200); // rAF can stall in background tabs
  }

  // ---- reveal on scroll ----
  var cardsSeen = {};
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        var t = e.target;
        if (t.classList.contains('card')) t.classList.toggle('in-view', e.isIntersecting);
        if (!e.isIntersecting) return;
        if (t.classList.contains('rv') && !t.classList.contains('in')) {
          t.classList.add('in');
          if (t.classList.contains('stat')) countUp($('.v', t));
        }
        if (t.matches && t.matches('svg') ) t.classList.add('in-view');
      });
    }, { rootMargin: '0px 0px -8% 0px' });
    $$('.rv, .card, .deep-content svg, .card-vis svg').forEach(function (e) { io.observe(e); });
  } else {
    $$('.rv').forEach(function (e) { e.classList.add('in'); });
    $$('.card, svg').forEach(function (e) { e.classList.add('in-view'); });
  }

  // ---- figure lightbox ----
  var figs = $$('.fig-zoom');
  if (figs.length) {
    var lb = document.createElement('div'); lb.className = 'lightbox'; lb.setAttribute('role', 'dialog'); lb.setAttribute('aria-modal', 'true');
    lb.innerHTML = '<button type="button">Close ✕</button><img alt=""><p></p>';
    document.body.appendChild(lb);
    var lastFocus = null;
    var close = function () { lb.classList.remove('on'); if (lastFocus) lastFocus.focus(); };
    figs.forEach(function (b) {
      b.onclick = function () {
        var img = $('img', b), cap = b.parentNode.querySelector('figcaption');
        $('img', lb).src = img.src; $('img', lb).alt = img.alt; $('p', lb).innerHTML = cap ? cap.innerHTML : '';
        lastFocus = b; lb.classList.add('on'); $('button', lb).focus();
      };
    });
    lb.onclick = function (e) { if (e.target === lb || e.target.tagName === 'BUTTON' || e.target.tagName === 'IMG') close(); };
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && lb.classList.contains('on')) close(); });
  }

  // ---- cold open: lines arrive one at a time ----
  $$('.cold-inner > *').filter(function (e) { return !/^(STYLE|SCRIPT)$/.test(e.tagName); }).forEach(function (e, i) { e.style.setProperty('--i', i); });

  // ---- scrolly: the sticky figure shows the state of the step being read ----
  $$('.scrolly').forEach(function (sc) {
    var steps = $$('.step', sc), fig = $('.scrolly-fig', sc), cur = -1;
    var els = $$('[data-in],[data-out],[data-hl]', fig).map(function (e) {
      var hl = (e.getAttribute('data-hl') || '').split(/[\s,]+/).filter(Boolean).map(Number);
      return { e: e, a: +e.getAttribute('data-in') || 0, b: +e.getAttribute('data-out') || Infinity, hl: hl };
    });
    steps.forEach(function (st, i) { if (!$('.n', st)) { var n = document.createElement('span'); n.className = 'n'; n.textContent = (i + 1) + ' / ' + steps.length; st.insertBefore(n, st.firstChild); } });
    function show(k) {
      if (k === cur) return; cur = k; var s = k + 1;
      fig.setAttribute('data-step', s);
      steps.forEach(function (st, i) { st.classList.toggle('on', i === k); });
      els.forEach(function (o) {
        o.e.classList.toggle('sv-off', !(s >= o.a && s < o.b));
        o.e.classList.toggle('sv-hl', o.hl.indexOf(s) >= 0);
      });
    }
    function pick() {
      var line = innerHeight * (innerWidth <= 760 ? 0.72 : 0.55), k = 0;
      steps.forEach(function (st, i) { if (st.getBoundingClientRect().top < line) k = i; });
      show(k);
    }
    var t = false;
    window.addEventListener('scroll', function () { if (t) return; t = true; requestAnimationFrame(function () { t = false; pick(); }); }, { passive: true });
    window.addEventListener('resize', pick);
    show(0);
  });

  // ---- page data + progress ----
  var dataEl = $('#rh-data'); if (!dataEl) return;
  var D = JSON.parse(dataEl.textContent);
  var KEY = 'rh:p:' + D.slug;
  var P = load(KEY, {}); P.got = P.got || {}; P.q = P.q || {}; P.g = P.g || {}; P.seen = P.seen || Date.now();
  var cards = $$('article.card');
  var qs = $$('.q[data-i]');
  var guesses = $$('.guess[data-g]');

  function status(gotN, yesN) {
    var nc = cards.length, nq = qs.length;
    if (gotN === nc && (nq === 0 || yesN / nq >= 0.8)) return 'understood';
    if (gotN >= Math.ceil(nc / 2)) return 'skimmed';
    return 'started';
  }
  function refresh() {
    var gotN = cards.filter(function (c) { return P.got[c.dataset.id]; }).length;
    var yesN = qs.filter(function (q) { return P.q[q.dataset.i] === 'y'; }).length;
    var ansN = qs.filter(function (q) { return P.q[q.dataset.i]; }).length;
    var pct = Math.round(100 * (gotN + yesN) / Math.max(1, cards.length + qs.length));
    var st = status(gotN, yesN);
    P.pct = pct; P.status = st; save(KEY, P);
    var fg = $('.ring .r-fg'); if (fg) fg.style.strokeDashoffset = (1 - pct / 100).toFixed(3);
    var rp = $('#ring-pct'); if (rp) rp.textContent = pct + '%';
    $$('[data-status]').forEach(function (b) { b.dataset.s = st; b.textContent = st[0].toUpperCase() + st.slice(1); });
    var sc = $('#quiz-score'); if (sc) sc.textContent = ansN ? (yesN + ' / ' + qs.length + ' known') : qs.length + ' questions';
    $$('.dots a').forEach(function (a) { a.classList.toggle('got', !!P.got[a.dataset.id]); });
    var gids = guesses.map(function (g) { return g.dataset.g; }).filter(function (v, i, a) { return a.indexOf(v) === i; });
    var gDone = gids.filter(function (g) { return P.g[g] && !P.g[g].skip; }), gOk = gDone.filter(function (g) { return P.g[g].ok; });
    $$('.g-score').forEach(function (e) { e.hidden = !gDone.length; e.textContent = '· guesses: ' + gOk.length + ' / ' + gDone.length + ' right'; });
  }

  // ---- guess first: commit, then reveal ----
  function fmt(v, u) { return (Math.round(v * 100) / 100) + u; }
  guesses.forEach(function (g) {
    var id = g.dataset.g, kind = g.dataset.kind, card = g.closest('article.card'), verdict = $('.g-verdict', g);
    function finish(rec, animate) {
      g.classList.add('done');
      if (card) card.classList.remove('gated');
      if (kind === 'choice') {
        var ans = +g.dataset.ans;
        $$('.g-opt', g).forEach(function (b) {
          b.disabled = true; var k = +b.dataset.k;
          if (k === ans) b.classList.add('right'); else if (k === rec.v) b.classList.add('pick');
        });
        verdict.textContent = rec.skip ? 'Answer:' : rec.ok ? 'Right.' : 'Not quite.';
      } else {
        var lo = +g.dataset.lo, hi = +g.dataset.hi, mn = +g.dataset.min, mx = +g.dataset.max, u = g.dataset.unit || '';
        var pos = function (v) { return (100 * (v - mn) / (mx - mn)).toFixed(2) + '%'; };
        var band = $('.g-band', g); band.style.left = pos(lo); band.style.width = 'calc(' + pos(hi) + ' - ' + pos(lo) + ')';
        var you = $('.g-you', g);
        if (rec.skip) { you.style.display = 'none'; verdict.textContent = 'Answer: ' + (lo === hi ? fmt(lo, u) : fmt(lo, u) + '–' + fmt(hi, u)) + '.'; }
        else {
          you.style.left = pos(rec.v);
          var off = rec.v < lo ? lo - rec.v : rec.v > hi ? rec.v - hi : 0;
          var truth = lo === hi ? fmt(lo, u) : fmt(lo, u) + '–' + fmt(hi, u);
          verdict.textContent = 'You said ' + fmt(rec.v, u) + '. Real: ' + truth + '. ' +
            (off === 0 ? 'Spot on.' : rec.ok ? 'Close.' : 'Off by ' + fmt(off, u) + (rec.v > hi ? ', too high.' : ', too low.'));
          $('output', g).textContent = fmt(rec.v, u);
        }
      }
      verdict.className = 'g-verdict' + (rec.skip ? '' : rec.ok ? ' ok' : ' no');
      if (animate) document.dispatchEvent(new CustomEvent('rh:guess', { detail: { id: id, ok: rec.ok } }));
    }
    function commit(rec) { if (P.g[id]) return; P.g[id] = rec; finish(rec, true); refresh(); }
    if (kind === 'choice') {
      $$('.g-opt', g).forEach(function (b) { b.onclick = function () { var v = +b.dataset.k; commit({ v: v, ok: v === +g.dataset.ans }); }; });
    } else {
      var inp = $('input', g), out = $('output', g), u = g.dataset.unit || '';
      inp.oninput = function () { out.textContent = fmt(+inp.value, u); };
      $('.g-lock', g).onclick = function () {
        var v = +inp.value, lo = +g.dataset.lo, hi = +g.dataset.hi, tol = +g.dataset.tol;
        commit({ v: v, ok: v >= lo - tol && v <= hi + tol });
      };
    }
    if (card) { var sk = $('.g-skip', card); if (sk) sk.onclick = function () { commit({ skip: 1, ok: false }); }; }
    if (P.g[id]) finish(P.g[id], false); else if (card) card.classList.add('gated');
  });

  // ---- cards: expand / collapse / got-it ----
  function setOpen(card, open, scroll) {
    card.classList.toggle('open', open);
    clearTimeout(card._st); card.classList.remove('settled');
    if (open) card._st = setTimeout(function () { card.classList.add('settled'); }, 500);
    var btn = $('.deeper', card), deep = $('.deep', card);
    btn.setAttribute('aria-expanded', open);
    if (open) deep.removeAttribute('inert'); else deep.setAttribute('inert', '');
    if (!open && scroll) {
      var top = card.getBoundingClientRect().top;
      if (top < 0) card.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
    }
  }
  cards.forEach(function (card) {
    var id = card.dataset.id;
    $('.deeper', card).onclick = function () { setOpen(card, !card.classList.contains('open'), true); };
    var col = $('.collapse', card); if (col) col.onclick = function () { setOpen(card, false, true); };
    var cb = $('.got input', card);
    cb.checked = !!P.got[id];
    cb.onchange = function () { if (cb.checked) P.got[id] = 1; else delete P.got[id]; refresh(); };
    setOpen(card, card.hasAttribute('data-open'), false);
  });

  // expand-all ("deep mode")
  var ea = $('#expand-all');
  if (ea) {
    var setAll = function (on) {
      ea.setAttribute('aria-pressed', on); $('.lbl', ea).textContent = on ? 'Collapse all' : 'Expand all';
      cards.forEach(function (c) { setOpen(c, on, false); }); save('rh:deep', on);
    };
    ea.onclick = function () { setAll(ea.getAttribute('aria-pressed') !== 'true'); };
    if (load('rh:deep', false)) setAll(true);
  }

  // deep links: #c-<id> or #<anchor inside a card> opens it
  function openFromHash() {
    var h = decodeURIComponent(location.hash.slice(1)); if (!h) return;
    var el = document.getElementById(h); if (!el) return;
    var card = el.closest('article.card');
    if (card && !card.classList.contains('open')) { setOpen(card, true, false); setTimeout(function () { el.scrollIntoView(); }, 480); }
  }
  window.addEventListener('hashchange', openFromHash); openFromHash();

  // ---- quiz ----
  qs.forEach(function (q) {
    var i = q.dataset.i;
    var show = $('.qshow', q), y = $('.qbtn.y', q), n = $('.qbtn.n', q);
    function paint() {
      var r = P.q[i] || '';
      q.dataset.r = r; y.setAttribute('aria-pressed', r === 'y'); n.setAttribute('aria-pressed', r === 'n');
    }
    show.onclick = function () { var s = q.classList.toggle('show'); show.textContent = s ? 'Hide answer' : 'Show answer'; show.setAttribute('aria-expanded', s); };
    y.onclick = function () { P.q[i] = P.q[i] === 'y' ? '' : 'y'; if (!P.q[i]) delete P.q[i]; paint(); refresh(); };
    n.onclick = function () { P.q[i] = P.q[i] === 'n' ? '' : 'n'; if (!P.q[i]) delete P.q[i]; paint(); refresh(); };
    paint();
  });
  var ra = $('#reveal-all');
  if (ra) ra.onclick = function () {
    var on = ra.getAttribute('aria-pressed') !== 'true'; ra.setAttribute('aria-pressed', on);
    ra.textContent = on ? 'Hide all answers' : 'Reveal all answers';
    qs.forEach(function (q) { q.classList.toggle('show', on); var s = $('.qshow', q); s.textContent = on ? 'Hide answer' : 'Show answer'; });
  };
  var rs = $('#quiz-reset');
  if (rs) rs.onclick = function () { P.q = {}; qs.forEach(function (q) { q.dataset.r = ''; $$('.qbtn', q).forEach(function (b) { b.setAttribute('aria-pressed', false); }); }); refresh(); };

  // ---- side dots: current card ----
  var dots = $$('.dots a');
  if (dots.length && 'IntersectionObserver' in window) {
    var map = {}; dots.forEach(function (a) { map[a.dataset.id] = a; });
    var dio = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        dots.forEach(function (a) { a.classList.remove('on'); });
        var a = map[e.target.dataset.id]; if (a) a.classList.add('on');
      });
    }, { rootMargin: '-45% 0px -50% 0px' });
    cards.forEach(function (c) { dio.observe(c); });
  }

  refresh();
})();
