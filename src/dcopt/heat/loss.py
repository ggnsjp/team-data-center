"""Heat loss of buried pre-insulated pipes from published coefficients: a check on model v2.

Model v2 takes the network loss as a flat share of the heat carried (2 % for the ambient loop, 8 %
for the central network; Params.loss_ambient and loss_central). The loss of a real pipe does not
depend on the heat it carries but on its length, its insulation and the temperatures:

    q [W per metre of route] = U x ( (T_supply + T_return) / 2 - T_ground )

This module computes that for a set of pipes. It is used to check the flat shares on the published
plans (experiments/heat_loss_check) and is the basis for a length-dependent loss term in the model.

Sources
  U, both pipes of a route together, W/(m K): Planungshandbuch Thermische Netze, version 2.0
     (EnergieSchweiz / Swiss Federal Office of Energy, 2025), table 10.1 (two single pipes) and table
     10.2 (twin pipe), insulation series 1 to 3; bonded steel pipes in polyurethane foam, soil
     1.2 W/(m K), cover 0.8 m. https://pubdb.bfe.admin.ch/de/publication/download/12410
  Ground temperature: the yearly wave measured at the Sapporo observatory in 1932-1937 (Yakuwa,
     1940, Journal of the Meteorological Society of Japan 18(1), "札幌の地温に就て"): at 1.0 m between
     3.3 C (25 March) and 16.8 C (5 September); the range decays as 24.5 exp(-0.5584 z) K with depth
     z in metres and lags about 30 days per metre. https://www.jstage.jst.go.jp/article/jmsj1923/18/1/18_1_7/_pdf
     Today's ground is probably a little warmer, which would make the losses slightly smaller.
"""
from __future__ import annotations

import math
from collections.abc import Iterable

DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
U_PAIR = {1: {50: 0.405, 80: 0.492, 100: 0.518, 150: 0.699, 200: 0.760, 250: 0.739},
          2: {50: 0.358, 80: 0.422, 100: 0.441, 150: 0.570, 200: 0.603, 250: 0.591},
          3: {50: 0.315, 80: 0.374, 100: 0.389, 150: 0.478, 200: 0.499, 250: 0.501}}
U_TWIN = {1: {50: 0.254, 80: 0.363, 100: 0.362, 150: 0.413, 200: 0.473},
          2: {50: 0.211, 80: 0.278, 100: 0.275, 150: 0.310, 200: 0.328},
          3: {50: 0.184, 80: 0.226, 100: 0.224, 150: 0.248, 200: 0.257}}
GROUND_MEAN_C = 10.0          # mid-value of the yearly wave at 1.0 m: (16.8 + 3.3) / 2
RANGE_AT_SURFACE_K, DECAY_PER_M = 24.5, 0.5584
COLDEST_DAY_AT_1M, LAG_DAYS_PER_M = 84, 30     # 25 March at 1.0 m
BURIAL_DEPTH_M = 1.2          # water mains in Sapporo lie at 1.1 to 1.2 m, below the 0.6 m frost depth


def u_value(dn: int, kind: str = "pair", series: int = 2) -> float:
    """W/(m K) per metre of route. kind "pair": two single pipes; "twin": both in one casing (the
    table ends at DN200; larger sizes are laid as two single pipes)."""
    if kind == "twin" and dn in U_TWIN[series]:
        return U_TWIN[series][dn]
    if kind not in ("pair", "twin"):
        raise ValueError(f"kind must be pair or twin, got {kind!r}")
    return U_PAIR[series][dn]


def ground_c(month: int, depth_m: float = BURIAL_DEPTH_M) -> float:
    """Ground temperature at pipe depth in the middle of a month (0 = January)."""
    day = sum(DAYS[:month]) + DAYS[month] / 2
    amplitude = 0.5 * RANGE_AT_SURFACE_K * math.exp(-DECAY_PER_M * depth_m)
    coldest = COLDEST_DAY_AT_1M + LAG_DAYS_PER_M * (depth_m - 1.0)
    return GROUND_MEAN_C - amplitude * math.cos(2 * math.pi * (day - coldest) / 365)


def loss_w_per_m(dn: int, supply_c: float, return_c: float, ground: float, kind: str = "pair",
                 series: int = 2) -> float:
    return u_value(dn, kind, series) * ((supply_c + return_c) / 2 - ground)


def monthly_loss_mwh(pipes: Iterable[tuple[int, float]], supply_c: float, return_c: float, kind: str = "pair",
                     series: int = 2, depth_m: float = BURIAL_DEPTH_M) -> list[float]:
    """MWh lost per month by pipes given as (nominal size, km of route), kept at temperature all year."""
    pipes = list(pipes)
    return [sum(loss_w_per_m(dn, supply_c, return_c, ground_c(m, depth_m), kind, series) * km * 1000 for dn, km in pipes)
            * DAYS[m] * 24 / 1e6 for m in range(12)]


def yearly_loss_mwh(pipes: Iterable[tuple[int, float]], supply_c: float, return_c: float, kind: str = "pair",
                    series: int = 2, depth_m: float = BURIAL_DEPTH_M) -> float:
    return sum(monthly_loss_mwh(pipes, supply_c, return_c, kind, series, depth_m))
