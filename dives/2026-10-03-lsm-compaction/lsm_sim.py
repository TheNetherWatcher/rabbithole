"""Count-based LSM compaction simulator: measures write amplification and run count
for leveling, tiering, and lazy leveling. Unit = one buffer flush. Insert-only,
unique keys (no dedup), so write amp here is pure merge cost, comparable to
Monkey/Dostoevsky Eq. W (L*(T-1)/2 leveling, L*(T-1)/T tiering)."""
import sys

def simulate(policy, T, L, n_flushes):
    last = L - 1
    runs = [[] for _ in range(L)]          # runs[i] = list of run sizes at level i
    writes = 0
    peak_runs = 0
    for _ in range(n_flushes):
        writes += 1                        # flush buffer -> level 0 run (1 unit)
        cur, i = 1, 0
        while True:
            lvl = runs[i]
            leveled = policy == "leveling" or (policy == "lazy" and i == last)
            if leveled:
                merged = (lvl[0] if lvl else 0) + cur
                if i > 0 or True:
                    writes += merged if lvl else 0   # rewrite existing + incoming
                runs[i] = [merged]
                cap = T ** (i + 1)
                if merged > cap and i < last:        # overflow -> push whole level down
                    cur, runs[i] = merged, []
                    i += 1
                    continue
                break
            else:                                    # tiered level
                lvl.append(cur)
                if len(lvl) >= T:
                    merged = sum(lvl)
                    writes += merged
                    runs[i] = []
                    cur = merged
                    if i < last:
                        i += 1
                        continue
                    runs[i] = [merged]               # last tiered level keeps merged run
                break
        peak_runs = max(peak_runs, sum(len(r) for r in runs))
    return writes / n_flushes, sum(len(r) for r in runs), peak_runs

if __name__ == "__main__":
    T = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    L = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    n = T ** L
    print(f"T={T} L={L} N={n} flushes")
    print(f"{'policy':10} {'write-amp':>10} {'runs@end':>9} {'peak runs':>10} {'theory W':>10}")
    th = {"leveling": L*(T-1)/2, "tiering": L*(T-1)/T, "lazy": (L-1)*(T-1)/T + (T-1)/2}
    for p in ("leveling", "tiering", "lazy"):
        wa, r, pk = simulate(p, T, L, n)
        print(f"{p:10} {wa:10.2f} {r:9d} {pk:10d} {th[p]:10.2f}")
