# io_uring: shared rings, zero-syscall I/O, and the security bill

`OS/kernels · io_uring (SQ/CQ rings, inline-then-punt execution, security fallout) · hard`

Date: 2026-10-03. Tags used below: **[V]** = checked against a source. **Revision note (2026-10-03):** PostgreSQL `io_method` default, Google kCTF figures, libuv 1.45/1.49 and the Alibaba ~10% figure were re-checked against primary pages in a follow-up pass; QEMU 5.0, Glommio, Seastar, Windows IoRing details and all of section 11 were NOT independently re-verified; code snippets were not compiled (see 1b and 13). Original verification tags: **[V]** read in primary source during research, **[K]** from memory/secondary, unverified. Flagged where it matters.

## 0b. Plain-English first (no jargon)

**Explain it simply.** Picture a busy cook who needs things from a helpful pantry assistant. The old way: the cook walks over, asks for one thing, waits, walks back, then repeats for every single item. Most of the time goes into the walking back and forth, not the fetching. io_uring replaces that with two trays on a shared counter: an "orders" tray the cook drops notes into, and a "done" tray the assistant drops results into. The cook stacks up several notes, rings the bell once, and goes back to cooking.

When the bell rings, the assistant first does whatever is within arm's reach right away. Anything that has to wait (a parcel that has not arrived yet, a book in the basement) gets handled without the assistant standing around: either "I'll tap you when it shows up" or "a helper will go fetch it". Results land in the done tray, each with the number from the original note so the cook can match them up. The point: fewer interruptions and many errands in flight at once.

**Everyday example.** Sam is cooking dinner and writes three notes: (1) "read me the first page of the recipe card", (2) "tell me when the grocery parcel arrives", (3) "bring the big cookbook from the basement". Sam numbers them 1, 2, 3, drops them in the orders tray, and rings the bell once. The assistant grabs the recipe card from the shelf right there and puts the page in the done tray before Sam has even looked up. For the parcel, nothing has arrived, so the assistant says "I'll flag it when the doorbell goes" and does not wait at the door. The basement book is far away, so a helper is sent. Later Sam glances at the done tray: slip 1 is there already, then slip 3 when the helper returns, then slip 2 when the parcel finally arrives. Sam matches each slip to its note by number. One bell, three errands, no waiting around, and results can come back in any order.

Now the same thing, technically.

## 1. Bare-minimum context

- Syscall = user→kernel mode switch. Cost = entry/exit + mitigations (post-Spectre/Meltdown), not the work itself. [paper §1]
- Readiness vs completion: epoll says "fd *can* be read"; you still do the `read`. Completion API says "your read *is done*, here are the bytes".
- Buffered I/O goes through the page cache; O_DIRECT bypasses it. Linux aio only did true async for O_DIRECT.
- SPSC ring buffer: single-producer/single-consumer queue with `head` (consumer) and `tail` (producer) indexes; lock-free with proper memory ordering.
- Acquire/release: producer *releases* (publishes) tail after writing entry; consumer *acquires* tail before reading entry. Entry visible iff tail visible.
- Little's law: in-flight ops = throughput × latency. NVMe needs deep queues to hit rated IOPS.

## 1b. Real-world context (where, how, why)

Tags as above: **[V]** seen in a fetched/searched source during this backfill pass; **[K]** not re-verified.

### What it is
A Linux kernel interface (since 5.1, 2019) for asynchronous I/O. The app and kernel share two ring buffers in memory: the app drops request descriptors (SQEs) on the submission queue, the kernel posts results (CQEs) on the completion queue, and one `io_uring_enter(2)` call can submit many requests and wait for completions. [V man7 io_uring(7)] Cloudflare's framing: it is "a full-blown runtime for processing I/O requests", with its own worker threads and queues. [V Cloudflare]

### Why it exists
- Before: Linux aio (O_DIRECT only, copies, >=2 syscalls per I/O) and epoll (readiness only, nothing for regular files), so apps bolted on thread pools. Details in section 3.
- Storage apps port from libaio easily, but networking "required rethinking": swapping epoll for io_uring notifiers "does not lead to an outcome that fully takes advantage" of it; the win is a changed event-loop design. [V liburing wiki "io_uring and networking in 2023"]
- Cost of not having it: a user-space thread pool (libuv-style) with context switches even for cached reads, or giving up deep queue depths from one thread.

### Where it's used (verified in this pass)
| System | Role |
|---|---|
| **PostgreSQL 18** | `io_method = io_uring` selects it for the new async I/O subsystem (alternatives `worker` and `sync`); needs a build with `--with-liburing` / `-Dliburing`. **Default is `worker`**: the PG 18 docs say "The default is `worker`" [V postgresql.org/docs/18/runtime-config-resource.html, fetched in this pass]. The release-announcement page, as fetched earlier, appeared to say `sync`; the versioned docs are the authoritative source, so treat `worker` as the default. Announcement claims "up to 3x" in some scenarios for AIO overall, not io_uring specifically. |
| **QEMU** | Block-layer AIO engine since QEMU 5.0, `-drive aio=io_uring` (others: `threads`, `native`); uses READV/WRITEV/FSYNC ops. [not independently re-verified; originally from a search of the 2019 patch series] |
| **TigerBeetle** | Single thread alternates `replica.tick()` and `io.run_for_ns()`; every I/O is async, submitted through io_uring on Linux. [V TigerBeetle blog + linux.zig] |
| **libuv (Node.js)** | v1.45.0 handed some file ops (read/write/fsync/fdatasync/stat family) to io_uring, "8x throughput" in the commit message, falling back to the thread pool. Opt-in via `UV_LOOP_USE_IO_URING_SQPOLL`; from v1.49.0 the default reverted to the thread pool. [V libuv fs docs, re-read in this pass, confirm 1.45.0 / 1.49.0 / the SQPOLL option; the "8x" figure is from the commit message via Phoronix, not re-verified] |
| **RocksDB** | Opt-in: `PosixFileSystem` async read via io_uring (`ReadAsync`/`Poll`) used by MultiGet and iterators; if not enabled, `ReadAsync` returns NotSupported. **Unverified (single secondary source: a mirrored commit page); the 2022 RocksDB blog does not mention io_uring.** |
| **Glommio (Datadog)** | Rust thread-per-core runtime built on io_uring with no helper threads; needs Linux 5.8+ and >=512 KiB locked memory. [not independently re-verified] |
| **Cloudflare** | Not a "we run it" claim: they dissected the io-wq worker pool because socket I/O is their core workload, and recommend `IORING_REGISTER_IOWQ_MAX_WORKERS` (5.15) over lowering `RLIMIT_NPROC`. [V Cloudflare blog] |
| **Counter-adopters** | Google disabled it on ChromeOS and production servers and blocks it for Android apps via seccomp-bpf (2023); in that post 60% of submissions in the past year exploited io_uring. [V read directly in the Google Security Blog post, 2023-06-14; section 9] |

### How it's used
Practitioners call **liburing** (the helper library "to setup and teardown io_uring instances" with a simplified interface) rather than raw syscalls; liburing is not tied to a kernel release but features need matching kernels. [V liburing README] Core call sequence: `io_uring_queue_init` -> `io_uring_get_sqe` -> `io_uring_prep_*` -> `io_uring_submit` (or `io_uring_submit_and_wait`) -> `io_uring_wait_cqe` -> `io_uring_cqe_seen`. [V liburing wiki]

Typical parameters: entries = power of two (e.g. 256); recommended networking flags `COOP_TASKRUN` (5.19+) and `SINGLE_ISSUER` + `DEFER_TASKRUN` (6.0/6.1+); `SQPOLL` only if a spare core is acceptable; multishot accept/recv with provided buffers (`IOSQE_BUFFER_SELECT`, watch `IORING_CQE_F_MORE`). [V liburing wiki, io_uring_setup(2)]

```c
// Illustrative, not compiled: written from the documented call sequence. A compile check was attempted
// but no Linux/liburing toolchain was available (macOS host, Docker daemon down).
struct io_uring ring;
struct io_uring_params p = {0};
p.flags = IORING_SETUP_SINGLE_ISSUER | IORING_SETUP_DEFER_TASKRUN;  // kernel >= 6.1
io_uring_queue_init_params(256, &ring, &p);

struct io_uring_sqe *sqe = io_uring_get_sqe(&ring);
io_uring_prep_read(sqe, fd, buf, 4096, 0);   // fd, buffer, len, file offset
sqe->user_data = 42;                         // echoed back in the CQE

io_uring_submit_and_wait(&ring, 1);          // one syscall: submit + wait for 1 completion
struct io_uring_cqe *cqe;
io_uring_wait_cqe(&ring, &cqe);
// cqe->res = bytes read or -errno; cqe->user_data == 42
io_uring_cqe_seen(&ring, cqe);
```
Usual integration pattern: one ring per thread, batch SQEs per loop iteration, correlate with `user_data`, re-arm multishot requests when `F_MORE` is clear (TigerBeetle's loop above is the canonical shape). Full runnable program: section 13.

### When to use it / when not
- **Use** when: many small ops can be batched; file and network I/O share one loop; you want deep queue depth from few threads (NVMe); you can redesign the loop and require a recent kernel. Search-level summaries and the liburing wiki agree on this shape. [V]
- **Skip** (stay on epoll, or libaio for O_DIRECT) when: it is a plain network server and you won't restructure around completions (Alibaba Cloud's epoll comparison states "the throughput of io_uring is about 10% higher than that of epoll when 1000 connects", with CPU vulnerability mitigations enabled [V read in this pass; one vendor's benchmark, no raw numbers published]); you need old-kernel portability; the workload is untrusted/sandboxed (Google's stance, section 9); you want portability (Windows IoRing is a similar but separate API [not independently re-verified; windows-internals.com]).
- Signs you picked wrong: gains of 1.06x-1.10x after a drop-in swap (section 2), `iou-wrk-*` thread pile-ups, or code full of kernel-version fallbacks.

### Who should care
- **Database/storage engineers**: deep NVMe queues, async buffer managers (PostgreSQL 18, RocksDB, TigerBeetle).
- **Runtime/library authors** (Node/libuv, Rust async runtimes, Zig): completion-model API and cancellation semantics.
- **Infra/SRE**: kernel version, `RLIMIT_NPROC`/`pids.max`, QEMU `aio=` choice.
- **Security/platform engineers**: whether to allow it in containers; syscall-based monitoring is blind to SQE opcodes (section 9).

## 2. The one-liner — and what it hides

**"io_uring is async I/O via two shared ring buffers, so you skip syscalls."**

Hides:
1. Most ops are **not** async: kernel first tries the op *inline, non-blocking* in submit context. Async is the fallback, and for buffered file I/O the fallback is a **thread pool** (`io-wq`), not hardware async.
2. "No syscalls" is only true with `SQPOLL` (burns a core) — otherwise one `io_uring_enter` per *batch*. Win = amortization.
3. Naive port gains ~nothing (measured: 1.06× buffer mgr, 1.10× shuffle). Gains come from batching + registered resources + task-work control + redesigned architecture.
4. It's a **second syscall interface**: ops live in SQEs, invisible to seccomp/syscall audit. Google disabled it on ChromeOS/prod.
5. Zero-copy isn't free: ownership of buffers/cancellation is the hard part; ZC send loses to memcpy for small payloads [K].

## 3. The problem

Before: Linux aio (`io_submit`/`io_getevents`).
- Async only for O_DIRECT; buffered "behaves in a synchronous manner". [V paper §1]
- Submit can still block (metadata fetch, device request slots exhausted) → apps still ran thread pools.
- Copies: 64B (iocb) + 8B pointer on submit, 32B (io_event) on completion → **104 B copied for "zero-copy" I/O**. [V]
- Completion ring exposed but "hard (impossible?) to use correctly". [V]
- ≥2 syscalls per I/O (submit + getevents) — "post spectre/meltdown ... a serious slowdown". [V]
- Devices <10µs latency, millions of IOPS: slow non-deterministic submit, bad single-core scaling.
- epoll: readiness only; regular files always "ready" → no file I/O help; pair with thread pool. Thread pool for buffered I/O = ≥2 context switches even on page-cache hit. [V paper §9.2]

Axboe tried extending aio (2010 and again) → more entry points, worse API → started fresh. Goals: easy to use/hard to misuse, extensible, efficient, scalable; "no memory copies for either submissions or completion events, and no memory indirections" [V §3–4]. Merged 5.1 (Jan 2019 merge, May 2019 release).

Headline numbers from paper §9: 4K random reads — aio 608K IOPS, io_uring 1.2M (no polling), 1.7M (polling). Authors' own caveat: "these values don't carry a lot of absolute meaning" (unfair: aio has no polling).

## 4. Mental model

**Restaurant order window.** Kitchen (kernel) and diner (app) share two conveyor belts: orders in (SQ), plates out (CQ). Diner stacks 32 order slips then rings the bell *once*. Cook grabs whatever's quick (inline), parks slow orders on a side-queue (poll waitlist) or hands them to a prep crew (io-wq).

Breaks where:
- Belt carries *indexes* to slips, not slips (SQ array indirection).
- Cook may *not* be asynchronous at all: simple orders finish while you're ringing the bell; CQE already there on return.
- Prep crew = real kernel threads in your process (since 5.12), counted against `RLIMIT_NPROC`.
- Once the cook has *read* a slip, you may reuse the slot — but the kernel may still be using your **buffers**.

## 5. Mechanism, traced

### 5.1 Memory layout

```
mmap(fd, IORING_OFF_SQ_RING   = 0x0)         SQ ring: head tail ring_mask ring_entries flags dropped array[]
mmap(fd, IORING_OFF_CQ_RING   = 0x8000000)   CQ ring: head tail ring_mask ring_entries overflow cqes[]   (single mmap w/ SQ since 5.4)
mmap(fd, IORING_OFF_SQES      = 0x10000000)  sqes[ entries ] each 64 B
```
(IORING_OFF_PBUF_RING = 0x80000000, 5.19.) Offsets inside rings come from `io_uring_params.sq_off / cq_off` returned by `io_uring_setup`.

SQE (64 B) [V field order; offsets reconstructed]:
```
 0 opcode u8 | 1 flags u8 | 2 ioprio u16 | 4 fd s32
 8 off/addr2 u64 | 16 addr u64 | 24 len u32 | 28 op-flags u32
32 user_data u64   <- echoed in CQE, your correlation id
40 buf_index/buf_group u16 | 42 personality u16 | 44 splice_fd_in/file_index u32
48 addr3 u64 + pad   (SQE128, 5.19: 128 B for NVMe passthrough cmd)
```
CQE (16 B): `user_data u64 | res s32 (bytes or -errno) | flags u32` (F_BUFFER, F_MORE, F_NOTIF; CQE32 = 32 B).

SQ ring holds **indexes into `array[]`**, which index `sqes[]`: kernel does `head = READ_ONCE(sq_array[cached_sq_head++ & mask]); sqe = &sq_sqes[head]` (with `array_index_nospec`). CQ indexes `cqes[]` directly. Indirection lets apps embed SQEs in own structures and submit non-contiguously. `IORING_SETUP_NO_SQARRAY` (6.6) drops it.

CQ defaults to 2× SQ entries (`CQSIZE` overrides); sizes → power of 2.

### 5.2 One `read(fd, buf, 4096)` end to end

```
app:   sqe = &sqes[tail & mask];  fill(opcode=READ, fd, addr=buf, len=4096, user_data=0xA1)
       array[tail & mask] = tail & mask
       store_release(sq.tail, tail+1)            # publish
       io_uring_enter(fd, to_submit=1, min_complete=1, GETEVENTS)   # 1 syscall for N sqes

kernel io_uring_enter -> io_submit_sqes (uring_lock)
   per SQE: io_alloc_req -> io_get_sqe -> io_submit_sqe -> io_init_req
   non-linked -> io_queue_sqe:
        issue_flags = NONBLOCK | COMPLETE_DEFER
        io_issue_sqe()  ----- inline attempt in *submitter's context* ---->
             page-cache hit / O_DIRECT w/ NOWAIT / socket w/ data  => completes, CQE posted
        ret == -EAGAIN ?
          io_queue_async -> copy SQE (slot about to be reused) -> io_arm_poll_handler
             APOLL_OK      pollable fd (socket/pipe): sleep on file waitqueue, no thread
             APOLL_READY   became ready meanwhile: queue as task_work, retry
             APOLL_ABORTED not pollable (regular file buffered, etc.): io_queue_iowq -> io_wq_enqueue
                              worker thread runs io_issue_sqe(UNLOCKED|IOWQ) *blocking*
app:   acquire(cq.tail) != cq.head ?  cqe = cqes[head & mask]; use(cqe.res, cqe.user_data)
       store_release(cq.head, head+1)
```
Key facts [V from source]:
- Non-blocking ops complete **inside the submit call**; CQE already in ring on return (paper §9.2).
- `IOSQE_ASYNC` skips inline attempt → straight to io-wq.
- Completions from poll/io-wq come back via **task_work** on the submitting task. Plain `TWA_SIGNAL` = IPI that interrupts userspace.
- `__io_submit_flush_completions` batches CQE posting.

Reality check: "async" for buffered file I/O = kernel thread pool doing blocking syscalls (iou-wrk-* threads) — like libuv's pool, just in-kernel and cheaper. Real async: O_DIRECT/NVMe with NOWAIT, sockets/pipes via poll.

### 5.3 io-wq details [V]
- Two pools: **bound** (regular files/bdev; sized from SQ ring) and **unbound** (sockets, char devs; max = `RLIMIT_NPROC`).
- Per-task, per-NUMA pools; workers are threads of submitting task (5.12 `NATIVE_WORKERS`), idle timeout 5 s.
- Hashed work serializes buffered writes to same inode.
- Control: `IORING_REGISTER_IOWQ_MAX_WORKERS` (5.15). Hitting `RLIMIT_NPROC`/cgroup `pids.max` → ring may burn CPU retrying thread creation (Cloudflare "missing manuals").

### 5.4 SQPOLL
Per-ring kernel thread polls SQ tail. Zero syscalls while awake.
```
thread idle > sq_thread_idle (default 1 s):
   atomic_or(sq.flags, NEED_WAKEUP); smp_mb__after_atomic(); recheck sq entries; sleep
app after tail store:
   full barrier;  if (load(sq.flags) & NEED_WAKEUP) io_uring_enter(SQ_WAKEUP)
```
The full barrier pairs with the thread's post-flag barrier — classic Dekker-style store→load race: without it app sees no flag while thread sees no entry → lost wakeup. Unprivileged since 5.13. Costs a core; Jasny et al. measure ~30 µs wake latency from sleep.

### 5.5 Flags that decide perf
| Flag | Ver | What |
|---|---|---|
| COOP_TASKRUN | 5.19 | no IPI; task_work runs at next kernel entry |
| SINGLE_ISSUER | 6.0 | one task submits → drop locks/atomics |
| DEFER_TASKRUN | 6.1 | task_work runs *only* inside `io_uring_enter(GETEVENTS)` on `ctx->work_llist`; needs SINGLE_ISSUER; gotcha: never call GETEVENTS → nothing completes |
| multishot accept/recv | 5.19/6.0 | 1 SQE → many CQEs; `CQE_F_MORE` clear ⇒ must re-arm |
| provided buffer rings | 5.19 | kernel picks buffer at data arrival; no buffer pinned per idle conn |
| SEND_ZC | 6.0 | 2 CQEs: result (F_MORE) then `F_NOTIF` = buffer reusable; `NOTIF_USAGE_ZC_COPIED` = kernel fell back to copy |
| fixed files/buffers | 5.1 | skip per-op fdget/refcount atomics and per-op page pin (pinned, memlock-charged, ≤1 GiB/buf) |
| IOSQE_IO_LINK | 5.3 | next SQE starts after prev success; error → rest `-ECANCELED`; HARDLINK doesn't sever |

## 6. The math

**Amortization.** Let `c_s` = enter syscall cost, `c_o` = per-op in-kernel work, `B` = ops per enter.
```
cost/op = c_s / B + c_o
```
→ plain terms: batching divides the fixed cost. Jasny et al. measure 5–6× fewer cycles/op at B ≥ 16 [V arXiv 2512.04859]. Limit B→∞ gives `c_o` — you can't beat it; that's why SQPOLL/polling matter only when `c_s/B` is still visible.

**Little's law for queue depth.** `IOPS = QD / latency`. 100 µs NVMe read, 1M IOPS ⇒ QD = 100. Sync I/O has QD=1 per thread ⇒ 10 K IOPS/thread; Jasny's synchronous POSIX baseline 16.5 K tx/s vs 376 K tx/s with io_uring (buffer manager, 1 thread) is mostly *QD*, not syscall cost. → batching isn't the only win; **concurrency in one thread** is.

**Ring index arithmetic.** `head`, `tail` free-running u32. `used = tail − head` (mod 2³²), `free = N − used`, slot = `idx & (N−1)` (N power of 2). Why free-running instead of wrapping at N: full vs empty distinguishable (`used==N` vs `0`) with no spare slot or flag; all N slots usable. Correct across u32 overflow because modular subtraction.

**Memory-ordering contract (SQ).** App: write SQE; `store_release(tail)`. Kernel: `load_acquire(tail)`; read SQE. Release→acquire edge ⇒ SQE writes happen-before kernel reads. Kernel consumes: `smp_store_release(sq.head)` (seen in `io_commit_sqring` [V]); app `load_acquire(head)` before reusing slot. CQ mirrored. Without release on tail, CPU/compiler could expose tail before entry bytes ⇒ kernel reads garbage SQE. (CQ-side acquire/release pairings are inferred from paper + liburing, not read from source.)

**CQ overflow bound.** Pending requests can exceed SQ size (SQE consumed ⇒ slot reusable, request still in flight). In-flight `P ≤ SQ_entries + inflight_async`; CQ = 2×SQ by default doesn't bound P. Hence `NODROP` (5.5): overflow CQEs held in kernel list, flushed on next `enter(GETEVENTS)`; a purely userspace CQ poller can stall forever.

## 7. Why it works

Core insight: **turn syscall into data.** Syscall = control transfer + argument marshalling. Move marshalling to shared memory (SQE), make control transfer batched or removable (SQPOLL), and make completion a memory read (CQE).

Ablate each piece:
- Remove shared rings → back to aio's copies/≥2 syscalls.
- Remove inline-first attempt → every op pays a context switch to a worker even on page-cache hit (thread-pool problem).
- Remove poll-arm path → sockets need worker thread per blocked op (thousands of threads) or you are back to epoll+read.
- Remove io-wq fallback → buffered file I/O blocks `io_uring_enter` (submit stalls for disk) — breaks the "submit never blocks" promise.
- Remove registration → per-op atomic refcount + page pin; Jasny: registered buffers part of the 2× gain.
- Remove DEFER_TASKRUN → IPIs interrupt app mid-batch, break batching, jitter.
- Remove `user_data` indirection → can't match out-of-order completions.

## 8. Design knobs & alternatives

Knobs: SQ depth; CQ size; batch size B; SQPOLL (core vs latency); IOPOLL (poll NVMe CQ; needs O_DIRECT; reaps via GETEVENTS or SQPOLL thread); COOP vs DEFER_TASKRUN; registered files/bufs; `IOWQ_MAX_WORKERS`; passthrough; multishot + buffer rings.

Alternatives:
- **epoll + threads**: simple, portable; no file I/O. Network gain of io_uring over tuned epoll ≈ ~10% @1000 conns (Alibaba blog, read in this pass; single vendor benchmark), single-digit–20% typical [K], big only with ZC/large batches.
- **libaio**: O_DIRECT only; competitive for tuned Seastar/Scylla (Scylla engineers reported no big win [K, unverified; Seastar/Scylla details not re-verified]).
- **SPDK**: userspace NVMe polling; "io_uring within ~10% of SPDK but ~2× the cores" (SYSTOR 2022, outside 2y window) [V via agent].
- **Windows IoRing**: "almost identical" design, far fewer opcodes. **IOCP**: completion-based but syscall per submit. **kqueue** (BSD/macOS): readiness only. TigerBeetle/Qt wrap them behind one API.

## 9. Where it breaks

**Security (the big one).**
- Google kCTF/VRP post (14 Jun 2023): "60% of the submissions exploited the io_uring component" (of 42 Linux kernel exploit submissions), "~1 million USD for io_uring alone". Disabled on ChromeOS, production servers; Android seccomp-blocks it for apps. Stance: safe only for trusted components. [V read directly in the Google Security Blog post]
- Bug classes = object-lifetime between ring-owned resources and user-visible mappings/fds, plus new opcodes reusing old fields:
  - CVE-2021-41073: `PROVIDE_BUFFERS` puts kernel `io_buffer*` in `req->rw.addr`; `loop_rw_iter` treats as user ptr; later `io_put_kbuf` frees attacker-adjacent memory (type confusion). 5.10–5.14.6.
  - CVE-2022-2602: race between registered files in flight and **unix-socket GC** → UAF.
  - CVE-2023-2598: OOB physical-page access in fixed-buffer registration (folio/compound page coalescing), 6.3-rc1→6.4-rc1, full LPE.
  - CVE-2024-0582: pbuf ring register → mmap → unregister leaves mapping to freed pages. (NVD says "memory leak"; mechanism from write-ups — confirm.)
- **Monitoring blind spot**: seccomp sees only `io_uring_setup/enter/register`, never the SQE opcodes. ARMO "Curing" rootkit PoC (2025) ran C2 + file ops via io_uring; Falco blind, Tetragon default policies miss, MS Defender didn't detect [V ARMO]. Ops run from io-wq/task_work context also dodge `sys_enter_*` tracing.
- Mitigations: `kernel.io_uring_disabled` sysctl (0 allow / 1 only `io_uring_group` or CAP_SYS_ADMIN, existing rings keep working / 2 `-EPERM` for all; 6.6 [K]); Docker default seccomp blocks it; containerd 2.0 removed from RuntimeDefault [search-only].

**Correctness/perf pitfalls.**
- Completions unordered. `fsync` can complete *before* the write is issued unless linked (man page quote). `IOSQE_IO_DRAIN` = full barrier, expensive.
- Cancel: `ASYNC_CANCEL` yields 2 CQEs, order unspecified; in-flight disk I/O "typically cannot be canceled" (stray DMA risk). Tokio's drop-cancels-future model collides: dropped future ≠ stopped kernel write into your buffer → owned-buffer APIs (without.boats).
- io-wq thread explosion vs `RLIMIT_NPROC`/`pids.max`.
- Multishot: ring of provided buffers runs dry ⇒ `-ENOBUFS`, multishot terminates [K]; absent `F_MORE` ⇒ re-arm.
- SEND_ZC: pin + extra notif CQE costs more than memcpy for small sends (~<10 KB) [K].
- io-wq/SQPOLL threads are real tasks ⇒ coredump/ptrace/freezer regressions [search-only].
- Kernel-version fragmentation: 5.19→6.0→6.1→6.6→6.15… portable code needs fallbacks; nginx cited regressions + tuning cost, never merged.
- Misconception: "io_uring = faster epoll." Jasny et al.: swapping interfaces naively → 1.06× / 1.10×.

## 10. In the wild

- **RocksDB**: io_uring on read paths only (MultiGet, iterator prefetch), thread-local rings, SINGLE_ISSUER|DEFER_TASKRUN; ~24% over pread on raw disk (**unverified (single secondary source)**; the 2022 RocksDB blog does not mention io_uring). Not writes/compaction. The opt-in claim is likewise unverified.
- **TigerBeetle**: single thread alternating `tick()` and `io.run_for_ns()`; all I/O via io_uring (kqueue/IOCP behind abstraction); a mid-2026 newsletter reports +8% from re-entering kernel after each completion callback to pipeline IO and CPU (secondary).
- **Seastar/Scylla**: io_uring reactor backend exists; long-default linux-aio+epoll [K, not independently re-verified].
- **libuv/Node**: io_uring for file ops only; network stays epoll; ref issue #1947 (+38% seq read, tighter variance in thread); later restricted for security [K].
- **QEMU** (not independently re-verified): 1.2M (no poll) / 1.7M (poll) 4K IOPS vs Linux AIO cliff ~608K (FOSDEM 2020); 2025 series makes io_uring the event loop (`aio_add_sqe`).
- **PostgreSQL 18**: `io_method=io_uring` (default `worker`, per the PG 18 docs [V]); guidelines from Jasny paper → +14%.
- **Glommio** (thread-per-core, io_uring-native; not independently re-verified), **tokio-uring** (stale since 0.5.0, May 2024), **nginx** (not merged).
- **10M IOPS/core** (Axboe, Ryzen 5950X, 2× Optane P5800X, 512B polled random reads, fixed files/bufs): per-IO software overhead microbenchmark, not app throughput. [V Phoronix]

## 11. Frontier

*Status: the items below were NOT independently re-verified in the follow-up pass; treat figures, versions and merge status as the original research's claims.*

1. **High-Performance DBMSs with io_uring: When and How to Use It** — Jasny, El-Hindi, Ziegler, Leis, Binnig. PVLDB 19(9):2317–2330 (2026), arXiv 2512.04859. [V numbers from PDF] Setup: EPYC 9654P, 8× PCIe5 Kioxia CM7-R, ConnectX-7 400G, Linux 6.15.
   - Problem: naive io_uring swap ⇒ 1.06× (buffer mgr), 1.10× (network shuffle).
   - Method: add one feature at a time — batching, fibers, DEFER_TASKRUN (avoids IPI preemption), registered buffers, NVMe passthrough, IOPoll, SQPoll.
   - Buffer manager: 173 K → 376 K tx/s (2.05×) one thread; +1 core for SQPoll → 546.5 K. Sync POSIX: 16.5 K. Shuffle: 12.0 → 30.5 GiB/s (2.31×).
   - Costs: io-wq fallback ≈ 7.3 µs/op; SQPoll wake ≈ 30 µs; needs app redesign. Applying to Postgres: +14%.
2. **Zero-copy receive (zcrx)** — Begunkov & Wei, merged Linux 6.15 (2025); DMA-BUF follow-up targeted 6.16, large buffers later (Phoronix-reported). [docs.kernel.org/networking/iou-zcrx.html]
   - Problem: kernel→user copy caps TCP RX at 100–400G.
   - Mechanism: page_pool hands user-registered memory to NIC RX queue; HW header/data split; flow steering to that queue; completion CQEs + refill ring returns buffers. Demo: one core saturates 200G.
   - Limits: needs NIC header/data split, flow steering, queue config; app owns buffer lifetime.
3. **BPF-controlled io_uring** — Begunkov struct_ops series (v1–v10, Jan–Feb 2026), LWN reports Axboe applied 17 Mar 2026 for 7.1 merge window; competing `IORING_OP_BPF` (Ming Lei) pending. [LWN 1062286, 1044989; merge status secondhand]
   - BPF program replaces the enter loop: `bpf_io_uring_submit_sqes()`, `bpf_io_uring_get_region()`, returns `IOU_LOOP_CONTINUE/STOP`. Goal: fewer syscalls, custom completion logic. No benchmarks seen.
4. **Task-level restrictions + cBPF filter** — `IORING_REGISTER_RESTRICTIONS_TASK`, `IORING_REGISTER_BPF_FILTER` (Jan 2026, v5 at LWN 1054225; **merge version unconfirmed**). cBPF so it works unprivileged in containers; per-opcode, cannot inspect args like seccomp, defaults allow.
5. **"Asynchronous I/O — With Great Power Comes Great Responsibility"** — Pestka, Paradies, Pohl, arXiv 2411.16254 (Nov 2024): API complexity limits DBMS adoption.
6. **Upstreaming a flexible and efficient I/O path in Linux (I/O Passthru)** — Joshi et al., FAST 2024: `IORING_OP_URING_CMD` + NVMe char dev `/dev/ngXnY` + SQE128; 16–40% higher IOPS than block path (fio); in SPDK, xNVMe, fio, liburing.
7. **xNVMe for DBMS I/O** — Houlborg, CIDR 2026 (title/URL only, not read). https://www.vldb.org/cidrdb/papers/2026/p6-houlborg.pdf
8. **ARMO "Curing"** — Apr 2025 PoC; Sysdig detection write-up.
9. Audit hooks: `security_uring_cmd` LSM (5.19); Dec 2024 patch for `io_uring_setup` LSM hook (Microsoft; merge unconfirmed).
10. Dropped: 2026-numbered CVEs (zcrx races, "PinTheft") — only vendor-snippet sourced, unverified against NVD.

Gap: no 2024–26 formal cross-OS benchmark paper found.

## 11b. Open problems

1. **Sandboxing.** Disable-for-untrusted is current answer. seccomp can't see opcodes; attack surface grows per opcode/registration type (zcrx, uring_cmd). Task-restriction/cBPF filter is the live attempt; coarse (no arg inspection). Hard because opcodes carry pointers/flags nested in shared memory the filter can't TOCTOU-safely inspect. [reasoning mine]
2. **Cancellation of in-flight block I/O.** Needs hardware-side cancel to avoid stray DMA into reused pages. Axboe on LKML: file/bdev I/O can't be cancelled.
3. **Truly async buffered I/O.** Page-cache miss alloc, block allocation, journalling, fsync still punt to io-wq; needs NOWAIT through every FS path. Async-buffered-read patches (2020: preadv 1m13s vs io_uring 12.0 s/82% CPU vs patched 9.3 s/52% CPU) fixed reads only partially.
4. **Resource accounting.** io-wq per-task×NUMA pools vs `RLIMIT_NPROC`/`pids.max`; no clean per-ring CPU accounting.
5. **Security observability.** EDR keyed on syscalls blind; LSM/KRSI hooks proposed, not default.
6. **API complexity vs adoption.** Pestka et al.; Jasny et al. say gains need redesign. Open: can a higher-level library give 80% of the win without redesign? (Tokio-uring's stall suggests cancellation semantics are the blocker.)
7. **Cross-OS standard.** Windows IoRing similar but narrower; BSDs/macOS no completion API.

## 12. Lineage

POSIX aio / glibc thread-emulated aio → Linux aio (2002, O_DIRECT) → Windows IOCP (1990s, completion model) → **io_uring 5.1 (2019)** → fixed resources, multishot, buffer rings (5.19–6.0) → DEFER_TASKRUN/SINGLE_ISSUER (6.0–6.1) → NVMe passthrough (5.19–6.0) → zcrx (6.15, 2025) → BPF-in-ring (7.1 target, 2026). Peers: Windows IoRing (Win11), SPDK.
Key papers: Axboe "Efficient IO with io_uring" (2019, v0.4); Joshi FAST'24; Jasny VLDB'26.

## 13. Hands-on (≤30 min)

See the syscall count collapse and the inline/punt split. Needs Linux ≥5.19, `liburing-dev`, `strace`.

```c
// Not compiled/run by the author of this dive (no Linux/liburing available when checked). cc -O2 t.c -luring -o t
#include <liburing.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define N 4096
int main(int argc, char **argv) {
    int sqpoll = argc > 2 && !strcmp(argv[2], "sqpoll");
    int fd = open(argv[1], O_RDONLY /* | O_DIRECT for true async */);
    struct io_uring r; struct io_uring_params p = {0};
    if (sqpoll) { p.flags = IORING_SETUP_SQPOLL; p.sq_thread_idle = 2000; }
    io_uring_queue_init_params(256, &r, &p);
    static char buf[N][4096];
    for (int round = 0; round < 100; round++) {
        for (int i = 0; i < 64; i++) {
            struct io_uring_sqe *s = io_uring_get_sqe(&r);
            io_uring_prep_read(s, fd, buf[i], 4096, (__u64)i * 4096);
            s->user_data = i;
        }
        io_uring_submit(&r);              // 1 enter per 64 reads (0 w/ SQPOLL awake)
        for (int i = 0; i < 64; i++) {
            struct io_uring_cqe *c;
            io_uring_wait_cqe(&r, &c);
            io_uring_cqe_seen(&r, c);
        }
    }
    printf("done\n");
}
```
Run: `dd if=/dev/urandom of=f bs=1M count=64; strace -f -c -e trace=io_uring_enter,pread64 ./t f` vs `... f sqpoll`.
Predict then check:
1. Enter count ≈ 100–200 (not 6400). Why not exactly 100? (wait_cqe enters when CQ empty.)
2. With page-cache-warm file: most CQEs already present on return from submit ⇒ `wait_cqe` doesn't enter (inline completion).
3. Drop caches (`echo 3 > /proc/sys/vm/drop_caches`), rerun, `ps -L` / `top -H` during run: see `iou-wrk-*` threads ⇒ buffered punt to io-wq.
4. Switch `open` to O_DIRECT (aligned buffers needed: use `posix_memalign`) → threads vanish on NVMe.
5. `sqpoll`: strace shows ~0 enters; `top -H` shows `iou-sqp-*` thread at 100% CPU.

## 14. Question ladder

**Mechanism**
1. What exactly happens, step by step, from `io_uring_submit()` for a socket read with no data yet?
2. Why does the SQ ring hold indexes into `array[]` rather than SQEs, and what did 6.6 change?
3. How does the kernel know the app has freed an SQE slot, and why is that safe with in-flight requests?
4. What does `CQE_F_MORE` mean for multishot recv and SEND_ZC, and how do the two differ?
5. Why must SQPOLL's NEED_WAKEUP flow have a full barrier on both sides?
6. What is task_work, and why does DEFER_TASKRUN require SINGLE_ISSUER?

**Why**
7. Why try inline non-blocking first rather than always queue?
8. Why two io-wq pools (bound/unbound)?
9. Why are free-running indexes better than wrapping indexes?
10. Why do provided buffer rings make multishot recv scale better than epoll+read for idle connections?

**Counterfactual**
11. If CQ were exactly SQ size and no NODROP, what breaks?
12. If io-wq workers were kernel threads (pre-5.12) not process threads, what changes for cgroups/creds/ptrace?
13. If SEND_ZC had no notification CQE, what could go wrong?
14. If the kernel read your SQE lazily (after returning) without copying it, what bug appears?

**Adversarial**
15. How would you hide file exfiltration from a seccomp+Falco setup using io_uring?
16. Where is the TOCTOU surface when the kernel reads shared-memory SQEs?
17. How could a registered-buffer bug give physical-memory access (cf. CVE-2023-2598)?
18. How would you DoS a host using only unprivileged io_uring and `RLIMIT_NPROC`?

**Connection**
19. Compare io_uring's SQ/CQ with NVMe's submission/completion queues. What does passthrough remove?
20. How does completion-based I/O change Rust's `Future` cancellation model?
21. How is Little's law behind both NVMe queue depth and why sync I/O is slow?

**Open**
22. Can a sandbox filter io_uring per-op without TOCTOU and without disabling it?
23. Can buffered file I/O ever be truly async on Linux without per-filesystem NOWAIT work?
24. Should the ring be BPF-programmable, or does that grow the attack surface faster than it removes syscalls?

<details><summary>Answers</summary>

1. SQE written, tail released; `enter` → `io_submit_sqes` → `io_queue_sqe` → inline `io_issue_sqe` with NONBLOCK → socket returns `-EAGAIN` → `io_queue_async` copies SQE → `io_arm_poll_handler` → `APOLL_OK`: request sleeps on socket waitqueue (no thread). Data arrives → wakeup → `io_poll_task_func` (task_work) rechecks with `vfs_poll`, reissues, posts CQE.
2. Lets apps submit non-contiguous SQEs / embed SQEs in own structs. `NO_SQARRAY` (6.6) removes the extra load and the indirection when apps don't need it.
3. Kernel `smp_store_release(sq.head)` after consuming (`io_commit_sqring`); app acquires head. Safe because kernel copies SQE into request (`io_req_sqe_copy`, FEAT_SUBMIT_STABLE 5.5) when it will need it later; user buffers aren't copied — you must keep those alive.
4. MORE on multishot: request still armed, more CQEs will come; absence ⇒ re-arm. MORE on SEND_ZC: a second `F_NOTIF` CQE follows meaning "buffer reusable"; the first CQE carries bytes sent.
5. Store-load ordering (Dekker): app stores tail then loads flag; thread stores flag then loads tail. Without full barrier both can read stale values → app sees no flag, thread sees no entries → sleeps forever with work pending.
6. task_work = callback run in the context of a specific task at kernel→user transition (or explicit point). DEFER_TASKRUN runs it only within `io_uring_enter(GETEVENTS)` on the ring's `work_llist`; only the submitter task may reap, hence single issuer.
7. Most ops (page-cache hit, ready socket, NOWAIT O_DIRECT) finish immediately; queueing costs ≥2 context switches. Inline = no handoff, CQE ready on return.
8. Bound ops (regular files/bdev) have bounded concurrency tied to device queue; unbound (sockets) can block indefinitely; mixing would let slow sockets starve disk work or force arbitrary cap.
9. Full vs empty distinguishable without a wasted slot; all N usable; modular subtraction handles u32 wrap.
10. Provided buffers are picked at data arrival, so idle connections hold no buffer; epoll+read typically needs a buffer per connection (or read-after-ready, which still needs buffer at that time but costs a syscall each).
11. Burst of completions exceeds CQ while app is busy ⇒ completions dropped (pre-5.5) or must be stored; with NODROP they pile in kernel memory until app enters; extreme case: lost/stalled completions.
12. Kernel threads: separate creds/cgroup/ptrace invisibility, harder accounting, no `RLIMIT_NPROC` coupling; 5.12 made them process threads: inherit cgroup/creds, visible to ptrace/coredump (and regressions).
13. App reuses/frees the buffer while NIC still DMAs from it ⇒ corrupted data on wire or use-after-free of page contents.
14. App reuses the slot, kernel executes the new SQE (or half-written one) ⇒ wrong op/args. Hence copy-on-defer.
15. Do exfil via SQEs: `OPENAT`, `READ`, `SEND`/`CONNECT` ops; seccomp sees only `enter`; Falco hooks syscalls → blind (ARMO Curing).
16. Kernel reads SQE fields from user-writable memory (after `READ_ONCE`); an app thread can mutate SQE or pointed-to structs concurrently. A per-opcode filter that inspects args at filter time may see different values than at execution; kernel mitigates by copying SQE before use, but pointer targets (iovecs, msghdr) remain user memory.
17. Fixed-buffer registration coalesces pages into compound-page folios; wrong arithmetic computes buffer range/length past the folio ⇒ read/write to adjacent physical pages through the registered buffer ⇒ kernel memory R/W ⇒ LPE.
18. Queue many blocking unbound ops (e.g., reads on a socket/pipe that never gets data) across many ring-submitting threads: each can spawn io-wq workers up to `RLIMIT_NPROC` (per-user), starving the user/container of threads; with `pids.max`, workers burn CPU retrying creation.
19. Same producer/consumer queue pair idea; io_uring has an extra software layer (block layer, page cache, FS). Passthrough (`URING_CMD` + `/dev/ng*`) skips block layer/FS so NVMe SQE goes nearly straight to device queue; you give up caching, FS semantics, LBA mgmt (16–40% IOPS gain in FAST'24).
20. Rust futures are cancelled by drop; with readiness that's safe. With completion, the kernel may still write into your buffer after drop ⇒ UB. Fix: ownership transfer of buffers (tokio-uring style APIs) or cancel-and-wait; cost: ergonomics, no `&mut [u8]` APIs.
21. IOPS = QD/latency: device has ~µs–100 µs latency, so to reach 1M IOPS need ~100 in flight. Sync I/O has QD=1/thread; io_uring/NVMe queues allow deep QD from one thread.
22. Open. Needs filtering at semantic level (opcode + stable args) with TOCTOU-safe copy; current cBPF filter doesn't inspect args. Alternative: capability-style per-ring restrictions (existing `REGISTER_RESTRICTIONS`) — coarse.
23. Open. Requires NOWAIT support for allocation, journalling, writeback throttling in each FS; or accept thread pool as the implementation (what io-wq is).
24. Open. BPF removes syscalls and enables custom completion logic but adds a verified-code attack surface and interaction with cancellation; history of BPF verifier bugs argues caution; unprivileged cBPF filter is the conservative variant.

</details>

## 15. Go deeper next

1. **NVMe queue pairs, doorbells, and SPDK polling** — what io_uring passthrough sits on top of.
2. **TCP zero-copy: MSG_ZEROCOPY, page_pool, header/data split, flow steering** — hardware side of zcrx.
3. **Kernel object lifetime & Linux LPE exploitation (kCTF, cross-cache attacks)** — why ring-owned resources keep producing UAFs.

## Sources

**Papers / specs**
- Axboe, Efficient IO with io_uring (v0.4, 2019) — https://web.archive.org/web/2024/https://kernel.dk/io_uring.pdf (origin kernel.dk cert fails)
- Jasny et al., PVLDB 19(9) 2026 — https://arxiv.org/abs/2512.04859 (code github.com/mjasny/vldb26-iouring)
- Pestka, Paradies, Pohl — https://arxiv.org/abs/2411.16254
- Joshi et al., FAST'24 — https://www.usenix.org/system/files/fast24-joshi.pdf
- Houlborg, CIDR 2026 — https://www.vldb.org/cidrdb/papers/2026/p6-houlborg.pdf (not read)
- SYSTOR 2022 storage APIs — https://atlarge-research.com/pdfs/2022-systor-apis.pdf

**Code / docs**
- UAPI header, io_uring/{io_uring,sqpoll,io-wq,poll}.c — https://github.com/torvalds/linux (master)
- liburing man pages, wiki "io_uring and networking in 2023" — https://github.com/axboe/liburing
- man7 io_uring_enter(2), io_uring_setup(2), io_uring_cancelation(7)
- zcrx docs — https://docs.kernel.org/networking/iou-zcrx.html
- sysctl — https://docs.kernel.org/admin-guide/sysctl/kernel.html
- Windows IoRing comparison — https://windows-internals.com/ioring-vs-io_uring-a-comparison-of-windows-and-linux-implementations/

**Articles**
- Google Security Blog, kCTF VRP learnings (2023-06-14) — https://security.googleblog.com/2023/06/learnings-from-kctf-vrps-42-linux.html
- Phoronix: Google restricting io_uring; 6.6 sysctl; 6.15 io_uring; 10M IOPS
- Cloudflare, io_uring worker pool — https://blog.cloudflare.com/missing-manuals-io_uring-worker-pool/
- ARMO Curing — https://www.armosec.io/blog/io_uring-rootkit-bypasses-linux-security/ ; Sysdig detection write-up
- StarLabs CVE-2021-41073 — https://starlabs.sg/blog/2022/06-io_uring-new-code-new-bugs-and-a-new-exploit-technique
- oss-security CVE-2022-2602, CVE-2023-2598 (openwall 2022/10/18/4, 2023/05/08/3)
- LWN: 776703, 810414, 879724, 906470, 1044989, 1054225, 1062286, 821274
- without.boats "io-uring" — https://without.boats/blog/io-uring/
- RocksDB async IO blog (2022-10-07); TigerBeetle abstraction blog + 2026-06-17 newsletter; libuv #1947; QEMU FOSDEM 2020; Alibaba io_uring vs epoll
- u1f383 pbuf vulnerabilities — https://u1f383.github.io/linux/2025/03/02/a-series-of-io_uring-pbuf-vulnerabilities.html

**Real-world context (1b) sources**
- PostgreSQL docs, resource settings (`io_method`) — https://www.postgresql.org/docs/18/runtime-config-resource.html (default `worker`) ; PG18 release announcement — https://www.postgresql.org/about/news/postgresql-18-released-3142/
- liburing README — https://github.com/axboe/liburing ; wiki "io_uring and networking in 2023" — https://github.com/axboe/liburing/wiki/io_uring-and-networking-in-2023
- man7 io_uring(7) — https://man7.org/linux/man-pages/man7/io_uring.7.html ; io_uring_setup(2) — https://man7.org/linux/man-pages/man2/io_uring_setup.2.html
- TigerBeetle, "A Programmer-Friendly I/O Abstraction Over io_uring and kqueue" — https://tigerbeetle.com/blog/2022-11-23-a-friendly-abstraction-over-iouring-and-kqueue/ ; linux.zig — https://github.com/tigerbeetle/tigerbeetle/blob/main/src/io/linux.zig
- Phoronix, libuv io_uring — https://www.phoronix.com/news/libuv-io-uring ; libuv fs docs — https://docs.libuv.org/en/v1.x/_sources/fs.rst.txt
- QEMU io_uring AIO patch series — https://patchew.org/QEMU/20191025160444.31632-1-stefanha@redhat.com
- RocksDB io_uring async-read commit — https://git.nextgraph.org/NextGraph/rocksdb/commit/8465cccde2ea7e5e76b0826a307a927a682dfc86 ; RocksDB async IO blog — https://rocksdb.org/blog/2022/10/07/asynchronous-io-in-rocksdb.html
- Glommio — https://github.com/DataDog/glommio
- Alibaba Cloud, io_uring vs epoll — https://www.alibabacloud.com/blog/io-uring-vs--epoll-which-is-better-in-network-programming_599544 (read in this pass)
- Phoronix, Google restricting io_uring — https://www.phoronix.com/news/Google-Restricting-IO_uring

**Unverified / dropped**: Google ~60% and Alibaba ~10% are now verified against their primary pages; RocksDB opt-in and ~24% claims are single-secondary-source; QEMU 5.0, Glommio, Seastar, Windows IoRing and section 11 not re-verified; code snippets not compiled; Scylla "no big win" claim [K]; 2026-numbered CVEs; BPF-filter merge version; sysctl landing version (6.6) not confirmed from kernel git; Docker default-seccomp claim search-only.
