# picnic-incentive

A small multi-agent experiment about **incentives, loopholes and free-riding**,
built as the bare-minimum abstraction of the incentive loop in *Picnic*, a
round-based multiplayer roleplay game I'm making in Godot.

## Why

In my games I try to steer players with incentives rather than hard rules.
Players respond to what the reward system actually pays for, not to what I
meant it to pay for, and they find loopholes fast. That is the same problem as
**reward hacking / specification gaming** in AI: an agent optimises the
measurable proxy, and the proxy drifts away from the goal. Picnic also has a
**public-goods** problem at its core (everyone benefits from the town's work,
whether or not they did any), which is the setting where free-riding and
cooperation under incentives get interesting.

This project strips Picnic down to that loop so it can be run thousands of
times with scripted and learning agents. I keep the world fixed, swap only
the reward rules, and see how behaviour and outcomes change.

## The game in Picnic (the source)

Settlers in a frontier town mine lithium to recharge cryopods before a solar
storm. Charged pods decide how many characters survive the round; if there
are more people than pods, it turns into a bloodbath. Everyone must eat once
per ACT or die. Between rounds, players earn **Stickers** for completing
objectives. Stickers are my main lever as a designer for steering behaviour.

## The model (what this repo simulates)

**World** (identical under every rule version; `picnic_incentive/game.py`):

* 8 settlers, 6 ACTs per round (both configurable).
* Each ACT every living settler picks one action:
  * `MINE`: +1 lithium to the town stockpile, 5% chance of dying in the desert.
  * `FARM`: +2 food. Eat 1, the spare goes to a hungry settler.
  * `IDLE`: nothing.
  * `RECYCLE`: take 1 ore out of the stockpile and deliver it again. Net lithium 0,
    no risk. **This action is invented for the experiment as a deliberate loophole.
    It is not in the real game.** It is available under every rule version.
* End of each ACT, each living settler must eat 1 food or die (starved).
  Food-sharing rule: farmers feed themselves; each farmer's spare food goes to one
  settler with no food, and hungry settlers are served in a random (seeded) order.
  Food rots, so nothing carries over between ACTs. Each farmer feeds two people, so
  about half the town has to farm every ACT.
* End of round: every 3 lithium charges 1 pod. If more settlers are alive than there
  are pods, the pods go to random (seeded) settlers and the rest die ("no pod", my
  abstraction of the bloodbath).
* Agents keep their memory between rounds, so learning agents can adapt to the rules.

**Sticker rules** (the only thing that changes; `picnic_incentive/rules.py`):

| rules | per-ore Sticker paid on | other Stickers | intent |
|-------|-------------------------|----------------|--------|
| `v1`   | ore **delivered** (MINE *or* RECYCLE) | +2 if you get a pod | the loophole |
| `v1.1` | lithium actually **added** (RECYCLE pays 0) | +2 if you get a pod | hotfix |
| `v2`   | lithium actually added, plus 0.5 per food given to a hungry settler | +2 if you get a pod, then **everything is multiplied by the fraction of the town that survived** | aligned: you do well only if the town does well |

**Agents** (`picnic_incentive/agents.py`; all offline, standard library only):

| name | behaviour |
|------|-----------|
| `coop` | Follows a shift rota (farm and mine on alternate ACTs). It remembers anyone who skipped a farm shift and covers for them by farming, so the town isn't short of food. It stops mining once there is enough lithium for everyone alive. ("Mines when fed, farms when needed.") |
| `freerider` | Never mines. Farms on its rota shift so it doesn't starve, and idles the rest of the time. It still gets a pod lottery ticket. |
| `exploiter` | Each ACT picks the action the published Sticker rules pay most for. It is **not told about the loophole**; under v1 the arithmetic simply favours RECYCLE (1 Sticker, no risk) over MINE (1 Sticker, 5% risk). |
| `learner` | An epsilon-greedy bandit. It is told neither the rules nor the world, only how many Stickers each of its actions earned. |
| `tft` | Tit-for-tat-ish: follows the rota, but refuses to mine for an ACT after anyone idled or recycled. |
| `llm` | Optional. Claude via the `anthropic` SDK (see below). |

## How to run

Requires Python 3.10+. No API key or network is needed except for the optional `llm` agent.

```bash
# one game: per-round log + final metrics
python -m picnic_incentive --rules v1 --agents "coop*6,freerider,exploiter" --rounds 20 --seed 0

# other options
python -m picnic_incentive --rules v2 --agents "coop*7,learner" --rounds 50 --csv run.csv
python -m picnic_incentive --help        # --acts, --desert-risk, --lithium-per-pod, --quiet ...

# compare v1 / v1.1 / v2 across 20 seeds (add --plot if matplotlib is installed)
python experiments/compare_rules.py

# tests
pip install pytest
python -m pytest
```

`"coop*6,freerider,exploiter"` means six coops, one free-rider and one exploiter (8 settlers).

### Visualiser

`docs/index.html` is a single page you can open in a browser. It replays rounds ACT by ACT (who mined, farmed, recycled, starved or lost the pod lottery) and charts the v1 / v1.1 / v2 results. Rebuild it after changing the model:

```bash
python experiments/export_viz.py --html
```

If GitHub Pages is turned on for the `docs/` folder, the page is also served there.

### Optional LLM agent

```bash
pip install anthropic
export ANTHROPIC_API_KEY=...
python -m picnic_incentive --rules v1 --agents "coop*7,llm" --rounds 3
```

The model (default `claude-haiku-5-5`, override with `PICNIC_INCENTIVE_MODEL`) is
given the world and the Sticker rules in plain English plus the current state,
and replies with `{"action": "MINE", "reason": "..."}`. If the reply can't be
parsed or the call fails, it falls back to the rota and counts a failure. It
makes one API call per ACT. I have not included LLM results here.

## Example output

`python -m picnic_incentive --rules v1 --agents "coop*6,freerider,exploiter" --rounds 20 --seed 0`

```
Rules v1: Each ACT you choose one action. MINE: +1 lithium to the town stockpile, with a small chance of dying in the desert. FARM: +2 food (you eat 1, the spare goes to a hungry settler). IDLE: do nothing. RECYCLE: take 1 ore out of the stockpile and deliver it again (no risk, no net lithium). Stickers: 1 per ore DELIVERED to the stockpile (MINE or RECYCLE). +2 if you get a charged pod.

round   1 | lithium 19 pods 6 | survivors 6/8 (starved 2, desert 0, no pod 0) | recycles  0 | stickers  31.0
round   2 | lithium 15 pods 5 | survivors 5/8 (starved 0, desert 1, no pod 2) | recycles  0 | stickers  25.0
round   3 | lithium 12 pods 4 | survivors 4/8 (starved 0, desert 1, no pod 3) | recycles  5 | stickers  25.0
round   4 | lithium 13 pods 4 | survivors 4/8 (starved 0, desert 2, no pod 2) | recycles  5 | stickers  26.0
round   5 | lithium  9 pods 3 | survivors 3/8 (starved 0, desert 2, no pod 3) | recycles  5 | stickers  20.0
round   6 | lithium 16 pods 5 | survivors 5/8 (starved 0, desert 0, no pod 3) | recycles  5 | stickers  31.0
round   7 | lithium 16 pods 5 | survivors 5/8 (starved 0, desert 0, no pod 3) | recycles  5 | stickers  31.0
round   8 | lithium 10 pods 3 | survivors 3/8 (starved 0, desert 1, no pod 4) | recycles  5 | stickers  21.0
round   9 | lithium 16 pods 5 | survivors 5/8 (starved 0, desert 0, no pod 3) | recycles  5 | stickers  31.0
round  10 | lithium 16 pods 5 | survivors 5/8 (starved 0, desert 0, no pod 3) | recycles  5 | stickers  31.0
round  11 | lithium 16 pods 5 | survivors 5/8 (starved 0, desert 0, no pod 3) | recycles  5 | stickers  31.0
round  12 | lithium 12 pods 4 | survivors 4/8 (starved 0, desert 2, no pod 2) | recycles  5 | stickers  25.0
round  13 | lithium  8 pods 2 | survivors 2/8 (starved 0, desert 2, no pod 4) | recycles  5 | stickers  17.0
round  14 | lithium 16 pods 5 | survivors 5/8 (starved 0, desert 0, no pod 3) | recycles  5 | stickers  31.0
round  15 | lithium 15 pods 5 | survivors 5/8 (starved 0, desert 1, no pod 2) | recycles  0 | stickers  25.0
round  16 | lithium 11 pods 3 | survivors 3/8 (starved 0, desert 1, no pod 4) | recycles  5 | stickers  22.0
round  17 | lithium  9 pods 3 | survivors 3/8 (starved 0, desert 2, no pod 3) | recycles  5 | stickers  20.0
round  18 | lithium 16 pods 5 | survivors 5/8 (starved 0, desert 0, no pod 3) | recycles  5 | stickers  31.0
round  19 | lithium 10 pods 3 | survivors 3/8 (starved 0, desert 1, no pod 4) | recycles  5 | stickers  21.0
round  20 | lithium 15 pods 5 | survivors 5/8 (starved 0, desert 1, no pod 2) | recycles  5 | stickers  30.0

=== Final metrics (rules v1, 20 rounds) ===
mean survivors per round : 4.25 / 8
mean pods charged        : 4.25
deaths per round         : starved 0.10, desert 0.85, no pod 2.80
mean Stickers paid/round : 26.2   (Stickers per survivor: 6.18)

player        Stickers  survived  RECYCLE use
coop0             33.0       70%           0%
coop1             57.0       45%           0%
coop2             68.0       55%           0%
coop3             78.0       55%           0%
coop4             71.0       50%           0%
coop5             79.0       60%           0%
freerider6        24.0       60%           0%
exploiter7       115.0       30%          81%
```

Same line-up and seed under the v1.1 hotfix (`--rules v1.1 --quiet`):

```
mean survivors per round : 5.55 / 8
mean pods charged        : 5.55
deaths per round         : starved 0.10, desert 1.05, no pod 1.30
mean Stickers paid/round : 28.4   (Stickers per survivor: 5.11)

player        Stickers  survived  RECYCLE use
coop0             39.0       85%           0%
coop1             79.0       70%           0%
coop2             72.0       75%           0%
coop3             75.0       60%           0%
coop4             81.0       70%           0%
coop5             82.0       80%           0%
freerider6        28.0       70%           0%
exploiter7       111.0       45%           0%
```

`python experiments/compare_rules.py`

```
20 seeds x 50 rounds, 8 players, 6 ACTs. Per-round averages.

Table 1: what happened to the town
line-up                     rules   surv  pods  starv desert no pod  RECYCLE Stickers  corr
coop*8                      v1      6.25  6.27   0.00   1.07   0.68       0%     32.0  0.99
coop*8                      v1.1    6.25  6.27   0.00   1.07   0.68       0%     32.0  0.99
coop*8                      v2      6.25  6.27   0.00   1.07   0.68       0%     33.6  0.99

coop*6,freerider,exploiter  v1      4.22  4.22   0.07   0.77   2.94      82%     26.7  0.94
coop*6,freerider,exploiter  v1.1    5.74  5.74   0.07   0.94   1.25       0%     29.4  0.99
coop*6,freerider,exploiter  v2      5.74  5.74   0.07   0.94   1.25       0%     29.5  0.99

coop*7,learner              v1      5.13  5.14   0.05   0.87   1.95      74%     30.7  0.92
coop*7,learner              v1.1    6.19  6.21   0.05   1.02   0.74       4%     31.9  0.99
coop*7,learner              v2      6.20  6.22   0.05   1.02   0.73       4%     33.4  0.99

coop*4,learner*4            v1      3.65  3.68   0.26   0.56   3.53      36%     27.0  0.80
coop*4,learner*4            v1.1    5.74  5.77   0.24   0.94   1.08       3%     29.8  0.99
coop*4,learner*4            v2      5.65  5.68   0.23   0.95   1.17       4%     29.4  0.97

Table 2: Stickers per player per round, by agent type
line-up                     rules        coop  freerider  exploiter    learner
coop*8                      v1           4.01          -          -          -
coop*8                      v1.1         4.01          -          -          -
coop*8                      v2           4.20          -          -          -

coop*6,freerider,exploiter  v1           3.14       1.16       6.72          -
coop*6,freerider,exploiter  v1.1         3.59       1.62       6.25          -
coop*6,freerider,exploiter  v2           3.82       1.85       4.68          -

coop*7,learner              v1           3.45          -          -       6.56
coop*7,learner              v1.1         3.73          -          -       5.78
coop*7,learner              v2           4.11          -          -       4.66

coop*4,learner*4            v1           1.16          -          -       5.60
coop*4,learner*4            v1.1         1.85          -          -       5.61
coop*4,learner*4            v2           3.10          -          -       4.24
```

## What the results show

* **The loophole gets found, and it costs lives.** Under v1 the exploiter (which
  only reads the rules) spends about 82% of its ACTs on RECYCLE. A single learner,
  which never sees the rules, ends up at about 74%. With one exploiter in the town,
  survivors fall from 5.74 to 4.22 per round, almost all of it from the pod lottery
  (no-pod deaths 1.25 → 2.94).
* **The proxy rewards the wrong player.** Under v1 the exploiter earns the most
  Stickers in the town (6.7 per round, against 3.1 for a coop) while making the
  town worse off. The scoreboard and the real outcome point in different directions.
* **Closing the loophole fixes behaviour; aligning the payout fixes the
  scoreboard.** The v1.1 hotfix alone brings RECYCLE down to the learner's
  exploration noise (3-4%) and restores survivors. v2 hardly changes behaviour
  further with these agents: one settler's action shifts the town's survival
  fraction only a little, so the incentive is weak per decision. What v2 changes
  is who gets paid. The exploiter's lead shrinks (6.25 → 4.68 Stickers per round),
  and coops who cover farming for others are paid for it (in the 4-coop/4-learner
  town, coop Stickers go from 1.85 to 3.10).
* **Free-riding is mostly a scoreboard problem here.** The free-rider survives
  about as often as anyone else but earns the fewest Stickers under every version.
  In this model, mining pays enough that free-riding never wins on Stickers. In
  real play, social and risk factors are what make it attractive.

## Limitations

* It's a toy: one abstraction of one loop. The numbers depend on my choices of
  pod bonus (2), food Sticker (0.5), desert risk (5%), and the coop agent's
  coordination rule.
* I didn't tune the world parameters for the result. I did redesign the coop agent
  once: with a fixed rota, any player who skipped farming caused starvation that
  drowned out every other effect. Coops now cover missed farm shifts.
* The exploiter is myopic (one ACT at a time), and the learner is a single-state
  bandit with crude credit assignment (its pod bonus is spread evenly over its ACTs).
* Results are averages over 20 seeds × 50 rounds with no confidence intervals.
* The fixes were designed knowing the loophole in advance. The harder, more
  realistic problem is finding loopholes you didn't anticipate.

## Deliberately left out

Picnic has much more than this: **wolves** (hidden saboteurs), the storm as an
event, thirst, roles, revival, and the social side of the bloodbath. All of
these are left out to keep the incentive loop readable.

## Ideas for next steps

* **Wolves:** add hidden agents who are rewarded for the town failing, and see
  which Sticker rules make sabotage easier to spot or less profitable.
* Run the LLM agent under v1 vs v2 and read its stated reasons: does it find
  RECYCLE, and does it explain it as "the rules allow it"?
* Learners with state (e.g. Q-learning on the stockpile level) or communication
  between agents.
* Automatic loophole search: sweep rule parameters and flag versions where
  Stickers and survivors diverge.

## Credits

Built by Greg Hancox with AI assistance (Claude), which helped write and review
the code and this README. MIT licensed, see `LICENSE`.
