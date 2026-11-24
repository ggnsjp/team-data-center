# Theme 1: the waste-heat network model, in full

This page states the model in `src/dcopt/heat/network.py` (version 2) completely: every set, coefficient, variable, constraint and objective, how each coefficient is computed, and worked numbers. Results are in [heat.md](heat.md). Reference numbers in square brackets point to the list in the [README](../../README.md#references).

**In one sentence.** Choose which streets get a pipe and of which size, which users connect and to which data center, and how much heat each user receives each month, so that the value of the kerosene replaced, minus heat-pump electricity and the annualized cost of pipes and heat pumps, is as large as possible: in expectation over scenarios, in the worst scenario, or with the smallest regret.

**Structure.** It is a mixed-integer linear program:
- a prize-collecting Steiner network [23, 24] in strong multi-commodity form, with discrete pipe sizes and several sources;
- twelve monthly heat balances per scenario;
- a first stage (the network) and a second stage (monthly deliveries), which makes it a two-stage stochastic program, or a two-stage robust program with a budgeted uncertainty set [31, 32, 34].

## 1. Sets and indices

| Symbol | Meaning |
|---|---|
| $\mathcal D$ | data centers (heat sources): Ishikari RE DC No. 1, Sakura, KCCS ZED, NTT-ME (planned) |
| $\mathcal U$ | heat users (candidate sites) |
| $\mathcal N = \mathcal D \cup \mathcal U$ | nodes; $n(u)$ is user $u$'s node |
| $\mathcal E$ | candidate links $e=\lbrace i,j\rbrace$ between nodes, each a shortest road path |
| $\mathcal A$ | arcs: both directions $(i,j)$ and $(j,i)$ of every link |
| $\delta^+(i), \delta^-(i)$ | arcs leaving and entering node $i$ |
| $\mathcal K$ | pipe sizes DN50, DN80, DN100, DN150, DN200, DN250 |
| $\mathcal T = \lbrace 1,\dots,12\rbrace$ | months |
| $\Omega$ | scenarios $\omega$ with probabilities $p_\omega$ |

**Candidate links.** Each node is linked to its $k=3$ nearest nodes by road distance. Each user is also linked to its nearest data center, and the data centers are linked to each other. Links longer than 8 km are dropped. With 4 data centers and 50 users this gives about 150 links.

## 2. Coefficients and how they are computed

### 2.1 Monthly demand

Each user $u$ of kind $\kappa(u)$ has an annual heat demand $A_u$ (MWh/yr): a default per kind, or floor area × intensity for greenhouses (0.40 MWh/m²/yr) and snow-melting areas (0.12 MWh/m²/yr). All of these are assumptions; see [data-sources.md](../data-sources.md).

The annual demand is spread over the months by a profile $\pi_{\kappa t}$ built from the JMA climate normals for Sapporo, 1991–2020 [12]:

```math
D_{ut} = A_u\,\pi_{\kappa(u),t}, \qquad \sum_t \pi_{\kappa t} = 1 .
```

With mean temperature $\bar\theta_t$, $\mathrm{days}_t$ days in the month and base temperature $T_b$, heating degree-days are

```math
\mathrm{HDD}_t(T_b) = \mathrm{days}_t\,\max(0,\;T_b - \bar\theta_t).
```

| Profile | $\pi_t$ proportional to | Used for |
|---|---|---|
| building | $\mathrm{HDD}_t(18\,^\circ\mathrm C)$ | hospitals, public buildings |
| greenhouse | $\mathrm{HDD}_t(15\,^\circ\mathrm C)$ | greenhouses |
| school | $\mathrm{HDD}_t(18)$, with August × 0.3 | schools |
| pool | $\tfrac12\,\mathrm{days}_t/365 + \tfrac12\,\mathrm{HDD}_t(18)/\sum\mathrm{HDD}(18)$ | pools, baths, hotels |
| snow | monthly snowfall | snow melting |
| flat | $\mathrm{days}_t$ | fish farm, factory |

The month has $h_t = 24\,\mathrm{days}_t$ hours, and the mean load is $\mu_{ut} = D_{ut}/h_t$ (MW).

### 2.2 Design peak and what a connection can deliver

**Design peak.** The design peak is the mean load of the heaviest month times a peak factor $f_\kappa$ (an assumption per kind: greenhouses 2.5, snow 3.0, buildings 1.8–2.0, pools, baths and hotels 1.4, fish farm and factory 1.2):

```math
P_u = f_{\kappa(u)}\,\max_t \mu_{ut}.
```

**Sizing.** Pipes and heat pumps are sized for $c_u = \alpha P_u$, a share $\alpha$ of the peak ($\alpha=1$ by default). The existing boiler covers anything above $c_u$.

**With weather scenarios.** Under the weather-year scenarios the demand itself varies: $\mu_{ut}$ becomes $\mu_{ut\omega}$, aggregated from the daily JMA observations of year $\omega$ with per-kind daily weights. The design peak is then taken over the whole set, $P_u = f_{\kappa(u)}\max_{t,\omega}\mu_{ut\omega}$ — the worst scenario's worst month — and is the same for every candidate build. The deliverable capacity is therefore a property of the scenario set, not of the built pipes; see the Limitations section for what that implies when plans built on different scenario sets are compared.

**Energy deliverable in a month.** Within a month, the hourly load is taken as spread evenly between $\underline L = \mu(1-b)$ and $\overline L = \mu(1+b)$, where $b=\min(f-1,1)$. A connection of size $c$ then delivers the expected value of $\min(L, c)$ over the month:

```math
\bar s_{ut} = h_t \cdot \begin{cases}
\mu_{ut} & c_u \ge \overline L \\
c_u & c_u \le \underline L \\
\dfrac{(c_u^2-\underline L^2)/2 + c_u\,(\overline L-c_u)}{\overline L-\underline L} & \text{otherwise.}
\end{cases}
```

**Example: a pool in January.**
- Demand: $A=800$ MWh/yr and $\pi_{\text{Jan}}=0.139$, so $D=111$ MWh and $\mu = 111/744 = 0.149$ MW.
- Spread: $f=1.4$ gives $b=0.4$, $\underline L = 0.089$ MW and $\overline L = P = 0.209$ MW.
- With $\alpha=1$ the connection delivers all 111 MWh.
- With $\alpha=0.7$ ($c=0.146$ MW) it still delivers $\bar s = 744 \times 0.1326 = 98.6$ MWh, or 89 % of January's demand, from a connection 30 % smaller.

### 2.3 Temperatures, heat pumps and what each MWh costs the network

**Heat-pump COP.** The COP is a fraction $\eta=0.5$ of the Carnot value, capped at 8. Temperatures are in °C and the lift is at least 1 K:

```math
\mathrm{COP}(\theta_h,\theta_c) = \min\Big\lbrace 8,\; \eta\,\frac{\theta_h+273.15}{\max(\theta_h-\theta_c,\,1)}\Big\rbrace .
```

**Two network designs (modes).**
- **Ambient loop.** The loop runs at $\theta_{net}=30$ °C, and each user has its own heat pump. The heat pump lifts from $\theta_{net} - 5$ K $=25$ °C to the user's supply temperature $\theta_u$:
  - greenhouses, schools and public buildings: 45 °C;
  - pools: 40 °C;
  - baths, hospitals, hotels and factories: 60 °C.
  
  A user that needs at most $\theta_{net} - 3$ K $= 27$ °C takes the heat directly: the fish farm (22 °C) and snow melting (25 °C).
- **Central heat pump.** A heat pump at the data center lifts 25 °C to 60 °C for everyone, so $\mathrm{COP} = 0.5 \times 333.15/35 = 4.76$.

Examples in ambient mode: 45 °C gives $0.5\times318.15/20 = 7.95$; 40 °C gives 10.4, capped at 8; 60 °C gives 4.76.

**Coefficients per MWh delivered to user $u$.** These are the electricity $e_u$, the waste heat drawn $r_u$, and the share of the delivered heat that travels through the pipes $\sigma_u$. The network heat loss is $\lambda$ = 2 % (ambient) or 8 % (central).

| Mode and user | $e_u$ (MWh el.) | $r_u$ (MWh waste heat) | $\sigma_u$ (network share) |
|---|---|---|---|
| ambient, heat pump at the user | $1/\mathrm{COP}_u$ | $(1-1/\mathrm{COP}_u)(1+\lambda)$ | $1-1/\mathrm{COP}_u$ |
| ambient, direct use | $0$ | $1+\lambda$ | $1$ |
| central | $(1+\lambda)/\mathrm{COP}$ | $(1+\lambda)(1-1/\mathrm{COP})$ | $1$ |

In ambient mode the pipes carry only the low-temperature part of the heat; the user's heat pump adds the electricity on site.

### 2.4 Value of a delivered MWh

Each MWh delivered replaces kerosene burned in a boiler with efficiency $\eta_b = 0.85$. Kerosene's lower heating value is 9.7 kWh/L, so one MWh replaces $1000/(9.7 \times 0.85) = 121.3$ L. With the kerosene price $p^{ker}_\omega$ (yen/L) and the electricity price $p^{el} = 25$ yen/kWh:

```math
v_{u\omega} = \frac{1000\,p^{ker}_\omega}{9.7\,\eta_b} - 1000\,p^{el}\,e_u \qquad \text{(yen/MWh)}.
```

| Kerosene price | Replaced fuel per MWh | Value, direct use ($e_u=0$) | Value with a COP 8 heat pump ($e_u=0.125$) |
|---|---|---|---|
| 115 yen/L (conservative bulk price, an assumption) | 13,948 yen | 13,948 yen/MWh | 10,823 yen/MWh |
| 156.8 yen/L (survey of 16 Nov 2026 [11]) | 19,018 yen | 19,018 yen/MWh | 15,893 yen/MWh |

**CO₂ avoided.** It is $2.50/(9.7 \times 0.85) = 0.303$ t per MWh. Heat-pump electricity from the grid (0.526 t/MWh) is subtracted in ambient mode; the central heat pump runs on the data center's renewable power.

### 2.5 Pipes

A pipe of size $k$ is a pre-insulated twin pipe with inner diameter $d_k$ (JIS G 3452) and a design velocity $w_k$ (1.0 m/s at DN50, rising to 2.2 m/s at DN250; an assumption). Its capacity at a supply–return difference $\Delta T$ (10 K ambient, 30 K central) is

```math
\bar Q_k = \rho\, w_k\, \frac{\pi d_k^2}{4}\, c_p\, \Delta T \,/\, 1000 \quad \text{(MW)}, \qquad \rho = 990\ \mathrm{kg/m^3},\; c_p = 4.18\ \mathrm{kJ/(kg\,K)}.
```

For example, DN150 has $d=0.1552$ m and $w=1.8$ m/s, so it carries 33.7 kg/s. That is $\bar Q = 1.41$ MW at 10 K and 4.23 MW at 30 K.

Installed cost per metre of route follows a straight line through the 2019 quotes for small networks [15], plus 33 % overhead (an assumption):

```math
c_k = 1.33\,\Big(40{,}000 + (\mathrm{DN}_k - 25)\,\frac{210{,}000}{225}\Big)\ \text{yen/m}.
```

DN150 costs 208,367 yen/m. DN80 costs 121,473 yen/m and carries 0.25 MW (ambient), while DN250 costs 332,500 yen/m and carries 4.62 MW. Per MW carried, the large pipe is about 7 times cheaper.

**Pipe load of a user.** At peak, user $u$ puts this load on every pipe along its path:

```math
q_u = c_u\,\sigma_u\,(1+\lambda) = \alpha P_u\,\sigma_u\,(1+\lambda) \quad \text{(MW)}.
```

### 2.6 Heat pumps, annuities and waste heat

**Heat-pump investment.** The investment for user $u$ is $H_u = c_u \cdot h^{user}$ when the user has its own heat pump (ambient) and $H_u = c_u \cdot h^{central}$ in central mode:
- $h^{user} = 150$ M yen/MW, an assumption for small heat pumps;
- $h^{central} = 100$ M yen/MW, from Odense, where two ammonia heat pumps cost about €0.65 M per MW of heat [16].

**Annuities.** Costs are annualized with the capital recovery factor $\mathrm{CRF}(r,n) = r(1+r)^n/((1+r)^n-1)$ at $r = 3$ %:
- pipes over 30 years: $\mathrm{CRF}_p = 0.0510$;
- heat pumps over 20 years: $\mathrm{CRF}_{hp} = 0.0672$.

**Waste heat.** Data center $d$ in scenario $\omega$ has IT load $L_{d\omega}$ (MW). With a recoverable share $\rho^{rec} = 0.6$ (an assumption), its recoverable waste heat is

```math
W_{dt\omega} = L_{d\omega}\, h_t\, \rho^{rec}\quad \text{(MWh)}.
```

At 10 MW in January this is $10 \times 744 \times 0.6 = 4{,}464$ MWh.

## 3. Decision variables

| Variable | Domain | Stage | Meaning |
|---|---|---|---|
| $y_{ek}$ | $\lbrace 0,1\rbrace$ | 1 | build link $e$ with pipe size $k$ |
| $x_u$ | $\lbrace 0,1\rbrace$ | 1 | connect user $u$ |
| $z_{ud}$ | $\lbrace 0,1\rbrace$ | 1 | user $u$ is served by data center $d$ |
| $g_{ua}$ | $[0,1]$ | 1 | share of user $u$'s commodity on arc $a$ (its path from its data center) |
| $s_{udt\omega}$ | $\ge 0$ | 2 | MWh delivered from $d$ to $u$ in month $t$ under scenario $\omega$ |

## 4. Constraints

**(C1) Flow of each user's commodity.** One unit leaves the chosen data center and arrives at the user:

```math
\sum_{a\in\delta^+(i)} g_{ua} - \sum_{a\in\delta^-(i)} g_{ua} =
\begin{cases} z_{ud} & i = d \in \mathcal D\\ -x_u & i = n(u)\\ 0 & \text{otherwise}\end{cases}
\qquad \forall u,\ i.
```

**(C2) One data center per user.** A connected user is served by exactly one data center; a user that is not connected by none:

```math
\sum_{d} z_{ud} = x_u \qquad \forall u.
```

**(C3) At most one pipe size per link.**

```math
\sum_{k} y_{ek} \le 1 \qquad \forall e.
```

**(C4) Heat runs only on built pipes that are big enough.** User $u$'s commodity may use link $e$ only if a pipe is built there that could carry $u$'s load on its own:

```math
g_{u,(i,j)} + g_{u,(j,i)} \le \sum_{k:\ \bar Q_k \ge q_u} y_{ek} \qquad \forall u,\ e=\lbrace i,j\rbrace .
```

This per-commodity linking is what makes the formulation strong. Its LP relaxation is much tighter than one aggregated flow per arc with a big-M link, the form most district-heating MILPs use [25, 26]. Restricting the sum to sizes that fit $q_u$ is valid and tightens it further.

**(C5) Pipe capacity.** The peak loads of all users whose paths use a link must fit the size built:

```math
\sum_{u} q_u\,\big(g_{u,(i,j)} + g_{u,(j,i)}\big) \le \sum_{k} \bar Q_k\, y_{ek} \qquad \forall e.
```

**(C6) Deliveries only to connected users, from their own data center, within what the connection can deliver.**

```math
s_{udt\omega} \le \bar s_{ut}\, z_{ud} \qquad \forall u,d,t,\omega.
```

**(C7) Waste heat available at each data center, each month, in each scenario.**

```math
\sum_{u} r_u\, s_{udt\omega} \le W_{dt\omega} \qquad \forall d,t,\omega.
```

## 5. Objectives

The annual net benefit of a plan in scenario $\omega$ is

```math
N_\omega = \underbrace{\sum_{u,d,t} v_{u\omega}\, s_{udt\omega}}_{\text{kerosene replaced minus electricity}}
\;-\; \underbrace{\mathrm{CRF}_p \sum_{e,k} c_k\, \ell_e\, y_{ek}}_{\text{pipes}}
\;-\; \underbrace{\mathrm{CRF}_{hp} \sum_u H_u\, x_u}_{\text{heat pumps}} .
```

Three objectives are offered. Each is a MILP over (C1)–(C7). For the robust ones a small $\epsilon\,\mathbb E[N]$ ($\epsilon = 10^{-4}$) breaks ties in favor of the better expected value.

| Name | Problem | When to use it |
|---|---|---|
| Expected (stochastic) | $\max\ \sum_\omega p_\omega N_\omega$ | scenarios with credible probabilities |
| Worst case (max-min) | $\max\ \eta \ \ \text{s.t.}\ \ \eta \le N_\omega\ \ \forall\omega$ | protect the weakest scenario |
| Min-max regret | $\min\ \rho \ \ \text{s.t.}\ \ \rho \ge N^\star_\omega - N_\omega\ \ \forall\omega$ | no probabilities; compare each scenario with its own best plan $N^\star_\omega$ [36] |

**Scenarios.** The default set has four scenarios with equal weight: the IT load at every data center is low or high, crossed with kerosene at 115 or 156.8 yen/L.

**Two-stage structure.** $y, x, z, g$ are fixed before the uncertainty resolves. The deliveries $s$ adapt to each scenario.

## 6. Robust design with a budgeted uncertainty set

The IT loads of the data centers are not published; only rough ranges $[L^{lo}_d, L^{hi}_d]$ are known. Following Bertsimas and Sim [31], the uncertainty set lets at most $\Gamma$ data centers sit at their low value at once:

```math
\mathcal L(\Gamma) = \big\lbrace L:\ L_d \in \lbrace L^{lo}_d, L^{hi}_d\rbrace ,\ \ |\lbrace d: L_d = L^{lo}_d\rbrace | \le \Gamma\big\rbrace .
```

$\Gamma = 0$ is the nominal plan. $\Gamma = |\mathcal D|$ protects against all data centers at their low value at once.

The two-stage adjustable robust problem [32, 34] is

```math
\max_{(y,x,z,g)\,\in\,\mathcal X}\ \ \min_{L\,\in\,\mathcal L(\Gamma)}\ \ \max_{s\,\in\,\mathcal S(y,x,z;\,L)}\ N(y,x,s),
```

where $\mathcal X$ is (C1)–(C5) and $\mathcal S$ is (C6)–(C7) with $W_{dt} = L_d h_t \rho^{rec}$.

**Why only vertices matter.** $L$ enters only the right-hand side of (C7). More waste heat can never lower the best delivery value. The worst case therefore puts exactly $\min(\Gamma, |\mathcal D|)$ data centers at their low value, and there are $\binom{|\mathcal D|}{\Gamma}$ such corners.

**Column-and-constraint generation** [33]:
1. **Master.** Maximize $\eta$ over the first-stage variables, subject to $\eta \le N(y,x,s^c)$ and $s^c \in \mathcal S(y,x,z;L^c)$ for every corner $c$ found so far. Each corner adds its own copy of the monthly deliveries (new columns) and one epigraph row (a new constraint). The solver's bound on $\eta$ is an upper bound UB on the robust value.
2. **Subproblem.** For the master's network, evaluate every corner. Each evaluation is one LP over $s$. The worst value is a lower bound LB, and the worst corner joins the master.
3. **Stop** when $\mathrm{UB}-\mathrm{LB} \le 0.5\,\%$ of UB, or when the worst corner is already in the master. Runs for larger $\Gamma$ start from the corners found at smaller $\Gamma$, because $\mathcal L(\Gamma-1)\subseteq\mathcal L(\Gamma)$.

**Price of robustness.** For the plan $x^\Gamma$ built for budget $\Gamma$ and the nominal plan $x^0$:

```math
\mathrm{PoR}(\Gamma) = \frac{N^{nom}(x^0)-N^{nom}(x^\Gamma)}{N^{nom}(x^0)}.
```

**Kerosene stays outside the budget.** In a max-min model of savings, the worst kerosene price is always the lowest one, so the price would never act as a real adversary. Its uncertainty is shown through regret instead.

## 7. How it is solved

**Solver.** HiGHS (open source) solves the problem through highspy. Gurobi can be used when installed (`DCOPT_SOLVER=gurobi`). With 50 candidate users and four scenarios the instance has about 26,000 variables (about 1,150 binary) and 20,000 rows.

**The difficulty.** Discrete pipe sizes weaken the LP bound, and the full MILP does not close in 60 s.

**The default method is an LP-guided kernel search:**
1. Solve the LP relaxation on all candidate links. Its value bounds the optimum.
2. Keep the links the LP uses (its $y$ above $10^{-6}$), plus the links of each data center's own plan (seeds).
3. Solve the MILP on those links only.
4. Optionally, solve the full MILP warm-started from that plan.
5. Re-evaluate every plan with exact recourse.

**How good are the plans?** We checked against Gurobi 14.0, the optional backend, using `experiments/solver_compare` on the full MILP with a cold start and 16 threads:
- *Standard candidate links.* Gurobi proves the optimum in 71 s (ambient) and 255 s (central). The kernel-search plans are within 0.2 % and 0.8 % of it.
- *Every user linked directly to every data center.* Gurobi ends at 1.5 % and 3.9 % gaps after 600 s.
- *HiGHS on the full MILP.* It stops at 18–38 % gaps on both candidate sets.

The plans themselves are good; HiGHS's bound is what is weak. A stronger formulation (cut-set inequalities, Benders cuts) that lets an open-source solver certify them is an open research question.

## 8. Checks

**Against version 1.** Restrict version 2 to one data center, one very large pipe size at 100,000 yen/m, a central COP of 4, no loss and kerosene at 115 yen/L. On the earlier 40-site candidate set it then reproduces version 1 exactly: 15 sites, 16.1 km and 137.5 M yen/yr. On the current 50-site set it matches version 1 within the solver's gap: 159.3 against 159.8 M yen/yr, 24 sites.

**Unit tests** (`tests/test_heatnet.py`) on a synthetic instance check:
- the per-data-center waste-heat limits;
- pipe capacity;
- that each user is served by one data center;
- the coupling between scenarios;
- that each robust objective does best on its own criterion;
- that C&CG matches the max-min over all corners;
- that the formulas match version 1.

## 9. The pair-by-pair baseline

The idea starter asks for five ranked partners per data center. Our baseline is the following.
1. **Score each user alone.** User $u$ gets its own pipe from data center $d$: the smallest size $k$ with $\bar Q_k \ge q_u$, along the road distance $\ell_{du}$. It also gets all of $d$'s waste heat. Its score is
   ```math
   \text{score}_{du} = \sum_t v_u \min\!\big(\bar s_{ut},\, W_{dt}/r_u\big) - \mathrm{CRF}_p\, c_k\, \ell_{du} - \mathrm{CRF}_{hp}\, H_u .
   ```
2. **Pick the five best** users with a positive score.
3. **Build the five pipes** and evaluate them together with the same delivery LP.

The shared network beats this baseline because it avoids duplicated pipes, lets small users join through short branches, and uses larger, cheaper-per-MW trunks.

## 10. A worked pair: data center No. 1 and the fish farm (ambient loop)

| Item | Value | How |
|---|---|---|
| Road distance | 2,483 m | OpenStreetMap shortest path |
| Demand | 5,000 MWh/yr, flat | assumed site and demand |
| Design peak $P$ | 0.68 MW | $1.2 \times 5{,}000/8{,}760$ |
| Supply temperature | 22 °C, so direct use | below 27 °C |
| Pipe | DN150 (1.41 MW) | smallest size with $\bar Q_k \ge q_u$ (DN100 carries only 0.54 MW) |
| Pipe investment | 517 M yen | $2{,}483 \times 208{,}367$ |
| Heat-pump investment | 0 | direct use |
| Saving per year | 69.7 M yen (115 yen/L) to 95.1 M yen (156.8 yen/L); expected 82.4 M yen | $5{,}000 \times v$ |
| CO₂ avoided | 1,516 t/yr | $5{,}000 \times 0.303$ |
| Simple payback | 6.3 years | $517 / 82.4$ |

## 11. A heat price for a pair

Each proposal (`dcopt.heat.proposal`, app page *Warm Ishikari Proposals*) gives the range of heat prices at which both sides of a pair gain. For data center $d$ and user $u$ with the dedicated pipe of Section 9, let
- $S_{du} = \sum_\omega p_\omega \sum_t \min\!\big(\bar s_{ut}, W_{dt\omega}/r_u\big)$ be the expected heat delivered per year (MWh),
- $F_{du}$ be the expected cost of the kerosene it replaces (yen per year),
- $C^{\mathrm{el}}_{du}$ be the expected cost of the heat pumps' electricity, so that $F_{du} - C^{\mathrm{el}}_{du}$ is the expected value of the heat in the score.

The supplier (the data center or a heat company) owns the pipe. Operation and maintenance are left out, as in the model.

| Mode | Supplier pays | Partner pays | Lowest price for the supplier, $\underline p_{du}$ | Highest price at which the partner gains, $\overline p_{du}$ |
|---|---|---|---|---|
| Ambient loop | the pipe | its heat pump and the electricity | $\mathrm{CRF}_p\, c_k\, \ell_{du} / S_{du}$ | $\big(F_{du} - C^{\mathrm{el}}_{du} - \mathrm{CRF}_{hp}\, H_u\big) / S_{du}$ |
| Central | the pipe, the central heat pump and its electricity | only the price | $\big(\mathrm{CRF}_p\, c_k\, \ell_{du} + \mathrm{CRF}_{hp}\, H_u + C^{\mathrm{el}}_{du}\big) / S_{du}$ | $F_{du} / S_{du}$ |

In both modes

```math
\overline p_{du} - \underline p_{du} = \frac{\text{score}_{du}}{S_{du}} ,
```

so a price that leaves both sides better off exists exactly when the pair's score is positive. The proposal also shows the midpoint $(\underline p_{du} + \overline p_{du})/2$. It splits the gain equally, which is the Nash bargaining price for two parties with linear utilities and no deal as the fallback.

**Worked pair (Section 10).** $\underline p = 0.0510 \times 517\ \text{M yen} / 5{,}000\ \text{MWh} = 5{,}280$ yen/MWh. The fish farm uses the heat directly, so $\overline p = 82.41\ \text{M yen} / 5{,}000\ \text{MWh} = 16{,}483$ yen/MWh. The midpoint is 10,881 yen/MWh, against 19,018 yen/MWh for heat from kerosene at 156.8 yen/L.

This is a price for one pair. In a shared network the cost of the common pipes must also be split among the partners. Whether a split exists that no group of partners would leave (the core of the network-design game) is an open question for this model; see the next research questions in the README.

## 12. CO2 and policy scenarios

**CO₂ avoided per MWh.** A MWh delivered to user $u$ avoids

```math
a_u = \frac{2.50}{9.7\,\eta_b} - \varepsilon^{el}\, e_u \qquad \text{(t CO₂ per MWh)} .
```

The first term is the kerosene not burned (0.303 t/MWh, Section 2.4; kerosene emits 2.50 kg CO₂ per litre [53]). The second is the heat pump's electricity $e_u$ (Section 2.3) at the emission factor $\varepsilon^{el}$ of that electricity. In the plans, $\varepsilon^{el}$ is the grid factor for the users' heat pumps (ambient loop) and zero for the central heat pump, which runs on the data center's renewable power. Any plan can also be reported under three electricity scenarios:

| Electricity for the heat pumps | $\varepsilon^{el}$ (t CO₂/MWh) | Basis |
|---|---|---|
| 100 % renewable power | 0 | the supply of data center No. 1 [2, 5] |
| National level for FY2030 | 0.25 | the Plan for Global Warming Countermeasures of 2025 [55] |
| Hokkaido Electric Power, standard plans | 0.526 | results of FY2024 [54] |

**Carbon price.** With a price $\pi$ (yen per tonne) on the CO₂ avoided, the value of a delivered MWh becomes

```math
v_{u\omega} + \pi\, a_u \qquad \text{(yen/MWh)} .
```

Today's fuel taxes are levied upstream and are part of the kerosene price, so $\pi$ is a price on top of them. The default is $\pi = 0$. For orientation, the reference prices of Japan's emissions trading scheme for FY2026 are 1,700 and 4,300 yen per tonne [56].

**Subsidy.** With a share $\phi$ of the investment paid by a subsidy, the project pays $(1-\phi)$ of every pipe and heat-pump annuity. The default is $\phi = 0$. For orientation, programmes that name such equipment pay 1/3 to 2/3 of the investment [57, 58].

Both scenarios enter the objective of Section 5 only through these coefficients, so the methods of Sections 5–7 apply unchanged.

**What is reported for a plan.** Let $C$ be its full annual cost (pipes and heat pumps, no subsidy), $V$ its expected annual value at $\pi = 0$ and $A$ its expected CO₂ avoided per year.

| Quantity | Formula | Meaning |
|---|---|---|
| Net benefit to the project | $V + \pi A - (1-\phi)\,C$ | what the plan's owners see under the policy |
| Plain net benefit | $V - C$ | the same plan with no policy money |
| Cost of a tonne avoided | $(C - V)/A$ | negative when the plan pays for itself; for a pair that does not pay, the carbon price at which it breaks even |
| Cost of the extra tonnes a policy brings | $\dfrac{(V_0 - C_0) - (V - C)}{A - A_0}$ | index 0 is the no-policy plan; it maximizes the plain net benefit, so this cost is not negative, up to the search gap |

**Where it appears.**
- The app's *Warm Ishikari* page has both policies as sliders (model v1, one data center) and compares the plan with the no-policy plan.
- Each proposal's calculation sheet lists the CO₂ avoided under the three electricity scenarios, the cost of a tonne, and the payback at subsidy rates of 1/3, 1/2 and 2/3.
- `experiments/heat_policy/run.py` re-optimizes the regional plan for a list of policies. Every policy gets the same candidate links, and every plan found is evaluated under every policy, so that the plans differ because of the policy and not because of the search. The results are in [heat.md](heat.md).

The carbon prices and subsidy rates are scenarios. They do not state how an actual scheme applies to a project.

## 13. Limitations

- **Monthly energy balances.** The model has no hourly operation, no storage and no pumping energy. Peaks enter only through $P_u$, $\alpha$ and the duration curve.
- **Deliverable capacity is not tied to the built pipes.** $c_u$ comes from $\alpha$ times the scenario set's design peak — the same for every build — and pipe sizes gate connectivity all-or-nothing. With demand-side uncertainty (the weather years) this makes plans built on different-sized scenario sets incomparable: the 50-year experiment shows the signature (see the weather-years section in [heat.md](heat.md)). The fix ties the deliverable cap to the built pipe size (a per-user path bottleneck).
- **Heat loss.** Losses are a flat share $\lambda$. A length-, size- and temperature-dependent loss, fixed per built pipe, is the next step.
- **Positions.** Two data-center positions are approximate and one is a placeholder. Several users are assumed sites.
- **Assumed parameters.** The peak factors, supply temperatures, velocities, the pipe-cost line and the heat-pump cost at the users are assumptions to be checked with experts and data.
