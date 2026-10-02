# Speculative decoding: why rejection sampling keeps the output exactly target-distributed

`LLM systems · Speculative decoding (draft → verify → modified rejection sampling) · hard`

---

## 1. Bare-minimum context

- **Autoregressive decoding**: one forward pass of the model per output token; token t+1 depends on token t, so passes are serial. ([Leviathan et al.](https://arxiv.org/abs/2211.17192))
- **Memory-bandwidth bound**: at small batch, each decode step reads all weights + the KV cache from HBM but does very little math on them; time ≈ bytes / bandwidth, not FLOPs / peak. ([Chen et al.](https://arxiv.org/abs/2302.01318), "Conditional Scoring")
- **KV cache**: per-layer keys/values for every previous token, kept so each new token only computes its own row of attention. ([vLLM docs](https://docs.vllm.ai/en/latest/features/speculative_decoding/))
- **Logits → distribution**: temperature, top-k, top-p are transforms that turn logits into the distribution p you actually sample from.
- **Total variation distance** TV(p,q) = ½ Σ|p(x) − q(x)|: the largest gap between the probabilities p and q assign to any event.
- **Teacher forcing / scoring**: given a known sequence, one forward pass returns the model's next-token distribution at *every* position at once (same thing as a prefill).

## 2. The one-liner — and what it hides

> "A small model guesses a few tokens, the big model checks them in one pass, so you get 2–3× faster decoding with identical output."

What that sentence hides:

1. **"Checks them"** isn't "keeps the matching ones". Under sampling, checking means a specific accept rule `min(1, p/q)` plus a specific *resample from the residual* on rejection. A naive "keep if equal" check is also correct but accepts far less (Σ p·q instead of Σ min(p,q)).
2. **"Identical output"** means identical *in distribution*, in exact arithmetic. It is not bitwise identical in practice, and batched implementations have been shown to break even the distributional guarantee.
3. **"One pass costs the same as one token"** is only true while the target is memory-bound. At large batch it's compute-bound and the speedup can go **below 1×**.
4. **"2–3×"** depends on the acceptance rate α, the cost ratio c, and draft length γ through one formula, and α depends on temperature, domain, language and tokenizer.
5. **"Small model"**: modern drafters aren't separate small models. They're heads on the target's hidden states (EAGLE, MTP) or block-diffusion drafters (DFlash), and in production drafts are usually argmax.

## 3. The problem

Decoding a 70B model at batch 1 reads ~140 GB of bf16 weights per token. On Chinchilla 70B across 16 TPU v4, Chen et al. measured **14.1 ms/token** for plain sampling. The hardware is mostly idle on compute: the minimum time per token is model bytes ÷ memory bandwidth, and that floor holds no matter how many FLOPs remain unused.

The constraint that forces the design: **you can't parallelize across output positions**, because token t+1 needs token t. But scoring a *known* sequence of k tokens *is* parallel (it's a prefill), and at small k it costs about the same wall time as one decode step. Chen et al. give three reasons:

1. Linear layers stay memory-bound for small k.
2. Attention is dominated by reading the KV cache, which doesn't grow with k.
3. Tensor-parallel all-reduces are latency-bound, not throughput-bound.

So the question becomes: *can we get a cheap guess of the next k tokens, score them in one target pass, and still produce samples from exactly the target distribution?* Blockwise parallel decoding (Stern et al., NeurIPS 2018) already did this for **greedy** decoding only, with custom-trained heads. The 2022–23 papers did it for **sampling**, with any off-the-shelf drafter.

## 4. Mental model

**An intern and an editor.** The intern (draft model q) quickly writes the next γ words. The editor (target p) reads the whole draft in one sitting. Reading goes left to right: each word is kept with a probability that depends on how much the editor "agrees". At the first word the editor strikes out, they write their own word instead and throw away everything after. If they keep everything, they add one more word of their own for free.

**Where the analogy breaks:**

- The editor doesn't "pick a better word" on rejection. They sample from a specific **residual distribution** `max(0, p − q)` that excludes exactly the mass the intern already over-proposed. That's what makes the result exact, and it's non-intuitive: the replacement is biased *away* from what the intern liked.
- The editor's read isn't free when the editor is busy with many manuscripts (large batch). Then reading γ+1 words costs γ+1 times as much.
- The intern isn't required to be any good. Correctness holds for **any** q, even uniform. Only speed depends on q.

## 5. The mechanism, traced

One iteration, γ = 3, temperature 1. Prefix: `"The cat sat on the"`.

```
          ┌──────────── draft (3 serial cheap passes) ────────────┐
prefix ─► q1 ─sample─► x1="mat"  q2 ─► x2="and"  q3 ─► x3="purred"
          └──────────────────────────────────────────────────────┘
                              │ one target forward over prefix+[x1,x2,x3]
                              ▼
            p1(·|prefix)  p2(·|..mat)  p3(·|..mat and)  p4(·|..and purred)
```

Position by position (numbers illustrative):

| i | draft token | q_i(x_i) | p_i(x_i) | accept prob min(1, p/q) | r_i ~ U(0,1) | result |
|---|---|---|---|---|---|---|
| 1 | "mat" | 0.50 | 0.60 | 1.00 | 0.71 | accept |
| 2 | "and" | 0.40 | 0.10 | 0.25 | 0.83 | **reject** → stop |
| 3 | "purred" | — | — | — | — | discarded |

On the rejection at i = 2 we sample a replacement from `norm(max(0, p2 − q2))`. Suppose for the vocab slice `{and, ., ,, while}`:

```
p2 = [0.10, 0.50, 0.30, 0.10]
q2 = [0.40, 0.30, 0.20, 0.10]
p2−q2 clipped = [0, 0.20, 0.10, 0]  →  normalized [0, 0.667, 0.333, 0]
```

"and" can't be chosen again: it was already over-proposed. Sample "." → emit `"mat ."`. Two tokens for one target pass plus three cheap draft passes.

If all three had been accepted, we'd also sample a 4th token from p4 (the "bonus" token). So each iteration emits 1..γ+1 tokens, and it is never slower in target calls than plain decoding.

**KV-cache bookkeeping** (what engines actually do):

- vLLM v1 schedules the draft tokens as part of the request's lookahead slots. After verify it does `num_computed_tokens -= num_rejected`. The rejected K/V entries stay in the paged blocks and get overwritten next step. Rollback is pointer arithmetic, no copy. ([scheduler.py](https://github.com/vllm-project/vllm/blob/main/vllm/v1/core/sched/scheduler.py))
- HF transformers crops both caches with `past_key_values.crop(-n)`.
- llama.cpp calls `llama_memory_seq_rm(mem, seq, n_past, -1)`. For recurrent/SSM hybrids, which can't drop a suffix of the state, it checkpoints the state before verifying and restores it on partial accept.

Leviathan's Algorithm 1, compactly:

```python
def spec_step(prefix, Mp, Mq, gamma):
    xs, qs = [], []
    for _ in range(gamma):                      # serial, cheap
        q = Mq(prefix + xs); x = sample(q)
        xs.append(x); qs.append(q)
    ps = Mp.score(prefix, xs)                   # ONE pass → gamma+1 dists
    for i, x in enumerate(xs):
        if rand() > min(1, ps[i][x] / qs[i][x]):
            resid = clip(ps[i] - qs[i], 0); resid /= resid.sum()
            return prefix + xs[:i] + [sample(resid)]
    return prefix + xs + [sample(ps[gamma])]    # all accepted: bonus token
```

Notation trap: Leviathan uses p = target, q = draft. Chen et al. (DeepMind) **swap** them, so their `min(1, q/p)` is the same rule.

## 6. The math

**Symbols.** p(x) is the target distribution at one position, q(x) the draft's, both over vocab V. γ is the draft length. α is the expected acceptance probability. c is the cost ratio = (time of one draft pass) / (time of one target pass).

### 6.1 Exactness (one position)

Draft samples x ~ q. Accept with probability a(x) = min(1, p(x)/q(x)). On reject, sample from r(x) = max(0, p(x) − q(x)) / Z.

Probability of emitting x′ **via acceptance**:
```
P(draw x′, accept) = q(x′) · min(1, p(x′)/q(x′)) = min(q(x′), p(x′))
```
→ in plain terms: the draft "covers" each token up to whichever of p, q is smaller.

Total rejection probability:
```
β = Σ_x min(p,q)          (acceptance prob)
P(reject) = 1 − β = Σ_x (p − min(p,q)) = Σ_x max(0, p − q) = Z
```
The normalizer of the residual equals the rejection probability. That isn't luck: it's forced by both being "the mass of p not covered by q".

Probability of emitting x′ **via rejection**:
```
P(reject) · r(x′) = Z · max(0, p(x′) − q(x′)) / Z = p(x′) − min(p(x′), q(x′))
```
Sum:
```
P(emit x′) = min(p,q) + (p − min(p,q)) = p(x′)          ∎
```
→ in plain terms: acceptance hands out `min(p,q)` of each token's mass. Rejection hands out exactly the leftover `p − min(p,q)`, never more, because the residual only lives where p > q.

**Why this form and not simpler:**

- *Plain rejection sampling* accepts with p/(M·q), M = max p/q. That's exact but needs a global bound M and accepts much less often. Leviathan A.2 shows the one-shot version accepts Σ p·min(q/p) ≤ Σ min(p,q).
- *"Keep the draft if the target's own sample equals it"* (sample-and-match) is exact too: emit the target's sample regardless. But it accepts with probability Σ p·q. For the toy in §13 that's **0.23 vs 0.83**.
- `min(1, p/q)` is the *largest* per-token accept probability that still leaves a valid (non-negative) correction. Accepting more anywhere would require negative residual mass. This is the maximal coupling of p and q.

**Sequence level.** The argument applies position by position. After a rejection the remaining drafts are discarded, so every emitted token is p-distributed conditional on the prefix actually emitted. Induction gives the joint distribution.

**Greedy as a special case.** With temperature → 0, p and q become one-hot. min(1, p/q) ∈ {0, 1}, so you accept iff argmax q = argmax p. The residual is the target's one-hot, so you emit the target's argmax. That is exactly Stern et al.'s 2018 greedy-match rule.

### 6.2 Acceptance rate is 1 − TV

```
β = Σ_x min(p(x), q(x))
  = 1 − ½ Σ_x |p(x) − q(x)|        (since min(a,b) = (a+b−|a−b|)/2, Σp = Σq = 1)
  = 1 − TV(p, q)
α = E_prefix[β]
```
→ in plain terms: you accept exactly as often as the two distributions overlap. Leviathan calls the distance D_LK and proves D_LK = 1 − Σ min(p,q). The TV identity is ours (D_LK = ½‖p−q‖₁); the paper doesn't use the words "total variation". It's also the best possible: no coupling of p and q can make X_draft = X_target with probability above 1 − TV.

### 6.3 Expected tokens per iteration

Assume each position accepts independently with probability α (Leviathan's simplifying i.i.d. assumption). The number of accepted drafts N is a geometric variable capped at γ, and you emit N + 1 tokens:
```
E[tokens] = Σ_{k=0}^{γ} α^k = (1 − α^{γ+1}) / (1 − α)
```
→ in plain terms: each extra drafted token is worth α^k, so returns decay geometrically. With α = 0.8 the 10th draft token is worth 0.8¹⁰ ≈ 0.11 tokens.

### 6.4 Wall-time speedup

One iteration costs γ draft passes plus one target pass = T(γc + 1), where T is the time of one target pass. Assume scoring γ+1 tokens costs the same as one. Then:
```
speedup(α, γ, c) = (1 − α^{γ+1}) / ((1 − α)(γc + 1))
```
The numerator rewards drafting. The denominator charges γc for it. There is no closed-form optimal γ. Numerically:

| c \ α | 0.6 | 0.7 | 0.8 | 0.9 |
|---|---|---|---|---|
| 0.01 | γ=7, 2.30× | γ=9, 2.97× | γ=14, 4.23× | γ=24, 7.49× |
| 0.05 | γ=4, 1.92× | γ=6, 2.35× | γ=8, 3.09× | γ=13, 4.67× |
| 0.10 | γ=3, 1.67× | γ=4, 1.98× | γ=6, 2.47× | γ=10, 3.43× |

(Reproduced by `spec_sim.py`.) A useful corollary (Leviathan 3.9): any speedup is possible iff α > c, and γ = 1 already gives ≥ (1+α)/(1+c).

**Compute cost.** Total FLOPs grow by (1 − α)(γĉ + γ + 1)/(1 − α^{γ+1}), where ĉ is the per-token FLOP ratio. At α = 0.8, γ = 5 that's **1.63× more arithmetic for 3.69× less latency** (Table 1). Speculative decoding *spends* FLOPs. That's the whole bet, and it's why §9's batch problem exists.

## 7. Why it works

Core insight: **verification of k known tokens is parallel; generation isn't; and the maximal coupling of p and q lets you convert a cheap guess into an exact sample with acceptance 1 − TV.** Two independent properties:

- **Correctness** comes from the accept/residual pair being the maximal coupling. It holds for any q.
- **Speed** comes from the hardware regime: memory-bound target, so γ+1 positions ≈ 1 position. Plus a q that's cheap (small c) and close (small TV).

Ablations:

| Remove / change | What breaks |
|---|---|
| Residual resampling (just resample from p on reject) | Biased: tokens where q > p get over-represented. Mass is double-counted. |
| Discarding drafts after first reject | Later drafts were conditioned on a token you didn't emit, so the distribution is wrong. |
| Bonus token | Still correct, but you lose one free token per fully-accepted iteration (~α^γ fraction). |
| `min(1, p/q)` → `p ≥ q ? 1 : 0` | Lossy and biased toward the draft. This is what "lenience" knobs do. |
| Memory-bound regime | Scoring γ+1 costs ~(γ+1)×, so the speedup can drop below 1. |
| Same tokenizer | p and q are over different supports. Σ min(p,q) is undefined, and you need string-level methods. |

## 8. Design knobs & alternatives

- **γ (draft length)**: optimal grows with α and shrinks with c (table above). Chen et al. found K = 3 best on XSum nucleus. Total generation-time *variance* rises with K, which hurts P99. vLLM's MTP docs recommend starting at `num_speculative_tokens=1`.
- **Draft type**:
  - *Separate small model*: Leviathan used drafts ~100× smaller than the target. Chen used a 4B draft deliberately **wide and shallow** (8 layers, d=6144) because depth is serial latency.
  - Yan et al. (NAACL 2025): drafter LM quality correlates weakly with speedup; latency (depth) dominates. A shallow-wide drafter gave +41% throughput despite lower acceptance.
  - *Heads on target hidden states*: Medusa (independent heads), Hydra (sequentially dependent heads), EAGLE (feature-level autoregression → EAGLE-3 fuses low/mid/high features, "training-time test"), DeepSeek-V3 MTP (trained in at pretraining).
  - *No drafter*: n-gram / prompt lookup, Lookahead (Jacobi iteration), suffix decoding. Strong on code and repetition, weak on open text (n-gram ≈ 2.1× on code vs ≈ 1.3× GSM8K in vLLM per Liu et al. 2026).
  - *Block-diffusion drafter* (DFlash, 2026): drafts the whole block in one pass, removing the draft's own serial loop.
- **Chain vs tree**: a token tree (SpecInfer, Medusa, EAGLE-2 dynamic trees, Sequoia DP-optimal trees) verifies many branches in one pass with a tree attention mask. More accepted tokens, more verify FLOPs.
- **Verification rule**:
  - Token-wise `min(1,p/q)` (standard).
  - **Block verification** (Sun et al.): accept jointly; provably optimal in expected tokens and never worse; +5–8% wall-clock.
  - Multi-draft optimal transport (SpecTr and follow-ups).
  - Sample-and-match: exact, lower α.
  - Lossy rules: Medusa typical acceptance, TRT-LLM relaxed acceptance, Judge Decoding.
- **Draft sampling**: Leviathan samples drafts from q. vLLM defaults `draft_sample_method="greedy"` and SGLang uses "target_only" (draft probs = 0). Both treat the draft as a **point mass**. Still exact (q is one-hot, so accept with prob p(x), residual = p with x removed), but acceptance is p(x) rather than min(1, p/q).

Why the paper version "won": it's exact for *any* drafter with no retraining, so you could bolt it onto an existing serving stack. Blockwise parallel decoding needed custom heads and was greedy-only. Lossy variants win benchmarks and lose trust.

## 9. Where it breaks

- **Large batch / compute-bound.**
  - EAGLE-3 in vLLM on an RTX 3090 (8B): **1.75× at bs=2 → 1.01× at bs=56** (EAGLE-3 paper).
  - Meta measured stock vLLM EAGLE going from 1.3× to **0.7×** from bs 2 → 48 ([2508.08192](https://arxiv.org/abs/2508.08192)).
  - vLLM's own 2024 blog showed 1.4–1.8× *slowdowns* at high QPS.
  - Liu et al. (MLSys 2026): verification is 42–95% of runtime; EAGLE-3 on GSM8K goes 1.73× → 1.21× from bs 1 → 128.
- **Temperature.** In real models, acceptance length falls when sampling vs greedy (e.g. T5-XXL EnDe 3.4× at T=0 vs 2.6× at T=1). At T=0 both models' argmaxes often agree. At T=1 the long tails disagree. *Subtlety*: TV isn't monotone in T. At very high T both distributions flatten toward uniform and TV shrinks again (see §13). The practical drop is in the T ∈ (0, 1] range people use.
- **Out-of-domain and multilingual.** Drafters distilled on English chat accept much less on other languages and under-represented tasks. Sandler et al. 2025 call this the "disparate impact" of speculative decoding: users of low-resource languages get less speedup.
- **Tokenizer mismatch.** Breaks the shared-support assumption. Exact fixes exist (Intel's SLEM/TLI, ICML 2025, up to 2.8×), but HF's universal assisted generation falls back to sample-and-match, and vLLM's heterogeneous-vocab mode is greedy-only.
- **"Lossless" ≠ bitwise.**
  - Verification runs the target on k+1 query tokens, a different kernel shape than plain decode. Reductions reorder, logits shift slightly, and near-tie argmaxes flip.
  - vLLM docs: lossless "up to the precision limits of hardware numerics" and "does not currently guarantee stable token log probabilities".
  - Thinking Machines (2025) traced most LLM nondeterminism to non-batch-invariant kernels; batch-invariant kernels fix it at a speed cost.
- **Batched implementations getting it wrong.** "Batch Speculative Decoding Done Right" (2025) claims existing batched implementations break output equivalence through the ragged-acceptance problem (per-row position IDs, masks, KV offsets). Fixing alignment cost up to 40% overhead. (Claim from abstract; not independently reproduced here.)
- **Lossy acceptance quietly changes the model.** A 2026 study of lossy verification found truncation-style rules (e.g. Medusa typical acceptance) fall below a real truncation-sampling baseline, with the gap growing on hard reasoning (+6.67 pp on AIME). (From abstract/HF page.)
- **Timing side channel.** How many tokens arrive per iteration depends on the input, because acceptance depends on content. Wei et al. 2024 fingerprint queries from token-per-iteration and packet patterns; Carlini & Nasr 2024 show topic inference over encrypted traffic from efficiency-induced timing. Mitigations (padding, fixed-size token bundling) give back latency.
- **Drafter maintenance.** Hidden-state drafters are tied to one checkpoint. EAGLE-3 drafter training is reported at ~128 H200-hours for an 8B target, and more for larger ones. Every target fine-tune or quantization change means retraining, or acceptance decays.

**Misconceptions:**

- "It's a free 2–3×." That's at batch 1.
- "It never helps throughput." MagicDec shows it does at long context.
- "A better draft model is always better." Latency dominates.
- "Lossless means same text." It means same distribution.

## 10. In the wild

- **vLLM** ([rejection_sampler.py](https://github.com/vllm-project/vllm/blob/main/vllm/v1/sample/rejection_sampler.py)):
  - The docstring says it "strictly follows" Leviathan et al.
  - Ragged flattened batch: `draft_token_ids [num_tokens]` + `cu_num_draft_tokens`, output `[batch, max_spec_len+1]` padded with −1, `MAX_SPEC_LEN=128`.
  - Greedy rows use a Triton kernel that stops at the first draft ≠ argmax. Random rows accept if `draft_prob > 0 and target_prob/draft_prob >= u`.
  - The residual is sampled with an exponential race `argmax(prob / Exp(1))`, Gumbel-max-equivalent and needing no renormalization.
  - Defaults to argmax drafts. Also offers `rejection_sample_method="block"`.
  - Methods: EAGLE-3, MTP, draft model, n-gram, suffix decoding. Main branch verifies chains, not trees, as of this snapshot.
- **SGLang**:
  - EAGLE-2/3 with dynamic trees, three knobs `--speculative-num-steps / -eagle-topk / -num-draft-tokens`, auto-tuned if unset.
  - Tree verification kernel walks one coin per depth over siblings (SpecInfer-style sampling without replacement), with top-k/top-p applied by renormalizing the target before verify.
  - Lossy thresholds `speculative_accept_threshold_{single,acc}` default to 1.0 (lossless).
  - Llama-3.1-8B, MT-Bench, H100, bs=1: 158 → 373 tok/s with EAGLE-3 (2.4×).
- **TensorRT-LLM**:
  - Medusa is **greedy-only** there (no typical acceptance).
  - DeepSeek-R1 MTP uses strict top-1 prefix matching by default, plus an optional **relaxed acceptance** (draft within target top-10 and δ=0.6 of top-1) applied only to the thinking phase. 2.16× → 2.33× on 8×B200 at bs=1.
  - Docs call speculative decoding a technique "at low batch sizes".
- **HuggingFace transformers**:
  - `assistant_model=` is **batch size 1 only**.
  - Uses Leviathan's rule when `do_sample=True`, plus a heuristic draft-length schedule (+2 on full accept, −1 otherwise).
  - Prompt lookup via `prompt_lookup_num_tokens`.
  - Universal assisted generation re-tokenizes drafts through text to support different tokenizers, using match-based acceptance.
- **llama.cpp**:
  - Default verification is **sample-and-match** (`common_sampler_sample_and_accept_n`): sample from the full sampler chain (temp/top-k/top-p/grammar) and accept while equal. Exact for any sampler, lower α.
  - A newer rejection path takes real draft distributions.
  - Many `--spec-type` options including `draft-eagle3`, `draft-mtp`, `draft-dflash`, n-gram variants.
- **DeepSeek-V3 MTP**:
  - One MTP module (depth 1) trained with the model.
  - 2nd-token acceptance **85–90%**, giving **1.8× TPS** (tech report §5.4.3).
  - Engines reuse that single module recurrently to draft 3+ tokens (SGLang steps=3; TRT-LLM "MTP Eagle"), so deeper positions accept less than 85–90%.
  - SGLang: 1.8× at bs=1, 1.5× at bs=32 on H200 TP8.
- **Chinchilla 70B** (Chen et al.): 2.0–2.5× on 16 TPU v4, bs=1. HumanEval: 14.1 → 5.73 ms/token.

## 11. Frontier (what's new)

| Year · venue | Work | Contribution |
|---|---|---|
| 2024 · ICML* | [EAGLE](https://arxiv.org/abs/2401.15077) | Draft autoregressively at the *feature* level (second-to-top layer) with the next token fed in. 2.7–3.5× on LLaMA2-Chat-70B. |
| 2024 · EMNLP* | [EAGLE-2](https://arxiv.org/abs/2406.16858) | Acceptance is context-dependent. Grow a dynamic tree using the drafter's calibrated confidence. 3.05–4.26×. |
| 2025 · NeurIPS* | [EAGLE-3](https://arxiv.org/abs/2503.01840) | Drop feature regression and predict tokens directly. Fuse low/mid/high features. Train with simulated multi-step drafting ("training-time test"), so it scales with data. Up to 6.5×; ~1.38× at bs=64 in SGLang. De facto production drafter through mid-2026. |
| 2024 · ICLR 2025* | [MagicDec](https://arxiv.org/abs/2408.11049) | At long context + large batch the bottleneck is KV loading, not weights. A sparse-KV (StreamingLLM-style) drafter stays cheap, so **speedup grows with batch**. Up to 2.51× for Llama-3.1-8B at bs 32–256. |
| 2024 · ICLR 2025* | [Block verification](https://arxiv.org/abs/2403.10444) | Token-by-token verification is suboptimal. Verifying the draft jointly is optimal in expected tokens and never worse. Drop-in, +5–8% wall-clock. |
| 2025 · ICLR spotlight | [Multi-draft canonical decomposition](https://arxiv.org/abs/2410.18234) | Optimal multi-draft acceptance = importance-sampling selection + single-draft speculative sampling. Closed form for 2 identical drafts. |
| 2026 · ICLR | [Speculative Speculative Decoding (Saguaro)](https://arxiv.org/abs/2603.03251) | While the target verifies, the drafter pre-drafts for each *likely verification outcome*. If the real outcome is in the set, the next draft is ready instantly. ~30% over optimized speculative baselines, up to 5× over autoregressive. |
| 2026 · ICML | [DFlash](https://arxiv.org/abs/2602.06036) | A lightweight **block-diffusion** drafter conditioned on target hidden features denoises the whole draft block in one pass, removing the drafter's own serial loop. Verification is standard, so still lossless. >6× and up to 2.5× over EAGLE-3. |
| 2026 · arXiv | [DDTree](https://arxiv.org/abs/2604.12989), [xPress](https://arxiv.org/abs/2608.02438) | DFlash samples positions independently, so drafts are individually likely but jointly improbable. DDTree builds best-first trees from its per-position marginals. xPress adds a small causal refiner (a few Jacobi passes): ~30% longer acceptance, ~1.3× throughput over DFlash on Qwen3-8B. |
| 2026 · MLSys oral | [Performance or Illusion?](https://arxiv.org/abs/2601.11580) | First systematic study on production vLLM. Speedups shrink with batch, verification dominates, and per-position acceptance decays (MTP 0.92 → 0.68 → 0.38). An oracle proposer would get 2.75× vs 2.1× actual. |
| 2026 · ICML | [SPEED-Bench](https://arxiv.org/abs/2604.09557) | Successor to Spec-Bench, with throughput split across concurrencies. Synthetic inputs overestimate real throughput, and optimal γ depends on batch size. |

\* Venue from the frontier agent's knowledge / a search result, not confirmed on the arXiv page.

**The arc**:

1. Separate small drafter (2023).
2. Heads on the target's own hidden states (Medusa/Hydra/EAGLE/MTP, 2024).
3. Smarter trees (Sequoia, EAGLE-2).
4. EAGLE-3 (2025).
5. Parallel drafters, mainly block diffusion (2026).

The serial bottleneck has moved from the target into the drafter, and now the drafter is being parallelized too. In parallel, systems work (MagicDec, Saguaro) is rescuing the large-batch regime, and theory work (block verification, multi-draft OT) is squeezing the verifier.

## 11b. Open problems

- **Optimal multi-draft verification.**
  - The optimal acceptance rule for n drafts is an optimal-transport LP over V^n outcomes.
  - Closed form is known only for 2 identical drafts (Khisti et al.).
  - Hu et al. 2025 computed the true bound via the dual and showed existing verifiers fall short, with sampling *without* replacement beating with-replacement.
  - Thomas & Pal (Nov 2025) reduce it to a convex problem in ≤ V variables using polymatroid structure.
  - Hard because the obvious greedy construction (verify drafts one by one) isn't optimal, and the exact LP is exponential.
- **Optimal tree shape under real acceptance.**
  - Sequoia's DP assumes positional independence; real acceptance depends on context (EAGLE-2's observation).
  - EAGLE-2's dynamic tree is a heuristic, not proven optimal.
  - Joint optimization of tree shape × verifier × *batch-level* compute budget is open.
- **Adaptive draft length at large batch.**
  - SpecDec++ frames per-step γ as an MDP with a threshold policy (+7–11%), but that's batch 1.
  - At large batch, one row's long draft costs every row compute.
  - SPEED-Bench finds optimal γ depends on batch size. There's no principled scheduler.
- **Fundamental limits.**
  - Yin et al. (NeurIPS 2024): expected rejections ≥ Σ TV, and speculative decoding is instance-optimal among unbiased sequential algorithms.
  - Pankratov & Alistarh (Dec 2025): accepted tokens per iteration grow only **logarithmically** in verifier parallelism.
  - Open: whether parallel drafters (diffusion) change the constants enough to matter at production batch sizes.
- **Exactness in batched, nondeterministic systems.**
  - Distributional exactness assumes the target's logits don't depend on batch composition. They do.
  - Open: cheap batch-invariant kernels, and correct ragged-acceptance batching without a 40% tax.
- **Lossy vs lossless.**
  - Judge Decoding (ICLR 2025) argues the standard test rejects *good* drafts: even human or GPT-4o text gets low acceptance. It reports 9× on 8B/405B with a learned judge.
  - Critics (lossy-verification study, 2026) show quality loss grows with task difficulty.
  - Unresolved: is "match the target distribution" even the right objective for reasoning models? SpecReason and Speculative Thinking move to step-level, semantics-based acceptance.
- **Side channels vs speed.** No mitigation found removes input-dependent timing without giving back a meaningful fraction of the speedup.

## 12. Lineage

- **2018**: Blockwise Parallel Decoding (Stern, Shazeer, Uszkoreit). Greedy-only, custom k-head model, up to 3.3× on translation.
- **2021–22**: Shallow Aggressive Decoding / aggressive decoding (copy input for editing tasks).
- **Nov 2022 / Feb 2023**: Speculative decoding (Leviathan, Kalman, Matias, Google; ICML 2023) and speculative sampling (Chen et al., DeepMind), independent and concurrent. Modified rejection sampling makes it exact for sampling with any drafter.
- **2023**: SpecInfer token trees (ASPLOS 2024); SpecTr multi-draft OT (NeurIPS 2023); Online Speculative Decoding and DistillSpec (drafter alignment).
- **2024**: Medusa, Hydra, EAGLE, EAGLE-2, Lookahead, Sequoia, LayerSkip (self-speculation), TriForce/MagicDec (long context), block verification, DeepSeek-V3 MTP.
- **2025**: EAGLE-3 becomes the production default; multi-draft theory; Judge Decoding; speculation for reasoning (SpecReason).
- **2026**: Diffusion drafters (DFlash → DDTree, xPress); Saguaro; systematic production studies (MLSys 2026, SPEED-Bench).

## 13. Hands-on (≤30 min)

`spec_sim.py` in this folder (numpy only, runs in ~2 s):

```bash
python spec_sim.py
```

What it shows, with actual output on seed 0 (V = 8, draft = target logits + Gaussian noise):

```
target p   : [0.0436 0.026  0.122  0.0418 0.0116 0.0698 0.4599 0.2253]
empirical  : [0.0434 0.0264 0.1217 0.0414 0.012  0.0706 0.4584 0.2261]
max |diff| : 0.0015   (sampling noise ~ 0.0022)
alpha theory = sum min(p,q) = 0.8256 = 1-TV = 0.8256; measured = 0.8258
sample-and-match acceptance = sum p*q = 0.2297
```

1. **Exactness**: 200k speculative samples land on p within sampling noise, even though q is visibly different.
2. **α = Σ min(p,q) = 1 − TV**: measured acceptance matches theory to 3 decimals.
3. **Why the residual matters**: sample-and-match would accept 0.23 instead of 0.83, roughly 3.6× fewer accepted drafts with the same draft. That's the cost llama.cpp's default path pays under sampling.
4. **Temperature isn't monotone**: α = 1.00 at T = 0.01 (argmaxes agree), 0.71 at T = 0.5, then *rises* to 0.90 at T = 2 as both distributions flatten. Real models in T ∈ (0, 1] show the drop because their tails disagree.
5. **Speedup table**: Theorem 3.8 maximized over γ, reproducing §6.4.

Things to try:

- Break the residual by resampling from `p` instead of `norm(max(0, p−q))` and watch the empirical distribution drift toward q.
- Make q uniform and confirm it's still exact, just slow (α = Σ min(p, 1/V)).
- Set q one-hot at argmax q (vLLM's default draft) and compare α to the sampled draft.

## 14. Question ladder

### Mechanism
1. What exactly does the target compute in its single verification pass, and why does it return γ+1 distributions rather than γ?
2. On rejection at position i, why are drafts i+1..γ discarded instead of re-checked?
3. What does vLLM do to the KV cache when 2 of 4 drafts are rejected?
4. With greedy decoding, what do the accept rule and the residual reduce to?

### Why
5. Why `min(1, p/q)` and not `p/q` capped by some global constant M?
6. Why does the residual's normalizer equal exactly the rejection probability?
7. Why did Chen et al. build a wide, shallow 4B drafter instead of using a Chinchilla-optimal 7B?
8. Why do vLLM and SGLang default to *argmax* drafts, and why is that still exact?
9. Why does the optimal γ grow with α?

### Counterfactual
10. If you resample from p (not the residual) on rejection, which tokens become over-represented?
11. What happens to speedup if c = 0 (an n-gram drafter)? Is the speedup then unbounded?
12. What if draft and target use different tokenizers but you run the standard algorithm anyway on the intersection vocab?
13. What if decode were compute-bound at batch 1?

### Adversarial
14. How could an observer of an encrypted streaming response learn something about the prompt because of speculative decoding?
15. Construct p, q such that α is near 0 but q is "good" in the sense of having the same argmax as p.
16. How could a batched implementation silently produce wrong outputs while every per-row unit test passes?

### Connection
17. How does speculative decoding relate to branch prediction in CPUs: what's the analog of the misprediction penalty?
18. How does MagicDec's "KV loading dominates" argument connect to PagedAttention and long-context serving?
19. How is the accept/residual construction related to the maximal coupling of two distributions?
20. How does DeepSeek-V3's MTP training objective double as a drafter?

### Open
21. Is lossless verification the right objective for reasoning models, or should acceptance be semantic?
22. Can a diffusion drafter's independence across positions be fixed without reintroducing serial cost?
23. What's the right per-row γ policy when compute is shared across a batch of 128?

### Answers

<details><summary>1</summary>It runs a teacher-forced forward over prefix + [x1..xγ]. The output at each position k is p(·|prefix, x1..x_{k−1}), for k = 1..γ+1. The extra one is the distribution after the last draft token, used for the bonus token when all γ are accepted.</details>

<details><summary>2</summary>They were drafted conditional on x_i, which you just didn't emit. Their q and p were computed for a prefix that no longer exists, so accepting them would sample from the wrong conditional.</details>

<details><summary>3</summary>It decrements `num_computed_tokens` by the number rejected. The K/V for the rejected positions stay in the paged blocks and are overwritten by the next step. No copy, no free.</details>

<details><summary>4</summary>p and q become one-hot. min(1, p/q) is 1 if argmax q = argmax p, else 0. The residual is the target's one-hot, so you emit the target's argmax. That is Stern et al.'s greedy match.</details>

<details><summary>5</summary>Capping by M needs a global bound on p/q (hard to know, often huge), and accepts p/(Mq), far less often. min(1, p/q) is the largest per-token acceptance that still leaves a non-negative correction mass. It achieves the optimal 1 − TV.</details>

<details><summary>6</summary>Both equal "the mass of p not covered by q": P(reject) = 1 − Σmin(p,q) = Σ(p − min(p,q)) = Σmax(0, p − q).</details>

<details><summary>7</summary>Draft depth is serial latency, and the drafter had to serve on the same 16 TPUs as the target with low communication. A 7B was fastest on 4 TPUs and slower on 16. Low c matters more than raw draft quality (also Yan et al. 2025).</details>

<details><summary>8</summary>It saves storing full draft distributions and is simpler. If q is a point mass at x, accept with min(1, p(x)/1) = p(x). The residual max(0, p − δ_x) is p with x removed, renormalized. The proof still goes through. The cost is acceptance p(x) instead of min(1, p(x)/q(x)).</details>

<details><summary>9</summary>Each extra draft is worth α^k expected tokens and costs c. Higher α means the geometric tail decays slower, so more drafts pay for their cost.</details>

<details><summary>10</summary>Tokens with q > p. They get min(p,q) = p via acceptance, plus more via resampling from p, so they're over-represented. Tokens with p > q are under-represented.</details>

<details><summary>11</summary>Speedup → (1 − α^{γ+1})/(1 − α) ≤ 1/(1 − α). It's bounded by α, not by c. Leviathan's bigram draft for T5-XXL had α ≈ 0.2, giving 1.25×. In practice there's also the hidden cost that verifying γ+1 positions isn't free.</details>

<details><summary>12</summary>p and q aren't over the same events: a token in one maps to several or a partial token in the other. The p/q ratio isn't meaningful and exactness breaks. You need string-level methods (SLEM) or the vocab intersection with care (TLI), or fall back to sample-and-match.</details>

<details><summary>13</summary>Scoring γ+1 positions would cost ~(γ+1) target passes. Speedup ≈ E[tokens]/((γ+1) + γc), and since E[tokens] ≤ γ+1 that's < 1. Speculative decoding only helps when there's spare compute.</details>

<details><summary>14</summary>Tokens per iteration (visible as packet sizes or timing in a stream) depend on how predictable the content is to the drafter, which depends on the prompt and response. Patterns can fingerprint queries or topics (Wei et al. 2024; Carlini & Nasr 2024). Defenses: pad or bundle tokens to a fixed cadence.</details>

<details><summary>15</summary>Let p = [0.34, 0.33, 0.33] and q = [0.98, 0.01, 0.01]. The argmax matches, but Σmin = 0.34 + 0.01 + 0.01 = 0.36. Under sampling, an overconfident drafter is penalized even when its top token is right.</details>

<details><summary>16</summary>Rows accept different counts, so per-row position IDs, attention masks and KV offsets diverge (ragged tensors). If padding or alignment is wrong, a row attends to another row's stale KV or a wrong position. Single-row tests can't see it. "Batch Speculative Decoding Done Right" reports exactly this class of bug.</details>

<details><summary>17</summary>Draft = predicted path. Verify = commit. Rejection = misprediction: you discard younger speculative work and resume from the correct state. The penalty is the wasted draft passes plus the wasted verify FLOPs on rejected positions. Unlike CPUs, the "architectural state" here is a distribution, so commit uses the residual, not the true value.</details>

<details><summary>18</summary>At long context, KV bytes per sequence dominate weight bytes, so decode stays memory-bound per sequence even at large batch. A drafter with a small or sparse KV cache is cheap relative to the target, which restores the spare-compute condition.</details>

<details><summary>19</summary>A maximal coupling of p and q makes X ~ q and Y ~ p equal with probability 1 − TV, the best possible. Speculative sampling is exactly that coupling: emit X when the coupling says X = Y, otherwise sample Y from the leftover.</details>

<details><summary>20</summary>MTP modules are trained during pretraining to predict tokens beyond next, conditioned on the main model's hidden state. At inference that's a built-in drafter with no separate model or cache. DeepSeek-V3 reports 85–90% acceptance of the second token.</details>

<details><summary>21</summary>Open. Lossless keeps guarantees, but Judge Decoding shows it rejects many good drafts. Semantic or step-level acceptance (SpecReason) is faster and sometimes more accurate, but quality loss grows on hard tasks for some lossy rules. No consensus.</details>

<details><summary>22</summary>Open. xPress adds a small causal refiner with a few Jacobi passes, and DDTree adds trees over marginals. Both recover some joint structure at small serial cost. Whether that closes the gap without new serial depth is unsettled.</details>

<details><summary>23</summary>Open. Long drafts for one row spend shared verify compute. SPEED-Bench shows the optimal γ shifts with batch size. Batch-aware γ scheduling (dynamic speculative decoding in vLLM, SGLang auto-tuning) is heuristic today.</details>

## 15. Go deeper next

1. **Maximal coupling and optimal-transport verification**: the theory behind multi-draft (SpecTr → canonical decomposition → global resolution).
2. **Batch-invariant kernels and LLM nondeterminism**: why logits depend on batch shape, and what it costs to fix.
3. **Block-diffusion language models**: how DFlash-style drafters denoise a block, and why independence across positions hurts acceptance.

## Sources

**Papers**
- Leviathan, Kalman, Matias. Fast Inference from Transformers via Speculative Decoding (ICML 2023). https://arxiv.org/abs/2211.17192
- Chen et al. Accelerating LLM Decoding with Speculative Sampling (DeepMind 2023). https://arxiv.org/abs/2302.01318
- Stern, Shazeer, Uszkoreit. Blockwise Parallel Decoding (NeurIPS 2018). https://arxiv.org/abs/1811.03115
- SpecInfer. https://arxiv.org/abs/2305.09781
- SpecTr. https://arxiv.org/abs/2310.15141
- Medusa. https://arxiv.org/abs/2401.10774 · Hydra. https://arxiv.org/abs/2402.05109
- EAGLE. https://arxiv.org/abs/2401.15077 · EAGLE-2. https://arxiv.org/abs/2406.16858 · EAGLE-3. https://arxiv.org/abs/2503.01840
- Lookahead Decoding. https://arxiv.org/abs/2402.02057
- Sequoia. https://arxiv.org/abs/2402.12374
- TriForce. https://arxiv.org/abs/2404.11912 · MagicDec. https://arxiv.org/abs/2408.11049
- LayerSkip. https://arxiv.org/abs/2404.16710
- Block Verification. https://arxiv.org/abs/2403.10444
- Multi-Draft Canonical Decomposition. https://arxiv.org/abs/2410.18234
- Towards Optimal Multi-draft SD. https://arxiv.org/abs/2502.18779
- Global Resolution (multi-draft). https://arxiv.org/abs/2511.15898
- DeepSeek-V3 Technical Report. https://arxiv.org/abs/2412.19437
- DFlash. https://arxiv.org/abs/2602.06036 · DDTree. https://arxiv.org/abs/2604.12989 · xPress. https://arxiv.org/abs/2608.02438
- DiffuSpec. https://arxiv.org/abs/2510.02358 · DART. https://arxiv.org/abs/2601.19278
- Speculative Speculative Decoding (Saguaro). https://arxiv.org/abs/2603.03251
- SpecReason. https://arxiv.org/abs/2504.07891 · Speculative Thinking. https://arxiv.org/abs/2504.12329
- Spec-Bench. https://arxiv.org/abs/2401.07851 · SPEED-Bench. https://arxiv.org/abs/2604.09557
- Speculative Decoding: Performance or Illusion? (MLSys 2026). https://arxiv.org/abs/2601.11580
- Decoding Speculative Decoding (NAACL 2025). https://arxiv.org/abs/2402.01528
- Batch Speculative Decoding Done Right. https://arxiv.org/abs/2510.22876
- The Disparate Impacts of Speculative Decoding. https://arxiv.org/abs/2510.02128
- Lossless SD for Heterogeneous Vocabularies (ICML 2025). https://arxiv.org/abs/2502.05202
- Judge Decoding (ICLR 2025). https://arxiv.org/abs/2501.19309
- Yin et al., theoretical limits (NeurIPS 2024). https://arxiv.org/abs/2411.00841
- Pankratov & Alistarh, SD speed-of-light. https://arxiv.org/abs/2512.11718
- SpecDec++. https://arxiv.org/abs/2405.19715
- Online Speculative Decoding. https://arxiv.org/abs/2310.07177 · DistillSpec. https://arxiv.org/abs/2310.08461
- When Speculation Spills Secrets. https://arxiv.org/abs/2411.01076
- Remote Timing Attacks on Efficient LM Inference. https://arxiv.org/abs/2410.17175
- Meta production speculative decoding. https://arxiv.org/abs/2508.08192
- Revisiting Lossy Verification (2026, abstract only). https://huggingface.co/papers/2607.26627

**Code / docs**
- vLLM speculative decoding docs. https://docs.vllm.ai/en/latest/features/speculative_decoding/
- vLLM rejection sampler. https://github.com/vllm-project/vllm/blob/main/vllm/v1/sample/rejection_sampler.py
- vLLM v1 scheduler. https://github.com/vllm-project/vllm/blob/main/vllm/v1/core/sched/scheduler.py
- SGLang speculative decoding. https://docs.sglang.io/advanced_features/speculative_decoding.html
- SGLang DeepSeek-V3. https://docs.sglang.io/basic_usage/deepseek_v3.html
- TensorRT-LLM speculative decoding. https://nvidia.github.io/TensorRT-LLM/advanced/speculative-decoding.html
- TensorRT-LLM DeepSeek-R1 MTP blog. https://github.com/NVIDIA/TensorRT-LLM/blob/main/docs/source/blogs/tech_blog/blog02_DeepSeek_R1_MTP_Implementation_and_Optimization.md
- TensorRT-LLM guided + speculative decoding. https://nvidia.github.io/TensorRT-LLM/1.2.0/blogs/tech_blog/blog12_Combining_Guided_Decoding_and_Speculative_Decoding.html
- HF candidate_generator.py. https://github.com/huggingface/transformers/blob/main/src/transformers/generation/candidate_generator.py
- llama.cpp speculative docs. https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md
- llama.cpp sampling.cpp. https://github.com/ggml-org/llama.cpp/blob/master/common/sampling.cpp
- Medusa reference utils. https://github.com/FasterDecoding/Medusa/blob/main/medusa/model/utils.py
- MagicDec code. https://github.com/Infini-AI-Lab/MagicDec

**Articles**
- vLLM blog, speculative decoding (Oct 2024). https://vllm.ai/blog/2024-10-17-spec-decode
- HF assisted generation. https://huggingface.co/blog/assisted-generation
- HF universal assisted generation. https://huggingface.co/blog/universal_assisted_generation
- LMSYS EAGLE-3 on Vertex. https://lmsys.org/blog/2025-12-01-eagle3-vertex/
- Together AI, MagicDec blog. https://together.ai/blog/speculative-decoding-for-high-throughput-long-context-inference
- Thinking Machines, Defeating Nondeterminism in LLM Inference (URL inferred from title, not fetched). https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/

**Unverified flags**
- Some venues (marked *) and 2026 papers summarized from abstracts.
- Leviathan's Sec 3.3 says c < 0.05, but Table 4 lists c = 0.11: an internal inconsistency in the paper.
- "α = 1 − TV" is our identification (D_LK = ½‖p−q‖₁).
