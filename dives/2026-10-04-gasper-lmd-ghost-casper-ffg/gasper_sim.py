"""Toy Gasper experiments (pure Python, stdlib only).

1. LMD-GHOST: latest-message-driven head selection + proposer boost.
2. Balancing attack: adversary keeps two branches tied; proposer boost breaks the tie.
3. Inactivity leak: epochs until the online set regains >2/3 of stake.

Simplified on purpose: weights are unit votes, no committees, no networking.
Constants mirror the consensus spec where noted.
"""

from collections import defaultdict

# ---------------------------------------------------------------- 1. fork choice

class Block:
    def __init__(self, root, parent, slot):
        self.root, self.parent, self.slot = root, parent, slot


class Store:
    def __init__(self, n_validators):
        self.blocks = {"G": Block("G", None, 0)}
        self.latest = {}            # validator -> (slot, block root)  (LMD: only the latest)
        self.weight_of = {v: 1 for v in range(n_validators)}
        self.boost_root = None
        self.boost_weight = 0

    def add_block(self, root, parent, slot):
        self.blocks[root] = Block(root, parent, slot)

    def vote(self, v, slot, root):
        old = self.latest.get(v)
        if old is None or slot > old[0]:           # newer message replaces older one
            self.latest[v] = (slot, root)

    def children(self, root):
        return [b.root for b in self.blocks.values() if b.parent == root]

    def is_ancestor(self, anc, node):
        while node is not None:
            if node == anc:
                return True
            node = self.blocks[node].parent
        return False

    def weight(self, root):
        # a vote for a descendant counts for every ancestor (subtree weight)
        w = sum(self.weight_of[v] for v, (_, r) in self.latest.items()
                if self.is_ancestor(root, r))
        if self.boost_root and self.is_ancestor(root, self.boost_root):
            w += self.boost_weight
        return w

    def head(self):
        node = "G"
        while True:
            kids = self.children(node)
            if not kids:
                return node
            # spec tiebreak: (weight, root) lexicographic
            node = max(kids, key=lambda r: (self.weight(r), r))


def demo_latest_message():
    s = Store(4)
    s.add_block("A", "G", 1)
    s.add_block("B", "G", 1)
    for v in (0, 1, 2):
        s.vote(v, 1, "A")
    s.vote(3, 1, "B")
    print("head with 3 votes A vs 1 vote B :", s.head())
    for v in (0, 1, 2):                       # same validators now vote B in a later slot
        s.vote(v, 2, "B")
    print("after latest messages move to B  :", s.head(), "(old votes for A are gone)")


# ------------------------------------------------- 2. balancing attack vs boost

def balancing(boost_pct, committee=100, adv_votes=30):
    """One slot's committee (`committee` unit votes) is split by the adversary's network
    trick: honest voters sit 50/50 on forks A and B, and `adv_votes` withheld adversary
    votes are released for B. B leads by adv_votes. The next honest proposer saw A,
    builds A2 on it, and A2 arrives timely, so A2 earns the proposer boost.
    Spec: boost = committee_weight * PROPOSER_SCORE_BOOST // 100 (40)."""
    honest = committee - adv_votes
    s = Store(committee)
    s.add_block("A", "G", 1)
    s.add_block("B", "G", 1)
    for v in range(honest // 2):
        s.vote(v, 1, "A")
    for v in range(honest // 2, honest):
        s.vote(v, 1, "B")
    for v in range(honest, committee):         # adversary releases withheld votes: B ahead
        s.vote(v, 1, "B")
    before = s.head()
    s.add_block("A2", "A", 2)
    s.boost_root = "A2"
    s.boost_weight = committee * boost_pct // 100
    return before, s.head(), s.boost_weight


def demo_boost():
    print("committee=100 votes; adversary withholds k votes, releases for B; honest A2 timely")
    print(f"{'k':>4} {'boost':>6} {'before':>7} {'after':>6}  honest chain wins?")
    for k in (10, 30, 39, 41):
        for pct in (0, 40):
            before, after, bw = balancing(pct, adv_votes=k)
            print(f"{k:>4} {pct:>5}% {before:>7} {after:>6}  {'yes' if after.startswith('A') else 'no'}")
    print("boost (40) beats any adversary holding < 40% of one slot's committee; 0% never does")


# --------------------------------------------------------- 3. inactivity leak

INACTIVITY_SCORE_BIAS = 4
INACTIVITY_PENALTY_QUOTIENT = 2 ** 24      # Bellatrix+ ; leak per epoch = bal*score / (4 * 2^24)
EJECTION_BALANCE = 16.0


def leak(offline_frac, start_balance=32.0, max_epochs=20000):
    """Epochs until online stake > 2/3 of total remaining stake, when `offline_frac`
    of validators never attest. Online scores stay 0; offline score += 4 each epoch."""
    n_on = 1000 * (1 - offline_frac)
    n_off = 1000 * offline_frac
    bal_off, score = start_balance, 0
    for epoch in range(1, max_epochs):
        if epoch > 4:                         # leak starts after MIN_EPOCHS_TO_INACTIVITY_PENALTY
            score += INACTIVITY_SCORE_BIAS
            bal_off -= bal_off * score / (INACTIVITY_SCORE_BIAS * INACTIVITY_PENALTY_QUOTIENT)
        if bal_off <= EJECTION_BALANCE:
            n_off_eff = 0                     # ejected at 16 ETH effective balance
        else:
            n_off_eff = n_off
        on, off = n_on * start_balance, n_off_eff * bal_off
        if on * 3 >= (on + off) * 2:
            return epoch, bal_off, score
    return None, bal_off, score


def demo_leak():
    print(f"{'offline':>8} {'epochs':>8} {'days':>7} {'offline bal':>12} {'ETH lost':>9}")
    for f in (0.34, 0.40, 0.50, 0.60):
        ep, bal, sc = leak(f)
        print(f"{f:>8.0%} {ep:>8} {ep * 6.4 / 60 / 24:>7.1f} {bal:>12.2f} {32 - bal:>9.2f}")


if __name__ == "__main__":
    print("== 1. LMD latest message ==")
    demo_latest_message()
    print("\n== 2. proposer boost vs thin lead ==")
    demo_boost()
    print("\n== 3. inactivity leak ==")
    demo_leak()
