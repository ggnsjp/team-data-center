"""The cheapest contract and battery for a target share of matched slots: a linear program.

A load L_t (MW) buys x_s times its yearly energy from solar plants and x_w times from wind plants,
each with the 30-minute shape of the area's fleet (s_t and w_t, scaled so that one unit delivers
the load's yearly energy), and may add a battery of power p (MW) and capacity e (MWh).

    min   c_s x_s E + c_w x_w E + k_p p + k_e e
    s.t.  m_t + ch_t - dis_t <= x_s s_t + x_w w_t          every slot: use and charging come from the
                                                           contract's output and from the battery
          soc_{t+1} = soc_t + (r ch_t - dis_t / r) h       r = sqrt(round-trip efficiency), h = 0.5 hours;
                                                           the last slot leads back to the first
          0 <= m_t <= L_t,  0 <= ch_t, dis_t <= p,  0 <= soc_t <= e,  e >= d p
          sum_t m_t >= target * sum_t L_t

E is the load's yearly energy; c_s and c_w are contract prices per MWh; k_p and k_e are the yearly
cost of battery power and capacity; d is the shortest duration a battery is built for (hours). Energy the load does not use in its slot (the surplus) earns
`surplus_value` per MWh, zero by default. The energy that is not matched is bought from the grid
whatever the contract, so it does not change which portfolio is cheapest for a given target.

Solving. HiGHS by default. With DCOPT_SOLVER=gurobi (or solver="gurobi") and gurobipy installed the
same program is passed to Gurobi, which is optional: nothing here needs it. On a full year (about
70,000 variables) HiGHS takes half a minute to a minute and Gurobi a few seconds.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog

from dcopt.matching.records import SLOT_H


def solver_name(solver: str | None = None) -> str:
    """HiGHS by default; DCOPT_SOLVER=gurobi (or solver="gurobi") uses Gurobi when gurobipy is installed."""
    name = (solver or os.environ.get("DCOPT_SOLVER", "highs")).lower()
    if name not in ("highs", "gurobi"):
        raise ValueError(f"solver must be highs or gurobi, got {name!r}")
    return name


def _linear_program(c, a_ub, b_ub, a_eq, b_eq, bounds, solver: str, interior: bool) -> np.ndarray | None:
    """min c.x  s.t.  a_ub x <= b_ub, a_eq x = b_eq, bounds. The optimal x, or None when there is none."""
    if solver == "gurobi":
        try:
            import gurobipy as gp
        except ImportError as e:  # pragma: no cover - depends on the environment
            raise RuntimeError("gurobipy is not installed: run `uv sync --extra gurobi`") from e
        lb = np.array([0.0 if lo is None else lo for lo, _ in bounds])
        ub = np.array([gp.GRB.INFINITY if hi is None else hi for _, hi in bounds])
        with gp.Env(params={"OutputFlag": 0}) as env, gp.Model("matching", env=env) as g:
            x = g.addMVar(len(c), lb=lb, ub=ub)
            g.setObjective(c @ x)
            g.addMConstr(a_ub, x, "<", b_ub)
            if a_eq is not None:
                g.addMConstr(a_eq, x, "=", b_eq)
            g.Params.Method = 2 if interior else -1            # barrier on the year with a battery
            g.optimize()
            return np.array(x.X) if g.Status == gp.GRB.OPTIMAL else None
    # the interior-point method is two to three times faster than simplex on the year with a battery
    res = linprog(c, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq, bounds=bounds,
                  method="highs-ipm" if interior else "highs")
    return res.x if res.status == 0 else None


@dataclass(frozen=True)
class Costs:
    """Prices for the program. Sources and reasons: docs/data-sources.md, "Renewable matching"."""
    solar_yen_kwh: float = 10.9            # generation cost of utility-scale solar, 2023 plant, policy costs included
    wind_yen_kwh: float = 16.3             # the same for onshore wind (Power Generation Cost Verification WG, 2025)
    battery_yen_kwh: float = 60_000.0      # assumption: 54,000 yen/kWh for the system (METI study group, FY2024) plus installation
    battery_yen_kw: float = 0.0            # installed cost per kW of power, when quoted separately
    battery_life_years: float = 15.0       # assumption
    discount_rate: float = 0.03            # as in theme 1
    battery_efficiency: float = 0.85       # assumption: round trip
    battery_min_hours: float = 3.0         # assumption: capacity is at least this many hours of the battery's power
    surplus_value_yen_kwh: float = 0.0     # assumption: the energy not used in its slot earns nothing (cautious)

    @property
    def crf(self) -> float:
        r, n = self.discount_rate, self.battery_life_years
        return r / (1.0 - (1.0 + r) ** -n) if r > 0 else 1.0 / n

    @property
    def battery_yen_mwh_year(self) -> float:
        return self.battery_yen_kwh * 1000.0 * self.crf

    @property
    def battery_yen_mw_year(self) -> float:
        return self.battery_yen_kw * 1000.0 * self.crf


@dataclass(frozen=True)
class Portfolio:
    target: float
    feasible: bool
    solar: float = 0.0             # contracted solar energy / the load's energy
    wind: float = 0.0              # contracted wind energy / the load's energy
    battery_mw: float = 0.0        # per MW of mean load
    battery_h: float = 0.0         # capacity in hours of the mean load
    matched: float = 0.0
    yen_per_kwh_used: float = 0.0  # yearly cost of contract and battery / the load's energy
    delivered: np.ndarray | None = None   # MW reaching the load per slot
    solver: str = "highs"

    @property
    def volume(self) -> float:
        return self.solar + self.wind


def _program(load, solar, wind, eff, with_battery):
    """The constraint matrix shared by the programs below. Variable order:
    [x_s, x_w, p, e, m (T), ch (T), dis (T), soc (T)]; without a battery only [x_s, x_w, m (T)]."""
    T = len(load)
    eye = sp.identity(T, format="csr")
    s, w = sp.csr_matrix(solar.reshape(-1, 1)), sp.csr_matrix(wind.reshape(-1, 1))
    if not with_battery:
        a_ub = sp.hstack([-s, -w, eye], format="csr")                        # m <= x_s s + x_w w
        return a_ub, np.zeros(T), None, None
    zero, col0 = sp.csr_matrix((T, T)), sp.csr_matrix((T, 1))
    ones = sp.csr_matrix(np.ones((T, 1)))
    r = eff ** 0.5
    nxt = sp.csr_matrix((np.ones(T), (np.arange(T), (np.arange(T) + 1) % T)), shape=(T, T))
    balance = sp.hstack([-s, -w, col0, col0, eye, eye, -eye, zero])          # m + ch - dis <= output
    ch_cap = sp.hstack([col0, col0, -ones, col0, zero, eye, zero, zero])     # ch <= p
    dis_cap = sp.hstack([col0, col0, -ones, col0, zero, zero, eye, zero])    # dis <= p
    soc_cap = sp.hstack([col0, col0, col0, -ones, zero, zero, zero, eye])    # soc <= e
    a_ub = sp.vstack([balance, ch_cap, dis_cap, soc_cap], format="csr")
    a_eq = sp.hstack([col0, col0, col0, col0, zero, -r * SLOT_H * eye, (SLOT_H / r) * eye, nxt - eye],
                     format="csr")                                           # soc_{t+1} - soc_t = ...
    return a_ub, np.zeros(4 * T), a_eq, np.zeros(T)


def cheapest(load: np.ndarray, solar: np.ndarray, wind: np.ndarray, target: float,
             costs: Costs = Costs(), battery: bool = True, max_volume: float = 50.0,
             solver: str | None = None) -> Portfolio:
    """The cheapest solar and wind contract, with a battery if allowed, that covers `target` of the
    load's energy in the same slots. `solar` and `wind` are the shapes scaled to the load's energy
    (score.shaped). Infeasible when the target cannot be reached with `max_volume` times the load's
    energy from each source."""
    load = np.asarray(load, dtype=float)
    solar, wind = np.asarray(solar, dtype=float), np.asarray(wind, dtype=float)
    T, energy = len(load), float(load.sum() * SLOT_H)                         # MWh
    mean = float(load.mean())
    a_ub, b_ub, a_eq, b_eq = _program(load, solar, wind, costs.battery_efficiency, battery)
    n = a_ub.shape[1]
    first_m = 4 if battery else 2
    # yen per year: contracts are paid for all they generate; the surplus earns surplus_value
    cs = (costs.solar_yen_kwh - costs.surplus_value_yen_kwh) * 1000.0 * energy
    cw = (costs.wind_yen_kwh - costs.surplus_value_yen_kwh) * 1000.0 * energy
    c = np.zeros(n)
    c[0], c[1] = cs, cw
    if battery:
        c[2], c[3] = costs.battery_yen_mw_year, costs.battery_yen_mwh_year
    scale = max(abs(cs), abs(cw), 1.0)
    row = sp.csr_matrix((-np.ones(T), (np.zeros(T, dtype=int), first_m + np.arange(T))), shape=(1, n))
    rows, rhs = [a_ub, row], [b_ub, [-target * float(load.sum())]]           # sum m >= target * sum L
    if battery:                                                               # d p - e <= 0
        rows.append(sp.csr_matrix(([costs.battery_min_hours, -1.0], ([0, 0], [2, 3])), shape=(1, n)))
        rhs.append([0.0])
    a_ub, b_ub = sp.vstack(rows, format="csr"), np.concatenate(rhs)
    bounds = [(0, max_volume), (0, max_volume)] + ([(0, None), (0, None)] if battery else [])
    bounds += [(0, v) for v in load] + ([(0, None)] * (3 * T) if battery else [])
    name = solver_name(solver)
    x = _linear_program(c / scale, a_ub, b_ub, a_eq, b_eq, bounds, name, interior=battery)
    if x is None:
        return Portfolio(target, False, solver=name)
    m = x[first_m:first_m + T]
    p, e = (float(x[2]), float(x[3])) if battery else (0.0, 0.0)
    yen = float(c @ x) + costs.surplus_value_yen_kwh * 1000.0 * float(m.sum() * SLOT_H)
    return Portfolio(target, True, float(x[0]), float(x[1]), p / mean, e / mean if mean else 0.0,
                     float(m.sum() / load.sum()), yen / (energy * 1000.0), m, name)


def best_delivery(load: np.ndarray, gen: np.ndarray, power_mw: float, energy_mwh: float,
                  efficiency: float = 0.85) -> float:
    """The most energy (as a share of the load's) that a battery of this size can deliver from this
    contract: the linear program that score.with_storage() is checked against."""
    load, gen = np.asarray(load, dtype=float), np.asarray(gen, dtype=float)
    T = len(load)
    a_ub, b_ub, a_eq, b_eq = _program(load, gen, np.zeros(T), efficiency, True)
    n = a_ub.shape[1]
    c = np.zeros(n)
    c[4:4 + T] = -1.0
    bounds = [(1, 1), (0, 0), (power_mw, power_mw), (energy_mwh, energy_mwh)]
    bounds += [(0, v) for v in load] + [(0, None)] * (3 * T)
    x = _linear_program(c, a_ub, b_ub, a_eq, b_eq, bounds, "highs", interior=False)
    if x is None:
        raise RuntimeError("the delivery program has no solution")
    return float(-(c @ x) / load.sum())
