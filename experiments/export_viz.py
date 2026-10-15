"""Dump replays and experiment results to JSON for the visualiser in docs/.

    python experiments/export_viz.py              # writes docs/viz_data.json
    python experiments/export_viz.py --html       # also rebuilds docs/index.html

Replays: a few line-ups under every rule set, every ACT of every round recorded.
Results: the same averages as compare_rules.py, plus how often a learner uses
RECYCLE round by round (does it learn the loophole?).
"""

import argparse
import json
import os
import sys
from statistics import mean

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))

from picnic_incentive.agents import make_agents  # noqa: E402
from picnic_incentive.game import World, run_game  # noqa: E402
from picnic_incentive.rules import RULESETS  # noqa: E402
from compare_rules import LINEUPS, RULE_ORDER, TYPES, agent_type, evaluate  # noqa: E402

REPLAY_LINEUPS = ["coop*6,freerider,exploiter", "coop*7,learner", "coop*4,learner*4"]
CODE = {"MINE": "M", "FARM": "F", "IDLE": "I", "RECYCLE": "R", None: "."}


def replay(lineup, rules_name, rounds, seed):
    g = run_game(RULESETS[rules_name], make_agents(lineup), rounds, seed, record=True)
    out = []
    for r in g.rounds:
        acts, storm = [], None
        for step in r["trace"]:
            if step.get("storm"):
                storm = {"pods": step["pods"], "winners": step["winners"],
                         "no_pod": step["no_pod"]}
            else:
                acts.append({"c": "".join(CODE[c] for c in step["choices"]),
                             "fed": {str(k): v for k, v in step["fed_by"].items()},
                             "died": {str(k): v for k, v in step["died"].items()},
                             "stock": step["stockpile"]})
        out.append({"acts": acts, "storm": storm,
                    "stickers": [round(s, 2) for s in r["stickers"]]})
    return {"players": g.agent_names, "rounds": out}


def learning_curve(lineup, rules_name, seeds, rounds):
    """Mean share of the learners' ACTs spent on RECYCLE, round by round."""
    per_round = [[] for _ in range(rounds)]
    for seed in seeds:
        g = run_game(RULESETS[rules_name], make_agents(lineup), rounds, seed)
        idx = [i for i, n in enumerate(g.agent_names) if agent_type(n) == "learner"]
        for k, r in enumerate(g.rounds):
            acts = sum(r["acts_taken"][i] for i in idx)
            per_round[k].append(sum(r["recycles"][i] for i in idx) / acts if acts else 0)
    return [round(mean(v), 4) for v in per_round]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, default=20)
    p.add_argument("--rounds", type=int, default=50)
    p.add_argument("--replay-rounds", type=int, default=30)
    p.add_argument("--html", action="store_true", help="inline the data into docs/index.html")
    args = p.parse_args()
    seeds = range(args.seeds)

    w = World()
    data = {
        "world": {"acts": w.acts, "desert_risk": w.desert_risk,
                  "lithium_per_pod": w.lithium_per_pod},
        "rules": {k: RULESETS[k].text for k in RULE_ORDER},
        "replays": {lu: {rn: replay(lu, rn, args.replay_rounds, 0) for rn in RULE_ORDER}
                    for lu in REPLAY_LINEUPS},
        "results": {"seeds": args.seeds, "rounds": args.rounds, "lineups": {}},
        "learning": {rn: learning_curve("coop*7,learner", rn, seeds, args.rounds)
                     for rn in RULE_ORDER},
    }
    for lu in LINEUPS:
        data["results"]["lineups"][lu] = {}
        for rn in RULE_ORDER:
            res = evaluate(lu, rn, seeds, args.rounds)
            data["results"]["lineups"][lu][rn] = {
                k: (round(v, 4) if isinstance(v, float) else v) for k, v in res.items()}

    docs = os.path.join(HERE, "..", "docs")
    os.makedirs(docs, exist_ok=True)
    blob = json.dumps(data, separators=(",", ":"))
    with open(os.path.join(docs, "viz_data.json"), "w") as f:
        f.write(blob)
    print(f"wrote docs/viz_data.json ({len(blob) // 1024} KB)")

    if args.html:
        tpl = os.path.join(docs, "template.html")
        with open(tpl) as f:
            html = f.read().replace("/*__DATA__*/null", blob)
        with open(os.path.join(docs, "index.html"), "w") as f:
            f.write(html)
        print("wrote docs/index.html")


if __name__ == "__main__":
    main()
