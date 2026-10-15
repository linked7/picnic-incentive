"""Run every Sticker rule set against a few line-ups over many seeds.

    python experiments/compare_rules.py            # stdlib only
    python experiments/compare_rules.py --plot     # also saves a PNG if matplotlib is installed

Table 1 (what happened to the town), averaged per round over all seeds:
  survivors, pods, and deaths by cause (starved / desert / no pod = bloodbath),
  RECYCLE  -- share of ACTs the exploiter/learner agents spent on the loophole,
  Stickers -- total Stickers paid out per round,
  corr     -- correlation between Stickers paid and survivors, round by round.
              High = the score tracks the real outcome; low = it doesn't.

Table 2 (who the rules reward): mean Stickers per player per round, by type.
"""

import argparse
import os
import sys
from statistics import correlation, mean, StatisticsError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # run from anywhere

from picnic_incentive.agents import make_agents  # noqa: E402
from picnic_incentive.game import run_game  # noqa: E402
from picnic_incentive.rules import RULESETS  # noqa: E402

LINEUPS = ["coop*8", "coop*6,freerider,exploiter", "coop*7,learner", "coop*4,learner*4"]
RULE_ORDER = ["v1", "v1.1", "v2"]
TYPES = ["coop", "freerider", "exploiter", "learner"]


def agent_type(name):
    return name.rstrip("0123456789")


def evaluate(lineup, rules_name, seeds, rounds):
    rows, recycle_rates = [], []
    per_type = {t: [] for t in TYPES}
    for seed in seeds:
        g = run_game(RULESETS[rules_name], make_agents(lineup), rounds, seed)
        rows += g.rounds
        for name, rate, stickers in zip(g.agent_names, g.recycle_rate(),
                                        g.per_agent("stickers")):
            t = agent_type(name)
            per_type[t].append(stickers / rounds)
            if t in ("exploiter", "learner"):   # the agents that optimise Stickers
                recycle_rates.append(rate)
    try:
        corr = correlation([r["town_stickers"] for r in rows], [r["survivors"] for r in rows])
    except StatisticsError:
        corr = float("nan")
    return {
        "survivors": mean(r["survivors"] for r in rows),
        "pods": mean(r["pods"] for r in rows),
        "starved": mean(r["starved"] for r in rows),
        "desert": mean(r["desert"] for r in rows),
        "no_pod": mean(r["no_pod"] for r in rows),
        "recycle": mean(recycle_rates) if recycle_rates else 0.0,
        "stickers": mean(r["town_stickers"] for r in rows),
        "corr": corr,
        "per_type": {t: mean(v) for t, v in per_type.items() if v},
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, default=20)
    p.add_argument("--rounds", type=int, default=50)
    p.add_argument("--plot", action="store_true")
    args = p.parse_args()
    seeds = range(args.seeds)

    results = {(l, r): evaluate(l, r, seeds, args.rounds) for l in LINEUPS for r in RULE_ORDER}

    print(f"{args.seeds} seeds x {args.rounds} rounds, 8 players, 6 ACTs. Per-round averages.\n")
    print("Table 1: what happened to the town")
    print(f"{'line-up':<28}{'rules':<6}{'surv':>6}{'pods':>6}{'starv':>7}{'desert':>7}"
          f"{'no pod':>7}{'RECYCLE':>9}{'Stickers':>9}{'corr':>6}")
    for lineup in LINEUPS:
        for r in RULE_ORDER:
            x = results[(lineup, r)]
            print(f"{lineup:<28}{r:<6}{x['survivors']:6.2f}{x['pods']:6.2f}{x['starved']:7.2f}"
                  f"{x['desert']:7.2f}{x['no_pod']:7.2f}{x['recycle']:9.0%}"
                  f"{x['stickers']:9.1f}{x['corr']:6.2f}")
        print()

    print("Table 2: Stickers per player per round, by agent type")
    print(f"{'line-up':<28}{'rules':<6}" + "".join(f"{t:>11}" for t in TYPES))
    for lineup in LINEUPS:
        for r in RULE_ORDER:
            pt = results[(lineup, r)]["per_type"]
            print(f"{lineup:<28}{r:<6}" +
                  "".join(f"{pt[t]:11.2f}" if t in pt else f"{'-':>11}" for t in TYPES))
        print()

    if args.plot:
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print("matplotlib not installed; skipping plot")
            return
        fig, ax = plt.subplots(figsize=(8, 4))
        width = 0.25
        for j, r in enumerate(RULE_ORDER):
            xs = [i + j * width for i in range(len(LINEUPS))]
            ax.bar(xs, [results[(l, r)]["survivors"] for l in LINEUPS], width, label=r)
        ax.set_xticks([i + width for i in range(len(LINEUPS))], LINEUPS, fontsize=8)
        ax.set_ylabel("mean survivors per round (of 8)")
        ax.legend(title="rules")
        fig.tight_layout()
        fig.savefig("survivors_by_rules.png", dpi=120)
        print("saved survivors_by_rules.png")


if __name__ == "__main__":
    main()
