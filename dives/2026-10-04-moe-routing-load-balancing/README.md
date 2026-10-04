# MoE routing and load balancing: from aux-loss to aux-loss-free

**Computer science · ML/AI · MoE top-k gating, expert collapse, aux-loss vs aux-loss-free (bias) balancing · hard · 2026-10-04**

---

## 0b. Plain English first

**Explain it simply.** Picture a hospital with 256 specialist doctors and a triage nurse at the door. Each patient (a word/token in a sentence) sees the nurse for a second, and the nurse sends them to the 8 doctors who look most relevant. Only those 8 do any work, so the hospital can employ a huge staff without every patient costing 256 consultations. That is a Mixture-of-Experts (MoE) language model: huge total knowledge, small cost per word.

The catch: the nurse learns from outcomes. Doctors who see more patients get better at their job, so the nurse sends them even more patients, and the rest sit idle and never improve. Soon 5 doctors do everything and 250 are wasted. Worse, on a real hospital floor the busiest doctor's queue sets how long everyone waits. Keeping the queues even is **load balancing**.

The classic fix is to *punish the nurse* (an extra "fairness penalty" on top of the real goal). It works, but the penalty fights the real goal: the nurse stops sending patients to the best doctor just to look fair. The newer fix (DeepSeek, 2024) is to leave the nurse alone and put a *sticky note on each doctor's door*: "busy, -0.001" or "idle, +0.001". The nurse still decides by merit, but the sticky notes tilt close calls toward idle doctors. Notes only change who gets *picked*, never how much that doctor's opinion *counts*.

**Everyday example.** 1,000 patients arrive, each needs 2 doctors → 2,000 consultations; fair share is 500 per doctor with 4 doctors. Doctor A gets 820, B 430, C 300, D 450. After the shift: A's note goes down a notch, B/C/D go up a notch. Next shift, a patient for whom A and B score nearly the same goes to B. Repeat 400 shifts and everyone sits near 500. Nobody was fined.

**Bridge.** Now the same thing, technically.

---

## 1. Bare-minimum context

- Transformer block = attention + position-wise FFN; MoE replaces the one FFN by N parallel FFNs ("experts") plus a router. [Shazeer 2017](https://arxiv.org/abs/1701.06538)
- Router = linear map `W_g ∈ R^{d×N}` from token hidden state `u` to N logits; top-k choose experts; output = gate-weighted sum of expert outputs.
- Total params ≠ active params; FLOPs/token scale with active (k experts), memory scales with total (N experts).
- Expert parallelism (EP): experts sharded across GPUs; tokens move via all-to-all dispatch/combine, so slowest GPU gates each layer.
- Top-k is non-differentiable w.r.t. *which* experts win; gradient reaches the router only via the gate values of chosen experts.
- Capacity factor (CF): hard per-expert token cap `CF · T/N`; overflow tokens are dropped (skip via residual). [Switch Transformer](https://arxiv.org/abs/2101.03961)

## 1b. Real-world context

**What it is.** A sparsely-activated FFN: N experts, per-token router picks k. Compute per token ≈ dense model with k experts; capacity ≈ N experts.

**Why it exists.** Dense scaling cost grows with every parameter. Sparse gating decouples capacity from FLOPs. Shazeer 2017 reached 137B params with up to 4096 experts; GShard (2020) hit 600B+ on 2048 TPUv3 in 4 days. Without balancing, learned routers collapse onto a few experts (see §9), wasting the extra parameters and breaking EP efficiency.

**Where it's used** (configs from model cards / papers; verify per release):

| System | Config | Role of routing |
|---|---|---|
| Mixtral 8x7B (Mistral) | 8 experts, top-2, ~47B total / ~13B active | coarse experts, softmax over top-2 logits |
| DeepSeek-V3/R1 | 1 shared + 256 routed, top-8, node-limited (M=4), 671B/37B | sigmoid affinity + aux-loss-free bias ([paper](https://arxiv.org/abs/2412.19437)) |
| OLMoE (AI2) | 64 experts, top-8, 7B total / 1B active, dropless | fully open recipe with routing analysis ([paper](https://arxiv.org/abs/2409.02060)) |
| Qwen MoE family | Qwen1.5-MoE: 60 routed + 4 shared, top-4; Qwen3-30B-A3B: 128 experts top-8 | global-batch balance loss (Qwen team's own paper below) |
| DBRX (Databricks) | 16 experts, top-4, 132B/36B | fine-grained vs Mixtral's 8 |
| Grok-1 (xAI) | 8 experts, top-2, 314B | open weights, coarse experts |
| Llama 4 (Meta) | Scout 16 experts / Maverick 128; shared expert + routed | **config details from secondary sources, unverified here** |
| Switch / ST-MoE (Google) | top-1, 128 experts / 32 experts | origin of aux loss and router z-loss |

**How it's used.** Practitioner touches: `num_experts`, `num_experts_per_tok` (top-k), balance-loss coefficient, capacity factor, EP size.

```bash
# Megatron-Core style flags (values as reported by implementation research; check your version's docs)
--num-experts 8 --moe-router-topk 2 \
--moe-router-load-balancing-type aux_loss --moe-aux-loss-coeff 1e-2 \
--moe-grouped-gemm --expert-model-parallel-size 4
```

```python
# the router, minimal (token-choice, Mixtral-like)
logits = h @ W_gate                          # [T, N]
w, idx = torch.topk(logits, k, dim=-1)       # select
w = torch.softmax(w, dim=-1)                 # gate over the k winners only
out = sum(w[:, j:j+1] * experts[idx[:, j]](h) ...)   # grouped GEMM in practice
```

**When to use / not.** Use MoE for high-concurrency serving and training where FLOPs are the bill and VRAM/interconnect are available. Prefer dense for low-traffic or single-GPU deployments (all N experts must still sit in memory: e.g. a 400B-total MoE needs multi-GPU just to load), strict latency-variance needs, or when you lack all-to-all bandwidth. Wrong-choice signs: GPU utilisation under ~50% at inference, wide gap between p50 and p99 step time, hot-expert GPU pegged while others idle.

**Who should care.** ML engineers pretraining MoEs (balance method decides quality), infra/serving engineers (stragglers, batch-dependent routing), security engineers (cross-batch leaks, §9).

## 2. The one-liner and what it hides

*"A router sends each token to its top-k experts, and a balancing loss keeps experts evenly used."* It hides:

1. **Balance has two meanings**: per-sequence vs per-batch vs per-corpus. They are different constraints with different costs to quality.
2. **The aux loss is a second objective** whose gradient lands on the same router weights as the LM loss.
3. **Selection and weighting need not use the same score.** That separation is the whole trick of loss-free balancing.
4. **Routing collapse is a feedback loop**, not a bug in init.
5. **At inference, nobody balances for you**: routing depends on who shares your batch.

## 3. The problem

- Compute per layer is gated by the *max* expert load under EP, not the mean. With mean 500 and max 1,750 (my toy run below: MaxVio ≈ 2.5), the layer takes ~3.5× the balanced time.
- Capacity caps (Switch: CF 1.0–2.0; ST-MoE: 1.25 train / 2.0 eval) turn imbalance into **dropped tokens** (quality loss) or padding (wasted FLOPs).
- Unbalanced training starves experts of gradient, so extra parameters are dead weight.

## 4. Mental model

Triage nurse + doctors (§0b). *Where it breaks*: unlike patients, tokens are not interchangeable; "similar tokens go to similar experts" is *desired* (that is specialization) but is exactly what makes load skewed when the data is skewed. Perfect balance and perfect specialization conflict, and the field disagrees where to set the dial (§11b).

## 5. The mechanism, traced (DeepSeek-V3-style, 4 experts, k=2 for readability)

One token with router logits `u·e_i = [1.2, 0.4, -0.3, 0.9]`. V3 uses sigmoid, not softmax.

```
affinity s_i = sigmoid(logit)    = [0.769, 0.599, 0.426, 0.711]
bias b_i (running state)         = [-0.20, +0.05, +0.12,  0.00]   # expert 0 has been hot
selection score s_i + b_i        = [0.569, 0.649, 0.546, 0.711]
top-2 of selection score         -> experts {3, 1}      (unbiased top-2 would be {0, 3})
gate g'_i = s_i for chosen       = {e1: 0.599, e3: 0.711}   # UNBIASED
g_i = g'_i / sum(g')             = {e1: 0.457, e3: 0.543}
y = x + 0.457*E1(x) + 0.543*E3(x) (+ shared expert output)
```

After the batch (T=1000 tokens, k=2 → 2000 assignments, mean load 500) loads `[820, 430, 300, 450]`:

```
e_i = mean - load_i = [-320, +70, +200, +50]
b_i += gamma * sign(e_i), gamma = 0.001   ->  b = [-0.201, +0.051, +0.121, +0.001]
```

No gradient touched anything. The bias is controller state, not a parameter. Selection ≠ weighting: expert 0 lost the slot but its gate math is unchanged for tokens that still pick it.

## 6. The math

**Switch/GShard aux loss** (Switch Eq. 4–6): `L_aux = α · N · Σ_i f_i · P_i`, with `f_i = (1/T) Σ_x 1[argmax p(x) = i]` (hard fraction) and `P_i = (1/T) Σ_x p_i(x)` (soft prob mass); N experts, T tokens, α=1e-2 in Switch.

- Under uniform routing `f_i = P_i = 1/N` → `L = α N · N · (1/N²) = α`. By Cauchy–Schwarz-type rearrangement this is the minimum for fixed Σ P_i = 1.
- Why a product, not `f²` or `P²`? `f_i` is non-differentiable (argmax). Using `f_i · P_i` lets gradient flow through `P_i` weighted by *how loaded expert i actually is*: `∂L/∂p_i(x) = α N f_i / T`. Popular experts get pushed down proportionally, and the loss is differentiable.
→ in plain terms: the penalty pushes the router's probability *down* on experts in proportion to how overloaded they are.

**Router z-loss** (ST-MoE): `L_z = (1/B) Σ_x (log Σ_j e^{x_j})²`, c_z = 1e-3. Penalises large router logits to keep softmax numerically sane.

**Loss-free balancing** (Wang et al. 2024; DeepSeek-V3): selection `s_i + b_i ∈ TopK(·)`, gate from unbiased `s_i`, update `b_i ← b_i + u · sign(c̄ − c_i)` where `c_i` = tokens routed to i in the batch and `c̄` the mean. Reported u = 0.001 (Wang) and γ = 0.001 for the first 14.3T tokens then 0.0 for the last 500B (V3).
→ in plain terms: an integral-style controller on load. Why `sign` and not proportional? Update size is independent of how big the violation is, so one wildly hot expert does not make the bias overshoot; the cost is a limit cycle of amplitude ≈ u in score space (see demo: u too big → permanent jitter).

**Why no gradient interference.** `∂L_LM/∂W` sees only the LM objective; `b` has no dependence on W through autograd. The aux-loss approach adds `α N f_i ∂P_i/∂W` to the same W: α too small → collapse, α too large → router logits are pulled toward uniform regardless of input, erasing specialization.

**V3 complement.** A sequence-wise balance loss with α = 0.0001 remains, "just to avoid extreme imbalance within any single sequence".

## 7. Why it works

Core insight: balance is a *constraint on selection frequency*, and selection frequency can be steered by an additive offset without altering the learned *scoring* function. Ablations:

- Remove bias, keep nothing → skewed expert popularity persists (my demo: MaxVio stays ≈ 2.57 at u=0).
- Use biased score for gating too → the bias leaks into the output weights and the bias value becomes part of the function the model must learn around; this is why V3 keeps gate from the raw score.
- Remove the node limit (V3 M=4) → balance is fine but cross-node all-to-all grows.
- Keep aux loss with big α → balance but worse perplexity (Wang: Loss-Controlled MaxVio 0.72/0.52 vs Loss-Free 0.04 at 1B/3B).

## 8. Design knobs and alternatives

| Knob | Trade-off |
|---|---|
| k / N (granularity) | more experts, smaller each → more combos (Mixtral: C(8,2)=28 pairs; fine-grained models have vastly more), better specialization, more all-to-all |
| Shared experts (DeepSeekMoE, Qwen1.5-MoE) | absorb common knowledge so routed experts specialise |
| CF / dropless | CF 1.25 drops <~1% in Switch's setting but needs tuning; Megablocks removes CF via block-sparse GEMM (dropless) |
| α, γ (u) | see §6; V3 anneals γ to 0 at the end |
| balance scope | sequence vs micro-batch vs global-batch (Qwen) |
| Expert Choice | each expert picks its top-C tokens → perfect balance, no drops, but variable experts/token and it breaks causal/batch independence (the §9 attack) |
| Sinkhorn / optimal transport (Megatron option) | exact balancing, extra compute |
| ReLU/Dirichlet routing | differentiable, dynamic k (frontier) |

## 9. Where it breaks

- **Collapse loop**: popular expert → more gradient → better → more popular.
- **Aux-loss dilemma** (above).
- **Micro-batch balancing bug** (Qiu et al. 2025): frameworks compute LBL per micro-batch of 1–4 sequences, forcing within-sequence uniformity. That punishes a code-only sequence for using code experts. Global-batch LBL fixes it.
- **Stragglers**: EP all-to-all is a synchronous barrier; one hot GPU stalls all.
- **Inference**: no controller at serve time; routing depends on batch composition.
- **Security**: cross-batch dependencies leak. Hayes–Shumailov–Yona 2024 ([Buffer Overflow in MoE](https://arxiv.org/abs/2402.05526)) show token-dropping with capacity lets an attacker's co-batched queries alter a victim's output. Yona–Shumailov–Hayes–Carlini 2024 ([Stealing User Prompts](https://arxiv.org/abs/2410.22884)) exploit Expert-Choice routing plus CUDA `topk` tie-breaking to recover a victim prompt with ~100 queries per token, shown on a two-layer Mixtral.
- **Misconception**: "experts specialise in domains". Wang–Hayou–Nalisnick 2026 argue routing reflects hidden-space *geometry*; Mixtral's own analysis found syntactic/token-level rather than topical specialization.
- Unverified in my research (excluded from the dive): a quoted 85% speedup from dropping 12% tokens; a 79.2% all-to-all latency share; specific validation-loss numbers for sequence- vs batch-wise losses from secondary summaries.

## 10. In the wild

- **DeepSeek-V3**: bias γ=0.001 then 0.0; sigmoid+normalise; node-limited M=4; tiny sequence-wise loss α=1e-4 as safety net.
- **Mixtral / Megatron default**: Switch-style aux loss, coeff ~1e-2, softmax over top-k logits.
- **Megablocks**: reformulates experts as one block-sparse matmul so imbalance costs nothing in FLOPs; no drops.
- **vLLM/SGLang** serving: `moe_align_block_size` sorts token-expert pairs and pads to block multiples before grouped GEMM.
- **OLMoE**: dropless token-choice, reports early routing saturation and low expert co-activation.

## 11. Frontier (verified abstracts fetched)

| Paper | Year · venue | Contribution |
|---|---|---|
| [Auxiliary-Loss-Free Load Balancing (Wang et al.)](https://arxiv.org/abs/2408.15664) | Aug 2024 · arXiv | bias-based balancing; 1B: ppl 9.56→9.50, MaxVio 0.72→0.04; 3B: 7.97→7.92, 0.52→0.04 (200B tokens) |
| [DeepSeek-V3 Technical Report](https://arxiv.org/abs/2412.19437) | Dec 2024 | the method at 671B scale |
| [ReMoE: ReLU routing (Wang, Zhu, Chen)](https://arxiv.org/abs/2412.14711) | Dec 2024 · ICLR 2025 | replace TopK+softmax with ReLU gates; fully differentiable, dynamic activation |
| [Demons in the Detail (Qiu et al.)](https://arxiv.org/abs/2501.11873) | Jan 2025 · ACL 2025 | global-batch LBL; up to 42.8B params / 400B tokens, better ppl and specialization |
| [OLMoE](https://arxiv.org/abs/2409.02060) | Sep 2024 · ICLR 2025 | open 7B/1B-active MoE, dropless routing study |
| [Scaling Laws for Fine-Grained MoE](https://arxiv.org/abs/2402.07871) | Feb 2024 | granularity as a scaling variable |
| [Myth of Expert Specialization](https://arxiv.org/abs/2604.09780) | Apr 2026 | routing reflects representation geometry |
| [Load Balancing with Similarity-Preserving Routers](https://arxiv.org/abs/2506.14038) | Jun 2025 | regularizer that keeps similar tokens together; reported 36% faster convergence |
| [DTop-p MoE](https://arxiv.org/abs/2512.13996) | Dec 2025 | PI controller sets layerwise top-p under global sparsity budget |
| [Path-Constrained MoE](https://arxiv.org/abs/2603.18297) | Mar 2026 | share routers across layers; no aux loss |
| [DirMoE](https://arxiv.org/abs/2602.09001) | Feb 2026 · ICLR 2026 | Dirichlet-based differentiable routing |

(Items after OLMoE in this table come from the frontier agent's verified-by-title report; I spot-fetched only the first rows' abstracts. Treat the 2026 entries and their numbers as lower confidence.)

## 11b. Open problems

- **Balance vs specialization Pareto**: no agreed frontier. Batch-wise loosening helps (Qiu), loss-free matches or beats aux loss (Wang), yet strict inference balance is still wanted for EP.
- **Training/serving mismatch**: bias controller exists only in training; at serve, batch makeup decides load. Decoupling routing from batch composition is unsolved (and it is also the security issue).
- **Learnability of routers**: linear routers + top-k have non-differentiable selection; ReLU/Dirichlet/OT routing trade stability for gradient. No sample-complexity theory.
- **Optimal granularity** beyond small scale.
- **Why the obvious fixes fail**: bigger α kills specialization; per-sequence balance forces uniformity where data isn't uniform; expert-choice gives balance but breaks batch independence.

## 12. Lineage

Jacobs et al. 1991 mixtures of experts → Shazeer 2017 noisy top-k + importance/load CV² losses → GShard 2020 (top-2, capacity, random 2nd expert) → Switch 2021 (top-1, `α N Σ f P`) → ST-MoE 2022 (z-loss) → Expert Choice 2022 → DeepSeekMoE 2024 (fine-grained + shared) → Loss-Free Balancing / DeepSeek-V3 2024 → global-batch LBL, differentiable routers 2025–26.

## 13. Hands-on

`loss_free_demo.py` (this folder, numpy only): frozen skewed router, 16 experts, top-2, T=4096 tokens/step, 400 steps. Real output from my run:

```
u=0.0    MaxVio step0=2.523  step100=2.580  mean(last100)=2.568  |b|max=0.000
u=0.001  MaxVio step0=2.523  step100=1.217  mean(last100)=0.084  |b|max=0.293
u=0.01   MaxVio step0=2.523  step100=0.098  mean(last100)=0.158  |b|max=0.360
u=0.05   MaxVio step0=2.523  step100=0.512  mean(last100)=0.492  |b|max=0.500
```

Reading: u=0 never balances; u=0.001 converges slowly but settles tight; u=0.01 converges fast but jitters; u=0.05 limit-cycles (never settles). Wang et al. report the same shape (0.001 best, 0.01 fluctuates). Caveat: toy, router frozen, no LM loss; it shows the controller, not model quality. Try: add a "quality" term where load raises expert score to see collapse feedback; swap `sign` for a proportional update.

## 14. Question ladder

**Mechanism**
1. Why does top-k + softmax-over-k give the router gradient only through chosen experts? <details><summary>Answer</summary>Unselected experts have gate 0 after masking; their logits do not affect output, so no gradient. Selection itself is discrete.</details>
2. In V3, which score multiplies the expert output, biased or raw? <details><summary>Answer</summary>Raw sigmoid affinity (normalised over the selected set). Bias only affects selection.</details>
3. What do `f_i` and `P_i` each represent and why is only `P_i` differentiable? <details><summary>Answer</summary>f = hard fraction of tokens whose argmax is i (non-diff), P = mean router prob (diff). Gradient is `α N f_i` weighting the P path.</details>
4. What does capacity `CF · T/N` do at overflow? <details><summary>Answer</summary>Excess tokens skip the expert via residual (dropped).</details>
5. What is MaxVio? <details><summary>Answer</summary>(max load − mean load)/mean load; 0 = perfect.</details>

**Why**
6. Why `sign` in the bias update? <details><summary>Answer</summary>Bounded step, no overshoot from outlier loads, simple; cost is jitter of order u.</details>
7. Why anneal γ to 0 at the end (V3)? <details><summary>Answer</summary>Freezes biases so late training/fine-tuning isn't perturbed by controller jitter; inferred rationale, paper just reports the schedule.</details>
8. Why does aux loss hurt quality at large α? <details><summary>Answer</summary>Its gradient pulls router logits toward uniform irrespective of token content, fighting the LM gradient.</details>
9. Why does micro-batch balancing hurt specialization? <details><summary>Answer</summary>Forces each tiny batch of 1–4 sequences to use all experts, even if all tokens are code.</details>
10. Why do shared experts help? <details><summary>Answer</summary>Common knowledge lives in always-on experts so routed ones need not duplicate it.</details>

**Counterfactual**
11. If gating used `s_i + b_i`, what changes? <details><summary>Answer</summary>Bias enters the function output, so a controller meant to be neutral perturbs predictions and couples to gradients.</details>
12. If load were measured per sequence not per batch? <details><summary>Answer</summary>Stricter, close to the micro-batch problem; V3 only keeps a tiny α for that.</details>
13. What if N doubles at fixed active FLOPs? <details><summary>Answer</summary>More combos, usually better quality (granularity scaling), but more all-to-all and memory; balance harder per expert but each is less critical.</details>

**Adversarial**
14. How can an attacker in your batch change your output with capacity limits? <details><summary>Answer</summary>Flood an expert so your tokens overflow and are dropped/rerouted (Hayes 2024).</details>
15. Why does expert-choice leak? <details><summary>Answer</summary>Experts choose across the whole batch, so rankings couple tokens of different users; CUDA topk tie-breaking makes the coupling exploitable (Yona 2024).</details>
16. How could you game a bias controller? <details><summary>Answer</summary>Speculative: skew traffic so biases drift; effects only matter if bias is shared across users' batches in serving. Not shown in the literature I verified.</details>

**Connection**
17. How is the bias controller like a PI loop / TCP congestion control? <details><summary>Answer</summary>Feedback on load error, step size trades speed vs oscillation.</details>
18. How does Megablocks change the cost of imbalance? <details><summary>Answer</summary>Dropless block-sparse GEMM: imbalance no longer causes drops or padding FLOPs, though stragglers across GPUs remain.</details>

**Open**
19. Is there a balance/specialization Pareto frontier? <details><summary>Answer</summary>Unsettled; evidence both ways.</details>
20. Can routing be made independent of batch composition at inference? <details><summary>Answer</summary>Open.</details>

## 15. Go deeper next

1. Expert-parallel inference: all-to-all, expert replication, EPLB-style placement.
2. Megablocks and grouped-GEMM kernels.
3. Differentiable routing (ReMoE, soft MoE, optimal-transport/Sinkhorn).

## Sources

**Papers**: [Shazeer 2017](https://arxiv.org/abs/1701.06538) · [GShard](https://arxiv.org/abs/2006.16668) · [Switch](https://arxiv.org/abs/2101.03961) · [ST-MoE](https://arxiv.org/abs/2202.08906) · [DeepSeekMoE](https://arxiv.org/abs/2401.06066) · [Wang et al. loss-free](https://arxiv.org/abs/2408.15664) · [DeepSeek-V3](https://arxiv.org/abs/2412.19437) · [ReMoE](https://arxiv.org/abs/2412.14711) · [Demons in the Detail](https://arxiv.org/abs/2501.11873) · [OLMoE](https://arxiv.org/abs/2409.02060) · [Buffer Overflow in MoE](https://arxiv.org/abs/2402.05526) · [Stealing User Prompts](https://arxiv.org/abs/2410.22884) · [Fine-grained scaling](https://arxiv.org/abs/2402.07871) · [Myth of Expert Specialization](https://arxiv.org/abs/2604.09780) · [Megablocks](https://people.eecs.berkeley.edu/~matei/papers/2023/mlsys_megablocks.pdf) · [DeepSpeed-MoE](https://arxiv.org/abs/2201.05596)

**Code/docs**: HF Transformers `modeling_mixtral.py` · vLLM fused_moe docs · Megatron-Core MoE docs · OLMo-core router.

**Verification note**: formulas and numbers for loss-free balancing and V3 (γ, α, expert counts, M, Wang tables) were checked against the arXiv HTML. Hayes/Yona/Qiu/ReMoE abstracts were fetched. Research subagents (Haiku) produced the rest; one stated γ≈0.01 for Wang, which is wrong (paper: u=0.001), and I used the paper's value.
