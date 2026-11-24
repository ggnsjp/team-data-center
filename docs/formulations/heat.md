# Theme 1: waste-heat network design

The complete formulation, with every coefficient and worked numbers, is in [heat-model.md](heat-model.md).

The model decides which heat users to connect to which data center, along which streets and with which pipes. It maximizes the value of the heat delivered minus the annualized pipe cost.

## Prototype formulation (v1)

**Sets.** Node $0$ is the data center. $U$ is the set of users. The candidate street links $E$ are each node's 3 nearest neighbours by road distance plus direct links from the data center, all within 8 km. The arcs $A$ are both directions of each link. The months are $T = \lbrace 1,\dots,12\rbrace$.

**Data.**
- $\ell_e$: road length of link $e$
- $p$: pipe cost per metre
- $\mathrm{CRF}$: capital recovery factor (3 %, 30 years)
- $D_{ut}$: demand of user $u$ in month $t$
- $W_t$: recoverable waste heat in month $t$
- $\mathrm{COP}$: coefficient of performance of the heat pump
- $v$: value per MWh delivered, equal to the avoided kerosene cost minus the heat-pump electricity cost

**Variables.**
- $y_e \in \lbrace 0,1\rbrace$: build link $e$
- $x_u \in \lbrace 0,1\rbrace$: connect user $u$
- $g_{ua} \in [0,1]$: flow of user $u$'s commodity on arc $a$
- $s_{ut} \ge 0$: heat delivered to $u$ in month $t$

```math
\max \; \sum_{u \in U}\sum_{t \in T} v\, s_{ut} \;-\; \sum_{e \in E} \mathrm{CRF}\, p\, \ell_e\, y_e
```

subject to
- **flow balance** for each user's commodity: one unit leaves node 0 and reaches $u$ when $x_u = 1$;
- $g_{u,(i,j)} + g_{u,(j,i)} \le y_e$ for each user $u$ and link $e = \lbrace i,j\rbrace$ (strong linking);
- $s_{ut} \le D_{ut}\, x_u$ for each user and month;
- $\sum_{u} (1 - 1/\mathrm{COP})\, s_{ut} \le W_t$ for each month (waste heat available).

This is a prize-collecting Steiner tree with monthly capacities, written in multi-commodity form, and solved with HiGHS.

**Baseline.** Score each user alone, with its own pipe from the data center, and take the best five ("top-5 pairs"). On the prototype data, the network gave 2.1 to 3.4 times the annual net benefit of the top-5 pairs across the price and pipe-cost cases tried.

## Version 2 (`dcopt.heat.network`)

**Sets.**
- $D$: data centers — Ishikari RE DC No. 1, Sakura, KCCS ZED, and NTT-ME (planned).
- $U$: users.
- $E$: candidate links. Each user links to its nearest data center, data centers link to each other, and each node links to its nearest neighbours.
- $K$: pipe sizes DN50, 80, 100, 150, 200, 250.
- $T$: months.
- $\Omega$: scenarios, with probabilities $p_\omega$.

**First stage.**
- $y_{ek} \in \lbrace 0,1\rbrace$: build link $e$ with size $k$.
- $x_u \in \lbrace 0,1\rbrace$: connect user $u$.
- $z_{ud} \in \lbrace 0,1\rbrace$: user $u$ is served by data center $d$.
- $g_{ua} \in [0,1]$: share of $u$'s commodity on arc $a$.

**Second stage.** $s_{udt\omega} \ge 0$ is the heat delivered from $d$ to $u$ in month $t$ under scenario $\omega$.

**Net benefit per scenario.**
```math
\mathrm{net}_\omega = \sum v_{u\omega}\, s_{udt\omega} - \mathrm{CRF} \sum c_k \ell_e y_{ek} - \mathrm{CRF}_{hp} \sum h_u x_u
```

**Objectives.**
- Expected: $\max \sum_\omega p_\omega\, \mathrm{net}_\omega$.
- Worst case: $\max \eta$ subject to $\eta \le \mathrm{net}_\omega$ for every $\omega$.
- Minimum of the maximum regret: $\min \rho$ subject to $\rho \ge \mathrm{OPT}_\omega - \mathrm{net}_\omega$ for every $\omega$.

**Constraints.**
- Flow of $g_u$: out minus in equals $z_{ud}$ at data center $d$, $-x_u$ at the user, and $0$ elsewhere.
- One data center per user: $\sum_d z_{ud} = x_u$.
- Link by size: $g_{u,(i,j)} + g_{u,(j,i)} \le \sum_{k:\,\mathrm{cap}_k \ge q_u} y_{ek}$.
- At most one size per link: $\sum_k y_{ek} \le 1$.
- Pipe capacity: $\sum_u q_u (g_{u,(i,j)} + g_{u,(j,i)}) \le \sum_k \mathrm{cap}_k\, y_{ek}$.
- Delivery only to the assigned data center: $s_{udt\omega} \le \mathrm{cap}_{ut}\, z_{ud}$.
- Waste heat per data center: $\sum_u r_u\, s_{udt\omega} \le W_{dt\omega}$.

**Temperature modes.**
- *Ambient:* a loop at about 30 °C with ΔT 10 K and 2 % heat loss.
  - Each user has its own heat pump, with COP = 0.5 × Carnot from 25 °C, capped at 8.
  - Users that need 27 °C or less take the heat directly.
- *Central:* the network runs at 60 °C, with ΔT 30 K, COP 4.76 and 8 % heat loss.

**Robust version.**
- Uncertainty set: at most $\Gamma$ data centers run at the low end of their IT-load range.
- Solved by column-and-constraint generation:
  - the master problem is the worst-case model over the corners found so far;
  - the subproblem evaluates every corner, one LP each.
- The kerosene price stays outside the budget; its effect is shown through regret.

**Solving.**
- HiGHS is the default; Gurobi is optional (`DCOPT_SOLVER=gurobi`).
- Pipe sizing weakens the LP bound, so the full MILP does not close in 60 s.
- The default method is an LP-guided kernel search: solve the LP relaxation, then solve the MILP restricted to the links the LP uses plus each data center's own plan.
- Every plan is then re-evaluated with exact recourse.
- The gaps against HiGHS bounds are 13–21 %, so **the plans are not certified optimal**. Gurobi reaches 4.7–9 % in 60 s.

**Check against v1.** Restricted to one data center, one large pipe size at 100,000 yen/m, COP 4 and no loss, version 2 reproduces version 1 exactly: 15 sites, 16.1 km, 137.5 M yen/year.

### Results so far (50 candidate sites, heat-pump investment included)

Four scenarios with equal weights: IT load low or high, crossed with kerosene at 115 or 156.8 yen/L. ZED's low IT load is 0.9 MW, from the city's plan. Heat pumps cost 150 M yen/MW at the users (an assumption) and 100 M yen/MW centrally (Odense data). Values are annual net benefits in million yen. The run logs are in `results/` (commit 2d3b342).

| Mode | Plan | Sites | Pipe km | Expected | Worst case | Max regret | Payback |
|---|---|---|---|---|---|---|---|
| ambient | stochastic | 13 | 7.8 | 93.8 | 55.4 | 18.4 | 10.6 y |
| ambient | worst case | 5 | 3.2 | 79.1 | 59.7 | 52.2 | 6.1 y |
| ambient | min-max regret | 13 | 7.9 | 91.5 | 51.5 | 17.9 | 10.6 y |
| central | stochastic | 15 | 8.0 | 81.5 | 34.6 | 6.7 | 10.5 y |
| central | worst case | 12 | 5.5 | 70.3 | 36.7 | 31.2 | 9.1 y |
| central | min-max regret | 17 | 8.4 | 81.1 | 32.2 | 5.1 | 10.8 y |

- **Without heat-pump investment,** the stochastic plans reach 149.5 (ambient, 19 sites) and 152.1 (central, 25 sites).
- **Value of the stochastic solution:** ambient 4.4 with the seeded candidate links and 28.7 without them (an earlier run reported 14.8, a different search draw; see the replication note under the weather years); central 0.0. **Expected value of perfect information:** ambient 8.3 with the committed recipe (10.0 reported earlier); central 3.9.
- **At today's kerosene price** (156.8 yen/L), the ambient plan connects 16 sites with 10.7 km and earns 140.3.
- **Check against v1:** v2 restricted to v1 gives 159.3, against 159.8 for v1, within the solver's 5.6 % gap (24 sites, 18.6 km).

**Each data center on its own: optimized network vs the top-5 pairs** (expected net)

| Data center | Ambient, optimized | Ambient, pairs | Central, optimized | Central, pairs |
|---|---|---|---|---|
| No. 1 | 91.3 | 65.3 | 80.6 | 40.4 |
| Sakura | 85.7 | 58.4 | 75.4 | 37.2 |
| ZED | 58.2 | 50.0 | 39.9 | 30.8 |
| NTT-ME (planned) | 3.8 | 0.8 | 0.0 | 0.0 |

**Robust sweep over Γ** (kerosene at 115 yen/L; column-and-constraint generation):
- *Ambient.* The Γ = 0 plan earns 66.0: five sites on ZED and road heating on the planned NTT-ME. Its worst case is 32.3 at Γ = 1 (ZED low) and −0.7 at Γ = 2 (ZED low and NTT-ME not built). The plan for every Γ ≥ 1 serves the same five sites from No. 1 and keeps 59.7 in every case. Its price of robustness is 9.7 %.
- *Central.* The Γ = 0 plan earns 38.0 with twelve sites on ZED, and its worst case is −1.4. The robust plan, eleven sites on No. 1, keeps 37.3 at a price of 1.8 %.

**Solver comparison** (`experiments/solver_compare`; the full expected-value MILP; cold start; 16 threads; values and bounds in million yen):

| Candidate links | Mode | Solver | Time limit | Value | Bound | Gap | Status |
|---|---|---|---|---|---|---|---|
| standard | ambient | HiGHS 1.16 | 300 s | 79.7 | 96.8 | 17.7 % | time limit |
| standard | ambient | Gurobi 14.0 | 300 s | 88.24 | 88.24 | 0 % | optimal in 70.8 s |
| standard | central | HiGHS 1.16 | 300 s | 68.3 | 92.6 | 26.3 % | time limit |
| standard | central | Gurobi 14.0 | 300 s | 82.00 | 82.00 | 0 % | optimal in 255 s |
| direct links to every data center | ambient | HiGHS 1.16 | 600 s | 66.1 | 106.7 | 38.1 % | time limit |
| direct links to every data center | ambient | Gurobi 14.0 | 600 s | 92.36 | 93.74 | 1.5 % | time limit |
| direct links to every data center | central | HiGHS 1.16 | 600 s | 60.1 | 93.9 | 36.1 % | time limit |
| direct links to every data center | central | Gurobi 14.0 | 600 s | 82.16 | 85.52 | 3.9 % | time limit |

The HiGHS kernel-search plans reach 88.08 and 81.31 on the standard links. That is within 0.18 % and 0.83 % of the proven optimum.

### Weather years: 50 years of daily JMA observations (`experiments/weather_years`)

The four published scenarios differ only on the supply side (IT load, kerosene price); demand is the same in all of them. This study adds demand-side uncertainty: 50 years (1976–2025) of daily JMA observations for Sapporo, station 47412 [12], fetched by `dcopt.heat.weather` into `data/jma/` (the CSVs ship with the repo) and turned into monthly demands with per-kind daily weights. The 30-year normals reproduced the sourced constants within 0.05 °C and 7.5 cm of annual snowfall. Weather spread: heating-degree-day index 0.913 (2023) to 1.142 (1984) and snowfall index 0.504 (1989) to 1.456 (2000) against the normals. Run: `uv run python experiments/weather_years/run.py ambient both --bound`; results in `results/weather_years/20261124-155559` (commit 5325afe). Values are annual net benefits in million yen; unmet demand is the share of the 50 candidate sites' total demand the plan does not serve (dominated by unconnected sites — the year-to-year movement is the weather signal).

**Stage A — 50 weather years, IT high, 156.8 yen/L:**

| Plan | Sites | Pipe km | Expected | Worst year | Unmet, expected → worst year |
|---|---|---|---|---|---|
| stochastic on the 50 years | 15 | 6.2 | 116.6 | 105.9 | 73.2 → 74.7 % |
| plan for the mean weather year, evaluated on the 50 years | 18 | 11.7 | 149.7 | 118.2 | 56.0 → 57.4 % |
| published 4-scenario plan, evaluated on the 50 years | 13 | 7.8 | 133.5 | 108.2 | 70.7 → 72.4 % |

**Stage B — 10 stratified years × the 4 published levels (40 scenarios):**

| Plan | Sites | Pipe km | Expected | Worst year |
|---|---|---|---|---|
| stochastic on the 40 scenarios | 10 | 5.2 | 84.8 | 49.6 |
| mean-scenario plan evaluated on the 40 | 13 | 7.8 | 83.7 | 30.1 |
| published 4-scenario plan evaluated on the 40 | 13 | 7.8 | 93.3 | 44.0 |

The published mean-scenario plan scores within 0.5 of the published stochastic plan on both sets (134.0 / 108.7 and 89.2 / 37.9).

**What the weather years say.**
- The published plan is robust to real weather. Built without any daily data, it earns 133.5 expected (108.2 in its worst year) on the 50 real years at the high kerosene price, and its unserved share grows only from 70.7 to 72.4 % from the average to the worst year.
- **A cross-set VSS is not identifiable in the current formulation.** The deliverable-capacity cap is derived from the scenario set's design peak ($\alpha$ times the worst month of the worst scenario) and is the same for every candidate build, while pipe sizes gate connectivity all-or-nothing. With demand-side spread this excludes builds the narrower set would allow: on the 50-year set the design peak is 21.5 % above the mean-year peak, 5 users climb a pipe size and 2 exceed the largest pipe (DN250) and are dropped rather than partially served. The decisive check: the LP bound of the 50-year first-stage model is 134.4, below the mean-built plan's evaluated 149.7 — that plan is provably outside the model's feasible set, so the apparent "VSS −33.1" is a formulation artifact, not a planning result. The published numbers are unaffected: their four scenarios have identical demand, so the convention never bound there.
- Within one set the comparison is legitimate: on the 40-scenario stage the LP bound (94.4) admits the mean-built plan, and the stochastic plan's edge is 1.1 with kernel gaps 11.2 / 18.7 % — directionally positive but not certified.
- **Replication inside the run:** the published RP reproduces exactly (93.8, 13 sites, 7.8 km). The published EEV 79.0 does not: the committed recipe gives **89.4** (VSS 4.4) — on this tree and on the publication commit `f83f7a3` alike (`uv run python experiments/heat_v2_compare/run.py --modes ambient --skip-rank` prints `EEV 89.4M` there; the same run's EVPI reads 8.3 against the published 10.0), and a 30 s limit returns the same 89.4. What moves the number is the candidate-link set: without the seeded per-data-center links the same EV solve evaluates to **65.1** (VSS 28.7). Both draws are recorded in `results.json` (`published_replication.eev_recipe`). The EV plan is one draw of a time-limited kernel search, and the published 79.0 sits between the no-seeds and seeded draws — a different search draw or solver environment upstream, not a different formula. The RP is robust to all of this; the EEV/VSS/EVPI triplet is not.

**Caveats.** Kernel gaps on the wide sets are 11–19 %: no plan here is certified optimal. Demands remain HDD-scaled annual estimates — daily resolution sharpens the winter shape of demand, not the underlying user data. The design-day peak (the daily data's sharpest signal) is computed (`daily_peak_mw`) but deliberately unused: using it consistently requires tying deliverable capacity to the built pipe size.

**What the results say.**
- Small or planned data centers are where uncertainty bites. A robust plan moves users to the large, operating center at a small price.
- Planning for the average scenario costs 4.4 to 28.7 a year against the stochastic plan in ambient mode, depending on the candidate links of the search; the earlier 14.8 was a single search draw.
- With heat pumps paid for, the ambient loop beats the central heat pump (93.8 against 81.5).

**Caveats.**
- Optimality: certified by Gurobi on the standard candidate links. With direct links to every data center the remaining gaps are 1.5–3.9 % (Gurobi, 600 s).
- Data-center positions are approximate or placeholders. Several users are assumed sites, and demand per building type is an assumption.
- The model has monthly energy balances only, with a flat heat-loss share.
- The largest pipe (DN250) carries 4.6 MW in ambient mode.

### CO2 and policy scenarios (`experiments/heat_policy`)

The formulas are in [heat-model.md](heat-model.md#12-co2-and-policy-scenarios). A carbon price $\pi$ adds $\pi$ times the CO₂ avoided to the value of the heat; a subsidy $\phi$ leaves the project $(1-\phi)$ of every annuity. Both are scenarios. The carbon prices 1,700 and 4,300 yen/t are the lower and upper reference prices of Japan's emissions trading scheme for FY2026; the subsidy rates 1/3, 1/2 and 2/3 are those of programmes that name such equipment (sources in [data-sources.md](../data-sources.md)).

**How the comparison is kept fair.** The plans come from a heuristic search, and a search can land on different plans for reasons that have nothing to do with the policy. A first version of this experiment showed it: with more candidate links, the no-policy plan came out worse (83.9 instead of 93.8), a difference as large as the policy effects. The experiment therefore gives every policy the same chances:
1. *Candidate links.* The links of the published plan, plus the links of each data center's own plan under the strongest carbon price and the strongest subsidy. The same 160 links for every policy.
2. *Pool.* Kernel search for every policy, once on the published links and once on all of them.
3. *Cross-evaluation.* Every build in the pool is evaluated under every policy (pipes fixed, deliveries re-optimized), and each policy takes the best build for its own objective.
4. *Polish.* The full MILP on all candidate links, started from that build, with a time limit; the polished builds join the pool and step 3 is repeated.

After step 4 no policy would prefer another policy's plan. The no-policy plan then has the largest plain net benefit, and the cost of the extra tonnes cannot be negative.

**Best plans found** (ambient loop; Gurobi 14.0, 300 s of polish per policy; money in M yen per year unless noted):

| Carbon price (yen/t) | Subsidy | Sites | Pipe (km) | CO₂ avoided, t/yr: Hokkaido Electric / FY2030 level / renewable | Investment (100 M yen) | Subsidy (100 M yen) | Carbon value | Net to the project | Plain net | Cost of the extra tonnes (yen/t) | Subsidy per extra tonne (yen/t) | Gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 13 | 7.8 | 3,927 / 4,277 / 4,594 | 23.0 | 0 | 0 | 93.8 | 93.8 | — | — | 5.5 % |
| 1,700 | 0 | 13 | 7.8 | 3,927 / 4,277 / 4,594 | 23.0 | 0 | 6.7 | 100.5 | 93.8 | — | — | 8.0 % |
| 4,300 | 0 | 14 | 9.8 | 4,874 / 5,362 / 5,804 | 32.8 | 0 | 21.0 | 111.3 | 90.4 | 3,618 | — | 11.4 % |
| 10,000 | 0 | 16 | 10.7 | 5,198 / 5,774 / 6,297 | 36.6 | 0 | 52.0 | 139.6 | 87.6 | 4,841 | — | 9.9 % |
| 20,000 | 0 | 19 | 11.9 | 5,725 / 6,383 / 6,979 | 43.0 | 0 | 114.5 | 195.6 | 81.1 | 7,071 | — | 9.0 % |
| 0 | 1/3 | 19 | 11.9 | 5,725 / 6,383 / 6,979 | 43.0 | 14.3 | 0 | 160.6 | 81.1 | 7,071 | 44,247 | 7.7 % |
| 0 | 1/2 | 30 | 24.2 | 7,922 / 9,020 / 10,014 | 79.0 | 39.5 | 0 | 227.4 | 9.8 | 21,012 | 54,450 | 4.3 % |
| 0 | 2/3 | 33 | 27.8 | 8,107 / 9,231 / 10,248 | 84.2 | 56.1 | 0 | 301.0 | −7.6 | 24,246 | 73,825 | 4.9 % |
| 4,300 | 1/2 | 30 | 24.2 | 7,922 / 9,020 / 10,014 | 79.0 | 39.5 | 34.1 | 261.5 | 9.8 | 21,012 | 54,450 | 3.5 % |

- *Net to the project* is what the plan's owners see under the policy; *plain net* is the same plan with no policy money.
- *Cost of the extra tonnes* is (plain net of the no-policy plan − plain net of this plan) / (extra CO₂ avoided, with heat pumps on Hokkaido Electric's standard power).
- *Subsidy per extra tonne* is the subsidy as an annuity (the same factors as the costs) divided by the extra CO₂ avoided. It is high because part of a subsidy pays for pipes that would be built anyway.
- *Gap* is the distance of the plan to the best bound of the full MILP on the candidate links. The plans are the best found, not proven optima.

**The same experiment with HiGHS alone** (120 s of polish per policy):

| Carbon price (yen/t) | Subsidy | Sites | Pipe (km) | CO₂ avoided, t/yr (Hokkaido Electric) | Net to the project | Plain net | Gap | Net against the table above |
|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 13 | 7.8 | 3,927 | 93.8 | 93.8 | 12.0 % | the same plan |
| 1,700 | 0 | 13 | 7.8 | 3,927 | 100.5 | 93.8 | 13.3 % | the same plan |
| 4,300 | 0 | 13 | 7.8 | 3,927 | 110.7 | 93.8 | 14.5 % | −0.6 % |
| 10,000 | 0 | 20 | 12.9 | 5,818 | 134.9 | 76.7 | 16.2 % | −3.4 % |
| 20,000 | 0 | 20 | 12.9 | 5,818 | 193.1 | 76.7 | 11.6 % | −1.3 % |
| 0 | 1/3 | 20 | 12.9 | 5,818 | 159.5 | 76.7 | 9.7 % | −0.7 % |
| 0 | 1/2 | 31 | 25.5 | 7,983 | 224.9 | 1.4 | 6.1 % | −1.1 % |
| 0 | 2/3 | 31 | 25.5 | 7,983 | 299.4 | 1.4 | 6.1 % | −0.5 % |
| 4,300 | 1/2 | 31 | 25.5 | 7,983 | 259.2 | 1.4 | 5.3 % | −0.9 % |

What the tables say:
- **The no-policy plan pays for itself.** It avoids 3,927 t a year with a net benefit of 93.8; a tonne avoided costs −23,883 yen. Both solvers return this plan, and it is the published one.
- **A carbon price moves the plan slowly.** The lower reference price changes nothing. The upper one adds one site in the best plan found; HiGHS keeps the 13-site plan there, which is 0.6 % worse under that price. Even 20,000 yen/t reaches only 19 or 20 sites.
- **A subsidy moves it much more.** With half of the investment subsidized the plan has 30 or 31 sites and avoids twice the CO₂. With two thirds the best plan no longer covers its full cost without the subsidy (plain net −7.6).
- **The extra tonnes cost real resources:** 3,600 to 7,100 yen per tonne under a carbon price, 21,000 to 24,000 yen under the larger subsidies.
- **The solvers agree on the picture and differ at the margin.** HiGHS's plans are within 3.4 % of the best found. Which site joins first, and at which price, is therefore not settled by HiGHS alone.

Run: `uv run python experiments/heat_policy/run.py` (HiGHS, about 12 minutes on 8 processes); `DCOPT_SOLVER=gurobi DCOPT_THREADS=4 uv run python experiments/heat_policy/run.py --workers 3 --polish 300` for the first table. The runs behind the tables were made on 2026-11-25.

## Open questions

- What are the temperature and the recoverable share of waste heat for each cooling type in the Ishikari data centers?
- What are the heat losses and the installed cost of buried pipes in Hokkaido? What do heat pumps cost?
- Can a stronger pipe-sizing formulation (cut-set inequalities, Benders cuts) let HiGHS certify the plans?
- How should deliverable capacity be tied to the built pipes (a per-user path bottleneck) so that plans built on different scenario sets compare cleanly? That would also make design-day sizing usable with the daily weather data.
- Can topology, temperature mode and heat-pump placement be co-optimized at street scale? We did not find this in the literature.
- How should the cost of a shared trunk be split fairly? The Shapley value on the fixed tree can be compared with the least core when each coalition's network is re-optimized, with the prize-collecting Steiner tree as the separation problem.
- Two-stage robust design under budgeted IT-load uncertainty, including planned data centers: we did not find a published network design of this kind.
