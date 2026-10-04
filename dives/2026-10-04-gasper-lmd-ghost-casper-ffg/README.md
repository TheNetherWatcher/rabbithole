# Ethereum Gasper: LMD-GHOST fork choice + Casper FFG finality

**Blockchain · Consensus · Gasper (LMD-GHOST + Casper FFG), proposer boost, reorg attacks, single-slot finality · Depth: hard · 2026-10-04**

> Verification note: constants below were checked against `ethereum/consensus-specs` (phase0 `beacon-chain.md`, `fork-choice.md`). Items marked **(unverified)** came from a single secondary source or conflicting research notes.

---

## 0b. Plain English first

**Explain it simply.** Imagine ~900,000 people who all have to agree on one shared notebook, and nobody is in charge. Every 12 seconds one person is randomly picked to write the next page. Sometimes two pages get written at once, or a page arrives late, so the notebook briefly has two versions. Gasper is the rulebook for (1) which version to *follow today*, and (2) when a page is so firmly agreed that *throwing it away would cost cheaters a fortune*.

Part one is **LMD-GHOST**: "follow the version most people most recently pointed at." Part two is **Casper FFG**: every ~6 minutes, people sign a public statement "I agree this page is part of history." If two-thirds of everyone signs, the page is *justified*; one more round of two-thirds on top and it is *finalized*. Anyone who signs two contradictory statements gets caught and loses money, so reversing a finalized page would force at least a third of all people to burn their deposits.

**Everyday example.** A town of 99 voters keeps a "latest news" board. Tuesday noon, the mayor posts "Bridge opens Friday" (page A). A prankster with slow-delivery tricks makes half the town hear about a rival post "Bridge opens Monday" (page B) first. Town splits 49/49 with two undecided wildcards the prankster controls. Each voter's rule: *"point at the post most of the town's latest pointers support."* The prankster feeds the wildcards' pointers one at a time to keep it a perfect tie forever, so the town never settles. The fix: whoever posts next gets a **bonus of 40 imaginary votes for the first few seconds** if their post arrives on time. A prompt honest post wins and the tie breaks. Every ~6 minutes the town also holds a signed roll call; once two-thirds sign the same post twice in a row, it is carved in stone.

**Bridge:** now the same thing, technically.

---

## 1. Bare-minimum context

- **Proof-of-stake**: validators lock 32 ETH (up to 2048 post-Pectra, EIP-7251); voting power = *effective balance*. [ethereum.org](https://ethereum.org/developers/docs/consensus-mechanisms/pos/)
- **Slot = 12 s, epoch = 32 slots = 6.4 min.** One proposer per slot; every active validator attests once per epoch, spread across slots via committees. [eth2book](https://eth2book.info/latest/part3/config/preset/)
- **Committees**: validators shuffled each epoch into ≤64 committees/slot of ≈128 (`TARGET_COMMITTEE_SIZE = 128`).
- **BFT thresholds**: tolerate < 1/3 Byzantine stake; 2/3 supermajorities intersect in > 1/3.
- **Slashing**: provable equivocation burns stake.
- **Partial synchrony**: messages arrive within an unknown bound Δ; **dynamic availability**: protocol keeps going when many validators go offline.

## 1b. Real-world context

**What it is.** The consensus protocol of Ethereum's Beacon Chain since the Merge (Sept 2022). A *fork-choice rule* (LMD-GHOST) picks a head so liveness never stalls; a *finality gadget* (Casper FFG) layered on checkpoints gives economic irreversibility. Formalized as "Gasper" by Buterin et al., [arXiv 2003.03052](https://arxiv.org/abs/2003.03052).

**Why it exists.** Tendermint-style BFT halts if ≥1/3 are offline and needs all-to-all voting rounds per block, which does not scale to ~10^5–10^6 validators with open, dynamic membership. Gasper keeps the chain *growing* whenever anyone is online (availability) and adds finality as an overlay that can stall without killing the chain. Cost of not having it: reorg-able chain, or a chain that halts.

**Where it's used.**
- **Ethereum mainnet**: ~0.9M active validators, ~39M ETH staked (secondary sources, **unverified** figures).
- **Consensus clients**: Lighthouse (Rust), Prysm (Go), Teku (Java), Nimbus (Nim), Lodestar (TS), Grandine (Rust); each implements the same spec fork choice.
- **Execution clients** (Geth, Nethermind, Besu, Erigon, Reth) take `safe`/`finalized` block tags from it; exchanges and bridges wait for `finalized`.
- **Gnosis Chain** runs an adaptation of the same beacon-chain design.
- **L2 rollups** (Optimism, Arbitrum, Base) derive "finalized" L1 status from it.
- **Staking pools / restaking** (Lido, EigenLayer) are slashed by its rules.

**How it's used.** A practitioner touches the Beacon API:

```bash
# checkpoints (justified / finalized)
curl -s localhost:5052/eth/v1/beacon/states/head/finality_checkpoints | jq
# whole fork-choice tree with weights (debug)
curl -s localhost:5052/eth/v1/debug/fork_choice | jq '.fork_choice_nodes | length'
# start a node from a recent finalized state instead of genesis (weak subjectivity)
lighthouse bn --checkpoint-sync-url https://<trusted-beacon-api>
```

JSON-RPC lets dapps ask for `eth_getBlockByNumber("finalized")` or `"safe"`. Typical rule: exchanges credit deposits at `finalized` (~13 min); wallets show `latest` (head).

**When to use / not.** Wait for `finalized` when value at risk > cost of ~13 min; use `safe` (justified) for mid-latency; `latest` only for UX. Gasper itself is not something you "choose", but the design choice recurs: if you need sub-second finality, you want BFT (Tendermint/CometBFT) with a small validator set, and you accept halting.

**Who should care.** Node operators (missed attestations, slashing, client diversity), MEV/builder teams (reorg windows), bridge/exchange/rollup engineers (finality semantics), protocol researchers.

---

## 2. The one-liner and what it hides

*"Gasper = LMD-GHOST for the head + Casper FFG for finality."* Hides:

1. FFG votes carry **two** roles: a finality link *and* a GHOST head vote; the two layers are coupled by a *filter* on the block tree.
2. "Latest message" means old votes are **overwritten**, which is exactly what makes balancing/bouncing attacks possible.
3. Finality is **economic**, not cryptographic: it needs ≥1/3 of stake slashable (accountable safety), and only works if slashing is detectable within the weak-subjectivity period.
4. The head rule has **no safety proof for sub-1/3 adversaries**: the fixes (proposer boost, equivocation discounting) are patches.
5. Under >1/3 offline, finality stops; the **inactivity leak** bleeds offline stake until 2/3 is restored (days).

## 3. The problem

Nakamoto longest-chain gives availability but only probabilistic finality; classical BFT gives deterministic finality but halts at 1/3 offline and costs O(n²) messages. Ethereum needed: ~10^5+ validators, open set, chain never halts, *and* a hard finality guarantee with slashing. Numbers: 12 s slots; one vote per validator per epoch (~900k votes / 32 slots ≈ 28k attestations per slot after committee split); at 2 epochs to justify + finalize, normal finality ≈ 2 epochs after the target epoch begins, ~12.8-19 min (64–95 slots per 3-Slot paper).

## 4. Mental model

A **river with a stone bridge being built**: LMD-GHOST is the floating raft you steer toward the strongest current (most recent votes); FFG periodically drives a stone pier (checkpoint) into the riverbed once two-thirds sign off. The raft may drift between piers; it can never cross a pier. **Where it breaks:** the raft is steered by *latest* currents, so a patient adversary can manipulate which current is "latest" at the moment it matters; piers also only get built if two-thirds are paying attention.

## 5. The mechanism, traced

Trace epoch *e*, one honest validator *v* (balance 32 ETH), 900,000 validators.

```
slot 0 of epoch e   (t=0s)    proposer P builds block B_e on head H
t = 0..4s                      attesters in slot's committee wait for B_e (deadline 4s = 1/3 slot)
t = 4s                         v signs AttestationData:
   { slot, index, beacon_block_root = B_e,           <- LMD-GHOST head vote
     source = justified checkpoint (epoch e-1, root S),
     target = (epoch e, root of epoch-boundary block) }  <- FFG vote (S -> T link)
t = 4..8s                      aggregators (selected by hash of slot signature) aggregate BLS sigs
t = 8s                         aggregates broadcast; next proposer includes them
epoch end                      process_epoch: sum balances with target==T;
                               if 3*target_balance >= 2*total_active_balance: justify T
                               if justified(e-1) and justified(e) consecutive: finalize e-1 (rules 1-4)
```

**FFG: one attestation = one supermajority-link vote** (source → target). Justification (spec `weigh_justification_and_finalization`): `previous_epoch_target_balance * 3 >= total_active_balance * 2`. Finalization needs a justified checkpoint C whose *direct child* checkpoint is also justified via a link from C (4 patterns over the last four epochs).

**LMD-GHOST head** (spec `get_head`, simplified):

```python
def get_head(store):
    blocks = get_filtered_block_tree(store)       # drop branches whose leaf state disagrees with
    head = store.justified_checkpoint.root        #   store's justified/finalized checkpoints
    while True:
        children = [r for r in blocks if blocks[r].parent_root == head]
        if not children: return head
        head = max(children, key=lambda r: (get_weight(store, r), r))   # weight, then root as tiebreak

def get_weight(store, root):
    state = store.checkpoint_states[store.justified_checkpoint]
    score = sum(state.validators[i].effective_balance
                for i in active_unslashed(state)
                if i in store.latest_messages and i not in store.equivocating_indices
                and get_ancestor(store, store.latest_messages[i].root, store.blocks[root].slot) == root)
    if store.proposer_boost_root != Root() and get_ancestor(store, store.proposer_boost_root, slot_of(root)) == root:
        score += (total_active_balance // SLOTS_PER_EPOCH) * PROPOSER_SCORE_BOOST // 100   # = 40% of one slot's committee
    return score
```

A vote for block X counts for X and *every ancestor* (subtree weight). Only the **latest** message per validator counts.

**Proposer boost**: if a block arrives for the current slot **before the attesting interval** (4 s) and is the first such block (and has the same shuffling-dependent root as the head), `store.proposer_boost_root` is set; reset on the next slot. Spec constant `PROPOSER_SCORE_BOOST = 40` (percent of one slot's committee weight).

**Real clients**: instead of walking the tree each time, **proto-array** (Lighthouse, Prysm, Teku, Nimbus, Lodestar) stores nodes in a flat vec in insertion (parent-before-child) order and applies weight *deltas* in one backward pass: `apply_score_changes` updates each node's weight and bubbles deltas to the parent; each node caches `best_child`/`best_descendant`, so head lookup is O(1) after a pass that is O(N) in nodes (N pruned at finalization). (The research notes claimed O(log n); that is wrong: it is an O(N) linear pass, O(1) lookup.)

## 6. The math

**Supermajority and accountable safety.** Let total stake = *n*. A supermajority link has ≥ 2n/3 stake. Two conflicting finalized checkpoints need two sets V₁, V₂ each with ≥ 2n/3; by inclusion–exclusion |V₁ ∩ V₂| ≥ 2n/3 + 2n/3 − n = n/3. Validators in the intersection signed *both* links. Claim (Casper FFG): any such overlap violates a slashing condition:

- **Double vote:** `data_1 != data_2 and data_1.target.epoch == data_2.target.epoch`
- **Surround vote:** `data_1.source.epoch < data_2.source.epoch and data_2.target.epoch < data_1.target.epoch`

→ in plain terms: you cannot sign two different statements about the same epoch, or a statement that "wraps" an earlier one, without a witness being able to prove it. So ≥ n/3 stake is provably guilty (*accountable safety*). Why 2/3 and not 1/2: with 1/2, intersection could be empty; 2/3 is the smallest threshold giving a *non-empty-by-a-third* intersection robust to f < n/3 faults while keeping liveness (n − f ≥ 2n/3 honest can still reach it).

**Why finalization needs two rounds, not one.** Justification alone only says "2/3 voted source→target"; a later conflicting justification could exist built from different sources without overlap violations. Finality of C requires a link C → C' with C justified, so that *any* conflicting justified checkpoint would need a link that surrounds or double-votes with C → C'. → in plain terms: the second round stops honest validators from being asked to sign something that contradicts an already-justified thing.

**Inactivity leak.** Spec: each epoch of non-finality (after 4), offline validator's inactivity score `s += INACTIVITY_SCORE_BIAS (=4)`; penalty per epoch `balance * s / (INACTIVITY_SCORE_BIAS * INACTIVITY_PENALTY_QUOTIENT_BELLATRIX)` with quotient 2²⁴ = 16,777,216 (phase0 launch value 2²⁶ = 67,108,864; **quotient value checked for phase0 only; Bellatrix+ value from eth2book notes**).
Score grows linearly in time t (s ≈ 4t), penalty rate ∝ s → balance decays as B(t) ≈ B₀ · exp(−t²/(2·2²²)) *(since dB/dt = −B · 4t / (4·2²⁴) = −B·t / 2²⁴ → B = B₀ e^(−t²/(2·2²⁴)))*. Solving for a halving: t ≈ √(2·2²⁴·ln 2) ≈ 4,800 epochs ≈ 21 days (matches toy sim below at the 16 ETH ejection point).
→ in plain terms: loss is *quadratic* in outage length. A 1-hour outage costs nearly nothing; 3 weeks costs half the stake. Quadratic form (not linear) is chosen so short outages are cheap but a long attack is ruinous, and so the offline fraction drops fast enough to recover finality in weeks, not years.

**Proposer boost threshold.** Boost weight W_b = 0.4·W_c (W_c = one slot's committee weight). A timely honest block's branch overtakes a withheld-vote lead L iff W_b > L. So a balancing adversary needs to hold ≥ 40% of a slot's committee; at adversary fraction β of total stake, expected adversarial votes in a committee ≈ β·W_c, so boost beats it when β < 0.4 (in the idealized model; the research notes say it is "designed for ~20%" because real attacks use multi-slot sandwiches, see §9).

## 7. Why it works

- **Safety (FFG):** 2/3 quorums intersect in ≥1/3, and intersection = slashable. Remove surround rule → attacker can finalize conflicting checkpoints by "wrapping" with no double vote. Remove double-vote rule → trivially sign both forks.
- **Availability (LMD-GHOST):** the head never depends on 2/3 participation; any online subset keeps extending.
- **Coupling:** the filter ensures the head follows the *latest justified checkpoint*, so honest validators following fork choice never produce slashable votes (this was the bug class behind "unrealized justification" fixes).
- **Latest message** keeps state O(#validators) rather than O(votes ever).
- Ablation: no proposer boost → balancing attack with a handful of validators per slot (§9). No equivocation discounting → avalanche attack. No inactivity leak → >1/3 offline halts finality forever.

## 8. Design knobs & alternatives

| Knob | Value | Trade |
|---|---|---|
| Slot / epoch | 12 s / 32 slots | shorter slots → more P2P load; shorter epochs → fewer aggregates per checkpoint, less safety margin |
| Committee size | 128 target | smaller = cheaper aggregation, weaker per-slot sampling |
| Proposer boost | 40% | higher → proposer can reorg more easily (ex-post reorg); lower → balancing attack |
| Effective balance cap | 32 → 2048 ETH (EIP-7251) | fewer validators (less P2P/BLS cost), fatter slashing risk per key |
| Weak-subjectivity period | ~ weeks, scales with validator churn | shorter = more social trust |

Alternatives: Tendermint/CometBFT (BFT, halts), GRANDPA+BABE (finalizes *chains*), Algorand BA★, Avalanche. Gasper's selling point: the head layer and finality layer degrade independently (an "ebb-and-flow protocol", Neu–Tas–Tse, [arXiv 2009.04987](https://arxiv.org/abs/2009.04987)).

## 9. Where it breaks

- **Balancing attack** (Neu–Tas–Tse 2021): adversary with a few % of stake per slot withholds votes, releases to keep two forks tied under LMD-GHOST ⇒ liveness lost. *Mitigation: proposer boost (2021–22)*.
- **Bouncing attack** (2019): withheld votes make justification alternate between forks; patched by only updating the justified checkpoint early in the epoch (the old `SAFE_SLOTS_TO_UPDATE_JUSTIFIED`, now removed from the spec in favor of the unrealized-justification design (spec check: constant absent from current `fork-choice.md`)).
- **Ex-ante / sandwich reorgs** (Schwarz-Schilling et al., [IACR 2021/1413](https://eprint.iacr.org/2021/1413)): adversary controlling consecutive proposals reorgs honest blocks by *pre-committing* in a way proposer boost (within-slot only) cannot stop.
- **Avalanche attack**: reuse of withheld blocks via equivocation; fixed by *equivocation discounting* (`equivocating_indices` excluded from weights).
- **Commitment attacks** (2024, [arXiv 2407.19479](https://arxiv.org/abs/2407.19479)): proposer coerces prior-slot attesters with reward threats; mitigation unresolved.
- **Client bugs / finality delays**: May 2023 two finality delays (11–12 May) under load (conflicting notes: one source also says May 2024 Prysm bug — **unverified, treat the year as 2023 until confirmed**); client concentration is a systemic risk.
- **MEV timing games**: proposers delay publishing to extract more MEV; risk of more missed slots/reorgs.
- **Misconception:** "finalized = cryptographically final." It's final unless ≥1/3 stake is willing to burn, and weak subjectivity means a new node can be fed a bogus checkpoint.

## 10. In the wild

- Clients implement spec fork choice via **proto-array** (Lighthouse, Prysm, Teku, Nimbus, Lodestar); fork-choice compliance test vectors live in `ethereum/consensus-specs`.
- Spec adds **proposer reorg** logic (`REORG_HEAD_WEIGHT_THRESHOLD = 20`, `REORG_PARENT_WEIGHT_THRESHOLD = 160`, `REORG_MAX_EPOCHS_SINCE_FINALIZATION = 2`): a proposer may deliberately build on the parent of a weak late block (reorging an unattested head).
- **MEV-Boost**: ~90% of blocks come from external builders; fork choice is oblivious, but timing games stress the 4 s attestation deadline.
- **Checkpoint sync** replaces genesis sync (weak subjectivity in practice).
- **EIP-7251 (Pectra, May 2025)** consolidates validators to cut P2P load.

## 11. Frontier (what's new)

Verified items marked ✓ (fetched); others are from research-agent notes, to be treated as leads.

| Year | Item | Contribution | Link |
|---|---|---|---|
| 2024 ✓ | *3-Slot-Finality Protocol for Ethereum* (D'Amato, Saltini, Tran, Zanolini) | partially synchronous finality gadget over a dynamically-available chain; finality within 3 slots vs 64–95 today (PODC 2024 per agent notes; arXiv page itself lists cs.DC) | [arXiv 2411.00558](https://arxiv.org/abs/2411.00558) |
| 2024 | *Towards Single Slot Finality* | evaluates protocols for SSF using single-vote total-order broadcast | [arXiv 2406.09420](https://arxiv.org/abs/2406.09420) |
| 2024 | *A Fast Confirmation Rule for the Ethereum Consensus Protocol* | confirm blocks within a slot, backward compatible with FFG | [arXiv 2405.00549](https://arxiv.org/abs/2405.00549) |
| 2025 ✓ | *Available Attestation: Towards a Reorg-Resilient Solution for Ethereum PoS* (Zhang, Li, Lu, Duan; USENIX Security 2025) | replaces HLMD-GHOST with a stable-chain rule; secure against known reorg attacks in synchrony (agent claims EIP-7942 + Glamsterdam consideration: **unverified**; the paper does not mention EIP-7942) | [IACR 2025/097](https://eprint.iacr.org/2025/097) |
| 2025–26 | *SoK: Speedy Secure Finality* | survey Goldfish → RLMD-GHOST → 3SF | [arXiv 2512.20715](https://arxiv.org/abs/2512.20715) |
| 2026 | *Majorum: Ebb-and-Flow Consensus with Dynamic Quorums* | 3-slot finality with one voting phase per slot | [arXiv 2601.03862](https://arxiv.org/abs/2601.03862) |
| 2026 | *Wonderboom* | million-scale signature aggregation | [arXiv 2602.06655](https://arxiv.org/abs/2602.06655) |
| 2024 | Orbit SSF | validator-set sampling for SSF with solo-staker friendliness | [ethresear.ch](https://ethresear.ch/t/orbit-ssf-solo-staking-friendly-validator-set-management-for-ssf/19928) |
| 2025–26 | Lean Ethereum / Minimmit | one-round BFT replacing Gasper; slot compression; post-quantum signatures (leanXMSS) — research, no fork assigned | [blog.ethereum.org](https://blog.ethereum.org/2025/07/31/lean-ethereum), [Commonware](https://commonware.xyz/blogs/minimmit) |

Upgrades touching consensus: Pectra (May 2025; MaxEB), Fusaka (Dec 2025; PeerDAS), Glamsterdam (planned; ePBS EIP-7732 with Payload Timeliness Committee, which alters proposer-boost semantics). All dates from agent notes; Pectra/Fusaka dates cross-referenced only once.

## 11b. Open problems

1. **Reorg resilience below 1/3**: LMD-GHOST + boost is not proven reorg-resilient; Available Attestation, view-merge, RLMD-GHOST are candidates. Why hard: any rule using *latest* messages lets withheld votes act later.
2. **Availability–finality dilemma** (Neu–Tas–Tse): impossible to have dynamic participation *and* safety under partitions simultaneously; ebb-and-flow is the best known compromise. SSF designs trade fault tolerance (some proposals discuss < 1/3 thresholds) for latency.
3. **Ex-ante reorg/MEV during the 13-min window**: removing it needs SSF/3SF, which raise message load (aggregation: Orbit, Wonderboom).
4. **Timing games & rational incentives**: delaying publication is individually profitable; no protocol-level equilibrium fix. Prevalence numbers in the notes (62.8% / 28.8%) are **unverified/contested**.
5. **Weak subjectivity**: social-layer trust remains; unresolved how to make it objective.
6. **Correlation penalty adequacy** (2024 critique) — theoretical, no live exploit known.
7. **Post-quantum**: BLS aggregation is not PQ-secure; hash-based aggregation (leanXMSS+STARKs) is research.

## 12. Lineage

GHOST (Sompolinsky–Zohar 2013) → Casper FFG (Buterin–Griffith 2017, [1710.09437](https://arxiv.org/abs/1710.09437)) → Gasper (2020, [2003.03052](https://arxiv.org/abs/2003.03052)) → ebb-and-flow analysis (2020) → proposer boost + equivocation discounting (2021–23) → Goldfish/RLMD-GHOST/view-merge (2022–23) → 3-slot finality (2024) → Lean consensus / Minimmit (2025+).

## 13. Hands-on (≤30 min)

`gasper_sim.py` (stdlib Python) in this folder:

```bash
python3 gasper_sim.py
```

Observed output:

1. **LMD latest message:** 3 votes A vs 1 B → head A; after the 3 validators' *latest* messages move to B, head flips to B.
2. **Proposer boost threshold (toy):** committee=100 votes; adversary releases k withheld votes for B. With 40% boost the timely honest block's branch wins for k=10, 30; at k=39 B's lead is 40 (honest split 30/31 plus 39 adversary votes), exactly equal to the boost, so the tie goes to B by root-name tiebreak; k=41 loses outright. With 0% boost it never wins. Boost beats adversaries holding fewer than ~40% of one committee.
3. **Inactivity leak:** 34% offline → 1,005 epochs (4.5 days, 0.94 ETH lost each); 40% → 3,111 epochs (13.8 d, 8 ETH); 50%/60% → ejection at 16 ETH after 4,826 epochs (21.4 d). Caveat: toy model, uniform offline validators, ejection at exactly 16 ETH balance, bias 4 and quotient 2²⁴.

Extension: query a real beacon node with the `curl` commands in §1b and watch `finalized.epoch` lag `current_justified.epoch` by 1–2.

## 14. Question ladder

**Mechanism**
1. Walk through what a single attestation commits to (which fields serve FFG, which serve LMD-GHOST).
2. When exactly does a checkpoint become justified, and when finalized?
3. How does a vote for block X contribute to weight of its ancestors?
4. What does `filter_block_tree` remove and why?
5. When is proposer boost applied and when is it reset?

**Why**
6. Why 2/3 and not 1/2 or 3/4?
7. Why does finalization need *two* justified consecutive checkpoints?
8. Why is the inactivity leak quadratic?
9. Why only the *latest* message per validator?

**Counterfactual**
10. Remove the surround-vote rule: describe an attack.
11. Remove proposer boost: describe a balancing attack.
12. Double the committee size: what changes?
13. Make boost 100%: what attack opens?

**Adversarial**
14. How does an adversary with 20% stake try to prevent finality?
15. Why does proposer boost fail against ex-ante reorgs?
16. How could a long-range attacker rewrite history and what stops a new node from believing it?

**Connection**
17. How does ebb-and-flow relate to the CAP theorem?
18. How is Gasper's finality different from Tendermint's?
19. What does ePBS change for the fork choice?

**Open**
20. Can finality be single-slot without losing 1/3 fault tolerance at 10^6 validators?
21. Is there a reorg-resilient, dynamically available protocol that survives asynchrony?

<details><summary>Answers</summary>

1. `beacon_block_root` = LMD-GHOST head vote; `source` and `target` checkpoints = FFG link; `slot`/`index` locate the committee.
2. Justified when ≥2/3 of total active balance attests the same target in the epoch (processed at epoch boundary); finalized when a justified checkpoint's next epoch's checkpoint is also justified via a link from it (4 rules over the last 4 epochs).
3. Subtree weight: the weight of a node is the sum of effective balances of validators whose latest message points at the node *or any descendant*.
4. Drops branches whose leaf state's justified/finalized checkpoints are inconsistent with the store, so head never follows a chain that would force a slashable vote.
5. Applied when the block for the current slot is first seen before the 4 s attesting interval (plus same dependent-root condition); reset at the next slot tick.
6. 2/3 is the minimum quorum such that two quorums intersect in ≥ 1/3 (accountability) while f < 1/3 faults still permit a quorum (liveness).
7. So that no honest validator can be driven by fork choice into signing a link that contradicts an already-justified checkpoint without being slashable themselves; a one-round rule leaves a gap with conflicting justifications.
8. Score grows linearly, penalty ∝ score, so loss ∝ t²: short outages are cheap, long ones ruinous.
9. Bounded state and recency; the cost is that old votes can be overwritten, enabling balancing/bouncing.
10. Adversary (≥1/3) signs A→B (wide) and later a nested C→D inside it; both finalize on conflicting forks with no double vote.
11. Split honest votes with delayed delivery; release withheld votes each slot to keep a tie, no block ever gets decisive weight.
12. More aggregation cost, better per-slot sampling of the validator set; shifts attack thresholds.
13. A single proposer can force the weight of its (possibly late, adversarial) block over a majority of attestations: a cheap ex-post reorg of honest blocks.
14. Stay online but withhold and release votes to bounce justification or balance forks; needs ~<1/3 but exploits LMD.
15. Boost is slot-local; an ex-ante adversary controls the next slot's proposer too and pre-arranges votes across slots.
16. Slashing penalties do not apply to exited validators; weak-subjectivity checkpoints (social consensus) tell a new node which history to follow.
17. Under partition you must choose availability (chain grows, no finality) or consistency (halt); ebb-and-flow exposes both views.
18. Gasper finality is economic and delayed (~2 epochs); Tendermint is immediate but halts when ≥1/3 are offline.
19. In-protocol builders; the Payload Timeliness Committee votes on payload reveal; fork choice weights must account for payload status; proposer boost semantics change.
20. Open: message load for 10^6 signers per slot (hence Orbit/Wonderboom/Minimmit), and thresholds below 1/3 are discussed.
21. Open: Goldfish is secure in sync but brittle to asynchrony; RLMD-GHOST trades vote expiry for asynchrony resilience.

</details>

## 15. Go deeper next

1. **RLMD-GHOST / view-merge / Goldfish**: vote expiry as a reorg-resilience knob.
2. **BLS12-381 aggregate signatures and the aggregation subnet P2P layer** (what limits validator count).
3. **ePBS (EIP-7732) and the Payload Timeliness Committee**.

## Sources

**Papers:** [Gasper 2003.03052](https://arxiv.org/abs/2003.03052) · [Casper FFG 1710.09437](https://arxiv.org/abs/1710.09437) · [Ebb-and-flow 2009.04987](https://arxiv.org/abs/2009.04987) · [Three Attacks 2021/1413](https://eprint.iacr.org/2021/1413) · [3SF 2411.00558](https://arxiv.org/abs/2411.00558) · [SSF 2406.09420](https://arxiv.org/abs/2406.09420) · [Fast Confirmation 2405.00549](https://arxiv.org/abs/2405.00549) · [Available Attestation 2025/097](https://eprint.iacr.org/2025/097) · [SoK Speedy Secure Finality 2512.20715](https://arxiv.org/abs/2512.20715) · [Majorum 2601.03862](https://arxiv.org/abs/2601.03862) · [Wonderboom 2602.06655](https://arxiv.org/abs/2602.06655) · [Commitment attacks 2407.19479](https://arxiv.org/abs/2407.19479) · [RLMD-GHOST 2302.11326](https://arxiv.org/abs/2302.11326)

**Code/docs:** [consensus-specs fork-choice.md](https://github.com/ethereum/consensus-specs/blob/master/specs/phase0/fork-choice.md) · [beacon-chain.md](https://github.com/ethereum/consensus-specs/blob/master/specs/phase0/beacon-chain.md) · [eth2book fork choice](https://eth2book.info/latest/part3/forkchoice/) · [eth2book inactivity](https://eth2book.info/latest/part2/incentives/inactivity/) · [ethereum.org Gasper](https://ethereum.org/developers/docs/consensus-mechanisms/pos/gasper/) · [Beacon API debug/fork_choice](https://docs.chainstack.com/reference/getdebugforkchoice) · [Lean Ethereum](https://blog.ethereum.org/2025/07/31/lean-ethereum)

**Articles/forums:** [Orbit SSF](https://ethresear.ch/t/orbit-ssf-solo-staking-friendly-validator-set-management-for-ssf/19928) · [View-merge](https://ethresear.ch/t/view-merge-as-a-replacement-for-proposer-boost/13739) · [Minimmit (Commonware)](https://commonware.xyz/blogs/minimmit) · [Ex-ante reorg note](https://notes.ethereum.org/@casparschwa/HkPjIzUQY) · [Paradigm: MEV-boost and consensus](https://www.paradigm.xyz/writing/mev-boost-ethereum-consensus)
