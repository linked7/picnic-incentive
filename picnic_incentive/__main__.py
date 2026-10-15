"""Command line entry point:

    python -m picnic_incentive --rules v1 --agents coop*6,freerider,exploiter --rounds 20 --seed 0
"""

import argparse
import csv

from .agents import make_agents
from .game import World, run_game
from .rules import RULESETS


def print_summary(result):
    n = result.n_players
    print(f"\n=== Final metrics (rules {result.rules}, {len(result.rounds)} rounds) ===")
    print(f"mean survivors per round : {result.mean('survivors'):.2f} / {n}")
    print(f"mean pods charged        : {result.mean('pods'):.2f}")
    print(f"deaths per round         : starved {result.mean('starved'):.2f}, "
          f"desert {result.mean('desert'):.2f}, no pod {result.mean('no_pod'):.2f}")
    print(f"mean Stickers paid/round : {result.mean('town_stickers'):.1f}   "
          f"(Stickers per survivor: "
          f"{result.mean('town_stickers') / max(0.01, result.mean('survivors')):.2f})")
    print(f"\n{'player':<13}{'Stickers':>9}{'survived':>10}{'RECYCLE use':>13}")
    for name, s, surv, rate in zip(result.agent_names, result.per_agent("stickers"),
                                   result.per_agent("survived"), result.recycle_rate()):
        print(f"{name:<13}{s:9.1f}{surv / len(result.rounds):10.0%}{rate:13.0%}")


def save_csv(result, path):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["round", "player", "stickers", "survived", "recycles",
                         "acts_taken", "lithium", "pods", "survivors"])
        for r in result.rounds:
            for i, name in enumerate(result.agent_names):
                writer.writerow([r["round"], name, f"{r['stickers'][i]:.3f}",
                                 r["survived"][i], r["recycles"][i], r["acts_taken"][i],
                                 r["lithium"], r["pods"], r["survivors"]])
    print(f"saved per-round data to {path}")


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="python -m picnic_incentive",
        description="picnic-incentive: a toy model of Picnic's incentive loop")
    p.add_argument("--rules", default="v1", choices=sorted(RULESETS))
    p.add_argument("--agents", default="coop*6,freerider,exploiter",
                   help="comma list, 'name*N' repeats: coop, freerider, exploiter, "
                        "tft, learner, llm (default: %(default)s)")
    p.add_argument("--rounds", type=int, default=20)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--acts", type=int, default=6, help="ACTs per round")
    p.add_argument("--desert-risk", type=float, default=0.05)
    p.add_argument("--lithium-per-pod", type=int, default=3)
    p.add_argument("--csv", help="optional path to save per-round, per-player data")
    p.add_argument("--quiet", action="store_true", help="hide the per-round lines")
    args = p.parse_args(argv)

    try:
        agents = make_agents(args.agents)
    except (ValueError, RuntimeError) as e:
        p.error(str(e))
    rules = RULESETS[args.rules]
    world = World(acts=args.acts, desert_risk=args.desert_risk,
                  lithium_per_pod=args.lithium_per_pod)

    print(f"Rules {rules.name}: {rules.text}\n")
    result = run_game(rules, agents, args.rounds, args.seed, world,
                      verbose=not args.quiet)
    print_summary(result)
    if args.csv:
        save_csv(result, args.csv)


if __name__ == "__main__":
    main()
