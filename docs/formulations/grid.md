# Theme 2: grid hosting capacity

This theme asks how much additional load a grid location can take. The load comes from data centers and, to a much smaller extent, from the heat pumps of theme 1.

**Status.** The method is implemented in `dcopt.grid` and checked on public benchmark systems. There is no public network model of the Hokkaido grid, so nothing on this page is a statement about Ishikari. The numbers below describe the benchmark systems and the method.

## What is computed

For a bus $b$ and a power factor $\cos\varphi$, the **hosting capacity** is the largest added load $\lambda$ (MW) for which the AC network still has an operating point within all limits:

```math
\begin{aligned}
\max\ & \lambda \\
\text{s.t.}\ & \textstyle\sum_{g \in G_i} S_g - S^d_i - \lambda\,(1 + j\tan\varphi)\,\mathbf{1}[i = b] = \sum_{l \ni i} S_{l,i}(V) + (Y^{sh}_i)^{*}\,|V_i|^2 && \text{for every bus } i \\
& \underline{v}_i \le |V_i| \le \overline{v}_i, \qquad |S_{l,i}(V)| \le \overline{s}_l, \qquad \underline{\theta}_l \le \angle V_f - \angle V_t \le \overline{\theta}_l \\
& \underline{p}_g \le P_g \le \overline{p}_g, \qquad \underline{q}_g \le Q_g \le \overline{q}_g
\end{aligned}
```

- $V_i$ is the complex voltage of bus $i$, and $S_{l,i}(V)$ is the complex power that branch $l$ draws from bus $i$ ($\pi$ model with taps and phase shifters).
- Existing loads $S^d$ stay fixed. All generators may redispatch, so this is the best case for the network.
- The added load can also be spread over several buses with fixed shares $w_i$ (replace $\mathbf{1}[i=b]$ by $w_i$).

The problem is non-convex. A local solver gives a feasible point, hence a **lower bound**: that much load can be hosted. A convex relaxation gives an **upper bound**: no operating point can host more. Together they bracket the true value, and the bracket is reported per bus:

```math
\text{gap} = \frac{\text{upper bound} - \text{lower bound}}{\text{upper bound}}.
```

## The lifted model

Write $W = V V^{H}$. Every quantity above is linear in the entries of $W$ on the network: $c_i = W_{ii} = |V_i|^2$ and $W_{ij} = w^r_{ij} + j\,w^i_{ij}$ for each connected pair $i<j$. With branch admittances $y_{ff}, y_{ft}, y_{tf}, y_{tt}$ written as $g + jb$:

```math
\begin{aligned}
P_{ft} &= g_{ff}\,c_f + g_{ft}\,w^r + b_{ft}\,w^i, & Q_{ft} &= -b_{ff}\,c_f - b_{ft}\,w^r + g_{ft}\,w^i,\\
P_{tf} &= g_{tt}\,c_t + g_{tf}\,w^r - b_{tf}\,w^i, & Q_{tf} &= -b_{tt}\,c_t - b_{tf}\,w^r - g_{tf}\,w^i,
\end{aligned}
```

where $(w^r, w^i)$ are the real and imaginary parts of $W_{ft}$. The model in the variables $(\lambda, P_g, Q_g, c, w^r, w^i)$ then has:
- **balances**: two linear equations per bus;
- **limits**: bounds on $P_g$, $Q_g$ and $c_i \in [\underline{v}_i^2, \overline{v}_i^2]$, and $\tan\underline{\theta}_l\, w^r \le w^i \le \tan\overline{\theta}_l\, w^r$;
- **thermal limits**: $P_{ft}^2 + Q_{ft}^2 \le \overline{s}_l^2$ at both ends, a second-order cone.

The only non-convex part is the link between $W$ and $V$: $W \succeq 0$ with rank one. `dcopt.grid.lifted` builds this model once per network. The relaxations and the AC problem below share it, so they cannot disagree about the network data.

## Upper bounds: two relaxations

Both drop the rank condition, so every AC operating point stays feasible.

- **SOCP** (Jabr 2006). Keep only the $2\times 2$ minors of $W$: $c_i\,c_j \ge (w^r_{ij})^2 + (w^i_{ij})^2$ for each connected pair.
- **SDP with chordal decomposition** (Lavaei and Low 2012; Jabr 2012; Molzahn et al. 2013). Require $W \succeq 0$. A greedy minimum-degree elimination gives the maximal cliques of a chordal extension of the network graph. $W$ has a positive semidefinite completion exactly when each clique block is positive semidefinite (Grone et al. 1984), so one small matrix constraint per clique replaces the constraint on the full matrix. The entries of $W$ on the fill edges are extra variables shared by the cliques; no linking constraints are needed. A Hermitian block $R + jI$ enters the solver as the real symmetric matrix with blocks `[[R, -I], [I, R]]`, which is positive semidefinite exactly when the Hermitian block is. Cliques of size two stay second-order cones.

What a bound certifies:
- No AC operating point hosts more than the bound.
- If the relaxation is infeasible, the network cannot serve even its existing load under that condition (used in the outage study below).
- On a radial network both relaxations coincide; on a meshed network the SDP bound is at least as tight.

The conic problems are solved with Clarabel, an open-source interior-point solver. Two numerical notes:
- With Clarabel's default settings the SDPs often stopped with numerical errors on the 300-bus system. A static regularization of $10^{-5}$ removed these failures in our runs.
- Many solves end with status `AlmostSolved` (Clarabel's reduced tolerances, about $5\times10^{-5}$ relative). The reported bound is the larger of the primal and dual objective values. The bounds are therefore certified up to solver tolerance, not in exact arithmetic.

## Lower bound: an AC point that is checked

`dcopt.grid.ac` solves the AC problem in rectangular coordinates $V = e + jf$. The lifted products are exact quadratics there ($c_i = e_i^2 + f_i^2$, $w^r_{ij} = e_i e_j + f_i f_j$, $w^i_{ij} = f_i e_j - e_i f_j$), so Jacobians and the Hessian of the Lagrangian are exact and sparse.

1. **Base point.** One optimal power flow without added load (least total generation) gives a feasible operating point of the network as it is. It is reused for every bus. A network without any load is a special case: the flat start is already feasible there and is used as it is, because the interior-point method is ill-conditioned on that problem (on the two-bus example it failed for about half of 200 copies whose data were perturbed by $10^{-10}$; on the systems with load, 357 perturbed solves all returned the same value).
2. **Direct run.** A primal-dual interior-point method in the style of MIPS (Wang et al. 2007) maximizes $\lambda$ from the base point.
3. **Proximal-point climb.** On the larger systems the direct run often stalls: at maximum loading the Newton systems become ill-conditioned. Then each round solves $\max\ \lambda - \rho\,\lVert x - x_k\rVert^2$ from the last verified point $x_k$. The added load never decreases between verified points. $\rho$ shrinks after a successful round and grows after a failed one.
4. **Independent check.** A point counts only if a separate routine, working from the complex voltages alone, finds every balance and limit satisfied within $10^{-6}$ per unit.

The interior-point method is local. A lower bound is always valid, but it need not be the best one. Only a closed bracket proves that it is.

## DC screening

Screening studies often use the DC power flow: no losses, no reactive power, no voltage limits. `dc_screening` solves the same question in that model as a linear program. It is neither a relaxation nor a restriction of the AC problem, so it can err on either side. When the DC value lies above the SDP bound, DC screening provably overstates the capacity of that bus.

## Which limit binds

At the AC point, each active limit has a multiplier $\mu$. Relaxing the limit by 1 % raises the hostable load by about:
- thermal rating $\overline{s}_l$: $0.02\,\mu\,\overline{s}_l^2$;
- voltage limit $\underline{v}_i$ or $\overline{v}_i$: $0.02\,\mu\,v^2$;
- generator limit: $0.01\,\mu\,|\text{limit}|$.

The binding limits are listed per bus, most sensitive first, with the element named (for example "branch 2-3" or "bus 46"). The tables group them into thermal, voltage, generation (P), reactive (Q) and angle, and report the kind with the largest summed sensitivity.

## Use

```python
from dcopt.grid import cases, hosting

case = cases.load("case118_ieee")             # PGLib-OPF, downloaded on first use; "ring5" needs no download
h = hosting.hosting_capacity(case, bus=58)    # an index into the case; case.label(58) is its bus number
print(h.ac, h.upper, h.gap, h.limit)          # MW hostable, MW upper bound, relative gap, binding kind
print(h.binding[0])                           # the most sensitive binding limit and its element
rows = hosting.hosting_map(case, workers=8)   # every bus
```

Also: `hosting_curve` (the bracket at several load levels) and `hosting_n1` (the worst single-branch outage).

## Results on benchmark systems

The systems are six cases of PGLib-OPF (IEEE PES Task Force; CC BY 4.0; the typical-operating-conditions files of the master branch on 2026-11-25). The script downloads them; they are not part of this repository. For every bus of every case, the added load has power factor 0.95 (lagging). All numbers come from `experiments/grid_hosting/run.py`, with the models as of commit `6f8405d`.

| System | Buses | AC point found | Gap < 0.1 % | Gap < 1 % | SDP gap, median / max | SOCP gap, median / max | DC above the SDP bound | DC / AC, median | Binding: thermal / voltage / generation |
|---|---|---|---|---|---|---|---|---|---|
| case14_ieee | 14 | 14 | 14 | 14 | 0.00 % / 0.0 % | 0.1 % / 0.6 % | 14 | 3.12 | 0 / 14 / 0 |
| case30_ieee | 30 | 30 | 27 | 27 | 0.00 % / 2.7 % | 64.4 % / 79.9 % | 30 | 2.24 | 26 / 3 / 1 |
| case39_epri | 39 | 39 | 3 | 6 | 10.99 % / 22.2 % | 44.6 % / 58.4 % | 14 | 1.06 | 0 / 0 / 39 |
| case57_ieee | 57 | 57 | 1 | 1 | 28.44 % / 48.2 % | 40.4 % / 60.6 % | 57 | 4.53 | 0 / 57 / 0 |
| case118_ieee | 118 | 118 | 29 | 50 | 1.39 % / 32.0 % | 13.8 % / 60.4 % | 96 | 1.14 | 57 / 53 / 8 |
| case300_ieee | 300 | 300 | 56 | 223 | 0.42 % / 30.2 % | 4.9 % / 52.5 % | 297 | 3.19 | 7 / 291 / 2 |

- *Gap* is (upper bound − AC point) / upper bound, with the tighter of the two bounds. *SDP gap* and *SOCP gap* use that relaxation alone.
- *DC above the SDP bound* counts buses where DC screening exceeds a certified upper bound.
- *Binding* is the kind of limit with the largest summed sensitivity at the AC point.

What the table says:

1. **A checked AC point exists at every bus**: 558 of 558. The largest violation found by the independent check is $1.0\times10^{-8}$ per unit.
2. **The bracket closes on the small systems and partly on the larger ones.** The gap is below 0.1 % at all 14 buses of the 14-bus system, 27 of 30, and 130 of 558 overall; it is below 1 % at 321 of 558.
3. **The bracket is wide where voltage or generator limits bind.** On the 57-bus system every bus is voltage-limited and the median gap is 28 %. On the 39-bus system generator limits dominate at every bus and the median gap is 11 %.
4. **DC screening overstates the hostable load at most buses.** It exceeds the certified upper bound at 508 of 558 buses. It exceeds the AC point at 554 buses and falls below it at 4 (all on the 118-bus system). The median ratio of the DC value to the AC point is between 1.06 and 4.53. A 2026 study of DC screening on a synthetic Texas grid reports the same direction (reference 47 of the README).
5. **The SOCP relaxation alone is not enough on meshed networks.** Its median gap is 64 % on the 30-bus system, where the SDP closes the bracket at 27 buses. On a radial feeder the two coincide (a test checks this on the built-in feeder).

**Is an open bracket the relaxation's fault or the local solver's?** A global solver gives some evidence. Gurobi 14.0 solved the same AC problem as a non-convex quadratic program (`global_gurobi`, optional):

| Problem | SDP bound (MW) | AC point (MW) | Global solver |
|---|---|---|---|
| built-in 5-bus ring, 3 load levels × 5 buses | — | — | optimal in all 15; best value equal to the AC point (within 0.0001 MW) |
| … of which bus 3 at load levels 0.6 and 0.8 | 243.29, 223.35 | 233.80, 219.12 | proves 233.80 and 219.12: the SDP bound is loose there |
| case30_ieee bus 29 | 10.62 | 10.50 | optimal, 10.50: equal to the AC point |
| case30_ieee bus 30 | 7.54 | 7.33 | optimal, 7.33: equal to the AC point |
| case30_ieee bus 26 | 7.46 | 7.29 | optimal, 7.29: equal to the AC point |
| case57_ieee bus 1 | 327.05 | 288.21 | best 288.21, bound 359.70 at 240 s |
| case57_ieee bus 7 | 255.27 | 158.98 | best 158.98, bound 287.66 at 240 s |
| case57_ieee bus 8 | 705.83 | 513.60 | best 513.60, bound 723.77 at 240 s |
| case39_epri bus 21 | 564.78 | 470.62 | best 470.62, bound 623.74 at 240 s |

Where the global solver finished, its optimum equals the AC point to five digits, so the open bracket there is the relaxation's slack. On the 39-bus and 57-bus systems it did not finish in 240 s, and its best point equals the AC point to two decimals. Its own bound was looser than the SDP bound at all four buses in these runs. In an earlier run at Gurobi's default tolerance it had reached 511.49 at the 39-bus bus, which is tighter than the SDP bound and still valid, because a looser tolerance only enlarges the feasible set. So the wide brackets there remain open.

`experiments/grid_global/run.py` regenerates this table (see Reproduce below); it needs Gurobi and a licence that covers the PGLib cases.

Gurobi runs with a feasibility tolerance of $10^{-9}$ in this check. At its default of $10^{-6}$ its solution may violate the limits just enough to host slightly more: the reported optimum then lay up to 0.07 % above the AC point, and on the built-in radial feeder, where the bracket is closed, above the certified upper bound. That is tolerance, not a better operating point; with $10^{-9}$ the two agree to seven digits there, and a test checks it.

**Load level.** On the 30-bus system, with every existing load scaled, the bracket stays closed and the hostable load falls steeply with the background load (AC point = upper bound, MW):

| Bus | × 0.6 | × 0.7 | × 0.8 | × 0.9 | × 1.0 |
|---|---|---|---|---|---|
| 5 | 114.2 | 89.2 | 63.8 | 38.2 | 12.2 |
| 8 | 130.4 | 101.8 | 72.9 | 43.6 | 14.0 |
| 7 | 122.4 | 95.6 | 68.5 | 41.0 | 13.1 |
| 2 | 111.6 | 87.1 | 62.3 | 37.3 | 12.0 |

A load that can be curtailed in the highest-demand hours could therefore be several times larger than a firm one on this system. Turning this into hours per year needs a real load-duration curve and a real network.

**Single-branch outages (N-1).** Each outage that keeps the network connected is solved on its own, with redispatch after the outage. On the 30-bus system, 38 of 41 outages keep it connected.
- At the load of the case as given, 7 of the 38 outages cannot serve even the existing load (the relaxation is infeasible). At load level 0.8 this holds for 4.
- At load level 0.7 all 38 are feasible, and the worst outage (branch 1-3) leaves 20.0, 19.9, 19.8 and 21.5 MW at buses 5, 8, 7 and 2, against 89.2, 101.8, 95.6 and 87.1 MW for the intact network. The bracket is closed in each case.

**Solve times.** Median per bus, 8 worker processes on a shared 16-core machine that was also running other jobs, so the times are indicative only:

| System | SOCP | SDP | AC point | Whole case (wall) |
|---|---|---|---|---|
| case14_ieee | 0.003 s | 0.011 s | 0.13 s | 1 s |
| case30_ieee | 0.006 s | 0.028 s | 0.08 s | 1 s |
| case39_epri | 0.007 s | 0.040 s | 0.87 s | 11 s |
| case57_ieee | 0.017 s | 0.21 s | 1.19 s | 18 s |
| case118_ieee | 0.035 s | 0.29 s | 2.29 s | 73 s |
| case300_ieee | 0.17 s | 2.5 s | 6.8 s | 547 s |

Two notes on the solvers:
- **Conic solver.** On 8 random buses of the 300-bus system, Clarabel's default settings ended 7 of 8 SDPs without a solution (6 numerical errors, 1 insufficient progress); with the static regularization at $10^{-5}$ all 8 returned a bound. In the full run all 558 SDPs returned a bound; 472 of them ended with the reduced-tolerance status.
- **AC solver.** The direct interior-point run was enough at 149 of the 558 buses (all of the 14-bus system, 28 of 30, but none of the 118-bus system). The proximal-point climb gave the point at the other 409.

We also tried the lifted nonlinear cuts of Coffrin et al. (2017) on 10 buses of each of the four larger systems. The bounds moved by less than 0.1 %, so the cuts are not included.

## What is certified and what is not

- **Certified, up to solver tolerance:** the upper bounds (no AC point hosts more) and the infeasibility of an outage case.
- **Checked independently:** the AC point satisfies every constraint within $10^{-6}$ per unit, so its load is hostable in the model.
- **Not certified:** that the AC point is the best one, unless the bracket is closed. And nothing here is certified about a real grid.

## Limits

- **Benchmark systems, not Hokkaido.** We found no public network model of the Hokkaido grid. Building one, from HEPCO Network's published data for 187 kV and above, the IEEJ standard models or OpenStreetMap, is the next step.
- **Best-case dispatch.** All generators redispatch freely to make room. A system operator assesses a connection against its own dispatch scenarios and rules, which leave less room.
- **No N-1 in the main table.** The study above shows how much it matters.
- **Static snapshots.** One operating condition at a time; load levels scale every load uniformly. There is no time series and no unit commitment.
- **Thermal, voltage and angle limits only.** No transient or small-signal stability, no short-circuit ratio, no margin to the voltage-stability limit.
- **A constant-power load at a fixed power factor.**
- **Local AC solver.** See above.

## Open questions

- Where voltage limits bind, the SDP bound is loose (57-bus system). Do tighter relaxations with bound tightening close these brackets (Coffrin et al. 2017; reference 42 of the README)?
- Which network model should represent Ishikari, and which limit binds first there for 10–30 MW of new load?
- How should the flexibility of data centers and heat pumps count: as a larger hostable load with a curtailment allowance, or as balancing capacity?

## Reproduce

```bash
uv run python experiments/grid_hosting/run.py --workers 8      # all six cases, then the two studies; about 12 minutes on the machine above
uv run python experiments/grid_hosting/run.py --cases ring5,feeder8,case14_ieee --study-case ""   # a few seconds
uv run pytest tests/test_grid_cases.py tests/test_grid_hosting.py
uv run --extra gurobi python experiments/grid_global/run.py --download   # the global-solver table; 240 s per long case
```

The global-solver script writes `results/grid_global/table.csv` and `provenance.json` (commit, Gurobi version, feasibility tolerance, time limit) and prints the table above. `--time-limit` and `--feas-tol` change the two settings the numbers depend on. Without gurobipy or a licence it prints a note and exits. The size-limited licence that comes with the gurobipy package solves the 5-bus ring and the feeder, but not the 30-, 39- and 57-bus cases.

The outage study in the first command runs at load level 0.7; `--n1-level 1.0` and `--n1-level 0.8` give the other two.

## References

Relaxations, benchmarks and tools are references 37–47 of the README. The six below are also its references 59–64:

- Grone, R., Johnson, C.R., Sá, E.M., Wolkowicz, H. (1984). Positive definite completions of partial Hermitian matrices. *Linear Algebra and its Applications*, 58, 109–124. https://doi.org/10.1016/0024-3795(84)90207-6
- Jabr, R.A. (2012). Exploiting Sparsity in SDP Relaxations of the OPF Problem. *IEEE Transactions on Power Systems*, 27(2), 1138–1139. https://doi.org/10.1109/TPWRS.2011.2170772
- Molzahn, D.K., Holzer, J.T., Lesieutre, B.C., DeMarco, C.L. (2013). Implementation of a Large-Scale Optimal Power Flow Solver Based on Semidefinite Programming. *IEEE Transactions on Power Systems*, 28(4), 3987–3998. https://doi.org/10.1109/TPWRS.2013.2258044
- Wang, H., Murillo-Sánchez, C.E., Zimmerman, R.D., Thomas, R.J. (2007). On Computational Issues of Market-Based Optimal Power Flow. *IEEE Transactions on Power Systems*, 22(3), 1185–1193. https://doi.org/10.1109/TPWRS.2007.901301
- Coffrin, C., Hijazi, H.L., Van Hentenryck, P. (2017). Strengthening the SDP Relaxation of AC Power Flows With Convex Envelopes, Bound Tightening, and Valid Inequalities. *IEEE Transactions on Power Systems*, 32(5), 3549–3558. https://doi.org/10.1109/TPWRS.2016.2634586
- Goulart, P.J., Chen, Y. (2026). Clarabel: An interior-point solver for conic programs with quadratic objectives. *Mathematical Programming Computation*, 18(4), 1279–1361. https://doi.org/10.1007/s12532-026-00320-7
