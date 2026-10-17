# Go's hybrid write barrier: why stacks are never re-scanned

`Computer science · Compilers/PL/runtimes · Go hybrid write barrier: Yuasa deletion + Dijkstra insertion, no stack re-scan, mark assist and pacing · hard`

> Go's collector marks while your program runs, so it must hear about pointer changes. Go 1.7 could not trust stacks (no barrier on stack writes), so it froze the world and re-scanned them: 10s to 100s of ms. The hybrid barrier shades the overwritten pointer, and the new one while a stack is unscanned, so a scanned stack stays black.

Interactive version: [index.html](index.html) (cold open, scroll story, step-through widget, guesses). This README is the plain-markdown fallback.


## In everyday words · An inspector, a shop that stays open, and a shout-it-out rule

<p class="dropcap">Imagine a warehouse that has to throw away anything nobody can reach anymore, but it can't close while it counts. So an inspector walks the aisles with tags: <b>white</b> means "haven't seen this box yet", <b>grey</b> means "seen it, haven't looked inside", <b>black</b> means "seen it and everything it points to". When the walk ends, every box still tagged white gets thrown out.</p>
<p>The trouble is that clerks keep moving boxes while the inspector works. A clerk can lift a white box off a shelf the inspector is about to skip, hold it, and clear the shelf. The inspector then finishes the walk, never sees that box, and bins it while the clerk is still carrying it. Go's garbage collector has this exact problem, and the fix is a house rule: <b>whenever a clerk takes a box off a shelf or puts one onto a shelf, they call out its name</b> and the inspector tags it. The clerk's own hands and pockets are too busy to police, so the inspector checks them once. The clever part of Go's rule is that after that one check, the pockets never need checking again.</p>
<h3 id="example">Everyday example</h3>
<p>Priya is a clerk. Shelf B holds box C. The inspector has already checked Priya's pockets (empty) and has just tagged shelf B as "to look inside". Priya takes C from shelf B into her hands, then clears the slot on the shelf. She calls out "C" as she clears the slot, so the inspector tags it. The inspector looks inside shelf B (now empty) and moves on, but C is already tagged and is kept. Without the call-out, C would still be white at the end, and the box in Priya's hands would be binned.</p>
<p>Before Go 1.8 the call-out rule was weaker, so the inspector had to <em>close the shop</em> at the end and re-check every clerk's pockets one last time. With 100,000 clerks that took long enough for customers to notice. The new rule removes the re-check.</p>
<p><b>Now the same thing, technically.</b></p>

## §1 · Prerequisites · Six things to know first

<ul>
<li><b>Tracing GC</b>: an object is live if a chain of pointers leads to it from a <i>root</i> (goroutine stacks, globals, registers). Everything else is freed. <a href="https://go.dev/doc/gc-guide" target="_blank" rel="noopener">Go GC guide</a>.</li>
<li><b>Concurrent marking</b>: the collector traces while the program (the <i>mutator</i>) keeps running and rewiring pointers, so the graph changes under the tracer.</li>
<li><b>Tri-color abstraction</b>: white = unvisited, grey = visited but its pointers not yet scanned (on the work queue), black = visited and scanned. White objects left at the end are garbage.</li>
<li><b>Strong invariant</b>: no black object points to a white object. If it holds, finishing the grey queue marks everything reachable. <a href="https://go.googlesource.com/proposal/+show/master/design/17503-eliminate-rescan.md" target="_blank" rel="noopener">Design doc 17503</a>.</li>
<li><b>Write barrier</b>: a few instructions the compiler wraps around pointer stores into the heap, so the collector hears about the change. Stack writes get none, because they are far too frequent.</li>
<li><b>Stop-the-world (STW)</b>: every goroutine pauses. Go keeps two short STW phases per cycle (sweep termination and mark termination).</li>
</ul>
<p><img src="img/fig/own-tricolor.svg" alt="Black to white pointers are allowed only when a grey object still reaches the white one; K2 to W2 is the dangerous case." width="720"><br><i>Black to white pointers are allowed only when a grey object still reaches the white one; K2 to W2 is the dangerous case.</i></p>

## §1b · Real-world context · Every Go binary runs it; you steer it with GOGC and GOMEMLIMIT

<h3>What it is</h3>
<p>A small piece of compiler-emitted code that runs on every heap pointer store <i>while a GC mark phase is active</i>. It records the old pointer being overwritten and the new pointer being written, so the concurrent collector can never miss an object that the program moves around. It is why Go's GC pauses are measured in tens to hundreds of microseconds instead of milliseconds.</p>
<h3>Why it exists</h3>
<p>Go 1.5 (2015) shipped a concurrent collector, and by 1.7 the one remaining unbounded pause was the stop-the-world <b>re-scan of goroutine stacks</b> at the end of marking, which the design doc says could take <b>10s to 100s of ms</b> with many goroutines. Go makes goroutines cheap enough to run 10<sup>5</sup> or more, so the pause scaled with a number users control. The hybrid barrier (proposal #17503, Go 1.8) removed it.</p>
<h3>Where it runs</h3>
<p>Every Go binary carries this runtime. I did not check any of these projects' GC settings, only that they are written in Go and so run this collector:</p>
<div class="grid">
<div class="gc"><b>Kubernetes, etcd</b><br>Control-plane servers where a GC pause shows up as API latency or a missed leader heartbeat.</div>
<div class="gc"><b>Docker / moby, containerd</b><br>Daemon processes that hold many goroutines per container.</div>
<div class="gc"><b>Prometheus</b><br>Large pointer-rich in-memory indexes, so GC CPU is a real cost.</div>
<div class="gc"><b>Terraform, Hugo, CockroachDB</b><br>Go programs whose heaps grow to many GB.</div>
</div>
<h3>How you touch it</h3>
<p>You never call the barrier. You steer the collector that turns it on and off:</p>
<pre><code>GOGC=100                  # heap goal = live + (live + roots) * GOGC/100   (default 100)
GOMEMLIMIT=3500MiB        # soft total-memory limit, Go 1.19+
GODEBUG=gctrace=1         # one line per GC cycle on stderr

// in code
debug.SetGCPercent(200)
debug.SetMemoryLimit(3500 &lt;&lt; 20)</code></pre>
<p>A real <code>gctrace</code> line (my machine, <code>gcdemo.go</code>, 14 P):</p>
<pre><code>gc 1 @0.003s 2%: 0.035+0.30+0.061 ms clock, 0.49+0.14/0.34/0+0.86 ms cpu, 3-&gt;4-&gt;0 MB, 4 MB goal, 0 MB stacks, 0 MB globals, 14 P
         ^wall%   ^STW sweep-term + concurrent mark + STW mark-term     ^heap at start-&gt;end-&gt;live   ^goal</code></pre>
<p>The first and last numbers in the clock triple are the two STW pauses. The middle one is the concurrent mark, and it is the phase during which the barrier is on.</p>
<h3>When to care, when not</h3>
<div class="two"><div class="use"><b>Tune GOGC / GOMEMLIMIT when</b> a profile shows <code>runtime.gcAssistAlloc</code>, GC CPU above ~25%, or you run in a container with a hard memory limit.</div><div class="skip"><b>Don't touch it when</b> pauses are already sub-millisecond and memory is not tight. The barrier itself is not tunable, and the alternatives (Java ZGC, Shenandoah) are different runtimes, not flags.</div></div>
<h3>Who should care</h3>
<p>Backend and infra engineers running latency-sensitive Go services (p99), SREs sizing memory in containers, and anyone writing <code>unsafe</code> or cgo code that stores pointers behind the compiler's back, since that bypasses the barrier.</p>

## §2 · The one-liner · "Shade the old and new pointer" hides five questions

<blockquote>"Go's write barrier shades the old and new pointer on every heap store during marking, so the collector can run concurrently."</blockquote>
<p>What that sentence hides:</p>
<ol>
<li><b>Stacks have no barrier at all.</b> So how can the collector trust a stack it scanned a millisecond ago?</li>
<li><b>The two shades fix two different races.</b> Each alone is broken, in a different place.</li>
<li><b>The shipped code is not the textbook pseudocode.</b> It buffers pointers and records both unconditionally.</li>
<li><b>The barrier is off most of the time.</b> It exists only during the mark phase, and the pacer decides when that is.</li>
<li><b>The barrier is not the latency risk anymore.</b> Mark assists, charged to whoever allocates, are.</li>
</ol>

## §3 · The problem · A stop-the-world rescan was the last unbounded pause

<div class="pull"><b>10s–100s ms</b><span>worst-case STW stack re-scan per GC cycle in Go 1.7, per the design doc. Hybrid barrier target: under 50 µs.</span></div>
<p>Go 1.5 (2015) made marking concurrent with a <b>Dijkstra insertion barrier</b>: on <code>*slot = ptr</code>, shade <code>ptr</code>. That keeps the strong invariant for the <i>heap</i>: no black heap object ever points to a white one.</p>
<p>Stacks are the catch. The compiler emits no barrier for stack writes (a local assignment is the most common operation in a program), so a stack can pick up a white pointer silently. Go 1.7 handled this by treating stacks as <b>permanently grey</b>: scanning a stack colors it black, but the moment its goroutine runs again it can hold a white pointer, so it is grey again. Marking therefore cannot finish until every stack touched since its scan is scanned <i>again</i>, with the world stopped, because a running goroutine could re-dirty it.</p>
<table><thead><tr><th>Go 1.7 mark termination</th><th>Cost</th></tr></thead><tbody>
<tr><td>Stacks to re-scan</td><td>every goroutine that ran since its stack was scanned</td></tr>
<tr><td>Pause length</td><td>"10s to 100s of ms" with many goroutines (design doc 17503)</td></tr>
<tr><td>Scales with</td><td>goroutine count and stack depth, both set by the application</td></tr>
</tbody></table>
<p>So the pause was unbounded in exactly the quantity Go encourages you to make large. Proposal 17503 (Clements and Hudson, 2016-10-21) set out to delete the re-scan. Its preliminary experiments put worst-case STW under 50 µs.</p>
<p>Why not put a barrier on stack writes? Because a barrier is a load, a compare and a possible call. Putting that on every local pointer assignment would tax all code, all the time, to protect a rare race. The design goal was the opposite: keep stack writes free and make the <i>heap</i> barrier smart enough that a scanned stack is provably safe.</p>

## §4 · Mental model · A stocktake in a shop that stays open

<p><b>A stocktake in an open shop.</b> Boxes are objects, shelves are heap objects, a clerk's hands are a goroutine stack. White, grey and black are tags. Whenever a clerk takes a box off a shelf or sets one on a shelf, they shout its name and the inspector tags it. The inspector checks a clerk's hands once; after that the clerk can't hide anything.</p>
<p><b>Where it breaks.</b></p>
<ul>
<li>The real inspector is a set of GC worker goroutines on other CPUs, so "shouting" is a memory write racing with their reads, not a conversation. That race is why the shipped barrier never checks the color of the holder (see the mechanism).</li>
<li>Shouting over-tags. A box that is thrown away a moment after being tagged still survives this cycle (floating garbage).</li>
<li>Clerks can also be forced to help count (mark assist), and the analogy has no equivalent of that tax on allocators.</li>
</ul>

## §5 · The mechanism, traced · Replaying one race shows what each shade is for

<p>The simulator in this folder (<code>barrier_sim.py</code>) replays one hand-scheduled race. Below is scenario <b>S1</b>: a goroutine's stack is already scanned and empty; it loads <code>C</code> out of <code>B</code>, then unlinks it from the heap. Toggle the deletion shade off to see the bug.</p>
<p><i>(Step-through widget: see index.html. The trace is reproduced by <code>python3 barrier_sim.py</code>.)</i></p>
<p>The simulator's verdict for all three races under five barriers (<code>python3 barrier_sim.py</code>):</p>
<table><thead><tr><th>Race</th><th style="white-space:nowrap">none</th><th style="white-space:nowrap">Yuasa only</th><th style="white-space:nowrap">Dijkstra only</th><th style="white-space:nowrap">hybrid</th><th style="white-space:nowrap">shade both</th></tr></thead><tbody>
<tr><td>S1 · load C to a <b>black</b> stack, then unlink from heap</td><td class="hb-bad" style="white-space:nowrap">C lost</td><td>ok</td><td class="hb-bad" style="white-space:nowrap">C lost</td><td>ok</td><td>ok</td></tr>
<tr><td>S2 · stack (still <b>grey</b>) is the only holder of C, store C into a black heap object, drop it</td><td class="hb-bad" style="white-space:nowrap">C lost</td><td class="hb-bad" style="white-space:nowrap">C lost</td><td>ok</td><td>ok</td><td>ok</td></tr>
<tr><td>S3 · scanned stack shares an object it already shaded</td><td>ok</td><td>ok</td><td>ok</td><td>ok</td><td>ok</td></tr>
</tbody></table>
<p>Read the table as the whole design. Insertion alone fails S1 (a black stack hides things), which is exactly why Go 1.7 needed to rescan stacks. Deletion alone fails S2 (a grey stack is not a consistent snapshot). The hybrid passes both.</p>
<p><img src="img/fig/own-races.svg" alt="The two races the hybrid barrier must win: S1 needs the deletion shade, S2 needs the insertion shade while the stack is grey." width="720"><br><i>The two races the hybrid barrier must win: S1 needs the deletion shade, S2 needs the insertion shade while the stack is grey.</i></p>
<h3>What the compiler and runtime actually do</h3>
<pre><code>// compiler, for every heap pointer store  *slot = ptr
if runtime.writeBarrier.enabled {          // CMPL runtime.writeBarrier, $0
    buf := gcWriteBarrier2()               // reserves 2 slots (16 B) in this P's wbBuf
    buf[0] = ptr                           // new value  (Dijkstra half)
    buf[1] = *slot                         // old value  (Yuasa half)
}
*slot = ptr

// runtime (mwbbuf.go): per-P buffer, wbBufEntries = 512 pointers = 4 KiB
// fast path = bump a pointer; when full -&gt; wbBufFlush() on the system stack:
//   for each entry: drop nil / tiny values, mark the object, push to the GC work queue</code></pre>
<p><img src="img/fig/own-wbbuf.svg" alt="A heap pointer store, from flag check to the per-P buffer; entries are marked in batches when the buffer fills." width="720"><br><i>A heap pointer store, from flag check to the per-P buffer; entries are marked in batches when the buffer fills.</i></p>
<p>Three differences from the textbook pseudocode, all visible in <code>mbarrier.go</code> and <code>mwbbuf.go</code>:</p>
<ol>
<li><b>Buffered, not immediate.</b> <code>shade</code> does not mark on the spot. Pointers go into a 512-entry per-P buffer and are marked in batches. Entry points <code>gcWriteBarrier1/2/3</code> reserve 8, 16 or 24 bytes; up to 8 pointers per call (<code>wbMaxEntriesPerCall</code>).</li>
<li><b>Unconditional.</b> The comment keeps the conditional pseudocode (<code>if current stack is grey: shade(ptr)</code>) as the proof, but the code path records <i>both</i> pointers every time. The comment gives the reason for not even conditioning on the <i>holder's</i> color: a mutator store followed by a mark-bit load can reorder against the GC's mark-bit store and slot load, and avoiding that needs an expensive memory barrier. So it always greys the pointer. Design doc 17503 lists this "unconditional" shape as a safe, easier-to-reason-about variant that costs about twice as much for most of the mark phase.</li>
<li><b>Buffers drain before termination.</b> <code>gcMarkDone</code> runs a "ragged barrier" with <code>forEachP</code>, flushing every P's buffer and work cache before it may declare marking done.</li>
</ol>
<h3>Stacks, scanned once</h3>
<pre><code>markroot(i):
    gp := stack of goroutine i
    suspendG(gp)                 // or park self in _Gwaiting (waitReasonGarbageCollectionScan)
    scanstack(gp)                // shade every pointer found, set gp.gcscandone
    // never scanned again this cycle: no rescan list, no STW rescan

newobject during mark:  gcmarknewobject()   // allocate black</code></pre>
<p>Allocate-black is a precondition the design doc names. Go already allocated black, so the hybrid barrier changed nothing there. Whether a goroutine's stack created mid-cycle is born black is something I did not verify (it lives in <code>proc.go</code>, which I did not read).</p>

## §6 · The math · Two conditions to lose an object, and pacing as arithmetic

<h3>1 · When is an object lost?</h3>
<p>An object <i>x</i> is freed wrongly only if two things both happen during marking:</p>
<div class="eq">(1) the mutator stores a pointer to white <i>x</i> into a <b>black</b> object<br>(2) every path from a grey object to <i>x</i> through white objects is destroyed before the GC follows it<small>→ in plain terms: a black object will never be looked at again, so a pointer hidden there is invisible, and removing the last "grey-protected" path means nobody else will find it either.</small></div>
<p>That is the classic two-condition result for concurrent tracing. A barrier only has to break <i>one</i> condition:</p>
<ul>
<li><b>Dijkstra insertion</b> <code>shade(ptr)</code> breaks (1): a black object never gains a white pointer. This is the <i>strong</i> invariant.</li>
<li><b>Yuasa deletion</b> <code>shade(*slot)</code> breaks (2): whatever was reachable when marking began stays reachable-or-shaded (snapshot-at-the-beginning).</li>
</ul>
<h3>2 · The weak invariant the hybrid actually keeps</h3>
<div class="eq">every white object pointed to by a black object is reachable from some grey object through a chain of white objects<small>→ in plain terms: a black object may point at a white one, but only if a grey object still has a path to that white one. The collector will find it when it gets to the grey object.</small></div>
<p>The design doc is explicit that the hybrid barrier <b>does not</b> keep the strong invariant: a black goroutine may store a white pointer into a black heap object without shading it. What it keeps is this weaker, "grey-protected" form, which is enough because Yuasa shading protects the chain.</p>
<h3>3 · Why the insertion half may stop once the stack is black</h3>
<p>Right after <code>scanstack</code>, the stack points only to objects the scan shaded. For a scanned stack to hide an object <i>y</i> in a black heap object it must first hold a pointer to <i>y</i> that the GC has not seen. It can only acquire one by (a) loading it from the heap, which needs the heap slot to be overwritten later or <i>y</i> to be grey-protected, and Yuasa covers the overwrite; or (b) allocating it, which is black. So <code>shade(ptr)</code> adds nothing for a black stack. For a <b>grey</b> stack it is required (race S2).</p>
<h3>4 · The pacer's arithmetic</h3>
<p>The barrier only runs while the collector is marking, and the pacer decides when that starts. From <code>mgcpacer.go</code>:</p>
<div class="eq">heapGoal = heapMarked + (heapMarked + lastStackScan + globalsScan) × GOGC / 100<small>→ in plain terms: after a cycle, let the heap grow by GOGC percent of (live heap + roots) before the next one finishes. Since Go 1.18 stacks and globals count, so a program with a huge number of goroutines gets a bigger goal.</small></div>
<p><img src="img/fig/own-cycle.svg" alt="Heap size over a few cycles for the worked example: marking starts inside the trigger band, the barrier runs until the mark ends, and the goal is 203 MB." width="720"><br><i>Heap size over a few cycles for the worked example: marking starts inside the trigger band, the barrier runs until the mark ends, and the goal is 203 MB.</i></p>
<p>Worked example: <code>heapMarked</code> = 100 MB, stacks 2 MB, globals 1 MB, GOGC = 100: goal = 100 + (100 + 2 + 1) × 1 = <b>203 MB</b>. The goal is clamped to at least a minimum heap of 4 MiB × GOGC/100.</p>
<div class="eq">trigger = clamp(goal − runway, minTrigger, maxTrigger)<br>minTrigger ≥ heapMarked + (goal − heapMarked) × 45/64 &nbsp;&nbsp; maxTrigger ≈ heapMarked + (goal − heapMarked) × 61/64<small>→ in plain terms: start marking early enough that the expected work finishes by the goal, but never earlier than ~70% or later than ~95% of the way from live heap to goal (for small heaps). The earlier it starts, the longer the barrier is on.</small></div>
<p>With the example above, the trigger lies between about 100 + 103 × 0.70 ≈ <b>172 MB</b> and 100 + 103 × 0.95 ≈ <b>198 MB</b>. <code>runway</code> is the pacer's estimate of how much the program allocates during the mark.</p>
<h3>5 · Mark assist</h3>
<div class="eq">assistWorkPerByte = scanWorkRemaining / (heapGoal − heapLive)<small>→ in plain terms: if marking has 40 MB of scanning left and only 20 MB of room before the goal, each byte you allocate must be paid for with 2 bytes of scanning.</small></div>
<p>An allocating goroutine's debt <code>gcAssistBytes</code> goes negative as it allocates; it must do <code>assistWorkPerByte × debt</code> scan work, but never less than <code>gcOverAssistWork</code> = 64 KiB per assist, so it builds credit instead of assisting on every allocation. Background workers target <code>gcBackgroundUtilization</code> = 25% of CPU; assists cover whatever gap remains. On GOMAXPROCS = 8 that is exactly 2 dedicated mark workers.</p>
<p>The ratio is published with separate atomic stores, so a reader can briefly see a skewed pair (a source comment says so).</p>

## §7 · Why it works · A scanned stack is shaded once and then cannot hide anything

<p><b>Core insight:</b> a stack only needs a barrier-protected hand-off at the moment it is scanned. After that, the deletion shade keeps it from smuggling anything out of the heap, and everything already on it was shaded by the scan. So a scanned stack is <i>permanently</i> safe for the rest of the cycle and the re-scan list disappears.</p>
<p><b>Ablation: remove each piece and see what breaks</b> (rows are the simulator's results):</p>
<table><thead><tr><th>Remove</th><th>What breaks</th></tr></thead><tbody>
<tr><td><code>shade(*slot)</code> (deletion)</td><td>S1: a black stack loads C and unlinks it; C is freed while held. Go 1.7 papered over this by rescanning stacks in STW.</td></tr>
<tr><td><code>shade(ptr)</code> while the stack is grey</td><td>S2: a grey stack stores its only pointer into a black object and drops it; the object is lost.</td></tr>
<tr><td>"scan the stack once"</td><td>Back to Go 1.7: STW rescan of every goroutine that ran, 10s–100s of ms.</td></tr>
<tr><td>Allocate-black during mark</td><td>A fresh object would be white and could be stored into a black object unseen. Design doc lists allocate-black as a requirement; Go already did it (<code>gcmarknewobject</code>).</td></tr>
<tr><td>Draining wbBuf before termination</td><td>Pointers sitting in a buffer are not yet marked, so mark termination could finish with work still hidden in a per-P buffer. <code>gcMarkDone</code> flushes with <code>forEachP</code> first.</td></tr>
</tbody></table>
<p>The price is a barrier that is more conservative than the minimum: because it records both pointers regardless of colors, it marks objects that a precise barrier would skip, and some of them die during the cycle anyway (<i>floating garbage</i>, reclaimed next cycle).</p>

## §8 · Design knobs & alternatives · GOGC and GOMEMLIMIT move the trade; the barrier stays fixed

<table><thead><tr><th>Knob</th><th>Effect</th><th>Trade-off</th></tr></thead><tbody>
<tr><td><code>GOGC</code> (default 100)</td><td>Heap goal = live + (live + roots) × GOGC/100</td><td>Doubling it roughly doubles heap overhead and halves GC CPU (Go GC guide)</td></tr>
<tr><td><code>GOMEMLIMIT</code> (Go 1.19)</td><td>Soft total-memory limit; goal is the min of the GOGC goal and the limit (minus non-heap memory, ~3% headroom)</td><td>GC CPU is capped near 50% over a window so a too-tight limit slows the program instead of thrashing. Leave 5–10% headroom (guide)</td></tr>
<tr><td><code>GOMAXPROCS</code></td><td>Sets the 25% dedicated-worker budget</td><td>Fewer Ps means fractional workers and more assist</td></tr>
<tr><td>Heap minimum (4 MiB × GOGC/100)</td><td>Floor for the goal on tiny heaps</td><td>Not directly settable</td></tr>
<tr><td>Memory ballast (old trick)</td><td>A large pointer-free allocation inflates "live" so cycles run less often. Twitch reported ~99% less assist work and ~45% better p99 at peak (2019, vendor blog)</td><td>Mostly superseded by <code>GOMEMLIMIT</code> + <code>GOGC</code></td></tr>
</tbody></table>
<h3>Barrier alternatives and why Go chose this one</h3>
<table><thead><tr><th>Approach</th><th>Needs</th><th>Used by</th></tr></thead><tbody>
<tr><td>Insertion only (Dijkstra)</td><td>STW rescan of stacks (or barriers on stacks)</td><td>Go 1.5–1.7</td></tr>
<tr><td>Deletion only (Yuasa / SATB)</td><td>A consistent snapshot, so all stacks scanned atomically at the start</td><td>Shenandoah's marking barrier, G1 (SATB)</td></tr>
<tr><td>Hybrid, conditional</td><td>Know whether the current stack is grey</td><td>Design doc's proof shape</td></tr>
<tr><td>Hybrid, unconditional</td><td>Nothing; ~2× the cost of the conditional form for most of the mark phase</td><td>What Go's buffer effectively does</td></tr>
<tr><td>Load barrier (colored pointers)</td><td>Cost on every pointer <i>load</i>, pointer metadata</td><td>ZGC</td></tr>
</tbody></table>
<p>Go bets that stores are rarer than loads, that a non-moving non-generational collector is simple enough to keep latency low, and that the barrier is off most of the time. The same bet fails for programs that mutate pointers heavily during long marks.</p>

## §9 · Where it breaks · Real bugs, assist stalls and the unsafe escape hatch

<h3>Real bugs (all historical; no open barrier-correctness bug surfaced in my search)</h3>
<ul>
<li><b>Wasm deletion barrier greyed the wrong object</b> (<a href="https://golang.org/issue/30873" target="_blank" rel="noopener">#30873</a>, #30872; fixed 2019, backported to 1.11/1.12): a reachable object could go unmarked. Lost-object bug in the exact class this dive is about.</li>
<li><b>Preemption inside barrier code</b> (<a href="https://golang.org/issue/22987" target="_blank" rel="noopener">#22987</a>, fixed 2017): a preemption inside <code>heapBits.bits</code> could lose a pointer and overflow the per-P buffer. Fixed with <code>go:nosplit</code>.</li>
<li><b>Crashes in <code>gcWriteBarrier</code>/<code>wbBufFlush</code></b> (#14149, #15293, <a href="https://golang.org/issue/42249" target="_blank" rel="noopener">#42249</a>): maintainers attributed them to heap corruption from cgo or <code>unsafe</code>; the barrier is where a bad pointer first gets dereferenced.</li>
</ul>
<h3>Costs</h3>
<ul>
<li><b>Mark assist latency</b> is the main user complaint now. No assist credit exists at cycle start, so allocating goroutines pay early. Field reports include hundreds of ms stalls with 1–2 ms STW pauses (<a href="https://github.com/golang/go/issues/16293" target="_blank" rel="noopener">#16293</a>) and one anecdotal ~10× latency during GC in <code>runtime.gcAssistAlloc</code> (a mailing-list thread). Pacer meta-issue: <a href="https://github.com/golang/go/issues/42430" target="_blank" rel="noopener">#42430</a>.</li>
<li><b>Barrier overhead</b> (<a href="https://github.com/golang/go/issues/22460" target="_blank" rel="noopener">#22460</a>): usually small because the barrier is off, but a few percent in some programs such as the compiler. A buffered fast path was about 4× faster on amd64 for the single-pointer case, about 2% on GC-heavy apps. <a href="https://github.com/golang/go/issues/20005" target="_blank" rel="noopener">#20005</a> (open) is about the code size of the enabled-flag check.</li>
<li><b>Floating garbage</b>: over-shading keeps some dying objects for one more cycle.</li>
<li><b>Stack scanning still costs CPU</b>, just not pause time. It also feeds the pacer (<code>lastStackScan</code>).</li>
</ul>
<div class="callout mis"><b>Misconceptions.</b> (1) "Stacks are rescanned at the end." Not since the hybrid barrier. (2) "The write barrier is always on." It is checked on every heap store but only <i>executes</i> during marking. (3) "GC latency means STW pauses." STW is now tens of µs; assists charged to allocating goroutines are the larger tail.</div>
<div class="callout gotcha"><b>unsafe / cgo.</b> A pointer written through <code>unsafe</code> arithmetic or from C bypasses the compiler's barrier. If marking is running, the object it points to can be freed. Use <code>GODEBUG=cgocheck</code> and the race/asan builds.</div>

## §10 · In the wild · The runtime buffers, records both, and allocates black

<p>Where the shipped runtime departs from the paper-and-pseudocode version:</p>
<ul>
<li><b>Buffered shading.</b> 512-entry per-P <code>wbBuf</code>; <code>next</code> and <code>end</code> are <code>uintptr</code> so updating them needs no barrier of its own.</li>
<li><b>Unconditional recording</b> of old and new pointers, justified by memory-ordering cost (see <code>mbarrier.go</code>).</li>
<li><b>Fast path saves two registers.</b> <code>gcWriteBarrier1/2/3</code> set a reserve size and jump to one shared body that only saves R12 and R13 on amd64; the slow path (flush) saves every general register.</li>
<li><b>Checkmark mode.</b> A debug mode re-marks the heap and shades every buffer entry to verify nothing was missed.</li>
<li><b>Stack scan as a root job.</b> <code>markroot</code> → <code>suspendG</code> → <code>scanstack</code> (self-scans move the goroutine to <code>_Gwaiting</code>), with <code>gcscandone</code> making it once-per-cycle.</li>
<li><b>Allocate-black</b> via <code>gcmarknewobject</code> during <code>_GCmark</code> and <code>_GCmarktermination</code>.</li>
</ul>
<h3>How other runtimes place their barriers</h3>
<table><thead><tr><th>Runtime</th><th>Barrier</th><th>Moves objects?</th></tr></thead><tbody>
<tr><td>Go</td><td>Hybrid store barrier, only during mark</td><td>No (non-moving)</td></tr>
<tr><td>Java ZGC</td><td>Load barrier (colored pointers), no store barrier for marking</td><td>Yes, concurrently</td></tr>
<tr><td>Shenandoah (JDK 13+)</td><td>SATB store barrier + Baker-style load-reference barrier</td><td>Yes, concurrently</td></tr>
<tr><td>Java G1</td><td>Store barriers (SATB + card marking); reworked in 2025 per a Schatzl blog post</td><td>Yes (regions)</td></tr>
</tbody></table>
<p>The pattern: a runtime that does not move objects needs only a marking barrier; one that moves them concurrently needs the more expensive load-side machinery.</p>

## §11 · Frontier · The barrier is settled; the work moved to locality and pacing

<div class="callout flag"><b>Plain statement:</b> the barrier design is settled. It has been the same hybrid shape since Go 1.8 (2017), and I found no 2024–2026 paper proposing a new Go write barrier (four extended searches, several dead ends). The active work moved to <i>how the marking is ordered</i> and <i>how the pacer reasons</i>, plus neighboring runtimes' barriers.</div>
<table><thead><tr><th>Year</th><th>Item</th><th>What changed</th></tr></thead><tbody>
<tr><td>2026</td><td><a href="https://go.dev/doc/go1.26" target="_blank" rel="noopener">Go 1.26: Green Tea GC on by default</a></td><td>Mark/scan works on whole pages instead of object by object, for locality. Google expects <b>10–40%</b> less GC CPU, ~10% more from vector instructions on newer amd64. Opt out with <code>GOEXPERIMENT=nogreenteagc</code>, expected removed in 1.27.</td></tr>
<tr><td>2025</td><td><a href="https://go.dev/blog/greenteagc" target="_blank" rel="noopener">Green Tea as a Go 1.25 experiment</a> (Knyszek and Clements)</td><td>Opt-in via <code>GOEXPERIMENT=greenteagc</code>; InfoQ reported early higher latency, fixed for 1.26 (secondary source). Tracking issue <a href="https://github.com/golang/go/issues/73581" target="_blank" rel="noopener">#73581</a>.</td></tr>
<tr><td>2025</td><td><a href="https://tschatzl.github.io/2025/02/21/new-write-barriers.html" target="_blank" rel="noopener">New write barriers for G1</a> (Schatzl, blog)</td><td>Java's G1 reworked its store barriers: a data point that barrier cost is still being engineered down elsewhere. Not peer-reviewed.</td></tr>
<tr><td>2026</td><td>Go 1.26 experimental <code>goroutineleak</code> profile</td><td>Uses the GC's reachability to find goroutines blocked forever. Not a barrier change; shows marking reused as a tool.</td></tr>
<tr><td>2022</td><td>Go 1.19 <code>GOMEMLIMIT</code></td><td>A memory-limit goal beside GOGC, with a ~50% CPU cap (<a href="https://go.dev/doc/gc-guide" target="_blank" rel="noopener">GC guide</a>).</td></tr>
<tr><td>~2021</td><td><a href="https://github.com/golang/go/issues/44167" target="_blank" rel="noopener">Pacer redesign #44167</a></td><td>Count stacks and globals as GC work; a feedback controller for assists. Its shipping release (reportedly 1.18) I did not verify against release notes.</td></tr>
</tbody></table>
<p>Not verified, so not relied on: the LXR collector (reference counting + concurrent trace; I could not confirm venue and year from snippets) and a 2025 Blackburn-group item whose title was truncated.</p>

## §11b · Open problems · Assist latency and the 25% budget are still unsettled

<ul>
<li><b>Assist tail latency.</b> Assists tax whoever allocates when marking falls behind, and no credit exists at cycle start. Fixing it means starting marking earlier (more CPU, more time with the barrier on) or slowing allocation (latency) or growing the heap (memory). The obvious fix just moves the cost. I found no recent Go-team statement; "open" here is inferred from the long-running issues (#16293, #42430).</li>
<li><b>The 25% worker budget at huge goroutine counts.</b> How the fixed CPU share interacts with 10<sup>6</sup> goroutines' stack-scan work: I found no discussion. Treat as unresearched.</li>
<li><b>Barrier code size and check cost.</b> #20005 (open): the enabled-flag test uses an absolute address and accounts for a large share of barrier instructions; per-G shadows were proposed. Whether it shipped is unconfirmed.</li>
<li><b>Does Green Tea change barrier cost?</b> The sources I found do not say.</li>
<li><b>Generational or compacting Go.</b> Go stays non-moving and non-generational; whether that stays optimal for pointer-heavy heaps is contested. I did not research the current proposals, so no position is attributed here.</li>
</ul>
<p>Why it stays hard: every lever (start earlier, assist harder, grow the heap, buffer more) trades latency, CPU or memory against another one, and the workload decides which hurts.</p>

## §12 · Lineage · 1978 insertion, 1990 deletion, 2017 hybrid

<ol>
<li><b>1978</b> · Dijkstra et al., on-the-fly GC: insertion barrier, tri-color invariant. <i>(title and venue from memory, not fetched)</i></li>
<li><b>1990</b> · Yuasa, real-time GC: deletion barrier, snapshot-at-the-beginning. <i>(same caveat)</i></li>
<li><b>2007</b> · Metronome (IBM real-time Java): a "double write barrier" the design doc equates to Go's hybrid.</li>
<li><b>2015</b> · Go 1.5: concurrent tri-color collector, <a href="https://go.dev/blog/go15gc" target="_blank" rel="noopener">Hudson's post</a>.</li>
<li><b>2016–17</b> · Go 1.7 coarsened Dijkstra + permagrey stacks → proposal <a href="https://github.com/golang/proposal/blob/master/design/17503-eliminate-rescan.md" target="_blank" rel="noopener">17503</a> → hybrid barrier in Go 1.8.</li>
<li><b>Later</b> · Buffered barrier (#22460), pacer redesign (#44167), <code>GOMEMLIMIT</code> (1.19, 2022).</li>
<li><b>2025–26</b> · Green Tea: page-oriented marking, default in Go 1.26.</li>
</ol>

## §13 · Hands-on · Break the barrier in a simulator, then count goroutines

<h3>Experiment 1 · Replay the races (2 min)</h3>
<pre><code>python3 barrier_sim.py</code></pre>
<p>Prints the barrier × race table and the S1 trace. Then break it: in <code>heap_store</code>, delete the line <code>self.shade(old, "deletion")</code> from the <code>hybrid</code> branch and rerun. S1 starts losing C. Add a fourth scenario where a <b>new</b> object is allocated white during marking and stored into a black object: you will need allocate-black to make it pass.</p>
<h3>Experiment 2 · Watch STW stay flat as goroutines grow (5 min)</h3>
<pre><code>go run gcdemo.go -g 1000
go run gcdemo.go -g 100000
go run gcdemo.go -g 500000
GODEBUG=gctrace=1 go run gcdemo.go -g 100000 2&gt;&amp;1 | grep '^gc ' | head</code></pre>
<p>My run (Go 1.27.2, 14 P, Apple silicon, 3 s of pointer churn):</p>
<pre><code>goroutines=1000   GCs=9 max STW pause=62us  total STW=0.4ms
goroutines=100000 GCs=9 max STW pause=133us total STW=0.4ms
goroutines=500000 GCs=9 max STW pause=104us total STW=0.4ms</code></pre>
<p>The worst pause stays around 100 µs from 1,000 to 500,000 goroutines. That is the headline of the design doc, observed. <b>Caveat:</b> the goroutines are idle and the heap is small, so this shows the absence of a goroutine-count-scaling STW, not that your service is pause-free. Also try <code>GOGC=25</code> and <code>GOGC=400</code> and watch the cycle count and the <code>GCCPUFraction</code> printed at the end.</p>

## §14 · Question ladder · Test yourself

### Mechanism

- In race S1 (black stack, nil store), what does the barrier do on <code>B.f = nil</code>, step by step?
  <details><summary>Answer</summary>The compiler tests <code>runtime.writeBarrier</code>; enabled, it reserves slots in the P's buffer and records the old value (C) and new value (nil). Nil is dropped at flush; C is marked grey and queued. C survives even though the heap no longer reaches it.</details>

- When is a goroutine's stack scanned, and what happens to it afterwards?
  <details><summary>Answer</summary>As a root job (<code>markroot</code>): the goroutine is suspended (or parks itself in <code>_Gwaiting</code>), <code>scanstack</code> shades every pointer found and sets <code>gcscandone</code>. It is not scanned again this cycle.</details>

- What does <code>gcMarkDone</code> do with the write-barrier buffers, and why?
  <details><summary>Answer</summary>It runs a ragged barrier with <code>forEachP</code>, flushing each P's buffer and work cache. Pointers still in a buffer are unmarked, so termination before flushing could miss reachable objects.</details>

- How does a mark assist decide how much to scan?
  <details><summary>Answer</summary><code>assistWorkPerByte = scanWorkRemaining / (heapGoal − heapLive)</code>. The goroutine's negative <code>gcAssistBytes</code> debt is multiplied by it, with a floor of 64 KiB of scan work per assist so it builds credit.</details>

### Why

- Why shade the <i>old</i> pointer instead of only the new one?
  <details><summary>Answer</summary>A black stack can load a white pointer from the heap and then unlink it. An insertion barrier ignores the overwrite. Shading the old value keeps it reachable-or-shaded (race S1).</details>

- Why is the insertion shade only needed while the stack is grey?
  <details><summary>Answer</summary>A freshly scanned stack points only to shaded objects, and the deletion shade stops it hiding others. A grey stack may hold the only pointer to an object and store it into a black object (race S2).</details>

- Why not put a barrier on stack writes instead?
  <details><summary>Answer</summary>Stack pointer writes are the most frequent operation in a program. A barrier there would tax all code to protect a rare race; the design keeps stack writes free and makes the heap barrier sufficient.</details>

- Why does the shipped barrier record both pointers regardless of the holder's color?
  <details><summary>Answer</summary>Checking the holder's mark bit races with the GC's own mark-bit store; on x86 the result can be r1==r2==0 without an expensive memory barrier. Always greying the pointer avoids the barrier (<code>mbarrier.go</code> comment).</details>

### Counterfactual

- What if Go allocated white during marking?
  <details><summary>Answer</summary>A new object could be stored into a black object and never be seen. The hybrid barrier requires allocate-black (design doc), which Go already did via <code>gcmarknewobject</code>.</details>

- What if the pacer started marking at 99% of the goal instead of ~70–95%?
  <details><summary>Answer</summary>The barrier would be on for less time but there is little runway: scan work must finish before the goal, so assist ratios spike and allocating goroutines pay latency, or the heap overshoots.</details>

- What if GOGC were 200 on a service with 1 GB live heap?
  <details><summary>Answer</summary>The goal is roughly 3× live instead of 2×, so cycles are about half as frequent, GC CPU roughly halves, and peak heap overhead roughly doubles (GC guide).</details>

- What changes if you remove the 25% background-worker target?
  <details><summary>Answer</summary>Marking would be paced only by assists, so allocating goroutines would do all the work when behind, concentrating latency in the application's own request path.</details>

### Adversarial

- How could you cause a use-after-free in Go despite the barrier?
  <details><summary>Answer</summary>Store a pointer through <code>unsafe</code> arithmetic or from C during marking: the compiler emitted no barrier, so the object can stay white and be freed. Checks: <code>GODEBUG=cgocheck</code>, race and asan builds.</details>

- How would you make a service suffer mark-assist latency on purpose?
  <details><summary>Answer</summary>Allocate heavily while marking runs and the pacer is behind: assists bill each allocation. A sharp change in live heap size is a known trigger (pacer issues #42430, #44167).</details>

- What would a bug that greyed the wrong object cause?
  <details><summary>Answer</summary>A reachable object left white and freed: memory corruption. It happened in the wasm deletion barrier (#30872/#30873, fixed 2019).</details>

### Connection

- How is this like OS copy-on-write or page-table dirty bits?
  <details><summary>Answer</summary>All three track mutation lazily: a barrier or fault records "this changed" so a background process can catch up later. The stack scan once-and-done mirrors scanning a snapshot.</details>

- Why do ZGC and Shenandoah need load-side barriers while Go does not?
  <details><summary>Answer</summary>They move live objects concurrently, so a loaded pointer might be stale. Go never moves heap objects, so it only needs to guard marking.</details>

- How does Green Tea relate to the barrier?
  <details><summary>Answer</summary>It changes the order and granularity of marking (by page, for locality), not the invariant. The barrier still guards correctness; I found no report of how Green Tea changes barrier cost.</details>

### Open

- Can assist tail latency be eliminated without more CPU or memory?
  <details><summary>Answer</summary>Not by a known method: starting earlier costs barrier-on time and CPU, assisting harder moves latency into the request path, a bigger heap costs memory. The trade is workload dependent.</details>

- Would a generational Go collector pay for the barrier it would need?
  <details><summary>Answer</summary>Contested and not researched here: a generational collector needs a remembered-set barrier on top of the marking barrier. Whether pointer-heavy Go heaps repay that cost is unsettled in my sources.</details>


## §15 · Go deeper next · Three dives that build on this

<ol>
<li><b>Green Tea GC:</b> page-oriented marking, why locality beats per-object work queues, vectorized scanning.</li>
<li><b>ZGC colored pointers and load barriers:</b> how a collector that moves objects concurrently pays on reads instead of writes.</li>
<li><b>Generational and card-marking barriers (G1):</b> remembered sets, SATB, and why Java's store barriers got reworked.</li>
</ol>
<p><code>barrier_sim.py</code> and <code>gcdemo.go</code> (in this folder) are the two experiments from the hands-on card.</p>

## Sources · Design docs, runtime source and issues

<h3>Design docs and posts</h3>
<ul>
<li><a href="https://github.com/golang/proposal/blob/master/design/17503-eliminate-rescan.md" target="_blank" rel="noopener">Proposal 17503: Eliminate STW stack re-scanning</a> (Clements, Hudson; 2016-10-21). Read in full for barrier, invariants, alternatives.</li>
<li><a href="https://github.com/golang/proposal/blob/master/design/17505-concurrent-rescan.md" target="_blank" rel="noopener">Proposal 17505: Concurrent stack re-scanning</a> (listed in search; not read).</li>
<li><a href="https://go.dev/blog/go15gc" target="_blank" rel="noopener">Hudson, "Go GC: Prioritizing low latency and simplicity" (2015)</a></li>
<li><a href="https://go.dev/doc/gc-guide" target="_blank" rel="noopener">A Guide to the Go Garbage Collector</a></li>
<li><a href="https://go.dev/blog/greenteagc" target="_blank" rel="noopener">Green Tea GC</a> · <a href="https://go.dev/doc/go1.26" target="_blank" rel="noopener">Go 1.26 release notes</a></li>
<li><a href="https://go.dev/blog/ismmkeynote" target="_blank" rel="noopener">ISMM keynote, "Getting to Go"</a> (appeared in results; summary only)</li>
</ul>
<h3>Runtime source (golang/go master, as fetched 2026-10-17)</h3>
<ul>
<li><a href="https://github.com/golang/go/blob/master/src/runtime/mbarrier.go" target="_blank" rel="noopener">mbarrier.go</a> · <a href="https://github.com/golang/go/blob/master/src/runtime/mwbbuf.go" target="_blank" rel="noopener">mwbbuf.go</a> · <a href="https://github.com/golang/go/blob/master/src/runtime/mgcmark.go" target="_blank" rel="noopener">mgcmark.go</a> · <a href="https://github.com/golang/go/blob/master/src/runtime/mgcpacer.go" target="_blank" rel="noopener">mgcpacer.go</a> · <a href="https://github.com/golang/go/blob/master/src/runtime/mgc.go" target="_blank" rel="noopener">mgc.go</a> · <a href="https://github.com/golang/go/blob/master/src/runtime/asm_amd64.s" target="_blank" rel="noopener">asm_amd64.s</a></li>
</ul>
<h3>Issues</h3>
<ul>
<li><a href="https://github.com/golang/go/issues/22460" target="_blank" rel="noopener">#22460</a> · <a href="https://github.com/golang/go/issues/20005" target="_blank" rel="noopener">#20005</a> · <a href="https://github.com/golang/go/issues/16293" target="_blank" rel="noopener">#16293</a> · <a href="https://github.com/golang/go/issues/42430" target="_blank" rel="noopener">#42430</a> · <a href="https://github.com/golang/go/issues/44167" target="_blank" rel="noopener">#44167</a> · <a href="https://github.com/golang/go/issues/73581" target="_blank" rel="noopener">#73581</a> · <a href="https://golang.org/issue/30873" target="_blank" rel="noopener">#30873</a> · <a href="https://golang.org/issue/22987" target="_blank" rel="noopener">#22987</a> · <a href="https://golang.org/issue/42249" target="_blank" rel="noopener">#42249</a></li>
</ul>
<h3>Other runtimes and articles</h3>
<ul>
<li><a href="https://developers.redhat.com/blog/2019/06/27/shenandoah-gc-in-jdk-13-part-1-load-reference-barriers" target="_blank" rel="noopener">Shenandoah in JDK 13: load reference barriers</a> · <a href="https://tschatzl.github.io/2025/02/21/new-write-barriers.html" target="_blank" rel="noopener">New write barriers for G1</a> · <a href="https://dl.acm.org/doi/full/10.1145/3538532" target="_blank" rel="noopener">ZGC deep dive (ACM)</a></li>
<li><a href="https://blog.twitch.tv/en/2019/04/10/go-memory-ballast-how-i-learnt-to-stop-worrying-and-love-the-heap/" target="_blank" rel="noopener">Twitch: Go memory ballast</a> (vendor blog)</li>
<li><a href="https://infoq.com/news/2025/11/go-green-tea-gc/" target="_blank" rel="noopener">InfoQ on Green Tea</a> (secondary)</li>
</ul>
<h3>Claims I could not verify</h3>
<ul>
<li>Dijkstra 1978 and Yuasa 1990 titles and venues (cited from the design doc's keys and memory); Hudson '97 and Auerbach '07.</li>
<li>The two-condition lost-object statement is the standard result in the GC literature; I did not fetch a paper for it.</li>
<li>Whether the shipped Go 1.8 barrier matched the design doc at that release; the current <i>source</i> was read, the 1.8 commit was not. The "unconditional" shape is read from the current <code>mbarrier.go</code> comment and the runtime's buffer code, not from a release note.</li>
<li>The exact compiler-emitted store sequence (which slot gets old vs new); the shown sequence is a faithful sketch, not disassembly.</li>
<li>Pacer redesign release (1.18), pacer stack-scan numbers (500k idle goroutines, 15 ms → 238 µs, commit 2a889b9d) and Twitch's figures are secondary or historical.</li>
<li>Application adoption (Kubernetes, etcd, etc.): only that they are written in Go.</li>
<li>That a goroutine's stack created mid-cycle is born black (<code>proc.go</code> not read).</li>
</ul>


## Files in this folder

- `barrier_sim.py`: replays three races under five barriers.
- `gcdemo.go`: idle goroutines + pointer churn, prints STW pauses.
- `gen_svgs.py`: generates the hero, card visuals, original figures and story.

