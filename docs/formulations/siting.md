# Theme 3: siting the next data center

This theme asks where a new data center should go. The first version answers a narrower question with what themes 1 and 2 can supply today: **where is the waste heat of a new data center worth most, and what does the grid connection cost there?**

**Status.** A first screen for Ishikari: 56 candidate sites, the heat value of each from the model of theme 1, the distance of each to the substations on the public map, and a small location model on top. Zoning, land, fibre and hazards are not in it yet, and neither is a hosting capacity, because there is no network model of the Hokkaido grid (see [grid.md](grid.md)).

## 1. The heat value of a site

Let $N^\star(\mathcal{D})$ be the expected net benefit of the best regional heat plan for a set of data centers $\mathcal{D}$ (model v2, stochastic, ambient loop; [heat-model.md](heat-model.md)). For a candidate site $j$ and an IT load $L$:

```math
h_j(L) = N^\star\big(\mathcal{D}_0 \cup \lbrace (j, L)\rbrace\big) - N^\star(\mathcal{D}_0) ,
```

where $\mathcal{D}_0$ are the four existing and planned data centers. The new data center has IT load $L$ in the high-load scenarios and $0.6\,L$ in the low-load ones (the ratio of data center No. 1; an assumption).

The plans come from a heuristic search, so the comparison is built to keep the search out of it (`dcopt.siting.heat_value`):
- **One instance for both sides.** The plan without the candidate is a feasible plan of the instance with it (the candidate simply supplies nothing). The value therefore cannot be negative.
- **The same plan without, for every site.** It is the published regional plan (93.8 M yen a year, 13 sites), carried over link by link.
- **Seeded search with.** The search for the plan with the candidate gets the links of the published plan and the links of the candidate's own best plan as extra candidates.

A reported value is the gain of the best plan found, so it is a **lower bound** on $h_j(L)$: a better search could only raise it.

## 2. The grid connection

`dcopt.siting.gridmap` reads the transmission lines, their voltage classes and the substations from OpenStreetMap, and measures for each site the straight-line distance $d_j$ to the nearest substation of at least 66 kV or at least 187 kV (the switchyards of power plants are left out). The annual cost of the connection is

```math
g_j = \mathrm{CRF}(3\,\%, 30)\; c^{line}\; d_j ,
```

with a cost per km $c^{line}$ that is an assumption (100 M yen/km by default, a slider in the app).

Around the existing data centers the map shows a 66 kV substation about 0.5 km away, the 275 kV line from the 569 MW gas power station within about 0.5 km, and the nearest 187 kV substations 6 to 8 km away. The map has no impedances, ratings or loads, so the room at a substation is unknown. The data is what volunteers mapped and is not checked against the grid operator's records.

## 3. The location model

With $z_j \in \lbrace 0,1\rbrace$ for "build at site $j$":

```math
\begin{aligned}
\max\ & \textstyle\sum_j (h_j - g_j)\, z_j \\
\text{s.t.}\ & \textstyle\sum_j z_j = n && \text{the number of new data centers} \\
& z_i + z_j \le 1 && \text{for sites closer than a spacing } \delta \\
& \textstyle\sum_{j \in J_s} L\, z_j \le H_s && \text{headroom of connection point } s \text{ (optional)}
\end{aligned}
```

- **Spacing.** The heat values are computed one site at a time. Two sites that would feed the same users do not add up, so pairs closer than $\delta$ (3 km by default) are excluded, and the chosen set is checked with one joint solve.
- **Headroom.** $H_s$ is a scenario value today. Once a network model exists, the hosting capacity of theme 2 takes its place; this is where the three themes meet.

## 4. Results for Ishikari (a new data center of 10 MW)

Candidates: the points of a 1.5 km grid inside the municipal boundary, each moved to the nearest road (56 sites). All money in M yen per year. From `scripts/export_siting.py` on 2026-11-25. The table shows the best values found, from the run with Gurobi (an optional solver); the HiGHS run is compared below.

| Site | Near | Heat value | Sites served from it | Heat delivered (MWh/yr) | To a 66 kV substation | To a 187 kV substation | Net, connected at 66 kV | Net, connected at 187 kV |
|---|---|---|---|---|---|---|---|---|
| g07 | 新港西一丁目 | 45.2 | 10 | 15,450 | 1.4 km (石狩) | 5.2 km (西札幌) | 37.9 | 18.5 |
| g08 | 花川北四条一丁目 | 44.9 | 16 | 17,750 | 1.7 km (石狩) | 5.5 km (西札幌) | 36.1 | 17.1 |
| g09 | 花川北七条三丁目 | 25.2 | 14 | 13,466 | 1.8 km (茨戸) | 4.8 km (篠路) | 16.0 | 0.6 |
| g38 | 弁天町 | 19.9 | 2 | 2,360 | 8.2 km (石狩) | 8.3 km (西当別) | −21.9 | −22.5 |
| g20 | 生振 | 16.8 | 1 | 4,000 | 4.7 km (茨戸) | 6.4 km (篠路) | −6.9 | −16.0 |
| g13 | 花川東一条四丁目 | 16.6 | 1 | 4,000 | 2.6 km (茨戸) | 5.0 km (篠路) | 3.3 | −9.0 |
| g03 | 花川南三条一丁目 | 14.6 | 11 | 15,700 | 1.9 km (樽川) | 3.7 km (西札幌) | 4.8 | −4.0 |
| g01 | 花川南七条五丁目 | 12.8 | 4 | 2,400 | 2.2 km (西札幌) | 2.2 km (西札幌) | 1.7 | 1.7 |

*Net* is the heat value minus the annual cost of a connection line at 100 M yen/km. The sites are named after the nearest quarter in OpenStreetMap.

What the study says:
1. **The heat has value at 19 of the 56 sites.** At the best one it is 45.2, almost half of what the whole regional plan earns today (93.8).
2. **What counts is being nearer to the heat users than the existing data centers are.** The two best sites are 1 to 2 km from the existing data centers, on the town side. A site 1.5 km away on the other side has no value, because heat is already in surplus at the port: the regional plan uses about 15 % of the existing data centers' recoverable heat.
3. **The grid connection decides how much of that is left.** The best sites are 1.4 to 1.8 km from a 66 kV substation and about 5 km from a 187 kV one. At 100 M yen/km, nine sites keep a positive net when they connect at 66 kV and four when they must connect at 187 kV; the best site keeps 37.9 or 18.5 of its 45.2. At 300 M yen/km, two sites keep a positive net at 66 kV and none at 187 kV.
4. **A second new data center is worth about a third of the first.** With 3 km between them, the best pair is g07 and g13: 61.8 together, which a joint solve confirms. The second adds 16.6 of heat value, and 3.3 after its own connection cost.

**The two solvers.** Both runs start from the same plan without a new data center (93.8). They give the same values at the four best sites (within 1.0). At 17 other sites the Gurobi run finds a better plan with the new data center, by up to 11.9 (site g01: 0.9 with HiGHS, 12.8 with Gurobi), and three sites that have no value with HiGHS have some with Gurobi. HiGHS is never higher. The order of the top sites does not depend on the solver; the values in the middle of the table do.

## 5. Limits

- **A first screen, not a site search.** The candidates are grid points, not vacant lots. Zoning, land size and price, fibre, flood, tsunami and ground conditions, and cooling water are not considered.
- **Heat values are lower bounds from a heuristic search.** Neighbouring sites can differ by more than their positions explain, so the order of close sites is not settled.
- **One site at a time.** Interactions are handled by the spacing rule and checked for the chosen set only.
- **No hosting capacity.** The grid enters as a distance. Whether a substation can take 10 MW is not known here.
- **The map is not the operator's data,** and the connection cost per km is an assumption.
- **The limits of theme 1 carry over:** demand per building type is an assumption, several users are assumed sites, and two data-center positions are approximate.

## 6. Next

- Put the hosting capacity of theme 2 in place of $H_s$ once a network model of Ishikari exists.
- Make the candidate data centers binary sources inside the heat-network model, so that sites and pipes are chosen together instead of one site at a time.
- Add land, hazard and fibre layers, and plan for uncertainty about which data centers will be built [29, 30, 48–52].

## Reproduce

```bash
uv run python scripts/export_siting.py --spacing 1500 --mw 10 --workers 8   # about a quarter of an hour
uv run streamlit run app/streamlit_app.py                                    # page "Siting"
uv run pytest tests/test_siting.py tests/test_siting_app.py
```

Reference numbers in square brackets point to the list in the [README](../../README.md#references).
