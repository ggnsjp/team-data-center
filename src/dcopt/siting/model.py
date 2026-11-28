"""Which candidate sites to pick: a small location model on top of the heat values.

    max   sum_j (h_j - g_j) z_j
    s.t.  sum_j z_j = n                                   the number of new data centers
          z_i + z_j <= 1        if |i - j| < spacing      two picks may not share a heat catchment
          sum_{j in s} L z_j <= H_s                       headroom of each connection point (optional)
          z binary

h_j   value of the waste heat of a data center at site j (theme 1, yen per year)
g_j   annual cost of its grid connection: an annuity on the distance to the connection point
The heat values are computed one site at a time, so they do not add up for two sites that would
feed the same users. The spacing rule keeps such pairs apart; `choose_sites` reports the plain
sum, and the export checks the chosen set with one joint solve.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp
from scipy.optimize import Bounds, LinearConstraint, milp

# Connection line, M yen per km: the middle of the standard unit costs for a two-circuit tower line that
# OCCTO published in March 2026 (land excluded); "66" is its 66/77 kV class and "187" its 154/187 kV class.
# The app's default, the export's pair check and the animation stills all read it. Source: docs/input-evidence.md.
LINE_COST_M_YEN_KM = {"66": 410, "187": 510}


@dataclass
class Choice:
    chosen: list[int]                  # indices of the picked sites, best first
    heat: float                        # sum of their heat values, yen per year
    grid: float                        # sum of their annual grid-connection costs, yen per year
    status: str                        # "optimal", or why nothing was picked
    score: np.ndarray = field(default_factory=lambda: np.zeros(0))   # h_j - g_j for every site

    @property
    def net(self) -> float:
        return self.heat - self.grid


def annuity(rate: float, years: int) -> float:
    return rate * (1 + rate) ** years / ((1 + rate) ** years - 1) if rate > 0 else 1.0 / years


def choose_sites(heat, grid_km, xy, n: int = 1, yen_per_km_year: float = 0.0, spacing_m: float = 0.0,
                 mw: float = 10.0, group=None, headroom: dict | None = None, exactly: bool = True) -> Choice:
    """Pick n sites. heat: yen per year per site. grid_km: km to the connection point (nan: unknown,
    treated as zero cost). xy: metric coordinates (m) for the spacing rule. group: the connection
    point of each site; headroom: {connection point: MW}. exactly=False picks at most n."""
    heat = np.asarray(heat, float)
    km = np.nan_to_num(np.asarray(grid_km, float), nan=0.0)
    xy = np.asarray(xy, float).reshape(len(heat), 2)
    grid = yen_per_km_year * km
    score = heat - grid
    m = len(heat)
    if m == 0 or n <= 0:
        return Choice([], 0.0, 0.0, "nothing to choose", score)
    rows, cols, vals, lo, hi = [], [], [], [], []

    def add(idx, coef, lower, upper):
        r = len(lo)
        rows.extend([r] * len(idx))
        cols.extend(idx)
        vals.extend(coef)
        lo.append(lower)
        hi.append(upper)

    add(list(range(m)), [1.0] * m, float(n) if exactly else 0.0, float(n))
    if spacing_m > 0:
        for i in range(m):
            for j in range(i + 1, m):
                if np.hypot(*(xy[i] - xy[j])) < spacing_m:
                    add([i, j], [1.0, 1.0], 0.0, 1.0)
    if headroom and group is not None:
        for s, cap in headroom.items():
            members = [j for j in range(m) if group[j] == s]
            if members:
                add(members, [mw] * len(members), 0.0, float(cap))
    a = sp.csr_matrix((vals, (rows, cols)), shape=(len(lo), m))
    res = milp(-score, constraints=LinearConstraint(a, lo, hi), integrality=np.ones(m), bounds=Bounds(0, 1))
    if res.x is None:
        return Choice([], 0.0, 0.0, "no feasible choice: fewer sites than asked satisfy the rules", score)
    chosen = sorted((j for j in range(m) if res.x[j] > 0.5), key=lambda j: -score[j])
    return Choice(chosen, float(heat[chosen].sum()), float(grid[chosen].sum()), "optimal", score)


def pareto(heat, grid_km) -> list[int]:
    """Sites that no other site beats on both counts: more heat value and a shorter grid connection."""
    heat, km = np.asarray(heat, float), np.asarray(grid_km, float)
    keep = []
    for j in range(len(heat)):
        better = (heat >= heat[j]) & (km <= km[j]) & ((heat > heat[j]) | (km < km[j]))
        if not better.any():
            keep.append(j)
    return sorted(keep, key=lambda j: km[j])
