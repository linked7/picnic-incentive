"""Run with:  python -m pytest"""

import random

from picnic_incentive.agents import make_agents
from picnic_incentive.game import World, play_round, run_game
from picnic_incentive.rules import RULESETS, round_stickers

V1, V11, V2 = RULESETS["v1"], RULESETS["v1.1"], RULESETS["v2"]
SAFE = World(desert_risk=0.0)   # no desert deaths, to make outcomes exact


class Fixed:
    """Test helper: an agent that always plays the same action."""
    def __init__(self, action):
        self.name, self.action = action.lower(), action

    def reset(self, rng):
        pass

    def act(self, obs):
        return self.action

    def end_round(self, actions, per_act, bonus):
        self.last_feedback = (actions, per_act, bonus)


def one_round(agents, world=SAFE, rules=V1, seed=0):
    for a in agents:
        a.reset(random.Random(seed))
    return play_round(rules, agents, world, random.Random(seed), 1)


# ---- world rules -------------------------------------------------------------

def test_everyone_starves_without_farmers():
    info = one_round([Fixed("MINE") for _ in range(4)])
    assert info["starved"] == 4 and info["survivors"] == 0


def test_one_farmer_feeds_exactly_one_other():
    info = one_round([Fixed("FARM"), Fixed("IDLE"), Fixed("IDLE")])
    assert info["starved"] == 1              # one idler starves in ACT 1, the other is fed
    assert info["acts_taken"].count(1) == 1  # the starved one only lived one ACT
    assert info["no_pod"] == 2               # nobody mined, so no pods for the other two


def test_pods_cap_survivors_and_bloodbath_kills_the_rest():
    # 4 farmers + 4 miners: everyone eats; 4 miners x 6 ACTs = 24 lithium = 8 pods.
    agents = [Fixed("FARM") for _ in range(4)] + [Fixed("MINE") for _ in range(4)]
    assert one_round(agents)["survivors"] == 8
    # With 3 lithium per pod but only 3 ACTs: 12 lithium = 4 pods for 8 people.
    info = one_round(agents, world=World(acts=3, desert_risk=0.0))
    assert info["pods"] == 4 and info["survivors"] == 4 and info["no_pod"] == 4


def test_recycle_adds_no_lithium():
    agents = [Fixed("FARM"), Fixed("FARM"), Fixed("MINE"), Fixed("RECYCLE")]
    info = one_round(agents)
    assert info["lithium"] == 6              # only the miner's 6 ore


def test_desert_can_kill_miners():
    info = one_round([Fixed("FARM"), Fixed("MINE")], world=World(desert_risk=1.0))
    assert info["desert"] == 1


# ---- determinism -------------------------------------------------------------

def test_same_seed_gives_identical_games():
    a = run_game(V1, make_agents("coop*5,freerider,learner,exploiter"), 20, seed=7)
    b = run_game(V1, make_agents("coop*5,freerider,learner,exploiter"), 20, seed=7)
    assert a.rounds == b.rounds


def test_different_seeds_differ():
    a = run_game(V1, make_agents("coop*7,learner"), 20, seed=1)
    b = run_game(V1, make_agents("coop*7,learner"), 20, seed=2)
    assert a.rounds != b.rounds


# ---- the loophole ------------------------------------------------------------

RECYCLE_ACT = {"delivered": 1, "net": 0, "food_given": 0}
MINE_ACT = {"delivered": 1, "net": 1, "food_given": 0}


def test_recycle_pays_in_v1_only():
    for rules, expected in ((V1, 1.0), (V11, 0.0), (V2, 0.0)):
        per_act, _ = round_stickers(rules, [RECYCLE_ACT], got_pod=False, survival_fraction=1.0)
        assert per_act == [expected]


def test_exploiter_recycles_in_v1_but_not_after_the_fix():
    lineup = "coop*6,freerider,exploiter"
    for rules, should_recycle in ((V1, True), (V11, False), (V2, False)):
        rate = run_game(rules, make_agents(lineup), 10, seed=0).recycle_rate()[-1]
        assert (rate > 0.5) == should_recycle


def test_loophole_costs_lives():
    def survivors(rules):
        return run_game(rules, make_agents("coop*6,freerider,exploiter"), 50, 0).mean("survivors")
    assert survivors(V1) < survivors(V11) - 0.5


# ---- v2 alignment ------------------------------------------------------------

def test_v2_pays_only_as_well_as_the_town_does():
    acts = [MINE_ACT] * 3
    full = sum(round_stickers(V2, acts, True, 1.0)[0]) + round_stickers(V2, acts, True, 1.0)[1]
    half = sum(round_stickers(V2, acts, True, 0.5)[0]) + round_stickers(V2, acts, True, 0.5)[1]
    assert half == full / 2
    # v1.1 pays the same whether the town survived or not.
    assert round_stickers(V11, acts, True, 1.0) == round_stickers(V11, acts, True, 0.5)


def test_v2_pays_for_feeding_others():
    fed = [{"delivered": 0, "net": 0, "food_given": 1}]
    assert round_stickers(V2, fed, False, 1.0)[0] == [0.5]
    assert round_stickers(V11, fed, False, 1.0)[0] == [0.0]


# ---- optional LLM agent (no API call is made) --------------------------------

def test_llm_reply_parsing_falls_back_gracefully():
    from picnic_incentive.llm_agent import LLMAgent
    agent = LLMAgent.__new__(LLMAgent)  # skip __init__, so no key/SDK needed
    agent.parse_failures, agent.reasons = 0, []
    obs = {"me": 0, "act": 2}
    assert agent.parse('Sure! {"action": "recycle", "reason": "x"}', obs) == "RECYCLE"
    assert agent.parse("I would rather not say.", obs) == "FARM"    # rota fallback
    assert agent.parse('{"action": "DANCE"}', obs) == "FARM"
    assert agent.parse_failures == 2
