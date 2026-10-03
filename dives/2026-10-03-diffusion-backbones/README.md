# Diffusion backbones: U-Net → DiT → MMDiT → beyond

**Domain:** ML/AI · **Topic:** Diffusion denoiser architectures (U-Net, ADM, LDM, DiT, U-ViT, MMDiT/Flux, SSM/linear, MoE, pixel-space x-prediction, RAE) · **Depth:** research · **Date:** 2026-10-03

---

## 0b. Plain English first

### Explain it simply

An image generator does not paint a picture in one go. It starts from pure TV static and cleans it up a little at a time, over 4–50 rounds, until a picture appears. Every round, the same "cleaner" looks at the current messy picture and says how to make it less messy. Everything you have heard about (Stable Diffusion, Flux, Sora) uses this same loop. What differs between them is mainly **how the cleaner is built inside**. That internal design is the "backbone", and it is what this dive is about.

Think of the cleaner as a restoration workshop. The older design (the **U-Net**) works like one restorer who first zooms out to see the rough shapes, then zooms back in to fix fine detail, and keeps sticky notes from each zoom level so that no detail gets lost on the way back. The newer design (the **diffusion transformer**, DiT) cuts the picture into small tiles and gives each tile its own worker. In every round, each worker can talk to every other worker. This is simpler and gets steadily better as you hire more workers, but the room gets very noisy when there are many tiles. The newest image designs (**MMDiT**, used in Stable Diffusion 3 and Flux) also seat the people who read your text prompt at the same table as the tile workers, so words and picture parts can talk to each other directly instead of passing notes.

### Everyday example

You type: *"a red fox reading a newspaper on a park bench, the headline says FOX NEWS"*.

1. The text gets read by a language model, which turns it into about 512 "word notes".
2. The system makes a 1024×1024 canvas of static. It does not work on the real pixels. It first squeezes the canvas into a much smaller "sketch space" that is 8 times smaller on each side.
3. That sketch is cut into 4,096 tiles.
4. The cleaner (Flux's backbone) runs about 28–50 times. In each round:
   - In the first 19 layers, the tile workers and the word-note readers keep their own notebooks but discuss everything together in one shared conversation.
   - In the next 38 layers, they merge into one big group.
   - At the end of each round, every tile says "nudge me this way", and the whole canvas takes one small step from static towards a picture.
5. Early rounds settle the big decisions: where the fox and the bench go. Late rounds settle the fur, the newsprint, and whether "FOX NEWS" is spelled right.
6. Finally, the sketch is expanded back to full-size pixels.

**Now the same thing, technically.**

---

## 1. Bare-minimum context

- **Diffusion / flow matching.** Training adds Gaussian noise to data, and a network learns to undo it. Sampling runs that network 4–50+ times, starting from noise. [DDPM](https://arxiv.org/abs/2006.11239), [rectified flow in SD3](https://arxiv.org/abs/2403.03206)
- **Prediction target.** The network outputs one of three things: the noise ε, the clean image x₀, or a velocity v. All three are linear functions of each other given x_t and t, but the choice affects how hard learning is (see §6 and §11).
- **Latent diffusion.** A VAE first compresses the image, for example 1024²×3 down to 128²×16. Diffusion then runs in that space, and the decoder maps back to pixels. [LDM](https://arxiv.org/abs/2112.10752)
- **Self-attention** costs O(T²·d) for T tokens of width d. Cross-attention uses queries from one sequence and keys and values from another. [Attention](https://arxiv.org/abs/1706.03762)
- **Conditioning.** The timestep t, a class label or text, and the guidance scale all have to get into the network somehow. *How* they get in is a backbone design decision.
- **FID.** The Fréchet distance between Inception features of real and generated images; lower is better. It is the ImageNet benchmark currency, and it has flaws (§9). [CMMD critique](https://arxiv.org/abs/2401.09603)

---

## 1b. Real-world context

### What it is, in one paragraph

A diffusion **backbone** is the neural network that runs at every denoising step. It takes three inputs: the noisy image or latent x_t, the noise level t, and a condition c (a class, text, or reference images). It outputs a prediction (noise, clean image or velocity) with the same shape as x_t. The sampler, the noise schedule and the VAE surround it, but nearly all the FLOPs, parameters and quality differences sit inside it. Architectures are commonly described in four families:
- **Convolutional U-Nets** with attention inserted: DDPM, ADM, Stable Diffusion 1.x/2.x/SDXL, EDM2.
- **Plain transformers over patches**, called DiTs: DiT, SiT, PixArt, Wan, Sora.
- **Multimodal joint-attention transformers**, called MMDiTs: SD3, Flux, HunyuanVideo, Qwen-Image.
- **Efficiency variants:** linear attention (SANA), state-space models (DiS, ZigMa), and mixture-of-experts models (DiT-MoE, Wan 2.2).

### Why it exists / why it matters

- The backbone runs **steps × (2 if using classifier-free guidance)** times per image. A 12B backbone at 50 steps with CFG means 100 forward passes of 12B parameters. Backbone efficiency is therefore the product's cost.
- The backbone decides **what scales**. DiT showed that FID tracks forward compute with correlation −0.93 ([DiT](https://arxiv.org/abs/2212.09748)). SD3 showed that validation loss keeps falling to 8B with no saturation, and that the loss tracks human preference ([SD3](https://arxiv.org/abs/2403.03206)). U-Nets had no clean scaling story, so labs moved to transformers to borrow LLM tooling and scaling intuition.
- The backbone decides **how text gets in**. Cross-attention lets text talk to the image. Joint attention lets text and image update each other. That difference shows up in prompt adherence and typography (§9).
- **Before** this line of work, GANs were state of the art on ImageNet. ADM's U-Net changes (§8) are what let diffusion beat them in 2021 ([ADM](https://arxiv.org/abs/2105.05233)).

### Where it's used

| System | Backbone | Role / notable detail |
|---|---|---|
| Stable Diffusion 1.5 / 2.1 | U-Net, 860M / 865M | Cross-attention to CLIP; still the base for a big LoRA/ControlNet ecosystem ([SDXL Tbl 1](https://arxiv.org/abs/2307.01952)) |
| SDXL (2023) | U-Net, 2.6B | Transformer blocks [0,2,10] per level: no attention at the highest resolution. Two text encoders ([SDXL](https://arxiv.org/abs/2307.01952)) |
| Stable Diffusion 3 / 3.5 | MMDiT, 2B / 8B | Two weight streams, joint attention, QK-norm, 16-channel VAE ([SD3](https://arxiv.org/abs/2403.03206), [3.5 card](https://huggingface.co/stabilityai/stable-diffusion-3.5-large)) |
| FLUX.1 (BFL, Aug 2024) | Hybrid MMDiT, 12B | 19 double-stream blocks, then 38 single-stream parallel blocks; 3-axis RoPE; guidance embedding ([code](https://github.com/black-forest-labs/flux/blob/main/src/flux/util.py)) |
| PixArt-α/Σ | DiT + cross-attention, 0.6B | T5-XXL text; about 10.8% of SD1.5's training compute ([PixArt-α](https://proceedings.iclr.cc/paper_files/paper/2024/hash/fe989bb038b5dcc44181255dd6913e43-Abstract-Conference.html)) |
| Sora (OpenAI) | DiT on "spacetime patches" | No size disclosed ([tech report](https://openai.com/index/video-generation-models-as-world-simulators/)) |
| Wan 2.1 / 2.2 | DiT + cross-attention; 2.2 = timestep-routed MoE (27B total / 14B active) | High-noise expert handles layout, low-noise expert handles detail ([Wan 2.2](https://github.com/Wan-Video/Wan2.2)) |
| HunyuanVideo | Dual-stream then single-stream, 13B | Full 3D attention; about 60 GB for 720p×129 frames ([repo](https://github.com/Tencent-Hunyuan/HunyuanVideo)) |
| SANA (NVIDIA) | Linear-attention DiT, 0.6–4.8B | DC-AE with 32× compression; under 1 s per 1024² image on a 16 GB GPU ([SANA](https://arxiv.org/abs/2410.10629)) |
| Qwen-Image | MMDiT, 20B | Qwen2.5-VL text encoder, Apache-2.0 ([card](https://huggingface.co/Qwen/Qwen-Image)) |

### How it's used

In 🤗 diffusers the backbone is a swappable module: `UNet2DConditionModel` (SD1.x/SDXL), `PixArtTransformer2DModel`, `SD3Transformer2DModel`, `FluxTransformer2DModel`. Every DiT-era pipeline uses `FlowMatchEulerDiscreteScheduler`.

```python
import torch
from diffusers import FluxPipeline

pipe = FluxPipeline.from_pretrained("black-forest-labs/FLUX.1-dev", torch_dtype=torch.bfloat16)
pipe.enable_model_cpu_offload()            # whole pipeline is ~50 GB in bf16 otherwise
print(type(pipe.transformer).__name__)     # FluxTransformer2DModel  <- the backbone
img = pipe(
    "a red fox reading a newspaper on a park bench, headline says FOX NEWS",
    height=1024, width=1024,
    num_inference_steps=28,                # dev: ~28-50 steps; schnell: 4
    guidance_scale=3.5,                    # a distilled guidance *embedding*, not real CFG
).images[0]
```

Typical knobs:
- **Steps:** SD3.5-Large 28 steps at CFG 3.5–4.5; Flux-schnell 4 steps at guidance 0.
- **Dropping T5:** `StableDiffusion3Pipeline(..., text_encoder_3=None)` removes the 4.7B T5 at a typography cost.
- **Speed:** `torch.compile` takes Flux-dev on an H100 from 6.7 s to 4.5 s ([PyTorch blog](https://pytorch.org/blog/torch-compile-and-diffusers-a-hands-on-guide-to-peak-performance/)). "Flux Fast" (compile + fused QKV + FA3 fp8) gets about 2.5× ([blog](https://pytorch.org/blog/presenting-flux-fast-making-flux-go-brrr-on-h100s/)).
- **Memory:** fp8 quantization via optimum-quanto plus offload fits in under 16 GB.
- **Caching:** feature caching via `transformer.enable_cache(...)` (FirstBlockCache, FasterCache, TaylorSeer…) ([docs](https://huggingface.co/docs/diffusers/main/en/optimization/cache)).

### When to use which

| Pick a U-Net (SD1.5/SDXL) when | Pick a DiT / MMDiT when |
|---|---|
| Low VRAM, fast steps, no T5 | Prompt adherence and in-image text matter (T5/LLM encoder + joint attention) |
| You need the mature ControlNet / IP-Adapter / LoRA catalogue (e.g. Illustrious/Pony anime bases) | You will scale parameters or data, or do video (every 2024–26 open video model is a DiT) |
| DeepCache-style speedups (these rely on U-Net skip structure) | Native multi-aspect / multi-resolution generation via RoPE |
| Small data, from scratch (locality bias helps, §9) | Large data and compute budget, where inductive bias matters less |

**Signs you picked wrong:**
- Duplicated subjects at off-train resolutions: you need resolution-aware positional embeddings or a timestep shift.
- Out-of-memory at video lengths: attention is O(T²), so you need sparse attention or a higher-compression VAE.
- No adapters available for your new base model: the ecosystem resets with every backbone.

### Who should care

- **ML researchers** choosing a backbone, latent space and prediction target.
- **ML infra / inference engineers**, for whom tokens and steps are the cost and quadratic attention is the wall.
- **Product teams** choosing a base model: license and adapter ecosystem often decide more than FID does.
- **Security and safety** people: memorization (§9) and its link to architecture are still open.

---

## 2. The one-liner, and what it hides

> "Diffusion models switched from U-Nets to transformers because transformers scale better."

What that sentence hides:

1. **Most of DiT's headline win over ADM came from moving to latent space, not from the transformer.** DiT-XL/2 costs 118.6 Gflops. ADM, a *pixel* U-Net, costs 1120. LDM-4, a latent U-Net, costs 103.6 ([DiT §5](https://arxiv.org/abs/2212.09748)). Compute-matched U-Nets such as EDM2 still compete ([EDM2](https://arxiv.org/abs/2312.02696)).
2. **How the timestep is injected mattered more than many block designs.** DiT's adaLN-Zero (FID 19.47) vs in-context tokens (35.24) on the same model is nearly a 2× gap from conditioning alone.
3. **Transformers did not really drop the U-Net's inductive biases; they rebuilt them.** Long skip connections (U-ViT, Hunyuan-DiT), 3×3 convolutions (SANA Mix-FFN), token downsampling (U-DiT, HDiT, PixelU) and local attention windows all came back.
4. **Since 2024 the biggest quality gains came from *outside* the block:**
   - the latent space (VA-VAE → REPA-E → RAE);
   - representation alignment (REPA);
   - the prediction target (JiT's x-prediction).

   ImageNet-256 FID went 2.27 → 1.13 with roughly the same transformer.
5. **"Scales better" applies to the loss, not to every capability.** Counting accuracy does not improve with scale ([numerosity study](https://arxiv.org/html/2510.11117v1)).

---

## 3. The problem

A denoiser must predict a dense, image-shaped output from a noisy input, **at every noise level t, with one shared set of weights**. That imposes four constraints:

- **Two jobs at different scales.**
  - At high t the input is nearly pure noise, so the network must produce global layout. That needs a large receptive field.
  - At low t it must restore texture. That needs precise local, high-frequency output.
  - A pure conv stack has a small receptive field. A pure global-attention stack is quadratic in resolution.
- **Resolution is enormous.**
  - A 256² RGB image has 196,608 numbers. Attention over every pixel would mean 65,536 tokens at 256², which is impossible in 2020.
  - DDPM therefore used a U-Net with attention only at 16×16 ([DDPM App. B](https://arxiv.org/abs/2006.11239)).
  - ADM, still in pixel space, cost **1120 GFLOPs per forward** at 256² ([DiT Tbl 2 notes](https://arxiv.org/abs/2212.09748)). Times 250 sampling steps, that is about 280 TFLOPs per image.
- **Conditioning has to reach every layer.** The network must behave very differently at t=0.9 than at t=0.1. DDPM added a sinusoidal t-embedding inside each ResBlock. Changing that to scale-and-shift (AdaGN) alone moved ImageNet-128 FID from 15.08 to 13.06 ([ADM Tbl 3](https://arxiv.org/abs/2105.05233)).
- **No scaling recipe.** U-Nets have many coupled hyperparameters: channel multipliers, ResBlocks per level, which resolutions get attention. In 2022 there was no simple rule for "make it 10× bigger". LLMs had one.

The latent-diffusion move (f=8 VAE) cut spatial positions by 64× and made attention-everywhere affordable. Once tokens were cheap, the question became: *do we still need the U-Net at all?*

---

## 4. Mental model

**A U-Net is a funnel with pneumatic tubes. A DiT is a flat room of equals.**

- **U-Net.** Features flow *down* a funnel: each level halves the resolution and doubles the channels, building context. They then flow *back up*. At each level, a skip connection (the pneumatic tube) shoots the high-resolution features straight across to the matching decoder level, so fine detail does not have to survive the bottleneck. Attention sits only at the cheap, low-resolution floors.
- **DiT.** The latent is cut into p×p patches. Every patch becomes a token of width d, and all T tokens talk to all other tokens in every one of N identical layers. There is no funnel, so resolution never changes. The timestep acts as a global "dial" that rescales every layer's normalization (adaLN).
- **MMDiT.** Text tokens join the same room, but they keep their own projection weights (their "own notebooks") while sharing one attention conversation.

**Where the analogy breaks:**
- A DiT is **not** structureless. Patchify is itself a strided convolution, so the "flat room" was built from a 2×-downsampled latent. Position embeddings re-inject geometry.
- Many "flat" models quietly re-add funnels and tubes:
  - U-ViT long skips;
  - token-downsampled attention in U-DiT and HDiT;
  - DDT's encoder/decoder split.
- In a U-Net, the skips are not merely "detail tubes". U-ViT found that *how* the skip merges matters: concat + linear helps, while plain addition gives nothing, because the residual stream already carries that signal additively ([U-ViT §3.1](https://arxiv.org/abs/2209.12152)).

---

## 5. The mechanism, traced

**One denoising step of Flux.1-dev at 1024×1024**, using the fox prompt. The shapes come from the BFL reference code ([util.py](https://github.com/black-forest-labs/flux/blob/main/src/flux/util.py), [sampling.py](https://github.com/black-forest-labs/flux/blob/main/src/flux/sampling.py), [layers.py](https://github.com/black-forest-labs/flux/blob/main/src/flux/modules/layers.py)). The SD1.5 U-Net path follows for contrast.

```
INPUTS at step k (t = 0.73, say)
  x_t      : latent 1 × 16 × 128 × 128      (1024/8 = 128, VAE z_channels = 16)
  txt      : T5-XXL output 1 × 512 × 4096
  pooled   : CLIP-L pooled 1 × 768
  t, g     : timestep 0.73, guidance 3.5

1. PACK + EMBED (patchify, p = 2)
  "b c (h 2) (w 2) -> b (h w) (c 2 2)"  ->  1 × 4096 × 64
  img_in  : Linear(64 -> 3072)          ->  img  1 × 4096 × 3072
  txt_in  : Linear(4096 -> 3072)        ->  txt  1 ×  512 × 3072
  vec = MLP(sinusoid(t)) + MLP(sinusoid(g)) + MLP(pooled)  -> 1 × 3072
  RoPE ids: img (0, row, col) for 64×64 grid; txt (0,0,0)   axes_dim [16,56,56]

2. 19 × DOUBLE-STREAM BLOCK  (MMDiT-style: separate weights, shared attention)
  for each stream s in {img, txt}:
     shift,scale,gate (×2) = Linear_s(SiLU(vec))              # adaLN modulation
     h_s = (1+scale)·LN(x_s) + shift
     q_s,k_s,v_s = QKV_s(h_s);  q_s,k_s = RMSNorm(q_s), RMSNorm(k_s)   # QK-norm
  q = cat(q_txt, q_img)  ->  1 × 24 heads × 4608 × 128      # 512 + 4096 tokens
  attn = softmax(RoPE(q)·RoPE(k)ᵀ/√128)·v                   # 4608² ≈ 21M scores/head
  split back -> x_s += gate·Proj_s(attn_s);  x_s += gate'·MLP_s(mod(LN(x_s)))

3. CONCAT -> 1 × 4608 × 3072

4. 38 × SINGLE-STREAM BLOCK  (shared weights, parallel attn+MLP à la ViT-22B)
  h = (1+scale)·LN(x) + shift
  [qkv | mlp_in] = linear1(h)                # one matmul -> 3·3072 + 12288
  out = linear2(cat(attn(qkv), GELU(mlp_in)))
  x += gate·out

5. FINAL LAYER
  drop txt tokens -> 1 × 4096 × 3072
  adaLN + Linear(3072 -> 64) -> unpack -> velocity v̂ : 1 × 16 × 128 × 128

6. SAMPLER (Euler, rectified flow)
  x_{t-Δ} = x_t + (t_{next} − t) · v̂          # one small straight-line step
```

Repeat steps 1–6 for about 28–50 timesteps. The schedule is **shifted towards high noise** for big images: Flux interpolates μ from 0.5 at 256 tokens to 1.15 at 4096 tokens. Then the VAE decodes 16×128×128 → 3×1024×1024.

**Same step in the SD1.5 U-Net at 512²** (config: [v1-inference.yaml](https://raw.githubusercontent.com/CompVis/stable-diffusion/main/configs/stable-diffusion/v1-inference.yaml)):

```
x_t 4×64×64 --conv_in--> 320×64×64
 DOWN  64² [Res,Res + SelfAttn+CrossAttn(77 CLIP tok)] 320ch  ──skip──┐
       32²  same, 640ch                                     ──skip──┐│
       16²  same, 1280ch                                    ──skip─┐││
        8²  Res only, 1280ch                                ──skip┐│││
 MID    8²  Res + Attn + Res                                      ││││
 UP     8² → 16² → 32² → 64²   concat(skip) at every level  <─────┘┘┘┘
conv_out -> ε̂ 4×64×64       (t enters every ResBlock as an added embedding)
```

The key contrasts:
- **Text access.** In the U-Net, text is read-only: queries come from the image, and keys and values from 77 frozen CLIP tokens. In Flux, text tokens are *updated* every double block, so the image can rewrite what the text representation means.
- **Where attention is.** The U-Net's biggest attention is at 64², which is 4,096 tokens, but at width 320. Flux attends over 4,608 tokens at width 3072, in all 57 blocks.

---

## 6. The math

### 6.1 The objective, and why the prediction target is a design choice

Forward process: x_t = α_t·x₀ + σ_t·ε, with ε ~ N(0, I).
- DDPM/VP: α_t = √ᾱ_t, σ_t = √(1−ᾱ_t).
- Rectified flow (SD3/Flux): α_t = 1−t, σ_t = t.

DDPM's loss ([Eq. 14](https://arxiv.org/abs/2006.11239)):

  L = E_{t,x₀,ε} ‖ ε − ε_θ(x_t, t, c) ‖²

→ *In plain terms:* the network sees a noisy image and the noise level, and must guess the noise that was added.

Given x_t and t, the three targets are interchangeable:

  x̂₀ = (x_t − σ_t ε̂)/α_t, and for rectified flow v = ε − x₀.

So why does the choice matter? Because **the network has to output that target with finite capacity**.
- x₀ lies on a low-dimensional image manifold.
- ε (and v, which contains ε) is full-rank noise in the ambient dimension D.

JiT's argument ([Li & He 2025](https://arxiv.org/abs/2511.13720)): with 16×16×3 = 768-dimensional pixel patches and a narrower bottleneck, predicting ε or v means carrying 768 dimensions of incompressible noise through the network.
- ε- and v-prediction fail outright (FID above 96, versus 8.62 for x-prediction in their ablation).
- x-prediction, converted to a v-loss, works.

→ *In plain terms:* asking a network to output something that lives on a small manifold is easier than asking it to reproduce random noise. This is invisible in 4-channel latents (D is small) and decisive in pixel space or high-dimensional latents.

### 6.2 adaLN-Zero: how t gets into every layer

With c = emb(t) + emb(y), one linear layer produces six vectors per block ([DiT code](https://github.com/facebookresearch/DiT/blob/main/models.py)):

  (β₁, γ₁, α₁, β₂, γ₂, α₂) = W·SiLU(c) + b,  with W = 0 and b = 0 at init

  x ← x + α₁ ⊙ Attn( (1+γ₁) ⊙ LN(x) + β₁ )
  x ← x + α₂ ⊙ MLP ( (1+γ₂) ⊙ LN(x) + β₂ )

→ *In plain terms:* the timestep rescales and shifts every normalized activation, and a gate α decides how much each block contributes.

**Why this form:**
- **(1+γ), not γ.** With γ=0 at init the scale is the identity, not zero.
- **The gate α, zero-initialised.** Every block starts as an identity residual, so the 28-layer network starts as "output = input projection". Gradients flow cleanly, which is the same trick as Fixup / zero-init ResNets.
- **Why not just add t as a token?** In-context conditioning has to fight for attention mass and influence the network through one token. Modulation touches every channel of every token directly.

DiT's ablation (DiT-XL/2, 400K steps; [App. Tbl 4](https://arxiv.org/abs/2212.09748)):

| Variant | FID | Gflops |
|---|---|---|
| in-context | 35.24 | 119.4 |
| cross-attn | 26.14 | 137.6 |
| adaLN | 25.21 | 118.6 |
| adaLN-Zero | 19.47 | 118.6 |

Caveat: U-ViT found *time-as-token* beats AdaLN in its setting, which had long skips ([U-ViT](https://arxiv.org/abs/2209.12152)). The ranking is not universal.

### 6.3 Cost: why tokens, not parameters, are the bill

For T tokens of width d with a 4× MLP, forward multiply-accumulates (MACs) per layer are:

  C(T, d) = 4Td² (QKV + output) + 8Td² (MLP) + 2T²d (QKᵀ and AV) = **12Td² + 2T²d**

→ *In plain terms:* the linear layers cost scales with tokens × width², and attention costs scales with tokens² × width.

The ratio is attention/linear = T/(6d), so attention dominates once T > 6d. For Flux (d=3072) that means beyond about 18K tokens. Images at 1024² sit below the crossover: 4,608 tokens means about 20% of layer MACs. Video at 720p×129 frames (about 119K tokens) is about 87% attention.

Check against the DiT paper (run `backbone_flops.py`): DiT-XL/2 gives N=28, T=256, d=1152, so 28·C = **118.4 G** vs **118.64** reported. Every DiT config matches within 0.2–5%. DiT's 512² model (T=1024) is reported at 524.6, and the formula gives 524.3. So DiT's "Gflops" are effectively forward GMACs (my inference; the paper does not say so).

Patch size enters as T = (I/p)². Halving p quadruples T and at least quadruples cost, while parameters stay constant. This is why DiT found that **Gflops, not parameters, predict FID**: S/2 and B/4 have similar Gflops and similar FID ([DiT Fig. 8](https://arxiv.org/abs/2212.09748)).

### 6.4 Resolution-dependent timestep shift

At higher resolution, neighbouring pixels are redundant, so the same σ destroys less information ([simple diffusion](https://arxiv.org/abs/2301.11093)). SD3 maps a timestep t_n tuned at n pixels to m pixels ([SD3 §5.3.2](https://arxiv.org/abs/2403.03206)):

  t_m = √(m/n)·t_n / (1 + (√(m/n) − 1)·t_n)

→ *In plain terms:* bigger images spend more of the schedule at high noise. For example, with √(m/n)=3, t_n = 0.5 maps to t_m = 0.75.

SD3 used a shift of 3.0 at 1024². RAE uses the same form with **m = effective latent dimension**, not pixel count. That shift alone moved its FID from 23.1 to 4.81 ([RAE](https://arxiv.org/abs/2510.11690)). The backbone takes the blame when this is wrong, but the schedule is the cause.

### 6.5 RAE's width condition

RAE (Theorem 1, [arXiv 2510.11690](https://arxiv.org/abs/2510.11690)): once Gaussian noise is added, the support of x_t is all of ℝ^D, even if the data sits on a low-dimensional manifold. A denoiser whose per-token width d < D (the token dimension) therefore cannot represent the optimal denoiser, and it incurs an irreducible loss.

→ *In plain terms:* your transformer must be at least as wide as the tokens it is denoising. In their experiments DiT-S (width 384) fails on DINOv2's 768-dimensional tokens, and it works once width ≥ 768. This is a backbone-sizing rule that comes from the *latent space*.

---

## 7. Why it works

**Why the U-Net worked first:**
- It gives multi-scale receptive fields cheaply: global layout at 8², texture at 64².
- Attention runs only where it is affordable.
- Skip connections let high-frequency detail bypass the bottleneck, which is essential at low t.
- Remove the skips and small models lose detail. SiD2 found small models lose about 0.2 FID without blockwise skips, while large ones do not care ([SiD2](https://arxiv.org/abs/2410.19324)).

**Why DiT won the 2023–26 default:**
1. **A one-knob scaling law.** Depth, width and patch size map onto Gflops, and Gflops map onto FID (r = −0.93). Bigger models are also more *compute*-efficient: XL/2 beats XL/4 after about 10¹⁰ training Gflops ([DiT](https://arxiv.org/abs/2212.09748)).
2. **The LLM stack transfers:** FlashAttention, FSDP and sequence parallelism, fp8, RoPE, QK-norm, MoE, torch.compile.
3. **Any-shape inputs are just token sequences:** video spacetime patches, variable aspect ratio, multiple images (Flux Kontext concatenates context tokens).
4. **Joint attention gives bidirectional text–image flow.** On CC12M, SD3 found that DiT < UViT < CrossDiT < **MMDiT** ([SD3 §5.2](https://arxiv.org/abs/2403.03206)).

**Ablation thinking: remove each piece of a modern MMDiT.**

| Remove… | What breaks | Evidence |
|---|---|---|
| adaLN-Zero gating | Convergence is about 2× slower (FID 19.5 → 25 at 400K) | DiT |
| QK-norm | Attention logits grow, attention entropy collapses, bf16 training diverges at high resolution | SD3; ViT-22B ([2302.05442](https://arxiv.org/abs/2302.05442)) |
| Separate per-modality weights (→ DiT with concatenation) | Worse validation loss, CLIP score and GenEval | SD3 §5.2 |
| T5 (keep only CLIP) | Typography win rate falls to 38%, prompt adherence to 46%; aesthetics unchanged | SD3 |
| RoPE / position embedding | U-ViT: "fails" with no position embedding | U-ViT |
| Resolution shift | Washed-out, under-structured images at 1024² | SD3 human eval |
| 16-channel VAE (→ 4) | Reconstruction FID 1.06 → 2.41, which caps sample quality | SD3 Tbl |

---

## 8. Design knobs and alternatives

### The knob list

| Knob | Range | Tradeoff |
|---|---|---|
| Patch size p | 1, 2, 4 (latent); 16/32/64 (pixel, JiT) | Cost ∝ 1/p⁴ when attention dominates (T² term); smaller p gives more detail per token |
| Width d / depth N | DiT-XL: 28 × 1152; Flux: 57 × 3072; SD3-8B: 38 × 2432 | Width must be ≥ token dimension (RAE); depth is cheaper in parameters but serial |
| Conditioning | in-context / cross-attn / adaLN(-Zero) / joint attention | §6.2; joint attention costs T_text extra tokens in every block |
| Text encoder | CLIP / T5-XXL / LLM (Gemma, Qwen2.5-VL, Mistral-24B) | Imagen: scaling T5 helps more than scaling the U-Net ([Imagen](https://arxiv.org/abs/2205.11487)) |
| Latent | SD-VAE f8c4 → f8c16 → DC-AE f32 → RAE (DINOv2/SigLIP) → pixels | Reconstruction vs "diffusability" (§9) |
| Prediction target | ε / v / x | x is necessary when tokens are high-dimensional (JiT) |
| Attention type | full / factorized / sliding-tile / linear / SSM | Quality vs O(T²) |
| Expert routing | dense / token MoE / timestep MoE | Capacity without per-step FLOPs |

### ADM's U-Net ablation (ImageNet-128, FID change vs baseline 15.33 at 700K; [ADM Tbl 1](https://arxiv.org/abs/2105.05233))

| Change | ΔFID |
|---|---|
| BigGAN residual up/downsampling | −1.20 |
| Attention at 32, 16, 8 (not only 16) | −0.72 |
| 4 heads | −0.54 |
| Depth 4 (narrower) | −0.21 (but slower in wall-clock, so dropped) |
| Rescale residuals by 1/√2 | **+0.16** (hurt) |
| All except rescale | −3.14 |

### Competing approaches

- **U-ViT** ([Bao 2023](https://arxiv.org/abs/2209.12152)): everything is a token (t, c, patches), with long skips joining block i to block L−i. Scores 2.29 on ImageNet-256, against DiT's 2.27. It showed the long skip, not up/downsampling, is the U-Net's essential part.
- **EDM2** ([Karras 2024](https://arxiv.org/abs/2312.02696)): stays a U-Net but makes every layer magnitude-preserving, with forced unit-norm weights, no GroupNorm, and SiLU divided by 0.596. Gets ImageNet-512 FID 2.41 → **1.81** at equal complexity, and matches the previous state of the art at 5× smaller size. This is the strongest "U-Nets were never the problem" result.
- **SiD2 / U-ViT pixel** ([Hoogeboom 2024](https://arxiv.org/abs/2410.19324)): FID 1.5 at 512 in *pixel* space. Spending compute on resolution (smaller patches) beats doubling channels.
- **SSMs** (DiS, ZigMa, DiM, DiG): linear in T. They win on memory at ≥1K resolution (DiG-S/2 is 2.5× faster than DiT-S/2 at 1792² and uses 75.7% less memory; [DiG](https://arxiv.org/abs/2405.18428)). They never led on FID, and no frontier model uses a pure SSM.
- **Linear attention + deep compression** (SANA): 0.6B parameters, claimed 100× higher throughput than Flux-12B. Production-grade for images, but SANA-Video 2.0 went *hybrid*, with about 25% softmax layers ([2607.21553](https://arxiv.org/abs/2607.21553)).
- **Autoregressive** (Emu3, VAR, Janus) and **AR + diffusion head** (MAR, Transfusion, BAGEL): see §11.

---

## 9. Where it breaks

- **Training instability at scale.**
  - Attention logits grow, attention entropy collapses, and bf16 training diverges. SD3 fixed this with RMSNorm on Q and K plus AdamW ε=1e-15. The authors call it "not a universal recipe".
  - Fixing logits exposes *massive activations*, reported at about 15K at 256 px and 24K at 512 px in rectified-flow transformers, which overflow fp16. ([2510.04236](https://arxiv.org/pdf/2510.04236); numbers taken from the abstract/summary, not verified in full text.)
  - U-Nets have their own version: EDM2 showed weights and activations drift upward during training, which silently decays the effective learning rate.
- **Off-resolution generation duplicates subjects, for different reasons in each family.**
  - U-Nets: the conv receptive field is too small at the new resolution ([ScaleCrafter](https://arxiv.org/abs/2310.07702)).
  - DiTs: position embeddings are extrapolated beyond training ([FiT](https://arxiv.org/abs/2402.12376), [LEDiT](https://arxiv.org/abs/2503.04344)).
  - Both: a wrong timestep shift.
- **Reconstruction vs generation tradeoff in the VAE.**
  - Higher-dimensional latents reconstruct better and generate *worse* for a fixed denoiser. For VA-VAE without alignment: f16d16 reconstructs at rFID 0.49 and generates at gFID 16.24; f16d64 reconstructs at 0.17 and generates at gFID 36.83 ([VA-VAE](https://arxiv.org/abs/2501.01423)).
  - The backbone gets blamed for a latent-space problem.
- **Text rendering and counting.**
  - Spelling is mostly a tokenizer problem. Character-aware ByT5 gains 25–30+ points over T5 ([Liu et al.](https://arxiv.org/abs/2212.10562)).
  - Counting fails across all state-of-the-art models and does not improve with scale ([T2ICountBench](https://arxiv.org/abs/2503.06884), [numerosity](https://arxiv.org/html/2510.11117v1)).
  - "MMDiT fixes composition" is unproven.
- **Quadratic video.**
  - HunyuanVideo, 5 s at 720p: 945 s of inference, of which 800 s is attention ([STA](https://arxiv.org/abs/2502.04507)).
  - Factorized spatial/temporal attention was abandoned for full 3D because it fails on large motion ([CogVideoX](https://arxiv.org/abs/2408.06072)).
- **Memorization.**
  - More than 1,000 training images have been extracted from Stable Diffusion and Imagen ([Carlini 2023](https://arxiv.org/abs/2301.13188)).
  - DiTs lack the "geometry-adaptive harmonic bases" that explain U-Net generalization. DiT generalization correlates with attention locality ([2410.21273](https://arxiv.org/abs/2410.21273)).
  - No matched U-Net vs DiT extraction study exists.
- **The ecosystem resets.** LoRAs, ControlNets and IP-Adapters are architecture-specific. FLUX.1-dev has about 42.7K adapters, and moving to a new backbone throws that away. SDXL-derived anime bases still dominate that community.

**Misconceptions:**
- *"Transformers beat U-Nets."* The evidence is confounded by latent vs pixel space and by training recipes. EDM2 (a U-Net) and SiD2 (U-ViT-ish) are competitive, and SD3's own comparison has UViT > DiT.
- *"DiTs have no locality bias."* Patchify, RoPE, Mix-FFN convolutions and local windows all add it back.
- *"Lower FID means a better architecture."* Many claims rest on 0.1–0.3 FID gaps under *different guidance methods* (CFG vs interval CFG vs AutoGuidance). Inception features also misjudge modern text-to-image ([CMMD](https://arxiv.org/abs/2401.09603)).
- *"Flux's guidance_scale is CFG."* It is not. On the dev model it is a distilled guidance embedding fed into `vec`: one forward pass instead of two.

---

## 10. In the wild

How production models deviate from the papers:

- **Flux.1**:
  - 2×2 latent *packing* gives `in_channels=64`.
  - **3-axis RoPE** with axes_dim [16, 56, 56]; the first axis is free for multi-image or editing indices.
  - The **single-stream blocks are not in the SD3 paper**: a parallel attention+MLP block from ViT-22B with a fused `linear1`.
  - **Guidance embedding** in dev; schnell differs only by `guidance_embed=False`.
  - **Dynamic timestep shift** that is linear in sequence length.
  - No paper with ablations exists, so all of this is from the code ([BFL flux](https://github.com/black-forest-labs/flux)).
- **SD3.5-Medium "MMDiT-X"** adds extra self-attention in the first 13 layers and was trained progressively from 256 to 1440 px ([card](https://huggingface.co/stabilityai/stable-diffusion-3.5-medium)).
- **SDXL** pulled attention *out* of the highest-resolution level and deleted the 8× level. It is a U-Net bending towards "attention at low resolution only".
- **PixArt** uses "adaLN-single": one shared modulation MLP for all blocks instead of one per block. This saves about 27% of parameters (recalled from memory, not re-verified). Wan 2.1 likewise shares one MLP that predicts 6 modulation vectors.
- **Hunyuan-DiT** adds U-ViT-style long skips to a DiT.
- **CogVideoX** uses "expert adaLN": separate modulation for text tokens and video tokens over one 3D attention. This is MMDiT's idea applied only to the norms.
- **Wan 2.2 MoE is routed by timestep, not token**: two 14B experts, with the switch at high→low noise. It is eDiff-I's 2022 "expert denoisers" idea ([eDiff-I](https://arxiv.org/abs/2211.01324)) brought back at 27B.
- **SANA** has no positional encoding at all; a 3×3 depthwise convolution in Mix-FFN supplies position.
- **Caching exploits backbone structure.**
  - DeepCache reuses deep U-Net features and recomputes only the shallow skip branch: 2.3× on SD1.5 ([DeepCache](https://arxiv.org/abs/2312.00858)).
  - DiTs have no such hierarchy, so TeaCache predicts when a whole forward can be skipped from timestep-modulated input deltas: up to 4.41× ([TeaCache](https://arxiv.org/abs/2411.19108)).
  - DDT shares its encoder output across adjacent steps *by design*.

---

## 11. Frontier (2024–2026)

### ImageNet-256 FID progression (class-conditional, FID-50K)

| Year | Model | Main lever | FID | Source |
|---|---|---|---|---|
| 2022 | DiT-XL/2 | Transformer on SD-VAE latents | 2.27 (CFG 1.5) | [2212.09748](https://arxiv.org/abs/2212.09748) |
| 2024 | SiT-XL/2 | Interpolant / flow objective, same net | 2.06 | [2401.08740](https://arxiv.org/abs/2401.08740) |
| 2024 | REPA + SiT-XL/2 | Align early hidden states to DINOv2 | 1.42 (interval CFG, 800 ep) | [2410.06940](https://arxiv.org/abs/2410.06940) |
| 2025 | LightningDiT + VA-VAE | DINOv2-aligned latent, modern DiT | 1.35 | [2501.01423](https://arxiv.org/abs/2501.01423) |
| 2025 | DDT-XL/2 | Encoder/decoder split | 1.31 (256 ep), 1.26 (400 ep) | [2504.05741](https://arxiv.org/abs/2504.05741) |
| 2025 | REPA-E | End-to-end VAE + diffusion | 1.12 (CFG) / 1.69 (none) | [2504.10483](https://arxiv.org/abs/2504.10483) |
| 2025 | RAE (DiT^DH-XL, DINOv2-B) | Frozen representation encoder as latent | 1.13 (guided) / 1.51 (none) | [2510.11690](https://arxiv.org/abs/2510.11690) |
| 2026 | RAEv2 | Sum of last-k encoder layers | 1.06 (80 ep) | [2605.18324](https://arxiv.org/abs/2605.18324) |
| 2026 | PAE | Prior-aligned AE (abstract only; guidance setting unverified) | 1.03 | [2605.07915](https://arxiv.org/abs/2605.07915) |

Pixel space on ImageNet-256:

| Model | FID | Source |
|---|---|---|
| PixelFlow | 1.98 | [2504.07963](https://arxiv.org/abs/2504.07963) |
| JiT-G/16 | 1.82 | [2511.13720](https://arxiv.org/abs/2511.13720) |
| DeCo | 1.62 | [2511.19365](https://arxiv.org/abs/2511.19365) |
| EPG | 1.58 | [2510.12586](https://arxiv.org/abs/2510.12586) |
| PixelDiT2 | 1.46 | [2609.24919](https://arxiv.org/abs/2609.24919) |

**Read this table carefully.**
- Guidance methods differ (CFG, interval CFG, AutoGuidance), and that alone moves FID by about 0.1–0.3.
- Several 2026 entries are unreviewed preprints.
- The gains since 2024 came mostly from the **latent space and the training signal, not the block design**.

### Deep dive A: Representation Autoencoders (RAE), Zheng, Ma, Tong, Xie (NYU), ICLR 2026. [arXiv 2510.11690](https://arxiv.org/abs/2510.11690)

- **Problem.** The SD-VAE is a ceiling. It has a low-dimensional latent (32×32×4), is trained only on reconstruction, and carries weak semantics. DDT's 1.26 already sits near the SD-VAE reconstruction floor (rFID about 1.2).
- **Mechanism.**
  - Swap the VAE encoder for a *frozen* DINOv2-B (patch 14 → 256 tokens × 768 dimensions at 256²) and train only a ViT-XL decoder (L1 + LPIPS + adversarial loss).
  - Reconstruction is *better* than SD-VAE: rFID 0.49 vs 0.62. With MAE it is 0.16.
  - Three fixes make diffusion work on 768-dimensional tokens:
    1. Width ≥ token dimension (Theorem 1, §6.5).
    2. A dimension-dependent timestep shift (FID 23.1 → 4.81).
    3. A noise-augmented decoder (4.81 → 4.28).
  - The **DiT^DH** design adds a shallow, wide head (2 layers, width 2048) to get width cheaply.
- **Results.** FID 2.16 at 80 epochs and 1.51 at 800 without guidance; 1.13 guided at both 256 and 512. About 16× faster convergence than REPA at matched compute.
- **Limitations.**
  - The DDT head *hurts* on low-dimensional SD-VAE latents (11.70 vs 7.13).
  - Raw pixels at equal dimension do much worse, which suggests structure matters, though JiT partly contests this through x-prediction.
  - Weaker fine reconstruction, which matters for editing ([2512.17909](https://arxiv.org/abs/2512.17909)).
- **Follow-ups.**
  - **Scale-RAE** ([2601.16208](https://arxiv.org/abs/2601.16208)), text-to-image at 0.5–9.8B with SigLIP-2:
    - RAE beats the FLUX VAE at every scale.
    - VAE models "catastrophically" overfit after 64 fine-tuning epochs, while RAE stays stable to 256.
    - The DDT head gives "negligible benefits at scale", but the **noise shift stays essential**.
    - Text rendering needs targeted decoder data.
  - **RAEv2** argues REPA ≈ x-prediction in RAE space, which makes the two complementary.

### Deep dive B: JiT, "Back to Basics: Let Denoising Generative Models Denoise". Li & He, CVPR 2026. [arXiv 2511.13720](https://arxiv.org/abs/2511.13720)

- **Problem.** Can a plain ViT on raw pixels with *large* patches work with no tokenizer, no pretraining and no auxiliary loss? Earlier answers said no.
- **Mechanism.**
  - Patches of 16/32/64 at 256/512/1024 keep T = 256 at every resolution.
  - The network predicts **x**, and the loss is still v-matching, using v̂ = (x_t − x̂)/t.
  - A linear *bottleneck* patch embedding (768 → as low as 16–512 → hidden) *improves* FID, which shows the useful information is low-rank.
  - Noise is scaled with resolution (2× at 512, 4× at 1024).
- **Results.** ImageNet-256 FID: B 4.37, L 2.79, H 1.86, G 1.82 (at 25 → 383 GFLOPs). ImageNet-512: G/32 2.11. Cost is nearly flat across resolution because T is fixed. In the target ablation, ε and v give FID above 96 and x gives 8.62.
- **Limitations.**
  - Still about 0.4–0.7 FID behind the best latent methods.
  - Each resolution needs its own noise and schedule tuning.
  - Large-G training is costly.
- **Follow-ups (2026).** It started a wave:
  - **PixelU**: U-shaped DiT, 1.63 at 256, beating JiT-G at about 1/3 the compute.
  - **PixelDiT2** (NVIDIA): 1.46 using frozen vision-foundation-model guidance.
  - **SiHC / "residual-stream burden"** ([2609.33895](https://arxiv.org/abs/2609.33895)): explains why noisy targets force the residual stream to carry noise through every layer, and widens it with hyper-connections (FID 1.71).
  - Theory ([2601.21419](https://arxiv.org/html/2601.21419)) formalizes when x beats ε/v from ambient vs intrinsic dimension.

### Deep dive C: the representation-alignment line (REPA → DDT → REPA-E → HASTE)

- **REPA** ([2410.06940](https://arxiv.org/abs/2410.06940), ICLR 2025 Oral):
  - Mechanism: a trainable MLP projects layer-~8 hidden states of the noisy input. A loss maximizes patch-wise cosine similarity with DINOv2 features of the *clean* image.
  - Training is 17.5× faster: SiT-XL/2 at 400K steps matches 7M-step vanilla SiT (FID 7.9 without CFG).
  - Interpretation: the DiT was wasting its early layers rediscovering semantics.
- **DDT** ([2504.05741](https://arxiv.org/abs/2504.05741)):
  - Builds that interpretation into the architecture: a 22-layer *condition encoder* (low-frequency semantics, with REPA) and a 6-layer *velocity decoder* (high-frequency output).
  - The encoder output can be **reused across adjacent sampling steps**, with a dynamic-programming schedule choosing which ones.
  - FID 1.26 at 400 epochs.
- **REPA-E** ([2504.10483](https://arxiv.org/abs/2504.10483)):
  - Training the VAE end-to-end with the diffusion loss collapses the latent, because diffusion prefers trivially easy latents. The REPA loss makes end-to-end training stable.
  - FID 1.12. The tuned VAE also works as a drop-in elsewhere.
- **The catch: "REPA Works Until It Doesn't" (HASTE, NeurIPS 2025)** ([2505.16792](https://arxiv.org/abs/2505.16792)):
  - Alignment speeds up early training, then plateaus or hurts; the teacher becomes a "straitjacket".
  - Turning it off early matches REPA's best FID with 28× fewer steps.

### Other 2024–26 advances

- **EDM2** (CVPR 2024) [2312.02696](https://arxiv.org/abs/2312.02696): magnitude-preserving U-Net plus post-hoc EMA. ImageNet-512 FID 1.81 without guidance.
- **DiT-MoE** [2407.11633](https://arxiv.org/abs/2407.11633): 16.5B parameters, 512 FID 1.80. The experts specialize by *position and timestep*, not by class.
- **EC-DiT** (Apple) [2410.02098](https://arxiv.org/abs/2410.02098): expert-choice routing up to 97B parameters.
- **FLUX.1 Kontext** [2506.15742](https://arxiv.org/abs/2506.15742): editing by plain token concatenation of context images; no new modules.
- **SANA / SANA 1.5** [2410.10629](https://arxiv.org/abs/2410.10629), [2501.18427](https://arxiv.org/abs/2501.18427): linear DiT + DC-AE. Inference-time scaling takes GenEval from 0.81 to 0.96.
- **Sparse video attention:**
  - STA ([2502.04507](https://arxiv.org/abs/2502.04507)): 945 s → 501 s end to end, training-free.
  - Radial Attention ([2506.19852](https://arxiv.org/abs/2506.19852)): O(n log n).
  - VSA ([2505.13389](https://arxiv.org/abs/2505.13389)): trainable; 2.53× fewer training FLOPs at equal loss.
- **Transfusion** [2408.11039](https://arxiv.org/abs/2408.11039) and **BAGEL** [2505.14683](https://arxiv.org/abs/2505.14683): one transformer with an LM loss on text and a diffusion/flow loss on images. BAGEL reaches GenEval 0.88.
- **LLaDA** [2502.09992](https://arxiv.org/abs/2502.09992): an 8B masked-diffusion LM whose backbone is a plain transformer without the causal mask. The backbone question for text is "nothing changes except the mask and the KV cache".

---

## 11b. Open problems

1. **What should the latent space be?** There are three camps with conflicting evidence:
   - **Semantic** latents: VA-VAE, REPA, RAE, Scale-RAE.
   - **Spectral or equivariance** regularization: "Diffusability of Autoencoders" ([2502.14831](https://arxiv.org/abs/2502.14831)) cuts high-frequency content for −19% FID; EQ-VAE ([2502.09509](https://arxiv.org/abs/2502.09509)).
   - **Dimensionality and prediction target**: JiT, SiHC.

   Why it is hard: every comparison changes the encoder, decoder and denoiser together, and nobody has run a controlled factorial study. Critics note RAE's reconstruction gap causes more object artifacts than its rFID predicts ([2512.17909](https://arxiv.org/abs/2512.17909)).
2. **Pixel vs latent at production scale.**
   - The pixel-space best (1.46) still trails latent methods (about 1.03–1.13) on ImageNet.
   - No compute-matched text-to-image or video comparison exists. Every production video model is latent.
   - The answer may hinge on the prediction target (x vs v), not on the architecture.
3. **Do U-Net inductive biases matter at scale?**
   - SiD2: large models do not need blockwise skips.
   - SD3: UViT beats DiT.
   - Locality helps DiT generalization ([2410.21273](https://arxiv.org/abs/2410.21273)).
   - SANA and LEDiT put convolutions back.

   A working hypothesis: multiscale structure and locality help when data or compute is limited and at high resolution, and fade at scale. This is untested beyond about 8B at matched compute.
4. **Scaling laws disagree.**

   | Study | Range | Finding |
   |---|---|---|
   | Liang et al. ([2410.08184](https://arxiv.org/abs/2410.08184)) | 1e17–6e18 FLOPs | Clean power law |
   | Abra ([2608.17286](https://arxiv.org/abs/2608.17286)) | up to 1e22 | About 200 image tokens per parameter is optimal, roughly 10× Chinchilla |
   | Chimera ([2607.28611](https://arxiv.org/abs/2607.28611)) | — | A balanced split for images |
   | Yin et al. ([2411.17470](https://arxiv.org/abs/2411.17470)) | video | Fixed-hyperparameter laws misjudge the optimal size by about 40% |

   Liang's budgets are about 3 orders of magnitude below Abra's.
5. **Is sparse attention a free lunch or an undertraining artifact?** VSA reports that fixed sparse patterns beat full attention at a compute-optimal budget (4.5e20 FLOPs) but *lose* at 4e21. Learned or routed sparsity may be the only kind that survives long training.
6. **Linear attention and SSMs.** Pure versions did not hold up for video ([Attention Surgery](https://arxiv.org/abs/2509.24899): "severely degrades video quality"). Hybrids with about 25% softmax layers match full attention. The open question is the right ratio and placement, mirroring the LLM hybrid debate.
7. **AR vs diffusion for images.**
   - Emu3 argues pure next-token prediction is enough, yet Emu3.5 bolted on a diffusion-style parallel decoder (DiDA) for 20× speed.
   - MAR and Fluid show continuous tokens beat VQ.
   - Unified models (Transfusion, BAGEL) split the difference.
   - Open question: does sharing one backbone hurt either modality at the frontier?
8. **Architecture vs memorization.** Mechanistic evidence says U-Nets and DiTs generalize through different inductive biases. No matched extraction study exists.
9. **Better metrics.** Most architecture claims are within FID noise once guidance method and epochs are matched. CMMD and human preference disagree with FID.

---

## 12. Lineage

```
U-Net (Ronneberger 2015, segmentation)
  └─ PixelCNN++ U-Net → DDPM (Ho 2020): 35.7M–256M, attn @16×16, additive t-emb
       └─ Improved DDPM / ADM (Dhariwal & Nichol 2021): AdaGN, BigGAN res, multi-res attn, 554M; beats GANs
            ├─ Imagen (2022): pixel cascade, Efficient U-Net, frozen T5-XXL
            ├─ eDiff-I (2022): ensemble of noise-level experts  ──────────────────┐
            ├─ LDM / Stable Diffusion (Rombach 2022): f8 VAE latent + cross-attn   │
            │    └─ SDXL (2023): 2.6B, attn moved to low-res                       │
            └─ EDM2 (2024): magnitude-preserving U-Net                             │
ViT (2020) ─┬─ U-ViT (Bao 2022): all-tokens + long skips                           │
            └─ DiT (Peebles & Xie 2022): patch tokens + adaLN-Zero, Gflops→FID     │
                 ├─ SiT (2024): flow/interpolant objective                         │
                 ├─ PixArt (2023), Hunyuan-DiT (2024): DiT + cross-attn            │
                 ├─ Sora (2024), CogVideoX, Wan 2.1: spacetime-patch DiTs          │
                 ├─ MMDiT / SD3 (Esser 2024): two-stream joint attn, QK-norm       │
                 │    └─ Flux.1 (2024): double→single stream, RoPE3, guidance emb  │
                 │         └─ Kontext (2025), HunyuanVideo, Qwen-Image, FLUX.2     │
                 ├─ DiT-MoE / EC-DiT (2024) ; Wan 2.2 timestep-MoE (2025) <────────┘
                 ├─ DiS/ZigMa/DiG (2024): SSM / linear ; SANA (2024): linear + DC-AE
                 ├─ REPA (2024) → LightningDiT/VA-VAE → DDT → REPA-E (2025)
                 ├─ RAE (2025) → Scale-RAE → RAEv2 / PAE (2026)
                 └─ HDiT, SiD2 → JiT (2025) → PixelU / PixelDiT2 / SiHC (2026)
```

---

## 13. Hands-on (≤30 min)

**Experiment 1: verify that tokens, not parameters, set the cost.** No GPU needed. Run [`backbone_flops.py`](backbone_flops.py):

```bash
python3 backbone_flops.py
```

It checks the per-layer cost formula 12Td² + 2T²d against all 12 Gflops numbers in DiT's Table 4 (they match within 0.2–5%). It then shows:
- DiT-XL's cost going 7 → 29 → 118 → 524 GMACs as p goes 8 → 4 → 2 → 1, with *identical* parameters;
- token counts for SD1.5, Flux, SANA and 720p video;
- the attention share of a Flux-width layer climbing from 18% at 4K tokens to 87% at video scale.

**Experiment 2 (GPU, about 10 min): see the backbone swap in diffusers.**

```python
import torch
from diffusers import DiffusionPipeline

for repo in ["stable-diffusion-v1-5/stable-diffusion-v1-5", "PixArt-alpha/PixArt-Sigma-XL-2-1024-MS"]:
    pipe = DiffusionPipeline.from_pretrained(repo, torch_dtype=torch.float16).to("cuda")
    net = getattr(pipe, "unet", None) or pipe.transformer
    print(repo, type(net).__name__, f"{sum(p.numel() for p in net.parameters())/1e6:.0f}M params")
    # Time one forward at increasing resolution to watch the scaling differ.
```

**Things to observe:**
- Time each backbone's forward pass at 512² and 1024². The U-Net's time grows roughly with pixels (it is conv-dominated). The DiT's grows faster once attention dominates.
- Then try `height=width=1536` on SD1.5 and look for duplicated subjects (§9).

---

## 14. Question ladder

**Mechanism**
1. In a DiT block, what exactly do the six adaLN-Zero vectors do, and what is the block's output at initialization?
2. What tensor shapes go into Flux's joint attention at 1024², and why are text tokens included in the softmax over image keys?
3. Why does halving DiT's patch size at least quadruple cost but leave parameter count unchanged?
4. Where does SD1.5's U-Net perform its most expensive attention, and how did SDXL change that?

**Why**
5. Why did adaLN-Zero beat cross-attention for *class* conditioning in DiT, yet SD3 still found joint attention best for *text*?
6. Why does x-prediction work on 768-dimensional pixel patches while ε- and v-prediction fail?
7. Why must the timestep schedule shift towards more noise at higher resolution, or with higher-dimensional latents?
8. Why did DiT's headline comparison with ADM overstate the "transformer vs U-Net" effect?

**Counterfactual**
9. What happens if you remove QK-norm from SD3 and train at 1024² in bf16?
10. What if MMDiT used one shared weight set for text and image (i.e. a plain DiT on concatenated tokens)?
11. What if RAE used DiT-S (width 384) on DINOv2-B tokens?
12. What if you removed all long skip connections from U-ViT, or from a 2B SiD2 model?

**Adversarial**
13. How would you make a well-trained 1024² DiT produce duplicated subjects without changing its weights?
14. How could a benchmark win of 0.2 FID be produced purely by evaluation choices?
15. Which architectural choices plausibly increase training-data memorization, and how would you test it?

**Connection**
16. How is Wan 2.2's MoE related to eDiff-I's expert denoisers, and how does it differ from DiT-MoE's token routing?
17. How does Flux's single-stream block relate to ViT-22B, and why does that matter for throughput?
18. How do DeepCache and TeaCache each depend on the backbone's structure?
19. How is LLaDA's backbone different from a causal LLM's, and what serving advantage does it lose?

**Open**
20. Is the best latent space semantic (RAE), spectrally regularized (EQ-VAE), or no latent at all (JiT)?
21. Do multiscale and locality inductive biases still matter at 10B+ parameters with matched compute?
22. Will sparse or linear attention survive long training at frontier scale, or only win when undertrained?

### Answers

<details><summary>1. adaLN-Zero vectors</summary>
They are shift β₁, β₂ and scale γ₁, γ₂ (applied as (1+γ)·LN(x)+β before attention and before the MLP), plus gates α₁, α₂ that multiply each branch before it is added to the residual. They come from one linear layer on SiLU(emb(t)+emb(y)). That layer is zero-initialised, so α=0 and the block is exactly the identity at init: x ← x + 0.
</details>

<details><summary>2. Flux joint-attention shapes</summary>
Image: 4096 tokens (128²/2² packed latent). Text: 512 T5 tokens. Both are projected to width 3072 with *separate* QKV weights, RMS-normalized (QK-norm), concatenated to 4608 tokens and split into 24 heads of 128. The softmax runs over all 4608 keys, so every image query can attend to text and every text query can attend to the image. That lets the text representation be updated by the image, which cross-attention never allows.
</details>

<details><summary>3. Patch size vs cost</summary>
T = (I/p)², so halving p multiplies T by 4. The linear terms (12Td²) scale by 4 and the attention term (2T²d) by 16, hence "at least" 4×. Parameters do not depend on T: the patch-embedding weights change only by the p²·C input dimension (tiny), and the transformer weights are per-token and shared.
</details>

<details><summary>4. SD1.5 vs SDXL attention placement</summary>
SD1.5 has attention (self + cross) at 64², 32² and 16² latent resolution. The 64² level means 4,096 tokens, which is the most expensive in T² though at width 320. SDXL uses transformer blocks [0, 2, 10] per level: none at the highest resolution and 10 at the lowest, and it drops the 8× level. This moves attention compute to where T is small.
</details>

<details><summary>5. adaLN vs joint attention</summary>
A class label is a single global vector, and modulating every channel by it is the cheapest, most direct injection. Text is a *sequence* with spatially specific meaning ("red" goes with "fox"), so it needs token-level routing. That is attention, not a global scale or shift. SD3 uses both: pooled text plus t go through adaLN, and the text tokens through joint attention.
</details>

<details><summary>6. x-pred vs ε/v on high-dimensional patches</summary>
Clean images lie on a low-dimensional manifold, while ε is full-rank Gaussian in all 768 dimensions. To output ε the network must carry 768 dimensions of incompressible information through its bottlenecks and residual stream. To output x it only needs the low-dimensional structure. In JiT's ablation ε and v give FID above 96 and x gives 8.62. SiHC frames this as "residual-stream burden".
</details>

<details><summary>7. Why shift the schedule</summary>
At higher resolution (or in higher-dimensional latents) neighbouring values are redundant. At the same σ the image's low frequencies survive, so the "hard" high-noise regime that sets global layout is under-trained. Shifting t (t_m = s·t/(1+(s−1)t) with s = √(m/n)) spends more steps at high effective noise. RAE: 23.1 → 4.81 FID from this alone.
</details>

<details><summary>8. DiT vs ADM confound</summary>
ADM is a pixel-space U-Net (1120 Gflops at 256²). DiT runs on f=8 VAE latents (118.6 Gflops) with the VAE's cost not counted. A latent U-Net (LDM-4) is 103.6 Gflops. Much of the gap is latent vs pixel and differences in training recipe. EDM2 (a U-Net) and SiD2 later showed compute-matched U-Net-like designs remain competitive.
</details>

<details><summary>9. No QK-norm</summary>
Attention logits grow during high-resolution fine-tuning, the softmax saturates to nearly one-hot (entropy collapse), gradients become spiky, and bf16 mixed precision diverges. SD3 observed this in a 2B model. The alternative was fp32, about 2× slower. ViT-22B saw the same at about 8B parameters.
</details>

<details><summary>10. One shared weight set</summary>
That is SD3's "DiT" baseline (concatenated tokens, shared weights). It did worse than CrossDiT and MMDiT on validation loss, CLIP score and GenEval. Text and image embeddings live in different statistical regimes, so forcing one projection to serve both wastes capacity. Note that Flux's 38 single-stream blocks *do* share weights. They come after 19 double-stream blocks have already aligned the two streams.
</details>

<details><summary>11. RAE with DiT-S</summary>
Width 384 is less than the token dimension of 768. By RAE's Theorem 1, the noised data's support is all of ℝ^768, so a width-384 bottleneck cannot represent the optimal denoiser. Training fails to reach good FID, and quality jumps once width ≥ 768. The DDT head exists to supply that width cheaply.
</details>

<details><summary>12. Removing long skips</summary>
U-ViT reports long skips are crucial at its scales (small models lose fine detail and converge slower). SiD2 found that small models lose about 0.2 FID without blockwise skips, while large models are unaffected or even slightly better. Skips act as a capacity crutch whose value shrinks with size.
</details>

<details><summary>13. Inducing duplicates</summary>
Sample far above the training resolution without adjusting the timestep shift. That under-allocates high-noise steps, so global layout never forms and local patterns repeat. Alternatively, extrapolate position embeddings (or exceed the U-Net's receptive field), so local regions each "think" they are the centre of an image and each draw a subject.
</details>

<details><summary>14. Gaming FID by 0.2</summary>
Any of these can do it:
- switch from plain CFG to interval CFG or AutoGuidance;
- tune the CFG scale on the evaluation set;
- report a later-epoch checkpoint;
- change the sampler or step count;
- use a different reference-statistics file;
- change the sample count.

All of these are present in the literature's headline tables, and several move FID by 0.1–0.3.
</details>

<details><summary>15. Architecture and memorization</summary>
Plausible amplifiers: higher capacity per sample (bigger models), strong text conditioning (Somepalli: captions matter as much as duplication), and less locality (DiT generalization correlates with attention locality). Test: train a U-Net and a DiT at matched FLOPs and data with planted duplicates, then run Carlini-style extraction (generate many samples per caption and measure near-duplicates to training images).
</details>

<details><summary>16. Wan 2.2 vs eDiff-I vs DiT-MoE</summary>
eDiff-I and Wan 2.2 route by *noise level*. The whole network switches at a timestep boundary (Wan: a high-noise expert for layout, a low-noise expert for detail), so each step runs one dense expert. DiT-MoE routes each *token* to top-k FFN experts inside every layer. Interestingly, its experts end up specializing by position and timestep anyway.
</details>

<details><summary>17. Single-stream and ViT-22B</summary>
Both use a parallel block: attention and MLP read the same normalized input. Their input projections are fused into one matmul (`linear1`) and their outputs into another (`linear2`). This raises GPU utilization (fewer, larger GEMMs) and was ViT-22B's throughput trick (about 15% faster at that scale, per that paper).
</details>

<details><summary>18. DeepCache vs TeaCache</summary>
DeepCache relies on the U-Net hierarchy: deep low-resolution features change slowly across steps, so they are cached, and only the shallow high-resolution path through the skip is recomputed. DiTs have no such hierarchy (every layer is full resolution). TeaCache instead estimates from the timestep-modulated input whether the *whole* output will change enough to recompute, and otherwise reuses the cached residual.
</details>

<details><summary>19. LLaDA backbone</summary>
Same transformer, but no causal mask (bidirectional attention) and trained to predict masked tokens at random mask ratios. It loses the KV cache, because every position can change every step, and generates a fixed-length canvas. Block diffusion and Fast-dLLM approximate caching to get it back.
</details>

<details><summary>20. Best latent space (open)</summary>
- **RAE / Scale-RAE**: semantics wins at scale.
- **Skorokhodov / EQ-VAE**: spectral smoothness matters, and semantics is incidental.
- **JiT / SiHC**: with x-prediction you may not need a latent at all.

No controlled factorial study separates encoder, decoder and denoiser effects.
</details>

<details><summary>21. Inductive biases at scale (open)</summary>
- Against: SiD2 (skips stop mattering for big models) and RAE's DDT head (negligible at scale).
- For: SD3 UViT > DiT, locality improving DiT generalization, SANA/LEDiT reintroducing convolutions, PixelU beating JiT at 1/3 the compute.

Likely data- and compute-regime dependent; untested beyond about 8B at matched compute.
</details>

<details><summary>22. Sparse/linear long-term (open)</summary>
VSA reports that fixed sparse patterns win at about 4.5e20 FLOPs but lose at 4e21. SANA-Video 2.0 and Attention Surgery find pure linear attention degrades video, while about 25% softmax hybrids match. Learned routing (VSA, NABLA) and hybrids are the live bets.
</details>

---

## 15. Go deeper next

1. **Flow matching vs diffusion objectives** (rectified flow, logit-normal t-sampling, why SiT beat DiT with the same network).
2. **Classifier-free guidance and its variants** (interval CFG, AutoGuidance, guidance distillation in Flux-dev): why guidance changes FID tables more than architecture does.
3. **Video diffusion attention** (3D full vs sliding-tile vs learned sparse, sequence parallelism for 100K-token denoising).

---

## Sources

### Papers: foundations
- U-Net, Ronneberger 2015: https://arxiv.org/abs/1505.04597
- DDPM, Ho 2020: https://arxiv.org/abs/2006.11239
- ADM, Dhariwal & Nichol 2021: https://arxiv.org/abs/2105.05233
- LDM, Rombach 2022: https://arxiv.org/abs/2112.10752
- Imagen: https://arxiv.org/abs/2205.11487
- eDiff-I: https://arxiv.org/abs/2211.01324
- DiT, Peebles & Xie: https://arxiv.org/abs/2212.09748
- U-ViT, Bao: https://arxiv.org/abs/2209.12152
- SDXL: https://arxiv.org/abs/2307.01952
- SD3 / MMDiT, Esser 2024: https://arxiv.org/abs/2403.03206
- simple diffusion, Hoogeboom 2023: https://arxiv.org/abs/2301.11093
- ViT-22B: https://arxiv.org/abs/2302.05442

### Papers: frontier
- SiT: https://arxiv.org/abs/2401.08740
- EDM2: https://arxiv.org/abs/2312.02696
- HDiT: https://arxiv.org/abs/2401.11605
- SiD2: https://arxiv.org/abs/2410.19324
- REPA: https://arxiv.org/abs/2410.06940
- VA-VAE / LightningDiT: https://arxiv.org/abs/2501.01423
- DDT: https://arxiv.org/abs/2504.05741
- REPA-E: https://arxiv.org/abs/2504.10483
- HASTE: https://arxiv.org/abs/2505.16792
- RAE: https://arxiv.org/abs/2510.11690
- Scale-RAE: https://arxiv.org/abs/2601.16208
- RAEv2: https://arxiv.org/abs/2605.18324
- PAE: https://arxiv.org/abs/2605.07915
- RAE critique: https://arxiv.org/abs/2512.17909
- JiT: https://arxiv.org/abs/2511.13720
- PixelFlow: https://arxiv.org/abs/2504.07963
- DeCo: https://arxiv.org/abs/2511.19365
- EPG: https://arxiv.org/abs/2510.12586
- PixelU: https://arxiv.org/abs/2606.27760
- PixelDiT2: https://arxiv.org/abs/2609.24919
- SiHC: https://arxiv.org/abs/2609.33895
- Prediction-dimensionality theory: https://arxiv.org/html/2601.21419
- Diffusability of AEs: https://arxiv.org/abs/2502.14831
- EQ-VAE: https://arxiv.org/abs/2502.09509
- DC-AE: https://arxiv.org/abs/2410.10733
- SANA: https://arxiv.org/abs/2410.10629
- SANA 1.5: https://arxiv.org/abs/2501.18427
- SANA-Video 2.0: https://arxiv.org/abs/2607.21553
- Attention Surgery: https://arxiv.org/abs/2509.24899
- DiS: https://arxiv.org/abs/2402.05608
- ZigMa: https://arxiv.org/abs/2403.13802
- DiG: https://arxiv.org/abs/2405.18428
- U-DiT: https://arxiv.org/abs/2405.02730
- DiT-MoE: https://arxiv.org/abs/2407.11633
- EC-DiT: https://arxiv.org/abs/2410.02098
- Race-DiT: https://arxiv.org/abs/2503.16057
- FLUX.1 Kontext: https://arxiv.org/abs/2506.15742
- Transfusion: https://arxiv.org/abs/2408.11039
- BAGEL: https://arxiv.org/abs/2505.14683
- LLaDA: https://arxiv.org/abs/2502.09992
- CogVideoX: https://arxiv.org/abs/2408.06072
- Wan 2.1 report: https://arxiv.org/abs/2503.20314
- STA: https://arxiv.org/abs/2502.04507
- Radial Attention: https://arxiv.org/abs/2506.19852
- VSA: https://arxiv.org/abs/2505.13389
- Scaling laws (Liang): https://arxiv.org/abs/2410.08184
- Video DiT scaling (Yin): https://arxiv.org/abs/2411.17470
- Abra: https://arxiv.org/abs/2608.17286
- Chimera: https://arxiv.org/abs/2607.28611

### Papers: failure modes
- ScaleCrafter: https://arxiv.org/abs/2310.07702
- FiT: https://arxiv.org/abs/2402.12376
- LEDiT: https://arxiv.org/abs/2503.04344
- Carlini extraction: https://arxiv.org/abs/2301.13188
- U-Net vs DiT generalization: https://arxiv.org/abs/2410.21273
- CMMD / Rethinking FID: https://arxiv.org/abs/2401.09603
- Character-aware text: https://arxiv.org/abs/2212.10562
- T2ICountBench: https://arxiv.org/abs/2503.06884
- Numerosity: https://arxiv.org/html/2510.11117v1
- Massive activations in RF transformers: https://arxiv.org/pdf/2510.04236
- DeepCache: https://arxiv.org/abs/2312.00858
- TeaCache: https://arxiv.org/abs/2411.19108

### Code / docs / model cards
- BFL flux reference code: https://github.com/black-forest-labs/flux
- FLUX.1-dev card: https://huggingface.co/black-forest-labs/FLUX.1-dev
- DiT code: https://github.com/facebookresearch/DiT/blob/main/models.py
- SD v1 config: https://raw.githubusercontent.com/CompVis/stable-diffusion/main/configs/stable-diffusion/v1-inference.yaml
- SD3.5 Large card: https://huggingface.co/stabilityai/stable-diffusion-3.5-large
- SD3.5 Medium card: https://huggingface.co/stabilityai/stable-diffusion-3.5-medium
- diffusers Flux docs: https://huggingface.co/docs/diffusers/main/en/api/pipelines/flux
- diffusers SD3 docs: https://huggingface.co/docs/diffusers/main/en/api/pipelines/stable_diffusion/stable_diffusion_3
- diffusers cache docs: https://huggingface.co/docs/diffusers/main/en/optimization/cache
- Wan 2.1: https://github.com/Wan-Video/Wan2.1
- Wan 2.2: https://github.com/Wan-Video/Wan2.2
- HunyuanVideo: https://github.com/Tencent-Hunyuan/HunyuanVideo
- Qwen-Image: https://huggingface.co/Qwen/Qwen-Image
- PixArt-α (ICLR 2024): https://proceedings.iclr.cc/paper_files/paper/2024/hash/fe989bb038b5dcc44181255dd6913e43-Abstract-Conference.html

### Articles
- Sora tech report: https://openai.com/index/video-generation-models-as-world-simulators/
- NVIDIA on EDM2: https://developer.nvidia.com/blog/rethinking-how-to-train-diffusion-models
- PyTorch, torch.compile + diffusers: https://pytorch.org/blog/torch-compile-and-diffusers-a-hands-on-guide-to-peak-performance/
- PyTorch, Flux Fast: https://pytorch.org/blog/presenting-flux-fast-making-flux-go-brrr-on-h100s/

**Uncertainty flags:**
- PAE's guidance setting is unverified.
- RAE's 1.13 may use AutoGuidance rather than plain CFG.
- The massive-activation numbers come from an abstract/summary only.
- PixArt's adaLN-single parameter saving is recalled from memory.
- The claim that DiT's "Gflops" are GMACs is inferred from the arithmetic.
- Several 2026 entries are unreviewed preprints.
