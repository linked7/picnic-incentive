"""The world: a bare-minimum version of one round of Picnic.

A frontier town has to charge cryopods before a solar storm. Each round:

  * There are several ACTs. In each ACT every living settler picks ONE action:
      MINE    +1 lithium to the town stockpile; small chance of dying in the desert
      FARM    +2 food: eat 1, the spare 1 goes to a hungry settler
      IDLE    do nothing
      RECYCLE take 1 ore out of the stockpile and deliver it again (net 0, no risk)
  * End of every ACT: each living settler must eat 1 food or die (starved).
    Farmers feed themselves. Each farmer's spare food goes to one settler who
    has none; hungry settlers are served in a random (seeded) order. Food rots,
    so nothing carries over to the next ACT.
  * End of the round: every LITHIUM_PER_POD lithium charges one pod. If more
    settlers are alive than there are pods, the pods go to random (seeded)
    settlers and the rest die (the "bloodbath", abstracted to a lottery).

Then Stickers are paid using the current Rules. Agents keep their memory
between rounds, so learning agents can adapt to the rules.
"""

import random
from dataclasses import dataclass, field

from .rules import Rules, round_stickers

ACTIONS = ["MINE", "FARM", "IDLE", "RECYCLE"]


@dataclass
class World:
    acts: int = 6               # ACTs per round
    desert_risk: float = 0.05   # chance a miner dies in the desert, per MINE
    lithium_per_pod: int = 3    # lithium needed to charge one cryopod


@dataclass
class GameResult:
    rules: str
    agent_names: list
    n_players: int
    rounds: list = field(default_factory=list)  # one dict per round

    def mean(self, key: str) -> float:
        return sum(r[key] for r in self.rounds) / max(1, len(self.rounds))

    def per_agent(self, key: str) -> list:
        """Sum a per-player list (e.g. "stickers", "survived") over all rounds."""
        return [sum(r[key][i] for r in self.rounds) for i in range(self.n_players)]

    def recycle_rate(self) -> list:
        """Fraction of each player's ACTs spent on RECYCLE (the loophole)."""
        recycles, acts = self.per_agent("recycles"), self.per_agent("acts_taken")
        return [r / a if a else 0.0 for r, a in zip(recycles, acts)]


def play_round(rules: Rules, agents: list, world: World, rng: random.Random,
               round_no: int) -> dict:
    n = len(agents)
    alive = [True] * n
    cause = [None] * n                 # "desert", "starved" or "no pod"
    acts = [[] for _ in range(n)]      # per-player list of what each ACT achieved
    recycles = [0] * n
    stockpile = 0
    last_actions = [None] * n

    for act in range(1, world.acts + 1):
        # 1. everyone alive chooses an action
        choices = {}
        for i, agent in enumerate(agents):
            if alive[i]:
                obs = {"round": round_no, "act": act, "acts": world.acts, "me": i,
                       "stockpile": stockpile, "alive": sum(alive), "players": n,
                       "alive_players": [j for j in range(n) if alive[j]],
                       "pods_needed_lithium": sum(alive) * world.lithium_per_pod,
                       "last_actions": list(last_actions), "rules": rules,
                       "world": world}
                action = agent.act(obs)
                choices[i] = action if action in ACTIONS else "IDLE"

        # 2. resolve actions in player order
        farmers = []
        for i, action in choices.items():
            ev = {"action": action, "delivered": 0, "net": 0, "food_given": 0}
            if action == "MINE":
                if rng.random() < world.desert_risk:
                    alive[i], cause[i] = False, "desert"
                else:
                    stockpile += 1
                    ev["delivered"] = ev["net"] = 1
            elif action == "RECYCLE":
                recycles[i] += 1
                if stockpile > 0:      # take one out, put it back: looks like work
                    ev["delivered"] = 1
            elif action == "FARM":
                farmers.append(i)
            acts[i].append(ev)

        # 3. eating: farmers feed themselves, spare food goes to the hungry
        hungry = [i for i in choices if alive[i] and i not in farmers]
        rng.shuffle(hungry)
        for giver, receiver in zip(farmers, hungry):
            acts[giver][-1]["food_given"] = 1
        for i in hungry[len(farmers):]:   # nobody had spare food for these
            alive[i], cause[i] = False, "starved"

        last_actions = [choices.get(i) for i in range(n)]

    # 4. storm: charge pods, hand them out
    pods = stockpile // world.lithium_per_pod
    living = [i for i in range(n) if alive[i]]
    winners = set(living) if len(living) <= pods else set(rng.sample(living, pods))
    for i in living:
        if i not in winners:
            alive[i], cause[i] = False, "no pod"
    survival_fraction = len(winners) / n

    # 5. Stickers, and feedback to the agents
    stickers = []
    for i, agent in enumerate(agents):
        per_act, bonus = round_stickers(rules, acts[i], i in winners, survival_fraction)
        stickers.append(sum(per_act) + bonus)
        agent.end_round([a["action"] for a in acts[i]], per_act, bonus)

    return {
        "round": round_no, "lithium": stockpile, "pods": pods,
        "alive_at_storm": len(living), "survivors": len(winners),
        "starved": cause.count("starved"), "desert": cause.count("desert"),
        "no_pod": cause.count("no pod"),
        "stickers": stickers, "survived": [1 if i in winners else 0 for i in range(n)],
        "recycles": recycles, "acts_taken": [len(a) for a in acts],
        "town_stickers": sum(stickers),
    }


def run_game(rules: Rules, agents: list, rounds: int = 20, seed: int = 0,
             world: World | None = None, verbose: bool = False) -> GameResult:
    """Play several rounds with the same agents and return everything that happened."""
    world = world or World()
    rng = random.Random(seed)           # world randomness (desert, food order, pods)
    for i, agent in enumerate(agents):  # each agent gets its own seeded RNG
        agent.reset(random.Random(seed * 1000 + i))

    result = GameResult(rules=rules.name, agent_names=[a.name for a in agents],
                        n_players=len(agents))
    for r in range(1, rounds + 1):
        info = play_round(rules, agents, world, rng, r)
        result.rounds.append(info)
        if verbose:
            print(f"round {r:3d} | lithium {info['lithium']:2d} pods {info['pods']} "
                  f"| survivors {info['survivors']}/{len(agents)} "
                  f"(starved {info['starved']}, desert {info['desert']}, "
                  f"no pod {info['no_pod']}) | recycles {sum(info['recycles']):2d} "
                  f"| stickers {info['town_stickers']:5.1f}")
    return result
