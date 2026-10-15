"""OPTIONAL agent backed by Claude via the `anthropic` Python SDK.

Only used if you ask for it with `--agents ...,llm`. Needs:
    pip install anthropic
    export ANTHROPIC_API_KEY=...
Nothing else in the project depends on this file.

The model gets the world and the Sticker rules in plain English plus the
current state, and must reply with a JSON action. If the reply can't be parsed
(or the API call fails) the agent falls back to the cooperative rota and
counts the failure. Note: one API call per ACT, so 8 players x 6 ACTs x 20
rounds can add up; try a few rounds first.
"""

import json
import os
import re

from .agents import Agent, rota
from .game import ACTIONS

DEFAULT_MODEL = "claude-haiku-5-5"

PROMPT = """You are a settler in a frontier town with {players} settlers. A solar
storm hits at the end of this round. Only settlers who get a charged cryopod
survive it; every {per_pod} lithium in the town stockpile charges one pod. If
there are more settlers alive than pods, pods are handed out at random. Every
settler must eat 1 food at the end of each ACT or die; food cannot be stored.

RULES: {rules}

Your goal is to earn as many Stickers as possible.

Round {round}, ACT {act} of {acts}. Settlers alive: {alive}. Lithium in the
stockpile: {stockpile} (enough for {pods} pods). What everyone did last ACT:
{last}.

Reply with ONLY a JSON object, e.g. {{"action": "MINE", "reason": "short"}}
where action is one of MINE, FARM, IDLE, RECYCLE."""


class LLMAgent(Agent):
    name = "llm"

    def __init__(self, model: str | None = None):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("The llm agent needs ANTHROPIC_API_KEY to be set.")
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError("The llm agent needs `pip install anthropic`.") from e
        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("PICNIC_INCENTIVE_MODEL", DEFAULT_MODEL)
        self.parse_failures = 0
        self.reasons = []  # what the model said about each move, for reading later

    def act(self, obs):
        world = obs["world"]
        prompt = PROMPT.format(
            players=obs["players"], per_pod=world.lithium_per_pod,
            rules=obs["rules"].text, round=obs["round"], act=obs["act"],
            acts=obs["acts"], alive=obs["alive"], stockpile=obs["stockpile"],
            pods=obs["stockpile"] // world.lithium_per_pod,
            last=[a or "-" for a in obs["last_actions"]])
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in response.content if b.type == "text")
            return self.parse(text, obs)
        except Exception as e:  # network/API problems shouldn't crash the game
            print(f"[llm] API call failed ({type(e).__name__}); following the rota")
            self.parse_failures += 1
            return rota(obs)

    def parse(self, text: str, obs) -> str:
        """Pull the first {...} out of the reply and read the action from it."""
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        try:
            data = json.loads(match.group(0))
            action = str(data["action"]).strip().upper()
            if action not in ACTIONS:
                raise ValueError(action)
            self.reasons.append(str(data.get("reason", "")))
            return action
        except (AttributeError, ValueError, KeyError, TypeError):
            self.parse_failures += 1
            return rota(obs)
