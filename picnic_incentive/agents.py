"""Agent policies. All of these run offline with the standard library only.

Every agent has the same tiny interface:
    reset(rng)                        -- once per game, with a seeded RNG
    act(obs) -> "MINE" | "FARM" | "IDLE" | "RECYCLE"
    end_round(actions, per_act, bonus) -- Stickers earned this round (learner uses it)
"""

from .game import ACTIONS


class Agent:
    name = "agent"

    def reset(self, rng):
        self.rng = rng

    def act(self, obs) -> str:
        raise NotImplementedError

    def end_round(self, actions, per_act, bonus):
        pass


def rota(obs, player=None) -> str:
    """The town's shift rota: farm and mine on alternate ACTs.

    Neighbouring players are on opposite shifts, so if everyone follows it,
    half the town farms and half mines every ACT -- exactly enough food.
    """
    player = obs["me"] if player is None else player
    return "FARM" if (player + obs["act"]) % 2 == 0 else "MINE"


class Cooperative(Agent):
    """Mines when the town is fed, farms when food is needed.

    It follows the rota, but remembers anyone who skipped a FARM shift. If
    those unreliable players leave the town short of farmers this ACT, the
    lowest-numbered reliable miners switch to farming to cover the gap. Every
    coop computes the same thing from the same public information, so they
    coordinate without talking. Once the stockpile can charge a pod for
    everyone alive, coops stop taking desert risks and just farm.
    """
    name = "coop"

    def reset(self, rng):
        super().reset(rng)
        self.unreliable = set()   # remembered across rounds

    def act(self, obs):
        # Learn who skipped a FARM shift last ACT.
        if obs["act"] > 1:
            prev = dict(obs, act=obs["act"] - 1)
            for j, action in enumerate(obs["last_actions"]):
                if action and action != "FARM" and rota(prev, j) == "FARM":
                    self.unreliable.add(j)

        if obs["stockpile"] >= obs["pods_needed_lithium"]:
            return "FARM"

        alive = obs["alive_players"]
        reliable = [j for j in alive if j not in self.unreliable or j == obs["me"]]
        needed = (len(alive) + 1) // 2      # each farmer feeds two people
        farmers = [j for j in reliable if rota(obs, j) == "FARM"]
        miners = [j for j in reliable if rota(obs, j) == "MINE"]
        shortfall = needed - len(farmers)
        if shortfall > 0 and obs["me"] in miners[:shortfall]:
            return "FARM"                   # cover for the missing farmers
        if shortfall < 0 and obs["me"] in farmers[shortfall:]:
            return "MINE"                   # too many farmers: go mine
        return rota(obs)


class FreeRider(Agent):
    """Never mines. Farms on its rota shift (so it doesn't starve), idles otherwise.
    It still gets a pod lottery ticket like everyone else."""
    name = "freerider"

    def act(self, obs):
        return "FARM" if rota(obs) == "FARM" else "IDLE"


class TitForTat(Agent):
    """Cooperates, but if anyone idled or recycled last ACT it refuses to take
    desert risks for them and farms instead."""
    name = "tft"

    def act(self, obs):
        if any(a in ("IDLE", "RECYCLE") for a in obs["last_actions"]):
            return "FARM"
        return rota(obs)


def expected_stickers(action: str, obs) -> float:
    """Stickers an action is expected to earn right now, read off the rules.

    This is the "rulebook reader": it uses only the published rule parameters,
    with no knowledge of which rule is a bug. It ignores the end-of-round pod
    bonus and survival scaling (they are the same whatever you do this ACT).
    """
    rules, risk = obs["rules"], obs["world"].desert_risk
    if action == "MINE":
        return 1.0 - risk                      # delivered AND net, unless you die
    if action == "RECYCLE":
        counts = rules.pay_on == "delivered" and obs["stockpile"] > 0
        return 1.0 if counts else 0.0
    if action == "FARM":
        return rules.food_sticker              # assumes the spare food finds someone
    return 0.0


class Exploiter(Agent):
    """Picks whatever action the rules pay most for, this ACT.

    It is not told about the loophole. Under v1 the arithmetic simply says
    RECYCLE (1 Sticker, no risk) beats MINE (1 Sticker, 5% death risk).
    """
    name = "exploiter"

    def act(self, obs):
        return max(ACTIONS, key=lambda a: expected_stickers(a, obs))


class Learner(Agent):
    """A tiny reinforcement learner (epsilon-greedy multi-armed bandit).

    It is NOT told the rules or the world. It only sees how many Stickers each
    of its actions earned at the end of the round (its pod bonus is shared
    equally across the ACTs it lived through), and gradually prefers the
    actions that paid best. If a loophole pays, it finds it by trial and error.
    """
    name = "learner"

    def __init__(self, epsilon: float = 0.1):
        self.epsilon = epsilon

    def reset(self, rng):
        super().reset(rng)
        self.value = {a: 5.0 for a in ACTIONS}   # optimistic start: try everything
        self.count = {a: 0 for a in ACTIONS}

    def act(self, obs):
        if self.rng.random() < self.epsilon:
            return self.rng.choice(ACTIONS)                      # explore
        return max(ACTIONS, key=lambda a: self.value[a])         # exploit

    def end_round(self, actions, per_act, bonus):
        share = bonus / len(actions) if actions else 0.0
        for action, stickers in zip(actions, per_act):
            reward = stickers + share
            self.count[action] += 1               # running average per action
            self.value[action] += (reward - self.value[action]) / self.count[action]


AGENTS = {
    "coop": Cooperative,
    "freerider": FreeRider,
    "exploiter": Exploiter,
    "tft": TitForTat,
    "learner": Learner,
}


def make_agents(spec: str) -> list:
    """Turn 'coop*6,freerider,llm' into agent objects. 'llm' is loaded lazily."""
    keys = []
    for part in (p.strip() for p in spec.split(",") if p.strip()):
        key, _, times = part.partition("*")
        keys += [key] * (int(times) if times else 1)

    agents = []
    for i, key in enumerate(keys):
        if key == "llm":
            from .llm_agent import LLMAgent  # optional; needs `anthropic`
            agent = LLMAgent()
        elif key in AGENTS:
            agent = AGENTS[key]()
        else:
            raise ValueError(f"unknown agent '{key}'; choose from {sorted(AGENTS)} or llm")
        agent.name = f"{agent.name}{i}"  # unique names, e.g. coop0, exploiter7
        agents.append(agent)
    return agents
