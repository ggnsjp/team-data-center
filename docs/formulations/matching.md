# Theme 4: how much of a data center's electricity is renewable, slot by slot

A data center can say that it runs on renewable electricity because, over a year, it bought as much renewable energy as it used. This theme counts the same year in three ways, on the 30-minute supply and demand records of the Hokkaido area: **by the year, by the 30-minute slot, and by what changed on the grid.**

**Who it helps.** Operators deciding how to buy power for a data center, and municipalities and grid planners working on renewable plans: a common set of numbers behind the words "100 % renewable".

**Status.** A first version. Two fiscal years of published 30-minute records (17,520 slots each, no gaps), a constant load, contracts shaped like the area's solar and wind fleets, a simple replay of the records for the effect on the grid, and a linear program for the cheapest portfolio. All numbers are estimates; the limits are in section 8.

## 1. The records

Hokkaido Electric Power Network publishes the area's supply and demand for every 30-minute slot from April 2024 [65]: the mean power in MW at the sending end, for the area demand and for each kind of supply (nuclear; thermal by fuel: LNG, coal, oil, other; hydro; geothermal; biomass; solar; wind; pumped storage; batteries; the interconnection with Honshu), and the output that solar and wind plants were told not to produce (curtailment). `dcopt.matching.records` downloads the monthly files into `data/cache/hepco_area/`, reads them by their column headings and checks them. The files are not part of this repository.

- **Signs.** The kinds of supply add up to the area demand in every slot, to the published integer. Pumped storage and batteries are positive when they generate and negative when they charge; the interconnection is positive when the area imports.
- **Checks.** Each fiscal year has 17,520 slots with no gap and no missing value, and supply equals demand in every slot.
- **Curtailment.** The records give how much output was curtailed, not why. In FY2025 biomass and thermal plants were also told to reduce output in some slots (8.1 and 1.3 GWh); that is not counted here as unused renewable energy, because their fuel is kept.
- **Earlier years** are published as hourly values in another layout and are not used here.

| | FY2024 | FY2025 |
|---|---|---|
| Area demand | 29.57 TWh | 30.10 TWh |
| Thermal generation (share of demand) | 18.60 TWh (62.9 %) | 17.62 TWh (58.6 %) |
| of which coal / LNG / oil / other | 39.5 / 12.9 / 5.2 / 5.4 % | 38.7 / 8.4 / 6.1 / 5.2 % |
| Hydro / biomass | 12.9 / 6.2 % | 15.8 / 7.4 % |
| Solar / wind | 10.7 / 10.2 % | 10.9 / 10.3 % |
| Nuclear | 0 | 0 |
| Net export over the interconnection | 1.05 TWh | 1.14 TWh |
| Solar and wind curtailed | 2.7 GWh (0.04 %) in 23 slots | 16.2 GWh (0.25 %) in 230 slots |
| Lowest thermal output of the year | 364 MW | 325 MW |
| Thermal output while solar or wind was curtailed: range (10th percentile) | 469 to 696 MW (514 MW) | 325 to 2,104 MW (540 MW) |
| Slots with solar and wind above half of demand / below 5 % | 1,393 / 2,498 | 1,425 / 2,368 |

## 2. Three ways of counting

A data center uses $L_t$ MW in slot $t$. Its contract with solar and wind plants delivers $G_t$ MW in the same slot.

```math
\text{volume} = \frac{\sum_t G_t}{\sum_t L_t}, \qquad
\text{matched} = \frac{\sum_t \min(L_t, G_t)}{\sum_t L_t}, \qquad
\text{surplus} = \frac{\sum_t \max(G_t - L_t, 0)}{\sum_t L_t}, \qquad
\text{volume} = \text{matched} + \text{surplus} .
```

- **By the year (volume).** "100 % renewable" by certificates means volume $= 1$.
- **By the slot (matched).** The share of the energy used that the contract generated in the same 30 minutes. With volume $= 1$, the share $1 - \text{matched}$ is supplied by other plants, and the same amount of contracted energy goes to other users at other times.
- **On the grid.** What the area's plants did differently because the data center is there (section 4).

**The contract.** The contract buys $x$ times the load's yearly energy, a share $\sigma$ of it from solar and the rest from wind. Each source has the 30-minute shape of the area's whole fleet, $S_t$ and $W_t$ in the records:

```math
G_t = x \left( \sigma\, \hat s_t + (1 - \sigma)\, \hat w_t \right), \qquad
\hat s_t = S_t \frac{\sum_\tau L_\tau}{\sum_\tau S_\tau}, \quad \hat w_t = W_t \frac{\sum_\tau L_\tau}{\sum_\tau W_\tau} .
```

One plant varies more than the whole area, so a real contract matches less than this.

**The load.** $L_t$ is constant. Operators do not publish load profiles; a constant load is the working assumption until measured profiles are available.

## 3. Storage and shifting

**A battery** of power $p$ and capacity $e$ stores the contract's surplus and returns it in the next slots that fall short. It charges only from the contract, and returns a share $\eta$ of what it took in. Charging at the first surplus and discharging at the first shortfall delivers the most energy a single store can; the tests compare this rule with the linear program of section 5 on the same data.

**Shifting work within the day.** A share $\phi$ of each day's energy may be done at another time of the same day, using spare capacity $\kappa$ (the site may draw up to $(1 + \kappa) L_t$). With $lo_t = (1 - \phi) L_t$ and $hi_t = (1 + \kappa) L_t$, the energy matched on a day is

```math
\sum_t \min(G_t, lo_t) + \min\Big( \phi \sum_t L_t,\ \sum_t \big[ \min(G_t, hi_t) - \min(G_t, lo_t) \big] \Big) .
```

The firm part is matched as before. The movable part goes to the slots where generation exceeds the firm part, up to the cap, and what does not fit there stays unmatched. Doing the same work with spare capacity $\kappa$ means owning $1 + \kappa$ times the equipment; its mean use falls to $1 / (1 + \kappa)$.

## 4. What changes on the grid: a replay of the records

The two counts above say which energy a data center may call its own. The replay asks what the area's plants did differently. It keeps every published slot and changes only this (`dcopt.matching.system`):

- Solar and wind produce what the weather gives. Hydro, biomass, geothermal, pumped storage, batteries and the interconnection stay as recorded.
- Thermal plants cover what is left. They can turn down to a floor $F$ and no further. In a slot where solar or wind was already curtailed, they are taken to be at their limit.
- An added load $D_t$ first uses output that was being curtailed in that slot; the rest raises thermal output.
- Added solar and wind output $N_t$ first lowers thermal output down to the floor; the rest is curtailed.

With $T_t$ the recorded thermal output, $C_t$ the recorded curtailment and $n_t = D_t - N_t$:

```math
\begin{aligned}
r_t &= \begin{cases} \max(T_t - F, 0) & C_t = 0 \\ 0 & C_t > 0 \end{cases} && \text{room to turn down} \\
a_t &= \min(\max(n_t, 0),\ C_t) && \text{curtailed output that the added load uses} \\
d_t &= \min(\max(-n_t, 0),\ r_t) && \text{thermal output that the added plants replace} \\
T'_t &= T_t + \max(n_t, 0) - a_t - d_t, \qquad C'_t = C_t - a_t + \max(-n_t, 0) - d_t .
\end{aligned}
```

With $D = N = 0$ the replay returns the records. In every slot $T'_t - C'_t - (T_t - C_t) = n_t$: energy is conserved.

**The floor.** $F$ is read from the same records: the low end (10th percentile) of thermal output in the slots in which solar or wind was curtailed, 514 MW in FY2024 and 540 MW in FY2025. The low end is used and not the median, because output is also curtailed for reasons other than a surplus in the whole area: in FY2025 solar or wind was curtailed at thermal outputs anywhere between 325 and 2,104 MW. The lowest thermal output of the year (364 and 325 MW) is the second case. The truth lies in how the operator commits plants hour by hour, which the replay does not model.

Two questions are answered with it:

1. **One data center.** *Existing plants:* $D_t = L_t$, $N_t = 0$ (the contract buys from plants that already exist). *New plants:* $D_t = L_t$, $N_t = G_t$ (the contract causes that much solar and wind to be built).
2. **The area as both grow.** $D_t$ is a constant added load and $N_t = (k - 1)(S_t + W_t + C_t)$: today's solar and wind fleets grown by a factor $k$, counting what they could have produced. The *break-even load* is the $D$ at which thermal generation over the year equals today's.

## 5. The cheapest portfolio for a target match

Which contract and battery reach a target share $\theta$ of matched energy at the lowest yearly cost? With $x_s, x_w$ the solar and wind volumes, $p$ and $e$ the battery's power and capacity, $m_t$ the matched power, $c_t$ and $q_t$ charging and discharging, $b_t$ the stored energy, $h = 0.5$ hours and $\rho = \sqrt{\eta}$:

```math
\begin{aligned}
\min\ & c_s x_s E + c_w x_w E + k_p\, p + k_e\, e \\
\text{s.t.}\ & m_t + c_t - q_t \le x_s \hat s_t + x_w \hat w_t && \text{use and charging come from the contract and the battery} \\
& b_{t+1} = b_t + (\rho\, c_t - q_t / \rho)\, h && \text{the last slot leads back to the first} \\
& 0 \le m_t \le L_t, \quad 0 \le c_t, q_t \le p, \quad 0 \le b_t \le e, \quad e \ge \delta\, p \\
& \textstyle\sum_t m_t \ge \theta \sum_t L_t
\end{aligned}
```

$E$ is the load's yearly energy, $c_s$ and $c_w$ are contract prices per MWh, $k_p$ and $k_e$ the yearly cost of battery power and capacity, and $\delta$ the shortest duration a battery is built for. The contract is paid for everything it generates; the surplus earns a set value (zero by default). The energy that is not matched is bought from the grid whatever the portfolio, so it does not change which portfolio is cheapest for a given target. A fiscal year is a linear program with about 70,000 variables and 88,000 rows; HiGHS solves it in half a minute to a minute.

## 6. Results (a constant load of 100 MW, 876 GWh a year)

From `scripts/export_matching.py` on 2026-11-26.

**A contract for exactly the yearly use (volume 1).**

| Contract | Matched, FY2024 | Matched, FY2025 | Worst 7 days (FY2025) | Longest run below 10 % (FY2025) |
|---|---|---|---|---|
| Solar only | 40.6 % | 40.6 % | 23.1 % | 17.5 h |
| Wind only | 72.4 % | 72.8 % | 18.4 % | 24.0 h |
| The area's mix (51 % solar) | 68.4 % | 68.9 % | 46.0 % | 12.5 h |
| Best mix (20 % solar, 80 % wind) | 75.6 % | 76.6 % | | |

**What raises the match** (the area's mix; FY2024 / FY2025).

| Lever | Setting | Matched |
|---|---|---|
| More volume | 1.5 times the yearly use | 78.9 / 79.5 % |
| | 2 times | 84.3 / 84.8 % |
| | 3 times | 89.7 / 89.8 % |
| | 5 times | 93.9 / 93.6 % |
| A battery (volume 1, power equal to the load, 85 % round trip) | 2 hours of the load | 74.9 / 75.5 % |
| | 4 hours | 79.9 / 80.7 % |
| | 8 hours | 84.7 / 85.8 % |
| | 24 hours | 88.2 / 88.8 % |
| Shifting work within the day (volume 1) | 10 % of the work, 10 % spare equipment | 71.5 / 72.0 % |
| | 20 % of the work, 25 % spare equipment | 75.3 / 75.8 % |
| | 50 % of the work, 100 % spare equipment | 84.6 / 85.3 % |

**On the grid** (the area's mix).

| Case | FY2024 | FY2025 |
|---|---|---|
| Existing plants: extra thermal generation, as a share of the energy used | 99.9 % | 98.9 % |
| Curtailed solar and wind the load could have used, as a share of its use | 0.13 % | 1.10 % |
| New plants, volume 1: change in thermal generation, as a share of the energy used (floor from the records / lowest of the year) | +0.8 / +0.2 % | +2.4 / +1.6 % |
| New plants, volume 1.5 | −47.6 / −49.0 % | −44.1 / −46.5 % |
| New plants, volume 2 | −94.9 / −97.4 % | −89.3 / −93.7 % |

**The area as both grow** (floor from the records / lowest of the year).

| Solar and wind | Break-even constant load, FY2024 | FY2025 | Share of their output curtailed with no added load, FY2024 | FY2025 |
|---|---|---|---|---|
| ×1.5 | 341 / 345 MW | 345 / 353 MW | 2.6 / 1.8 % | 4.6 / 3.1 % |
| ×2 | 656 / 668 MW | 657 / 678 MW | 9.2 / 7.5 % | 12.3 / 9.7 % |
| ×3 | 1,201 / 1,231 MW | 1,199 / 1,245 MW | 23.9 / 21.6 % | 27.5 / 24.0 % |

What the numbers say:

1. **"100 % by the year" is about two thirds by the slot.** A contract for the yearly use, shaped like the area's fleets, covers 68 to 69 % of the energy in the slot it is used. Solar alone covers 41 %, wind alone 72 to 73 %, and the best mix (about 80 % wind) 76 to 77 %. The two years agree within one point.
2. **Every lever has diminishing returns.** Twice the volume gives 84 to 85 %, five times 94 %. A battery of four hours gives 80 to 81 % and a full day 88 to 89 %: the days of weak wind in a row are beyond a battery. Moving a fifth of the day's work, with a quarter more equipment, gives 75 to 76 %, and the equipment is then used 80 % of the time.
3. **Buying from existing plants changes nothing on the grid.** With no new plant, thermal plants cover 98.9 to 99.9 % of what the data center uses. The curtailed output a 100 MW load could have used was 0.1 % of its use in FY2024 and 1.1 % in FY2025: there is little unused renewable energy in the area today.
4. **Today, new plants matter more than the slot match.** If the contract causes solar and wind of the same yearly volume to be built, thermal generation in the area rises by only 0.2 to 2.4 % of what the data center uses, although the slot match is still 69 %. When the contract has a surplus, thermal plants turn down for everyone else.
5. **That stops being true as solar and wind grow.** With twice today's solar and wind and no added load, 8 to 12 % of their output would be curtailed in this replay, and with three times, 22 to 28 %. Then a surplus is wasted more often, and the slot match (storage, shifting, mix) starts to decide what a contract achieves.
6. **Growth on both sides.** Twice today's solar and wind makes room for about 660 to 680 MW of round-the-clock load before thermal generation is back at today's level; one and a half times, for about 340 to 350 MW; three times, for about 1,200 to 1,250 MW. Data-center growth beyond that raises thermal generation unless other carbon-free supply is added.

## 7. Inputs and where they come from

| Input | Value | Kind | Basis |
|---|---|---|---|
| Area demand and supply by kind, 30-minute | FY2024 and FY2025, 17,520 slots each | Published measurement | Hokkaido Electric Power Network [65]; used unchanged; checked for gaps and for supply = demand |
| Data-center load | constant; 100 MW in the tables | Assumption | No public load profile of a commercial data center was found. A constant load is the reference case; results scale with the size except where curtailment is involved |
| Shape of contracted solar and wind | the area's fleets, slot by slot | Derived from the records | Optimistic for a single plant, which varies more than the whole area |
| Solar share of the area's mix | 51 % (FY2024), 52 % (FY2025) | Derived from the records | Solar energy / (solar + wind energy) |
| Battery round-trip efficiency | 85 % | Assumption | see [docs/data-sources.md](../data-sources.md#renewable-matching-theme-4) |
| Battery power in the counting tables | equal to the load | Assumption | A battery sized to carry the whole load |
| Thermal floor | 514 MW (FY2024), 540 MW (FY2025); second case 364 and 325 MW | Derived from the records | 10th percentile of thermal output in the slots with curtailed solar or wind; second case: the lowest output of the year |
| Contract prices, battery cost and life | see the cost table | Published figures and assumptions | [docs/data-sources.md](../data-sources.md#renewable-matching-theme-4) |

## 8. Limits

- **A replay, not a dispatch model.** Section 4 keeps hydro, pumped storage, the interconnection and plant commitment as recorded. In reality they would respond, mostly in the direction of less curtailment. There are no network limits.
- **One floor for the year.** The level thermal plants can turn down to depends on which units run and on reserve needs. The two cases bracket it only roughly.
- **The area's fleet as the contract.** A single plant, or a new offshore wind farm, has a different shape from today's fleet.
- **A constant load.** Real data centers vary with their work. AI training and inference may follow different patterns.
- **No nuclear in the records.** If a nuclear unit returns, the room for solar and wind and the response to added load both change.
- **Two years.** FY2024 and FY2025 agree closely on the counts, but curtailment differs by a factor of six between them.
- **Costs.** The linear program's result depends on the prices put in; the volumes and battery sizes are more robust than the yen figures.

## 9. Next

- Measured load profiles of data centers, and plant-level renewable profiles, in place of the two assumptions above.
- A dispatch model of the area (thermal commitment, pumped storage, the interconnection) in place of the replay.
- Emissions: the records split thermal output by fuel, so an hourly emission rate of the area can be estimated and compared with the yearly factor used in theme 1.
- The waste-heat credit of theme 1 on the same footing: fuel replaced by waste heat next to the electricity the data center uses.
- The older hourly records (FY2016 to FY2023) for the variation from year to year.
- The link to themes 2 and 3: a site and a connection that let a data center use output that would otherwise be curtailed.

## Reproduce

```bash
uv run python -m dcopt.matching.records 2024 2025      # download the records (24 files, about 4 MB)
uv run python scripts/export_matching.py               # the numbers in this page -> results/matching/
uv run python scripts/export_matching.py --portfolio   # with the linear programs (several minutes)
uv run streamlit run app/streamlit_app.py              # page "Renewable matching"
uv run pytest tests/test_matching.py tests/test_matching_app.py
```

Reference numbers in square brackets point to the list in the [README](../../README.md#references).
