# Nanite-style virtualized geometry: cluster DAG, crack-free LOD, micro-triangle rasterization

**Computer science · Graphics/GPU · Nanite-style virtualized geometry (cluster DAG, locked-border LOD, software rasterization, two-pass HZB culling) · hard · 2026-10-04**

> Source-quality note. Karis' SIGGRAPH 2021 slides (155 pp) were too large for my fetch tool, so core mechanism claims come from secondary write-ups that quote them (blogs, Epic docs, meshoptimizer discussions, course notes). Where I verified a primary page myself it is marked **[verified]**; where sources disagree it is flagged **[conflict]**; everything else is **[secondary]**.

---

## 0b. Plain English first

**Explain it simply.** Think of a map app. Zoomed out, a city is a grey blob; zoomed in, you see every house. The app does not keep one giant picture and shrink it. It keeps the city cut into small tiles, and for every tile it keeps cruder versions too. You only ever load the tiles you can see, at just the sharpness your screen can show. Nanite does this for 3D models. A statue with a million tiny triangles is chopped into little patches of 128 triangles. Each patch has coarser stand-ins. Every frame the GPU asks, for each patch: "if I used the coarse version, would anyone notice on screen?" If not, it uses the coarse one. The trick that makes it work is that neighbouring patches always agree on the exact points along their shared edges, so a coarse patch next to a fine patch still fits like a jigsaw piece, with no gaps.

**Everyday example.** A game has a stone dragon statue made of about 1,000,000 triangles. Stand 2 metres away: the statue fills the screen, so you need nearly all the detail; the game draws the fine patches facing you and skips the back of the statue. Walk 200 metres away: the statue is a 30-pixel smudge. The game swaps each patch for its coarsest stand-in, maybe a few hundred triangles in total, and nobody can tell. Walk back slowly: patches near the middle of the statue get sharper first, one patch at a time, and no seam ever opens up because the borders between patches never moved.

**Bridge.** Now the same thing, technically.

---

## 1. Bare-minimum context

- **Rasterization**: GPU turns triangles into pixels; hardware shades pixels in 2×2 quads (needed for texture derivatives).
- **LOD (level of detail)**: cheaper versions of a mesh used when far away. Classic LOD = a few hand/auto-made versions per object, switched by distance.
- **Meshlet / cluster**: a small fixed-size triangle batch (here 128 triangles) processed as a unit.
- **Quadric error metric (QEM)**: Garland & Heckbert's way to collapse mesh edges while tracking geometric error ([CMU](https://publications.ri.cmu.edu/surface-simplification-using-quadric-error-metrics)).
- **Visibility buffer**: write "which triangle is here" per pixel instead of shading; shade later once per pixel.
- **HZB**: hierarchical-Z, a mip pyramid of the depth buffer holding farthest depth per region; used for conservative occlusion tests.

## 1b. Real-world context

**What it is.** A rendering pipeline (Unreal Engine 5's Nanite, plus open clones) that stores each mesh as a hierarchy of triangle clusters at many detail levels, selects the right cut through that hierarchy on the GPU every frame so that error is ≲1 pixel, and rasterizes the result with a mix of hardware and compute-shader rasterization.

**Why it exists.** Classic LOD has three costs: artists/tools must author LOD chains per asset; each object pops when it switches level; and the CPU submits a draw call per object, capping scene complexity. Film-quality or photogrammetry assets (millions of triangles each) were unusable in real-time. Nanite makes triangle count roughly scale with *pixels on screen*, not scene size, and moves culling/LOD/draw-building to the GPU.

**Where it's used.**
- Unreal Engine 5: Nanite (Epic's docs: [Nanite virtualized geometry](https://dev.epicgames.com/documentation/unreal-engine/nanite-virtualized-geometry-in-unreal-engine)).
- Fortnite: Epic's blog says Nanite is used in Chapter 4+ for building meshes ([Epic blog](https://www.unrealengine.com/blog/battle-testing-unreal-engine-5-1-s-new-features-on-fortnite-battle-royale-chapter-4)) [secondary].
- *The Matrix Awakens* (2021) tech demo; shipped games reported to use it include Black Myth: Wukong and Senua's Saga: Hellblade II [secondary, community lists].
- meshoptimizer (zeux): meshlet building, border-locking simplification, cluster partitioning that Nanite clones build on ([GitHub](https://github.com/zeux/meshoptimizer)).
- Bevy "virtual geometry" (meshlet renderer, experimental since 0.14): same pipeline, hardware rasterization only at time of the author's post ([jms55](https://jms55.github.io/posts/2024-06-09-virtual-geometry-bevy-0-14/)) [secondary].
- NVIDIA RTX Mega Geometry (Feb 2025): cluster acceleration structures (`VK_NV_cluster_acceleration_structure`) so ray tracing can use the same cluster idea **[verified]** ([NVIDIA](https://developer.nvidia.com/blog/nvidia-rtx-mega-geometry-now-available-with-new-vulkan-samples/)).
- Unity: an official `com.unity.virtualmesh` reference package, not production-ready [secondary].

**How it's used.**
- Unreal: tick **Enable Nanite Support** on a Static Mesh; global `r.Nanite 0/1`; streaming pool `r.Nanite.Streaming.StreamingPoolSize`; buffer-size cvars `r.Nanite.MaxCandidateClusters` (12 B each) and `r.Nanite.MaxVisibleClusters` (16 B each) **[verified: Epic technical details]**. Epic also exposes Position/Normal Precision per mesh.
- Open-source build side, via meshoptimizer (signatures from memory of the public header, check `meshoptimizer.h` for your version):

```cpp
// 1. cluster a mesh into <=128-tri meshlets
size_t maxm = meshopt_buildMeshletsBound(index_count, 128, 128);
std::vector<meshopt_Meshlet> ml(maxm);
std::vector<unsigned> mv(maxm * 128);      // vertex indices
std::vector<unsigned char> mt(maxm * 128 * 3);
size_t n = meshopt_buildMeshlets(ml.data(), mv.data(), mt.data(),
    indices, index_count, &pos[0].x, vcount, sizeof(Vec3),
    /*max_vertices*/128, /*max_triangles*/128, /*cone_weight*/0.f);

// 2. simplify a merged group with its border locked (per Nanite group step)
float err = 0;
size_t out = meshopt_simplify(dst, group_idx, group_idx_count,
    &pos[0].x, vcount, sizeof(Vec3),
    group_idx_count / 2, /*target_error*/1e9f,
    meshopt_SimplifyLockBorder | meshopt_SimplifySparse, &err);
// err is relative to mesh extent; scale with meshopt_simplifyScale()
```
  A single-header `clusterlod.h` doing the whole DAG is reported in meshoptimizer's recent releases [secondary].

**Use it / skip it.**
- Use: opaque, mostly static, high-poly geometry (scans, sculpts, CAD, rock/architecture kits), many instances.
- Skip: translucency (not supported), forward/mobile renderers (Nanite needs the deferred pipeline and SM6-class features), small low-poly meshes where classic LOD wins (one measured test claims Nanite loses under ~2M triangles/mesh, [CRDG Japan](https://crdg.jp/studio-tech-1/en/2025/05/29/3338/); blog-grade evidence), heavily masked/alpha foliage and large WPO animation (see §9).

**Who should care.** Engine/graphics programmers; technical artists deciding import settings; ML/vision people doing 3D Gaussian-splat LOD (the same DAG idea is being ported, §11).

---

## 2. The one-liner and what it hides

"Nanite renders unlimited triangles by streaming and LOD-ing 128-triangle clusters at pixel scale."

What it hides:
1. How can two *independently* simplified neighbouring groups meet without cracks?
2. How does the GPU pick a consistent LOD cut with **no neighbour communication**?
3. Why a **DAG** and not a tree, and why alternate which borders are locked?
4. Why a *software* rasterizer beats the hardware one for tiny triangles.
5. What it costs: overdraw, masked materials, animation, ray tracing, streaming.

## 3. The problem

- Source asset: 1M–1B triangles. Screen: 1080p = 2.07M pixels. Visible detail needed ≈ 1 triangle per pixel at most, so ≲ 2M visible triangles ≈ 16k clusters, *independent of source size*.
- Classic discrete LOD: popping, per-asset authoring, per-object draw call and CPU culling.
- Hardware rasterizer inefficiency: pixels are shaded in 2×2 quads, so a triangle covering one pixel still launches at least 4 pixel-shader lanes, i.e. ≥75% of the work is thrown away (helper lanes).
- Constraint forcing the design: LOD decisions must be local (per cluster, parallel on GPU), yet globally watertight.

## 4. Mental model

A zoomable map in tiles with borders that are *pinned*. Pins mean the fine tile and the coarse tile share the same border points, so they interlock at any mix.

Where it breaks: the pins make tile borders un-simplifiable. A tile border stays dense forever unless the *next* level draws its tile borders somewhere else. So the map must be re-tiled at every zoom level with different cuts (that is why it's a DAG, §5).

## 5. The mechanism, traced

Offline build (per mesh):

```
level 0:  T triangles → partition (graph partition on shared edges) → clusters of ≤128 tris
repeat:
  group    : merge 8–32 spatially adjacent clusters [secondary: UE constants]
  lock     : every edge shared with a DIFFERENT group has both vertices locked
  simplify : QEM collapse inside the group to ~50% triangles (borders untouched)
  record   : group error e_g = max(e_g_raw, max child error)    # monotone
             group bounds = hull(children bounds, own bounds)   # nested
  split    : re-cluster the simplified group into new ≤128-tri clusters
             (these are the group's "parent" clusters)
  next level re-partitions the NEW clusters, so last level's locked borders
  now fall inside groups and get simplified
until one root cluster remains
```
Result: each cluster has (self error, self bounds) and (parent error, parent bounds). All clusters in a group share the same pair.

Runtime, per frame, ONE cluster example (cluster X, error e=0.8 cm, parent error 1.9 cm, camera 25 m away, 1080p, 60° FOV):

1. Projected error of X ≈ e·H/(2·d·tan(φ/2)) = 0.8·1080 / (2·2500·0.577) ≈ 0.30 px ≤ 1 px → X is fine enough.
2. Projected error of its parent = 1.9·1080/(2·2500·0.577) ≈ 0.71 px ≤ 1 px → parent is *also* fine enough, so a coarser cluster gets drawn and X is skipped.
3. Camera moves to 12 m: parent ≈ 1.48 px > 1 px → parent too coarse; X ≈ 0.62 px ≤ 1 → **X is drawn**.
4. Then, cluster passes frustum + HZB occlusion test; survivors are binned by projected triangle size.
5. Big triangles → hardware raster; tiny ones → compute-shader raster. Each writes a 64-bit value into the visibility buffer with an atomic max (depth in the high bits so nearest wins).
6. Later passes read the buffer, look up (clusterID, triangleID), fetch the triangle, interpolate, and shade each pixel once; materials are binned by tile.

GPU traversal: persistent threads pull BVH nodes from a lock-free work queue; a node that is not "small enough to draw" pushes its children back to the queue; leaves are clusters [secondary: elopezr, Karis]. Culling is two-pass (§7).

Visibility buffer layout **[conflict]**: sources agree it is 64 bits/pixel with ~30-bit depth, a 7-bit in-cluster triangle ID (128 triangles = 2^7), and a cluster ID filling the rest; one source says 27-bit cluster ID with 30-bit depth, another describes 25-bit cluster ID in a 32-bit word + 32-bit depth word. I could not confirm against the slides.

## 6. The math

**QEM (collapse cost).** For a triangle plane p = (a,b,c,d), a²+b²+c²=1, squared distance of point v=(x,y,z,1) to the plane is (pᵀv)² = vᵀ(ppᵀ)v. Per vertex, Q = Σ_planes ppᵀ (a 4×4 symmetric matrix). Collapsing vertices 1,2 to v̄ costs Δ(v̄) = v̄ᵀ(Q₁+Q₂)v̄, minimized by solving the 4×4 linear system with last row (0,0,0,1) [Garland & Heckbert 1997].
→ in plain terms: each vertex remembers "how far from my old surface planes am I allowed to drift"; summing matrices means errors add without storing the planes. This form (matrix sum) is why collapses are O(1) after setup.

**Screen-space error.** World error e at distance d. Image plane half-height at distance d is d·tan(φ/2) world units and maps to H/2 pixels, so one world unit = (H/2)/(d·tan(φ/2)) px:

  proj(e, d) = e · H / (2 · d · tan(φ/2)),  d = max(‖cam − c‖ − r, ε)  (bounding sphere c, r)

→ in plain terms: error shrinks with distance and grows with resolution; using the *nearest point of the sphere* makes the estimate conservative (never optimistic).

**Selection rule.** Draw cluster c ⇔ proj(e_self, d_self) ≤ τ < proj(e_parent, d_parent), τ ≈ 1 px.

**Why monotonic?** If e_parent ≥ e_self and bounds_parent ⊇ bounds_self then d_parent ≤ d_self so proj is non-decreasing going up any DAG path. Then along every leaf→root path there is exactly one crossing of τ, and siblings (same group) share the parent's numbers, so they all agree. The cut is consistent without anyone talking to neighbours. Remove either rule and (see experiment) cuts overlap or leave holes.

**Size accounting.** Each level keeps ~50% triangles: total DAG triangles ≈ T(1 + ½ + ¼ + …) = 2T, depth ≈ log₂(T/128). For T = 10⁹: ≈ 23 levels. Storage: Epic reports 14.4 bytes per *input* triangle on average, and a 1.5M-triangle example at 19.64 MB vs 148.95 MB for a 4-LOD standard static mesh (7.6×) **[verified: Epic technical details]**.

## 7. Why it works

- **Watertight**: locked border vertices are identical in every level, so a fine group beside a coarse group shares exact vertices. No stitching, no skirts.
- **Local decision**: monotone error + nested bounds + group-shared numbers → GPU threads decide per cluster, in parallel, no synchronization.
- **Constant work per pixel**: error ≈ 1 px means ≈ 1 triangle per pixel regardless of source size.
- **Two-pass occlusion culling** [secondary]: pass 1 draws clusters that were visible last frame, tested against last frame's HZB; build a new HZB from that depth; pass 2 re-tests everything pass 1 culled against the new HZB and draws what was wrongly culled. Result is conservative-correct without a CPU readback.
- **Software raster**: one wave handles a whole cluster (128 triangles, up to ~3× faster than hardware for pixel-sized triangles [secondary: reported by Karis/blogs]) with 64-bit atomic write to the visibility buffer, no quad waste.
- Ablation: no border lock → cracks; borders never moved → root cluster never reaches 1 and un-simplifiable seams (meshoptimizer discussion: border vertices are 30–50% of verts at level 1 **[verified]**); no monotone error → overlaps/holes (my toy: 50/3000 random views broken); tree not DAG → every group border persists across levels.

## 8. Design knobs & alternatives

- Cluster size: 128 tris (7-bit triangle ID, multiple of wave size). meshoptimizer user report: 256v/128t beat 64v/64t because rasterization cost dominated **[verified]**.
- Group size 8–32 clusters [secondary]; bigger = better simplification, more streaming coupling.
- τ (≈1 px): bigger = faster, shimmers more; Nanite's visual stability relies on temporal AA.
- Position precision (`2^P` grid; 21 bits/axis max) trades size vs stairstepping [secondary].
- Page streaming: 128 KB pages, 32 KB root pages [secondary] (not stated on Epic's technical details page I fetched).
- Alternatives: classic discrete LOD (cheap, popping, authoring); progressive/view-dependent meshes (Hoppe) which cannot be evaluated in parallel per cluster; Quick-VDR's clustered hierarchy of progressive meshes (Yoon et al., 2004) [secondary]; mesh shaders + meshlets without a DAG; voxel/impostors for aggregates.

## 9. Where it breaks

- **Overdraw / thin geometry**: simplification removes few triangles from layered or holey meshes, and many depth layers must be drawn before occlusion bites; one article claims 2× worse than expected [80.lv, blog-grade].
- **Aggregates** (leaves, grass, hair): disconnected parts do not collapse into a plane; thin features vanish or stay dense. Epic's answer in the UE 5.8 docs: Nanite Assemblies, Voxels, Skinning **[verified]**.
- **WPO/animation**: cluster bounds are static; displaced vertices can be culled wrongly, needing "max WPO distance"; per-frame animation also invalidates cached virtual shadow map pages [forums/blogs, secondary].
- **Masked materials**: need separate raster bins and per-pixel alpha test in the raster loop; costly.
- **No translucency; deferred-only**: VR forward and mobile are out (Meta docs, Arm blog) [secondary].
- **Ray tracing**: Nanite clusters do not map to hardware BLAS directly; cluster acceleration structures (RTX Mega Geometry) are the 2025 response **[verified existence]**.
- **Streaming**: undersized pool thrashes; pop-in with fast cameras; SSD effectively required [secondary].
- **Subpixel shimmer**: sub-pixel triangles → temporal instability; relies on TSR/TAA [Epic thin-geometry docs, secondary].
- Misconceptions: "free LODs" (no: cost moves to material shading, shadows, memory); "always faster" (no: measured results mixed: one forum test shows Nanite ~1.5 ms slower than an overdraw-optimized LOD scene; another reports RTX 3090 55–58 FPS vs 47–49 [secondary]).

## 10. In the wild

- UE5 deviates from textbook by quantizing and bit-packing everything, material binning in compute (UE 5.4, GDC 2024 "Nanite GPU Driven Materials"; I could not fetch the slides, details from Scthe's notes) [secondary], and optional work graphs.
- Bevy: asset processing builds the meshlet DAG with meshopt+METIS; runtime does two-pass culling; hardware raster only at the time of the post, so expect worse micro-triangle perf [secondary].
- meshoptimizer's recipes ask for `LockBorder`/`Sparse` and report root counts of 5–19 meshlets on Bunny/Dragon/Cliff (never 1 without tricks) due to disjoint triangles **[verified: discussion #750]**.

## 11. Frontier (what's new)

Verified by me via fetch unless marked.

1. **CuRast** (arXiv 2604.21749, Apr 2026; Schütz, Lipp, Kristmann, Wimmer): CUDA software rasterizer with a 3-stage pipeline by triangle size; 2–5× (unique) / up to 12× (instanced) faster than Vulkan on hundreds of millions of triangles, but Vulkan stays an order of magnitude faster for low-poly meshes. Targets dense opaque photogrammetry. Evidence the "software raster for dense meshes" claim is alive. **[verified]**
2. **Virtualized 3D Gaussians** (arXiv 2505.06523, May 2025; Yang, Xu, Jiang, Lin, Dai): Nanite-inspired cluster hierarchy for 3D Gaussian splats, offline hierarchy + online cluster selection, up to billions of Gaussians. **[verified]**
3. **LODGE** (NeurIPS 2025, arXiv 2505.23158; Kulhanek et al.): hierarchical LOD for large-scale Gaussian splatting with depth-aware filtering, importance pruning, spatial chunks with dynamic loading and opacity blending to hide seams. Note: it solves seams by *blending*, not by locked borders, because splats have no shared vertices. **[verified]**
4. **RTX Mega Geometry** (NVIDIA, Feb 2025): cluster acceleration structures and partitioned acceleration structures for Vulkan, with open `nv_cluster_builder` / `nv_lod_cluster_builder`; continuous-LOD streaming for ray tracing. **[verified]** A "2.0 / Gears of War: E-Day" claim from one agent report I could not verify, so omitted.
5. **Nanite Foliage** (UE 5.8 docs): Assemblies (instanced parts), Voxels (near-pixel-sized voxels at distance), Skinning (bone-driven wind). Example from the doc: 41M-triangle tree, 12 unique parts, 2,160 instances, 850 bones; disk 3.5 GB → 29 MB for the largest tree; streaming memory 36 MB → 2.7 MB per tree in view. **[verified]** (an "UE 5.7 / 200 trillion polygons" claim in one agent note was wrong/unsupported and is dropped).
6. **DGF** (HPG 2024; AMD, Barczak, Benthin, McAllister): dense hardware-friendly lossy meshlet format, 128-byte blocks, designed to be read directly by ray-tracing hardware. [ACM page returned 403; reported by an agent, not verified by me.] Link: https://dl.acm.org/doi/10.1145/3675383
7. Also reported, not verified by me: GPU work-graph procedural generation (HPG 2024 best paper), Eurographics 2025 mesh-shader procedural resurfacing.

## 11b. Open problems

- **Aggregate LOD**: no accepted way to simplify foliage/hair into a coarser *representation* that preserves coverage and shading; voxels are Epic's first production answer (UE 5.8), still new.
- **Deforming geometry**: cluster bounds and the DAG are built for rigid shapes; skinning/WPO/morphs break error bounds. Skinned Nanite is marked experimental in 5.5+ per sources [secondary]. Why hard: error bounds must hold for every pose.
- **Ray tracing**: hardware BVH builds for clusters at 1-pixel LOD per frame; shared visibility between rays; cluster-AS is the 2025 hardware answer, open how engines stream/blend LOD between primary and secondary rays.
- **Portability**: 64-bit image atomics and persistent threads limit Nanite to desktop-class GPUs; mobile and WebGPU ports (community, e.g. Scthe's nanite-webgpu) are partial [secondary].
- **Attribute-aware error**: QEM weights normals/UVs heuristically; no perceptual error model tied to shading.
- **Splats vs meshes**: no shared border to lock in 3DGS, so seams are hidden by blending (LODGE); principled analogue unsettled.

## 12. Lineage

Progressive meshes / view-dependent simplification (Hoppe, 1996–97) → Quadric error metrics (Garland & Heckbert, SIGGRAPH 1997) → clustered hierarchy of progressive meshes in Quick-VDR (Yoon et al., IEEE Visualization 2004) [secondary] → meshlets + mesh shaders (NVIDIA Turing, 2018; [secondary]) → Nanite (Karis, SIGGRAPH Advances 2021) → open clones (meshoptimizer, Bevy) → GPU-driven materials (GDC 2024) → cluster ray tracing (RTX MG 2025) → Gaussian-splat cluster LOD (2025). Cignoni et al. "Batched Multi-Triangulation" (2005) is a frequently cited precursor I did not retrieve.

## 13. Hands-on (≤30 min): `cluster_dag_1d.py`

A 1-D polyline stands in for the mesh: clusters of 8 segments, groups of 4, group simplified to half with end points locked, offsets alternate by level, plus monotone error/nested bounds. It then picks cuts for random cameras and checks the selected clusters tile the curve exactly.

```
$ python3 cluster_dag_1d.py
DAG: 511 clusters, root err 60.817
monotone err + nested bounds : tiling failures 0 / 3000
ablate monotone rules        : tiling failures 50 / 3000
cut cam=-500 tau=0.5 : 256 clusters, per level {0: 256}
cut cam=-500 tau=4   : 128 clusters, per level {0: 8, 1: 116, 2: 4}
cut cam=-500 tau=20  :  16 clusters, per level {4: 16}
```
Try: set `G=2`, change the offset line to `off = 0` always (never move borders) and look at root error/cluster counts; or break only the hull to see which half of the ablation does the damage. Caveat: 1-D toy, error measured vertically; it demonstrates the consistency argument, not Nanite's quality or speed.

## 14. Question ladder

**Mechanism**
1. What do two adjacent groups at different LOD levels have in common along their border, and why does that prevent cracks?
2. Walk one cluster through the selection test when the camera moves from 25 m to 12 m (use §5's numbers).
3. What exactly happens in pass 2 of two-pass occlusion culling, and why is pass 1 needed at all?
4. How does a 64-bit atomic max implement visibility and depth test at once?
5. Why must every cluster in a group share the same parent error and bounds?

**Why**
6. Why 128 triangles per cluster?
7. Why a DAG and not a tree?
8. Why is the software rasterizer faster for tiny triangles even though it's "slower silicon"?
9. Why use a bounding-sphere nearest point rather than the center for distance?

**Counterfactual**
10. What if you did not lock group borders and instead stitched afterwards?
11. What if parent error could be smaller than a child's error?
12. What if cluster size doubled to 256?

**Adversarial**
13. Build a mesh that makes Nanite's cut huge no matter the distance.
14. How does a wind shader make a leaf disappear at the screen edge?
15. Which streaming pattern thrashes the 128 KB page pool?

**Connection**
16. How does this relate to mip-mapping and virtual textures?
17. How is a 3DGS LOD hierarchy the same / different (seams, borders)?

**Open**
18. How would you get a proper LOD for a tree canopy that keeps average colour, silhouette, and shadow-casting?
19. Can a forward renderer use a visibility buffer pipeline without the deferred G-buffer?

<details><summary>Answers</summary>

1. They share identical vertex positions on the shared edges (locked during both groups' simplification), so geometry meets exactly whatever each side's density.
2. At 25 m: self 0.30 px, parent 0.71 px, both ≤ τ=1, so the parent (or a coarser ancestor) is chosen and X is skipped. At 12 m: self 0.62 px, parent 1.48 px > 1 → X passes `self ≤ τ < parent`, is drawn.
3. Pass 1 culls using last frame's HZB (stale); it draws those clusters, builds a fresh HZB from the resulting depth; pass 2 re-tests the clusters pass 1 culled against the new HZB and draws those now visible. Pass 1 exists to get a good depth pyramid cheaply without a CPU readback.
4. Depth sits in the high bits of the 64-bit word, so max (reverse-Z) keeps the nearest sample; the low bits carry the IDs, so the surviving value *is* the visible triangle.
5. If siblings disagreed, one might be drawn at fine and its neighbour at coarse in the same group, but their shared interior vertices are not locked, so a crack/overlap appears. Shared numbers make the whole group switch atomically.
6. Wave-size multiples (32/64) and the 7-bit triangle ID in the visibility buffer; small enough for fine culling, large enough to amortize per-cluster overhead.
7. In a tree each group's borders would be the same borders at every level, so they'd never simplify; a DAG lets level k+1 re-group clusters so old borders fall inside new groups.
8. Hardware shades 2×2 quads and has per-triangle setup overhead; a 1-pixel triangle wastes ≥75% of lanes. Compute rasterizes a cluster per wave with tiny loops and atomic writes, no helper lanes. Silicon speed is irrelevant when it's mostly idle.
9. The error bound must hold for the *nearest* point of the cluster's bounding volume; the center under-estimates projected error for large clusters.
10. Stitching needs per-pair logic between all LOD combos and a runtime neighbour check; locking trades simplification quality (borders stay dense) for zero runtime coordination.
11. Parent could be selected together with its child or neither selected; overlaps and holes (my ablation: 50/3000 random views broken).
12. Fewer clusters/less culling overhead but coarser culling granularity, bigger overdraw waste, and visibility-ID bits change. meshoptimizer's 256v/128t experiment hints larger vertex budgets help simplification.
13. Dense layered or disconnected sheets (foliage cards, hair): simplification can't remove triangles without changing coverage, so projected error stays small and the cut stays fine.
14. Culling uses original bounds; WPO moves vertices outside them; the cluster is culled while visible. Max WPO distance expands bounds.
15. Camera sweeping fast through high-detail areas with more distinct visible pages than the pool holds; evict/reload loop.
16. Same idea: ~1 texel/triangle per pixel, streamed on demand, with feedback of what's needed; geometry's hard part is that topology must stay watertight.
17. Same hierarchical cluster selection by projected footprint; but splats have no shared borders so seams are hidden by opacity blending (LODGE) rather than locked vertices.
18. Open: needs coverage-preserving aggregate representation (voxels, impostors, learned) plus shadow-consistent proxy; Epic's voxel approach is one answer.
19. Open/partly: visibility-buffer forward variants exist in research/engines but Nanite as shipped requires deferred; the mobile support gap is open.

</details>

## 15. Go deeper next

1. Mesh shaders + work graphs: how GPUs self-schedule geometry.
2. Virtual shadow maps: why Nanite and VSM are co-designed.
3. 3D Gaussian splatting level-of-detail and streaming.

## Sources

**Papers / talks**
- Karis, "A Deep Dive into Nanite Virtualized Geometry," SIGGRAPH 2021 Advances (not fetched, too large): https://advances.realtimerendering.com/s2021/Karis_Nanite_SIGGRAPH_Advances_2021_final.pdf
- Garland & Heckbert 1997: https://publications.ri.cmu.edu/surface-simplification-using-quadric-error-metrics
- Yoon et al., Quick-VDR: https://gamma.cs.unc.edu/QVDR/QVDR-vis.pdf
- CuRast: https://arxiv.org/abs/2604.21749
- Virtualized 3D Gaussians: https://arxiv.org/abs/2505.06523
- LODGE: https://arxiv.org/abs/2505.23158
- DGF (not verified): https://dl.acm.org/doi/10.1145/3675383
- GDC 2024 Nanite GPU-Driven Materials (not fetched): https://media.gdcvault.com/gdc2024/Slides/GDC+slide+presentations/Nanite+GPU+Driven+Materials.pdf

**Docs / code**
- Epic, Nanite technical details: https://dev.epicgames.com/documentation/unreal-engine/nanite-technical-details
- Epic, Nanite foliage: https://dev.epicgames.com/documentation/unreal-engine/nanite-foliage
- Epic, Nanite overview: https://dev.epicgames.com/documentation/unreal-engine/nanite-virtualized-geometry-in-unreal-engine
- NVIDIA RTX Mega Geometry: https://developer.nvidia.com/blog/nvidia-rtx-mega-geometry-now-available-with-new-vulkan-samples/
- meshoptimizer: https://github.com/zeux/meshoptimizer ; discussion #750: https://github.com/zeux/meshoptimizer/discussions/750
- Bevy virtual geometry: https://jms55.github.io/posts/2024-06-09-virtual-geometry-bevy-0-14/

**Articles (secondary, quality varies)**
- https://www.elopezr.com/a-macro-view-of-nanite/
- https://jglrxavpok.github.io/2024/04/02/recreating-nanite-runtime-lod-selection.html
- https://traceyang.com/en/2026/06/11/nanite-end-to-end-pipeline-walkthrough-qa/
- https://trickybitsblog.github.io/2024/04/20/nanite.html
- https://www.sctheblog.com/blog/nanite-materials-notes/
- https://courses.grainger.illinois.edu/CS418/sp2023/text/nanite.html
- https://80.lv/articles/discussing-the-possibilities-and-drawbacks-of-unreal-engine-5-s-nanite
- https://crdg.jp/studio-tech-1/en/2025/05/29/3338/
