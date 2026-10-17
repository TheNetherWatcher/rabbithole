#!/usr/bin/env python3
"""Simulate Spectre v1's mistraining + vote-over-rounds logic, without real
hardware (no clflush/rdtscp needed). Models:
  - a 2-bit saturating branch-predictor counter that moves toward "taken"
    (in bounds) on real legal calls and toward "not taken" on real illegal
    (attack) calls -- exactly as a real predictor updates after the branch
    actually resolves, regardless of what it predicted
  - calls interleaved within a round of fixed size (30), attack calls spread
    evenly through the round rather than bunched together
  - the 2*runnerup+5 confidence-margin vote across up to 999 rounds

Shows why the paper's 25:5 (5:1) ratio keeps the predictor saturated enough
to keep firing speculative reads, and what happens if the ratio tips the
other way.
"""
import random

SECRET = 81
NOISE = 0.02
MAX_ROUNDS = 999
CALLS_PER_ROUND = 30


def run_attack(attack_calls, rounds=MAX_ROUNDS, trials=200):
    train_calls = CALLS_PER_ROUND - attack_calls
    stride = max(1, round(CALLS_PER_ROUND / attack_calls)) if attack_calls else CALLS_PER_ROUND + 1
    successes, round_counts, fires_total, calls_total = 0, [], 0, 0

    for _ in range(trials):
        counter = 2           # 0..3 saturating counter, >=2 predicts "in bounds"
        results = [0] * 256
        won, finished_round = False, rounds

        for r in range(1, rounds + 1):
            for c in range(CALLS_PER_ROUND):
                is_attack = attack_calls > 0 and (c % stride == 0) and (c // stride < attack_calls)
                predicted_in_bounds = counter >= 2
                calls_total += 1

                if predicted_in_bounds and is_attack:
                    fires_total += 1
                    idx = SECRET if random.random() > NOISE else random.randrange(256)
                    results[idx] += 1

                # real outcome updates the counter regardless of the prediction
                counter = min(3, counter + 1) if not is_attack else max(0, counter - 1)

            j = max(range(256), key=lambda i: results[i])
            k = max((i for i in range(256) if i != j), key=lambda i: results[i])
            if results[j] >= 2 * results[k] + 5 or (results[j] == 2 and results[k] == 0):
                won = (j == SECRET)
                finished_round = r
                break
        round_counts.append(finished_round)
        if won:
            successes += 1

    avg_rounds = sum(round_counts) / len(round_counts)
    fire_rate = fires_total / max(1, calls_total // CALLS_PER_ROUND * attack_calls) if attack_calls else 0
    return successes / trials, avg_rounds, fire_rate


if __name__ == "__main__":
    print(f"{'attack calls/round':<20}{'success rate':<15}{'avg rounds':<13}{'speculation fired'}")
    for attack in [1, 5, 10, 15, 25, 29]:
        rate, rounds, fire = run_attack(attack, trials=150)
        print(f"{attack}/30 (train {30-attack})   {rate*100:>6.1f}%       {rounds:>7.1f}     {fire*100:>6.1f}% of attack calls")

    print("\nThe paper's ratio, 5 attack calls per 30 (25 training), keeps the")
    print("predictor saturated at 'in bounds' for nearly every attack call, so")
    print("speculation fires reliably and the vote resolves in very few rounds.")
    print("Too many attack calls (25+/30) erode the counter between trainings,")
    print("so prediction flips to 'out of bounds' before many attack calls get")
    print("a chance to run speculatively -- the leak rate (and thus the attack's")
    print("overall success) collapses even though 999 rounds are still available.")
