# PagedAttention: KV-cache block tables, fragmentation, copy-on-write, preemption

**Subject:** Computer science · **Domain:** LLM systems · **Topic:** PagedAttention and KV-cache memory management · **Depth:** hard · **Date:** 2026-10-10

---

## 0b. Plain English first

### Explain it simply

Picture a busy restaurant with one long bench. When a party walks in, the host doesn't know how long they'll stay or how many friends will join later. So the cautious host blocks off enough bench for the biggest party that could possibly arrive, maybe 20 seats for a group of 3. The bench fills with empty "reserved" seats, and new guests wait outside while the room is two-thirds empty.

A large language model has the same problem with its working memory. While it writes an answer, it keeps a running notebook of everything said so far (the "KV cache"), and that notebook grows by one line per word. Older servers set aside one solid stretch of GPU memory per conversation, sized for the longest possible answer. Most of it sat empty. PagedAttention swaps the bench for small four-seat tables. A party gets one table, takes another when it fills up, and the tables don't have to be next to each other. A little card (the "block table") records which tables belong to which party. Nearly every seat ends up in use, so the GPU serves two to four times as many conversations at once.

### Everyday example

Maya asks a chatbot: "Write a haiku about rain." That's 7 words of question. Tables seat 4. Her notebook needs 2 tables: table #7 holds words 1–4 and table #1 holds words 5–7, with one seat free. The model writes "Soft", which lands in that free seat on table #1. Now table #1 is full. When it writes "drops", the host grabs any free table (#3, across the room) and writes it there. Maya's card now reads `7 → 1 → 3`. A minute later Maya's friend asks the *same* question with "give me two versions". Both versions share tables #7 and #1, since the question is identical. Only when version 2 needs to write somewhere different does it get its own copy of the last table. When Maya finishes, her tables are wiped and handed to the next guest straight away.

**Now the same thing, technically.**

---

## 1. Bare-minimum context

- **Autoregressive decoding.** An LLM generates one token per forward pass. Each new token attends to all previous tokens. ([Vaswani et al. 2017](https://arxiv.org/abs/1706.03762))
- **KV cache.** Each layer's key/value vectors for past tokens are cached so they aren't recomputed every step. The cache grows by one row per token per layer. ([HF docs](https://huggingface.co/docs/transformers/main/en/kv_cache))
- **Prefill vs decode.** Prefill processes the whole prompt in parallel and is compute-bound. Decode emits one token at a time and is memory-bandwidth-bound, so throughput comes from batching many sequences. ([DistServe](https://arxiv.org/abs/2401.09670))
- **Continuous (iteration-level) batching.** Requests join and leave the batch at every decode step instead of waiting for a whole batch to finish. ([Orca, OSDI'22](https://www.usenix.org/conference/osdi22/presentation/yu))
- **OS virtual memory.** Pages, page tables, copy-on-write `fork()`, swapping. PagedAttention borrows all of these. ([OSTEP ch. 18](https://pages.cs.wisc.edu/~remzi/OSTEP/vm-paging.pdf))
- **GQA.** Grouped-query attention: several query heads share one K/V head, which shrinks the KV cache. ([Ainslie et al. 2023](https://arxiv.org/abs/2305.13245))

## 1b. Real-world context

### What it is, in one paragraph

PagedAttention is a way to store an LLM's KV cache in fixed-size **blocks** (16 tokens by default in vLLM) that can sit anywhere in GPU memory. A per-request **block table** maps the request's logical blocks to physical ones, and the attention kernel follows that table while computing attention. Memory is allocated one block at a time as the sequence grows. Blocks are reference-counted so requests can share them (common prefixes, parallel samples, beam candidates), and they are copied only on write. The idea is OS paging applied to the KV cache. It was introduced in the vLLM paper (Kwon et al., SOSP 2023, [arXiv 2309.06180](https://arxiv.org/abs/2309.06180)).

### Why it exists

- **The pain.** Before vLLM, serving systems such as FasterTransformer and Orca stored each request's KV cache as one contiguous tensor, pre-allocated for the maximum possible length because the output length is unknown up front. The vLLM paper measured only **20.4%–38.2%** of KV memory holding actual token state in those systems; vLLM reached **96.3%** ([paper §2–3](https://arxiv.org/abs/2309.06180)).
- **Why it matters.** Decode is memory-bound, so throughput is roughly proportional to how many sequences fit in the batch. Wasted KV memory means a smaller batch, which means fewer tokens per second per dollar.
- **The fix's payoff.** The paper reports **2–4× throughput** at the same latency versus FasterTransformer and Orca, with bigger gains for longer sequences, bigger models and complex decoding.

### Where it's used

| System | Role of paged KV |
|---|---|
| **vLLM** | Reference implementation. V1 engine: `block_size` default 16, `gpu_memory_utilization` 0.92, automatic prefix caching **on by default**, recompute-based preemption ([cache.py](https://raw.githubusercontent.com/vllm-project/vllm/main/vllm/config/cache.py), [optimization docs](https://docs.vllm.ai/en/latest/configuration/optimization/)) |
| **TensorRT-LLM** | Paged `KVCacheManager` with `tokens_per_block` default **128** (power of 2, set at build), block reuse on by default, LRU eviction, optional host-memory offload ([docs](https://nvidia.github.io/TensorRT-LLM/advanced/kv-cache-reuse.html)) |
| **Hugging Face TGI** | Uses PagedAttention via vLLM's CUDA kernels; block table and KV sharing for parallel sampling ([docs](https://huggingface.co/docs/text-generation-inference/en/conceptual/paged_attention)) |
| **SGLang** | RadixAttention: paged KV indexed by a radix tree of token prefixes for automatic cross-request reuse ([arXiv 2312.07104](https://arxiv.org/abs/2312.07104)) |
| **FlashAttention / FlashInfer** | Ship paged-KV attention kernels that engines call (cited as the PagedAttention baselines in [vAttention](https://arxiv.org/abs/2405.04437)) |
| **Mooncake (Kimi)** | Builds a disaggregated, KV-cache-centric serving architecture on top of block-granular KV that moves between GPU, DRAM and SSD ([arXiv 2407.00079](https://arxiv.org/abs/2407.00079)) |
| **LMCache** | KV cache layer that captures blocks from engines like vLLM and shares or offloads them across engines and queries ([arXiv 2510.09665](https://arxiv.org/abs/2510.09665)) |

### How it's used

Practitioners rarely touch the block table. They set how much memory the pool may take, how long sequences may be, and whether prefixes are cached:

```bash
vllm serve meta-llama/Llama-3.1-8B-Instruct \
  --gpu-memory-utilization 0.90 \   # fraction of GPU memory for weights + activations + KV pool
  --max-model-len 8192 \            # longest sequence; caps per-request block count
  --block-size 16 \                 # tokens per KV block (default 16)
  --enable-prefix-caching \         # hash full blocks, reuse across requests (on by default in V1)
  --kv-cache-dtype fp8              # halve KV bytes per token (optional)
```

```python
from vllm import LLM, SamplingParams
llm = LLM(model="meta-llama/Llama-3.1-8B-Instruct",
          gpu_memory_utilization=0.9, max_model_len=8192)
# n=4 parallel samples share the prompt's blocks via refcounts; only the tail block is copied
outs = llm.generate(["Write a haiku about rain."], SamplingParams(n=4, max_tokens=64))
```

Typical values: block size 16 (vLLM) or 64–128 (TRT-LLM), memory utilization 0.85–0.95. Usual pattern: one engine per GPU group behind an OpenAI-compatible endpoint. At startup the engine profiles memory, then turns everything left into a fixed pool of KV blocks. The log line reporting "# GPU blocks" is the number to watch.

### When to use it, when not to

- **Use it** whenever you serve many concurrent, variable-length generations: chat, agents, batch inference, RAG. It's the default in every major open engine, so the real choice is the block size and prefix-cache policy.
- **Skip or reconsider** for single-stream, latency-only inference (one user, batch size 1). There fragmentation is irrelevant and a contiguous cache with the fastest dense kernel can win. [vAttention](https://arxiv.org/abs/2405.04437) argues that contiguous-virtual, paged-physical memory through CUDA VMM gets PagedAttention's memory benefits without changing the kernel, with up to 1.23× higher throughput.
- **Signs you picked wrong:** frequent preemption in logs (pool too small, or `max_num_seqs` too high); low prefix-cache hit rate with block size 128 on short prompts (block granularity too coarse); KV memory full while GPU compute sits idle (consider FP8 KV or offload).

### Who should care

- **ML infra / serving engineers:** capacity planning, choosing block size, prefix-cache and preemption tuning.
- **Backend engineers** building on LLM APIs: prompt layout. Put stable content first so prefix caching hits.
- **Security engineers:** shared prefix caches are a cross-tenant timing side channel.
- **Kernel authors:** every attention kernel must handle indirect, non-contiguous KV.

---

## 2. The one-liner, and what it hides

> "PagedAttention is virtual memory for the KV cache. It cuts fragmentation so you can batch more."

What that sentence hides:

1. **The attention kernel itself changes.** Softmax over keys scattered across blocks has to be computed block by block, with a correct global normalization. The paper's kernel was 20–26% slower than FasterTransformer's in isolation.
2. **Fragmentation drops but does not vanish.** Internal fragmentation is bounded to the *last* block of each sequence, which trades block size against kernel efficiency and sharing granularity.
3. **Allocating on demand means you can run out mid-generation.** That forces preemption (swap or recompute), which the contiguous design never needed.
4. **Sharing is the second big win.** Reference counts plus copy-on-write enable parallel sampling, beam search and prefix caching. That sharing is also a security hole (timing side channels).
5. **The GPU has no MMU in the loop here.** Translation is done in software, inside the kernel, by reading a table from memory. That is why alternatives like vAttention exist.

## 3. The problem

KV bytes per token for a transformer:

```
bytes/token = 2 (K and V) × L (layers) × H_kv (KV heads) × d_head × s (bytes/elem)
```

- **OPT-13B** (the paper's example; MHA, hidden 5120, 40 layers, FP16): 2 × 40 × 5120 × 2 = **800 KB/token**. A 2048-token request needs about **1.6 GB**.
- **Llama-2-7B** (MHA, 32 layers, 32 heads × 128): 2 × 32 × 32 × 128 × 2 = **512 KiB/token**.
- **Llama-3-8B** (GQA, 8 KV heads): 2 × 32 × 8 × 128 × 2 = **128 KiB/token**.

Pre-vLLM systems allocated `max_len × bytes/token` per request up front, because a request might produce up to `max_len` tokens. The paper names three kinds of waste (§3.1):

| Waste | Cause | Example from the paper (Fig. 3) |
|---|---|---|
| **Reservation** | Slots reserved for future tokens are held for the request's whole life | Slots for token 500 are reserved at step 1 but unused until step 500 |
| **Internal fragmentation** | Reserved for max length, but the request ends early | Request A reserves 2048, prompt 7 → up to 2038 never used; Request B (max 512) wastes 507 |
| **External fragmentation** | Variable-size contiguous chunks leave holes the allocator can't use | Buddy-allocator gaps between requests |

Net effect: **20.4–38.2%** effective utilization. The batch was KV-limited at a third of the possible size, while decode is bandwidth-bound and gets close to linearly more throughput per extra sequence until compute saturates.

**The forcing constraint:** output length is unknown at admission time. If you knew it, you could allocate exactly and solve the rest with a good allocator. The paper's "Orca (Oracle)" baseline does exactly that, and vLLM still beats it by 1.7–2.7× on ShareGPT, because external fragmentation and reservation waste remain.

## 4. Mental model

**OS paging.** Request = process. Token = byte. KV block = page (16 tokens). Block table = page table. Free-block pool = physical frame allocator. Parallel samples = `fork()` with copy-on-write. Preemption = swap-out.

**Where the analogy breaks:**

- **No hardware translation.** An OS uses an MMU and TLB per memory access. Here the attention kernel loads `block_table[seq][j]` from GPU memory and computes addresses itself. No TLB, no page faults. Translation is software, and the paper's kernel was 20–26% slower than FasterTransformer's.
- **Access is perfectly predictable.** Every decode step reads *every* block of every sequence in order. There's no locality to exploit and no "working set" smaller than the whole sequence. So "page out the cold pages" makes no sense: you swap out *whole sequences*, all or nothing.
- **Recompute is an option.** An OS can't regenerate a page's contents, but an LLM can rebuild a dropped KV cache by re-running prefill on prompt + generated tokens. vLLM V1 defaults to recompute, not swap.
- **Pages are append-only.** A sequence only ever writes to its last block (except copy-on-write). There's no random write, which is why the "last block" is the only possible fragmentation.

## 5. The mechanism, traced

Follow the paper's own example (Fig. 6) with block size **B = 4**: Maya's 7-token prompt, then decode.

### Step 0: prefill (7 tokens)

```
logical blocks needed = ceil(7 / 4) = 2
free pool: [0,1,2,3,4,5,6,7,8,...]   → allocator hands out 7, then 1 (any free block)

Block table (Maya, seq 0)
 logical  physical  filled
   0   →     7        4/4   [t1 t2 t3 t4]
   1   →     1        3/4   [t5 t6 t7 __]

Physical memory (each cell = 1 block of 4 token slots, per layer, per KV head)
 #0 [free] #1 [t5 t6 t7 __] #2 [free] #3 [free] ... #7 [t1 t2 t3 t4]
```

The prefill kernel writes K,V for all 7 tokens into slots `(7,0..3)` and `(1,0..2)`. vLLM uses a fused reshape-and-block-write kernel for this.

### Step 1: decode token 8 ("Soft")

```
seq len 7 → 8. Last block (phys #1) has 1 free slot → write there, no allocation.
 logical 1 → phys 1   4/4 [t5 t6 t7 t8]
```

Attention for token 8 visits blocks in logical order: block table entry 0 → phys #7, entry 1 → phys #1.

### Step 2: decode token 9 ("drops")

```
seq len 8 → 9. Last block full → allocate a new block → allocator returns #3.
 logical 2 → phys 3   1/4 [t9 __ __ __]
```

The block table is now `[7, 1, 3]`. Wasted slots for this sequence: 3, and only ever in the last block.

### Step 3: parallel sampling (n = 2) with copy-on-write

Maya's friend submits the same prompt with `n=2`. vLLM maps both samples to the same physical prompt blocks:

```
Sample A table: [7, 1]     Sample B table: [7, 1]
refcount: #7 = 2, #1 = 2
```

Both samples now want to write token 8 into the half-full block #1:

```
Sample A writes to #1 → refcount(#1)=2 > 1 → COPY: allocate #4, copy t5..t7 into #4,
                                              A's table → [7, 4], refcount(#1)=1
Sample B writes to #1 → refcount(#1)=1 → write in place.
```

One block copied, 3 tokens' KV, instead of duplicating the whole prompt. Beam search extends this into a tree: blocks whose refcount drops to 0 when a beam is pruned go back to the free pool.

### Step 4: attention over scattered blocks

For one query `q` (token 9, one head), the kernel computes:

```python
m, l, acc = -inf, 0.0, zeros(d)
for j, phys in enumerate(block_table):        # [7, 1, 3]
    K = kv_pool.K[layer, phys]                # (B, d) - contiguous inside the block
    V = kv_pool.V[layer, phys]
    n = min(B, seq_len - j*B)                 # last block partially filled
    s = K[:n] @ q / sqrt(d)                   # scores for this block
    m_new = max(m, s.max())
    scale = exp(m - m_new)
    p = exp(s - m_new)
    l = l * scale + p.sum()
    acc = acc * scale + p @ V[:n]
    m = m_new
out = acc / l
```

Each GPU warp reads one block, so loads are coalesced *within* a block. Only the jump *between* blocks is indirect. That is why block size can't be 1 in practice.

### Step 5: memory runs out → preemption

Suppose the pool is full when sequence S needs a new block. vLLM (FCFS) preempts the **most recently arrived** sequence group:

```
recompute (vLLM V1 default): free all of victim's blocks; requeue victim with
                             prompt' = prompt + generated tokens; later one prefill rebuilds KV
swap (original paper): copy victim's blocks to CPU block pool over PCIe; copy back later
```

Groups (beam candidates, parallel samples) are preempted together because they share blocks.

### Step 6: finish and prefix caching

When Maya's request ends, her blocks' refcounts hit 0. With automatic prefix caching (vLLM V1), full blocks are *not* wiped. They go to an LRU free queue with their hash intact:

```
hash(block_k) = H(hash(block_{k-1}), token_ids_in_block_k, extra_keys)
extra_keys: LoRA id, multimodal hashes, cache_salt
```

A later request whose first 4 tokens match `[t1..t4]` finds `hash(block_0)` in the table, reuses physical #7 (refcount 0 → 1), and skips prefill for those tokens. Only full blocks are hashed, so a 7-token match reuses 4 tokens, not 7 ([vLLM prefix caching design](https://raw.githubusercontent.com/vllm-project/vllm/main/docs/design/prefix_caching.md)).

## 6. The math

### 6.1 KV footprint and maximum batch

Let `M` be the bytes left for the KV pool after weights and activations, and `b = 2 L H_kv d_h s` the bytes per token. The pool holds `T = M / b` token slots.

With **contiguous max reservation**, each request costs `L_max` slots regardless of its actual length, so

```
N_contig = floor(T / L_max)
```

With **paging**, each request costs its actual length rounded up to blocks. If `ℓ` is the current length,

```
N_paged ≈ T / E[ B·ceil(ℓ/B) ]
```

→ in plain terms: contiguous allocation pays for the worst case. Paging pays for the actual average, plus at most one block per sequence.

Worked example (back-of-envelope, not measured). One A100-80GB, Llama-3-8B FP16: weights about 16 GB. With `gpu_memory_utilization=0.92`, about 73.6 GB is usable. Subtracting weights and an assumed ~2 GB of activations leaves `M ≈ 55 GB` → `T ≈ 55e9 / 131072 ≈ 420k` slots. With `L_max = 8192`, contiguous allows **51** sequences. Paged with mean length 700 allows about **590**, until compute-bound. Real engines also cap `max_num_seqs` (default 256 or similar, depending on version).

### 6.2 Internal fragmentation is bounded by the last block

A sequence of length `ℓ` occupies `B·ceil(ℓ/B)` slots, so waste is `w = B·ceil(ℓ/B) − ℓ ∈ [0, B−1]`. If `ℓ mod B` is roughly uniform (lengths are long compared to B),

```
E[w] = (B − 1) / 2,      waste fraction ≈ (B − 1) / (2 · E[ℓ])
```

→ in plain terms: with B = 16 and 600-token sequences, about 7.5 empty slots per sequence, or **1.25%** waste. With B = 512, waste is about 42%. Waste grows linearly with block size and shrinks with sequence length.

Why not just make B = 1? The cost on the other side is per-block overhead in the kernel: one indirect lookup, and less coalesced memory traffic. That cost scales like `ℓ/B`. Total cost is roughly `α·(B−1)/2 + β·ℓ/B`, which is minimized at `B* ≈ sqrt(2βℓ/α)`. That gives a moderate block size, and the paper found 16–128 best on ShareGPT, with 16 the default. This cost model is illustrative, not from the paper.

### 6.3 Block-wise softmax must renormalize across blocks

Attention for query `q_i` over `ℓ` keys is

```
o_i = Σ_t softmax(q_i·k_t/√d)_t · v_t = ( Σ_t e^{s_t} v_t ) / ( Σ_t e^{s_t} ),   s_t = q_i·k_t/√d
```

Split the tokens into blocks `j`. Per block, keep `m_j = max_{t∈j} s_t`, `l_j = Σ_{t∈j} e^{s_t − m_j}` and `a_j = Σ_{t∈j} e^{s_t − m_j} v_t`. Two partial results merge exactly:

```
m = max(m_1, m_2)
l = e^{m_1−m} l_1 + e^{m_2−m} l_2
a = e^{m_1−m} a_1 + e^{m_2−m} a_2
o = a / l
```

→ in plain terms: each block only needs to report its local max, its local sum and its local weighted value. Rescaling by `e^{m_j − m}` puts every block on the same scale, so the result is bit-for-bit the same math as contiguous attention (up to float rounding). That is why paging is **lossless**, unlike KV eviction or quantization. The paper's Eq. 4 writes the global softmax denominator. The running-max form above is how modern kernels such as FlashAttention and FlashInfer implement it for numerical stability.

Why this form and not a simpler one: you can't softmax each block independently and average, because the normalizer is global. The subtracted max prevents `exp` overflow in FP16/BF16, where `e^{11.1}` already exceeds the FP16 max of 65504.

### 6.4 Swap vs recompute

Back-of-envelope, not from the paper. For a victim with `ℓ` tokens:

```
t_swap ≈ 2 · ℓ·b / BW_pcie  (+ per-transfer overhead × number of blocks)
t_recompute ≈ 2·P·ℓ / F_eff   (P = params, F_eff = achieved FLOP/s)
```

Llama-3-8B, ℓ = 1000: `ℓ·b = 131 MB` → about 5 ms each way at ~25 GB/s. Recompute is `2·8e9·1000 = 1.6e13` FLOP, about 50–100 ms at 150–300 TFLOP/s achieved. So for large blocks with GQA, swap is cheaper per byte. **But** per-block transfer overhead dominates at small B (many 16-token copies). The paper (Fig. 19, OPT-13B) found swap bad at small blocks and recompute flat across block sizes. The two were comparable at B = 16–64, and recompute never cost more than about 20% over swap. vLLM V1 chose recompute as the default; it's simpler and needs no CPU block pool.

## 7. Why it works

**Core insight:** the KV cache only ever grows at the end, and attention reads it in order. So it needs neither contiguity nor reservation. It needs a cheap *index* from logical position to physical location, plus the ability to compute softmax in chunks.

Ablation, removing each piece in turn:

| Remove | What breaks |
|---|---|
| **Block table (indirection)** | Back to contiguous: reservation plus external fragmentation, 20–38% utilization |
| **On-demand allocation** (allocate all blocks at admission) | Back to reservation waste. You'd need to know the output length |
| **Fixed block size** (variable-size chunks) | External fragmentation returns. Fixed size means any free block fits any request, so the free list never fragments |
| **Reference counts** | No sharing: parallel sampling and beam search duplicate the prompt KV. The paper measured beam-search savings of 37.6–55.2% (Alpaca) and 44.3–66.3% (ShareGPT) |
| **Copy-on-write** | Sharing is only safe for read-only blocks, so the last partially-filled shared block would corrupt the other sample |
| **Online-softmax merge** | Can't compute attention block by block without materializing contiguous K/V, which is a copy per step |
| **Preemption** | On-demand allocation can deadlock or OOM when every running sequence needs one more block and none are free |

Why fixed-size blocks kill external fragmentation: any free block satisfies any request for one block. External fragmentation needs "enough total free memory, but no single hole big enough", and every request here asks for exactly one unit, so that can't happen.

## 8. Design knobs & alternatives

| Knob | Small value | Large value |
|---|---|---|
| **Block size B** | Less internal waste, finer prefix-cache hits, but more indirection, less coalescing, many tiny swap transfers | Better kernel efficiency, fewer table entries, but up to B−1 waste per sequence, and prefix hits only in multiples of B (TRT-LLM's 128 vs vLLM's 16) |
| **gpu_memory_utilization** | Safety margin for activation spikes, fragmentation of the PyTorch allocator | More blocks, risk of OOM on long prefill |
| **max_num_seqs / max_num_batched_tokens** | Less preemption, better inter-token latency | Higher throughput, more preemption under bursty load |
| **Preemption mode** | Recompute: no CPU memory, costs FLOPs | Swap: costs PCIe, needs pinned host pool |
| **Prefix caching** | Off: no cross-request reuse, no timing channel | On: skip prefill on hits, LRU churn, timing side channel unless salted per tenant |
| **KV dtype** | FP16/BF16: exact | FP8/INT4/2-bit (KIVI): 2–8× more tokens, accuracy cost |

**Competing approaches:**

- **Contiguous + oracle length prediction.** Predict output length and reserve exactly. Mispredictions force reallocation or waste. External fragmentation remains. It lost to paging even with a perfect oracle (vLLM vs Orca-Oracle: 1.7–2.7×).
- **vAttention** ([ASPLOS'25](https://arxiv.org/abs/2405.04437)). Keep KV **virtually contiguous**, map physical pages on demand through the CUDA VMM APIs (`cuMemMap`). Unmodified attention kernels, up to 1.23× throughput vs paged FlashAttention/FlashInfer kernels. Costs: driver page granularity (2 MB by default, which the paper works around), and less natural fine-grained sharing.
- **Radix-tree KV (SGLang RadixAttention).** Same physical pages, but indexed by a radix tree of token sequences instead of per-block hash chains. Natural for multi-call programs with branching prefixes, plus cache-aware scheduling.
- **Token-dropping / compression** (StreamingLLM, H2O, SnapKV, KIVI). Shrink the KV itself instead of packing it better. Orthogonal to paging and often combined, but lossy.

## 9. Where it breaks

- **Preemption thrash.** vLLM admits requests based on the prompt's blocks, then grows them on demand. Under load, many sequences hit "need one more block" together and the newest gets evicted, recomputed, re-admitted and evicted again. My toy simulation (section 13) shows **818 preemptions in ~1000 steps** at B = 16 with a greedy admission policy. Engines mitigate this with a watermark (keep x% of blocks free) and `max_num_seqs` caps. No published study I found measures thrash directly; treat that as a gap.
- **Output-length uncertainty is still the root problem.** Paging moves the cost from wasted memory to preemption risk; it doesn't remove it. See "Robust KV Cache Management under Output Token Length Uncertainty" ([arXiv 2607.16892](https://arxiv.org/abs/2607.16892), evaluated on the Azure LLM 2024 trace).
- **Head-of-line blocking.** FCFS plus long prefills stall decodes. Chunked prefill (Sarathi-Serve, [arXiv 2403.02310](https://arxiv.org/abs/2403.02310): 2.6× capacity for Mistral-7B, up to 5.6× for Falcon-180B vs vLLM) splits prefill into chunks batched with decodes. vLLM V1 enables it by default.
- **Cross-tenant timing side channels.** Shared prefix caches make cache hits measurably faster (lower time-to-first-token). *The Early Bird Catches the Leak* (Song et al., IEEE TIFS, [arXiv 2409.20002](https://arxiv.org/abs/2409.20002)) recovers other users' prompts **token by token** from KV-cache hit timing, with black-box tests against online services. *Auditing Prompt Caching in LM APIs* (Gu et al., ICML'25, [arXiv 2502.07776](https://arxiv.org/abs/2502.07776)) found **global cross-user cache sharing at 7 API providers, including OpenAI**. Block granularity matters: a 16-token block leaks at 16-token resolution, and the attacker brute-forces the next block. Mitigation: per-tenant `cache_salt` (vLLM's extra hash keys), or isolating caches per user, which gives up cross-user reuse.
- **Hash collisions in prefix caching.** vLLM's docs warn that fast non-cryptographic hashes (xxhash) carry collision risk in multi-tenant setups. A collision would serve another prompt's KV. Default is SHA-256, which is pickle-based, so hashes aren't stable across versions.
- **Kernel overhead.** The paper's paged attention kernel was 20–26% slower than FasterTransformer's at the op level. That matters at small batch, where memory isn't the bottleneck.
- **Small-B swap cost.** Many small PCIe transfers each pay a fixed overhead; see section 6.4.

**Misconceptions:**

- *"PagedAttention saves memory like quantization."* No. It stores **exactly the same KV**. It reduces *waste* and adds sharing. Attention output is mathematically identical.
- *"Fragmentation is zero."* External fragmentation is zero. Internal waste is up to B−1 slots per sequence.
- *"Paging means hardware page faults."* No MMU is involved in classic PagedAttention. The table lookup is a load inside the kernel. vAttention is the variant that uses the hardware's virtual memory.
- *"Prefix caching is free."* It costs hashing, LRU bookkeeping and a security boundary.

## 10. In the wild

- **vLLM V1.** Block size 16 by default. `gpu_memory_utilization` is **0.92** in `CacheConfig`; older docs and examples say 0.9. Prefix caching is **on by default** with hash chain `(parent, tokens, extras)` and LRU eviction that evicts a freed request's tail block first. Recompute is the default preemption mode, and chunked prefill is on by default with decodes scheduled first. The block table is append-only in V1. Deviation from the paper: the paper's default was swap with a CPU block pool, and prefix sharing needed explicit pre-reservation.
- **TensorRT-LLM.** `tokens_per_block` defaults to 128, must be a power of 2, and is set at engine build time. Block reuse is on by default, but blocks become reusable **only after the producing request terminates**. Optional host-memory secondary cache. Deviation: coarser blocks mean better kernels, coarser prefix hits and more tail waste.
- **TGI.** Uses vLLM's PagedAttention kernels and a block table. The docs don't describe a prefix-cache policy (unverified).
- **SGLang.** RadixAttention indexes KV pages by a radix tree for automatic reuse across calls. The paper reports up to 6.4× throughput, but that number covers the whole runtime, not RadixAttention alone. Page-size defaults weren't verified here.
- **Mooncake / LMCache / CachedAttention.** Treat blocks as units that move across GPU HBM, CPU DRAM and SSD, and between prefill and decode machines. Mooncake (Kimi): up to 525% throughput in simulated scenarios, 75% more requests on real workloads.

## 11. Frontier (what's new)

| Year · Venue | Work | Contribution | Link |
|---|---|---|---|
| 2025 · ASPLOS | **vAttention** (Prabhu et al.) | Demand-paged physical memory behind contiguous virtual KV through CUDA VMM. Unmodified kernels, up to 1.23× throughput vs paged FlashAttention/FlashInfer | [2405.04437](https://arxiv.org/abs/2405.04437) |
| 2024 · OSDI | **DistServe** (Zhong et al.) | Disaggregate prefill and decode onto different GPUs, which means moving KV blocks between them. 7.4× more requests or 12.6× tighter SLO, >90% of requests meet latency | [2401.09670](https://arxiv.org/abs/2401.09670) |
| 2024–25 · arXiv / FAST'25 | **Mooncake** (Qin et al., Moonshot AI) | KV-cache-centric disaggregated architecture pooling GPU/DRAM/SSD. Up to 525% throughput (simulated), +75% requests in production | [2407.00079](https://arxiv.org/abs/2407.00079) |
| 2024 · ICML | **KIVI** (Liu et al.) | Tuning-free 2-bit KV quantization (keys per-channel, values per-token). 2.6× less peak memory, 4× batch, 2.35–3.47× throughput | [2402.02750](https://arxiv.org/abs/2402.02750) |
| 2024 · arXiv | **SnapKV** (Li et al.) | Choose which KV to keep at prefill by an observation window. 3.6× faster generation, 8.2× memory efficiency at 16K, up to 380K context on one A100-80GB | [2404.14469](https://arxiv.org/abs/2404.14469) |
| 2024 · ICLR | **StreamingLLM** (Xiao et al.) | Attention sinks plus a sliding window keep models stable to 4M tokens. 22.2× faster than sliding-window recompute | [2309.17453](https://arxiv.org/abs/2309.17453) |
| 2025 · arXiv | **LMCache** (Cheng, Jiang et al.) | Open KV cache layer: capture, offload and share engine KV blocks across engines and queries | [2510.09665](https://arxiv.org/abs/2510.09665) |
| 2025 · arXiv | **PagedEviction** | Block-wise KV pruning inside vLLM's paged layout without CUDA kernel changes | [2509.04377](https://arxiv.org/abs/2509.04377) |

Trend: the frontier moved from *packing* the KV cache (solved by paging) to *where* KV lives (disaggregation, tiered offload), *whether* to keep it (eviction, quantization) and *who may share it* (side channels).

## 11b. Open problems

- **Scheduling under unknown output length.** Paging turned reservation waste into preemption risk. Admission control that keeps memory high without thrashing is still open. Learned length predictors are noisy, and conservative watermarks waste memory again ([2607.16892](https://arxiv.org/abs/2607.16892)).
- **Multi-tenant cache sharing vs privacy.** Global prefix caches leak, and per-user caches throw away reuse. Proposed middle grounds include sharing only after k users have hit a prefix, noise on TTFT, and per-org salts. Recent work also finds contention noise degrades the attacks but doesn't remove them (arXiv 2608.09225, 2609.06853, both very recent and unverified by me).
- **Lossy compression vs retrieval fidelity.** Eviction methods hold LongBench averages (SnapKV within ~1.5% at 10% retention per FastKV, [2502.01068](https://arxiv.org/abs/2502.01068)) but break on needle-style retrieval. Low budgets can also *lengthen* reasoning traces. Averages hide failures, so evaluating these methods is itself contested.
- **Paging + speculative decoding + preemption.** Speculative tokens take KV blocks that may be rolled back. I found no study of how this interacts with preemption under memory pressure.
- **Paging vs hardware VM.** vAttention shows that indirection in software isn't the only design. Whether future GPUs or drivers make fine-grained hardware paging cheap enough to retire software block tables is unresolved.
- **Measured fragmentation on real traces.** No paper I found compares contiguous vs paged allocation head to head on the public Azure LLM trace. Most "60–80% waste" numbers in blogs trace back to the vLLM paper's own setup.

## 12. Lineage

```
Atlas paging / virtual memory (1962)
  → OS copy-on-write fork, swapping (1970s–80s)
FasterTransformer (contiguous KV, static batch)
  → Orca (OSDI'22): iteration-level batching, still contiguous KV
    → vLLM / PagedAttention (SOSP'23): block tables, CoW, swap/recompute
      → SGLang RadixAttention (2023–24): radix-tree prefix reuse
      → vLLM automatic prefix caching (hash chains, LRU)
      → vAttention (ASPLOS'25): hardware VM instead of software tables
      → Disaggregation & tiering: DistServe (OSDI'24), Mooncake (FAST'25), LMCache (2025)
      → Lossy KV: StreamingLLM (ICLR'24), KIVI (ICML'24), SnapKV (2024), PagedEviction (2025)
```

## 13. Hands-on (≤30 min)

`kv_alloc_sim.py` in this folder simulates one GPU's KV pool (32,768 token slots, max_len 2048, 3000 synthetic requests with lognormal prompt and output lengths) under FCFS admission, decoding one token per step:

```bash
python3 kv_alloc_sim.py
```

Output (seed 0):

```
pool=32768 slots, max_len=2048, 3000 requests, mean prompt=231, mean output=433

allocator                   KV util  concurrent  ext frag  preempts
contiguous / max             32.0%        16.0     0.1%         -
contiguous / oracle          50.3%        24.7    78.9%         -
paged / block=1              97.8%        50.3      0.0%       881
paged / block=16             96.9%        49.8      0.0%       818
paged / block=128            89.7%        45.2      0.0%       463
paged / block=512            72.0%        34.6      0.0%        82
```

What to notice:

- **Contiguous/max: 32% utilization.** That's inside the paper's measured 20.4–38.2% band.
- **Contiguous/oracle**, which knows every output length, still reaches only 50%. External fragmentation is 79%: that much of the free memory sits outside the largest hole, so the next request doesn't fit even though plenty is free.
- **Paged/16: 96.9%.** That lines up with the paper's 96.3%, and concurrency triples vs max reservation.
- **Block size trade-off.** Utilization falls as B grows, matching the `(B−1)/(2·E[ℓ])` estimate.
- **Preemptions.** Greedy admission causes many preemptions at small B. Add a watermark (only admit if `free_blocks > 5%`) and watch preemptions drop and concurrency fall. That's the thrash vs utilization knob.

Try: raise `MAX_LEN` to 8192 (contiguous/max collapses), or make outputs bimodal.

## 14. Question ladder

**Mechanism**
1. Walk through what the kernel loads, in order, to compute attention for token 9 in the traced example.
2. When exactly does vLLM allocate a new physical block, and what is written into the block table?
3. In parallel sampling with n = 4, how many blocks are copied on the first decode step if the prompt is 30 tokens and B = 16?
4. What happens to a finished request's blocks when prefix caching is on vs off?

**Why**
5. Why do fixed-size blocks eliminate external fragmentation entirely?
6. Why does an "oracle" contiguous allocator that knows output length still lose to paging?
7. Why did vLLM pick B = 16 and not B = 1 or B = 256?
8. Why is preemption all-or-nothing per sequence group instead of evicting individual blocks like an OS?
9. Why does prefix caching hash only full blocks, and why chain the parent hash?

**Counterfactual**
10. Remove reference counting but keep block tables. What breaks, and what do you lose?
11. If output lengths were known exactly at admission, would paging still be worth it?
12. If GPUs had a cheap, fine-grained hardware MMU for device memory, what parts of PagedAttention would disappear?

**Adversarial**
13. How would you extract another tenant's system prompt from a shared prefix cache, and what does block size do to your attack cost?
14. Design a workload that maximizes preemption thrash in vLLM.
15. How could a hash collision in prefix caching cause a correctness or confidentiality failure?

**Connection**
16. How does PagedAttention relate to OS copy-on-write `fork()`, and where does the analogy fail?
17. How do disaggregated prefill/decode systems (DistServe, Mooncake) depend on block-granular KV?
18. How does KV quantization (KIVI) compose with paging?
19. How does the online-softmax merge in paged attention relate to FlashAttention's tiling?

**Open**
20. Can admission control achieve near-100% KV utilization without preemption, given unknown output lengths?
21. Is there a prefix-sharing policy that keeps most of the throughput benefit while being provably safe against timing attacks?
22. Will software block tables survive, or will hardware virtual memory (vAttention-style) replace them?

### Answers

<details><summary>1. Kernel loads for token 9</summary>
It reads the block table `[7, 1, 3]` and seq_len 9. For block 0 it loads K,V of physical #7 (4 tokens). For block 1, physical #1 (4 tokens). For block 2, physical #3, masking to 1 valid token. It computes block-local scores, max and sum, and merges them with the online-softmax rescaling. Each warp reads one block, so loads are coalesced inside a block. Only the block jump is indirect.
</details>

<details><summary>2. When a new block is allocated</summary>
Only when the sequence's last block is full and a new token must be written (`len % B == 0` before the write), or at prefill for `ceil(prompt/B)` blocks. The allocator pops any free physical block id and appends `(phys_id, filled=1)` to the table. If none is free, the scheduler preempts a sequence group first.
</details>

<details><summary>3. Blocks copied with n=4, prompt 30, B=16</summary>
The prompt uses blocks 0 (16 tokens, full) and 1 (14 tokens, partial), both refcount 4. On the first decode, each sample writes into block 1. The first three writers find refcount > 1 and copy (3 copies). The last finds refcount 1 and writes in place. So **3 block copies**, and block 0 is never copied.
</details>

<details><summary>4. Finished blocks with and without prefix caching</summary>
Off: refcount goes to 0 and the blocks return to the free pool, their contents meaningless. On (vLLM V1): full blocks keep their hash and go to an LRU free queue. They can be reused by a new request with a matching hash chain, or evicted when the allocator needs space. A freed request's blocks are queued in reverse, so the tail evicts first.
</details>

<details><summary>5. Fixed-size blocks and external fragmentation</summary>
External fragmentation means a request can't be satisfied despite enough total free memory, because no single hole is big enough. Every allocation here asks for exactly one block, and every free block is one block, so any free block satisfies any request.
</details>

<details><summary>6. Why oracle contiguous still loses</summary>
It removes reservation and internal waste but not external fragmentation. Variable-size contiguous chunks leave holes (79% of free memory outside the largest hole in the simulation). FCFS head-of-line blocking also means the next big request waits while smaller holes stay idle. It also can't share prompt blocks between samples.
</details>

<details><summary>7. Why B=16</summary>
Waste per sequence is about (B−1)/2, which favors small B. Kernel efficiency (coalesced loads, fewer table lookups, fewer small PCIe swaps) favors large B. The paper's sweep found 16–128 best on ShareGPT, with 16–32 best on short Alpaca sequences, so 16 is a safe default. TRT-LLM picks 128 to favor kernel efficiency.
</details>

<details><summary>8. All-or-nothing preemption</summary>
Every decode step reads every block of a sequence, so there's no cold subset to evict. A sequence missing any block can't run. Groups share blocks, so evicting one member alone frees little and breaks refcount accounting, which is why groups are gang-scheduled and preempted together.
</details>

<details><summary>9. Hashing full blocks and chaining</summary>
A partial block's contents still change as tokens are appended, so its hash isn't stable. Chaining the parent hash makes a block's identity depend on the whole prefix, not just its 16 tokens. KV at position t depends on all tokens before t, so the same 16 tokens after a different prefix have different K,V.
</details>

<details><summary>10. No reference counting</summary>
Paging and fragmentation benefits remain, but you can't share safely: you wouldn't know when a shared block can be freed or must be copied. Parallel sampling and beam search would duplicate prompt KV, losing the 37.6–66.3% beam-search savings, and prefix caching becomes impossible.
</details>

<details><summary>11. Known output lengths</summary>
Mostly yes. Exact reservation still suffers external fragmentation unless you compact memory (copying KV), and still can't share. Paging also lets you admit before the full length is needed, which raises concurrency over the request's lifetime. The gain would shrink, though: vLLM beat Orca-Oracle by 1.7–2.7×, vs 2.7–8× over Orca-Max.
</details>

<details><summary>12. Cheap hardware MMU</summary>
The software block table and indirection in kernels go away, which is roughly vAttention's approach using CUDA VMM. You'd still need on-demand mapping, refcounts or CoW (hardware CoW would need fault handling), a preemption policy and prefix hashing. The allocator logic stays; only the translation moves into hardware.
</details>

<details><summary>13. Prompt extraction from a shared prefix cache</summary>
Send probes that share a guessed prefix and measure TTFT. A hit (faster) confirms the guess matches cached blocks from another tenant. Extend block by block (Early Bird recovers prompts token by token). Larger B means more candidates per step, since a hit requires matching a whole block, but each confirmation leaks more. Defenses: per-tenant salt, isolation, or noise.
</details>

<details><summary>14. Maximizing preemption thrash</summary>
Many requests with short prompts (cheap to admit) and long outputs, arriving in bursts, with `max_num_seqs` high and no watermark. All sequences cross block boundaries at similar times, the pool empties, the newest get preempted, re-admitted and preempted again. Recompute mode makes each cycle cost a full prefill.
</details>

<details><summary>15. Hash collision failure</summary>
If two different prefixes hash equal, request B reuses request A's physical KV. B's output is then conditioned on A's tokens: wrong answers, plus possible leakage of A's content into B's output. That's why vLLM defaults to SHA-256 and warns about xxhash in multi-tenant settings.
</details>

<details><summary>16. Relation to fork()</summary>
Parallel samples are forked processes sharing pages, refcounted and copied on write. It fails because there's no MMU fault (CoW is triggered by the scheduler checking refcounts), no locality-driven paging, and contents can be recomputed instead of swapped.
</details>

<details><summary>17. Disaggregation and blocks</summary>
Prefill nodes produce KV and decode nodes consume it. Transfer, caching and placement operate on blocks: fixed-size units that can be sent over RDMA, stored in DRAM/SSD tiers (Mooncake, LMCache) and mapped into the decoder's block table without contiguity.
</details>

<details><summary>18. KIVI and paging</summary>
They're orthogonal. Quantization shrinks bytes per token (b), so each block holds the same tokens in fewer bytes, or more tokens fit in the pool. Paging still manages blocks. Complication: per-channel key quantization needs a group of tokens, which interacts with block boundaries and the residual full-precision tail.
</details>

<details><summary>19. Online softmax and FlashAttention</summary>
Same math. FlashAttention tiles K/V into chunks that fit SRAM and merges partial softmax results with the running max and sum. Paged attention just makes the tiles come from non-contiguous blocks given by a table, which is why paged variants of FlashAttention and FlashInfer exist.
</details>

<details><summary>20. Full utilization without preemption</summary>
Open. Without length knowledge you must either over-reserve (waste) or accept preemption risk. Predictors, watermarks and SLO-aware schedulers trade between the two. No method guarantees both under adversarial or heavy-tailed lengths.
</details>

<details><summary>21. Safe prefix sharing</summary>
Open. Candidates: share only prefixes seen by ≥k distinct tenants, add TTFT noise or padding, per-org salts (which gives up cross-org reuse), or constant-time responses (which gives up the latency benefit). Each costs hit rate or latency, and formal guarantees are rare.
</details>

<details><summary>22. Software tables vs hardware VM</summary>
Open. vAttention shows hardware VM can match or beat paged kernels, but 2 MB driver page granularity and the lack of hardware CoW for sharing limit it. Software tables remain the default in vLLM, TRT-LLM and SGLang as of 2026.
</details>

## 15. Go deeper next

1. **Chunked prefill and Sarathi-Serve:** stall-free batching, and why decode-first scheduling matters for TBT.
2. **Prefill/decode disaggregation (DistServe, Mooncake):** KV transfer over RDMA, goodput as the objective.
3. **KV-cache timing side channels:** prompt extraction attacks and defenses in multi-tenant serving.

## Sources

**Papers**
- Kwon et al., *Efficient Memory Management for Large Language Model Serving with PagedAttention*, SOSP 2023. https://arxiv.org/abs/2309.06180 · https://doi.org/10.1145/3600006.3613165
- Yu et al., *Orca*, OSDI 2022. https://www.usenix.org/conference/osdi22/presentation/yu
- Zheng et al., *SGLang: Efficient Execution of Structured Language Model Programs*. https://arxiv.org/abs/2312.07104
- Prabhu et al., *vAttention*, ASPLOS 2025. https://arxiv.org/abs/2405.04437
- Zhong et al., *DistServe*, OSDI 2024. https://arxiv.org/abs/2401.09670
- Agrawal et al., *Sarathi-Serve*. https://arxiv.org/abs/2403.02310
- Qin et al., *Mooncake*. https://arxiv.org/abs/2407.00079
- Liu et al., *KIVI*, ICML 2024. https://arxiv.org/abs/2402.02750
- Li et al., *SnapKV*. https://arxiv.org/abs/2404.14469
- Xiao et al., *StreamingLLM*, ICLR 2024. https://arxiv.org/abs/2309.17453
- Cheng et al., *LMCache*. https://arxiv.org/abs/2510.09665
- Gao et al., *CachedAttention*. https://arxiv.org/abs/2403.19708
- *PagedEviction*. https://arxiv.org/abs/2509.04377
- Song et al., *The Early Bird Catches the Leak*, IEEE TIFS. https://arxiv.org/abs/2409.20002
- Gu et al., *Auditing Prompt Caching in Language Model APIs*, ICML 2025. https://arxiv.org/abs/2502.07776
- *Robust KV Cache Management under Output Token Length Uncertainty*. https://arxiv.org/abs/2607.16892
- FastKV. https://arxiv.org/abs/2502.01068
- Ainslie et al., *GQA*. https://arxiv.org/abs/2305.13245
- Vaswani et al., *Attention Is All You Need*. https://arxiv.org/abs/1706.03762

**Code / docs**
- vLLM `CacheConfig`: https://raw.githubusercontent.com/vllm-project/vllm/main/vllm/config/cache.py
- vLLM engine args: https://raw.githubusercontent.com/vllm-project/vllm/main/vllm/engine/arg_utils.py
- vLLM prefix caching design: https://raw.githubusercontent.com/vllm-project/vllm/main/docs/design/prefix_caching.md
- vLLM optimization docs: https://docs.vllm.ai/en/latest/configuration/optimization/
- TensorRT-LLM KV cache reuse: https://nvidia.github.io/TensorRT-LLM/advanced/kv-cache-reuse.html
- TGI PagedAttention: https://huggingface.co/docs/text-generation-inference/en/conceptual/paged_attention
- HF KV cache docs: https://huggingface.co/docs/transformers/main/en/kv_cache
- OSTEP paging chapter: https://pages.cs.wisc.edu/~remzi/OSTEP/vm-paging.pdf

**Unverified / flagged:** SGLang page-size default; whether swap preemption still exists in vLLM V1; arXiv 2608.09225 and 2609.06853 (very recent, not checked); the A100 capacity numbers in §6.1 and the swap/recompute timings in §6.4 are back-of-envelope estimates, not measurements.
