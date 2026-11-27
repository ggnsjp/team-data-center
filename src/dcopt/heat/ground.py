"""Heat from the ground next to data-center waste heat: two comparisons on an exported plan.

"Heat from the ground" means two different things, and each meets the waste heat of a data center
on a different point.

  Hot geothermal water   hot enough to use without a heat pump, but found only where the geology puts
                         it, so it has to be carried to the users. `line` prices that pipe with the
                         model's own sizes and costs (dcopt.heat.network.PIPE_SIZES) and takes its
                         heat loss from dcopt.heat.loss.
  Shallow ground heat    the ground at about 10 C, under every building, through a heat pump.
                         `ground_cop` applies the model's heat-pump rule (Params.carnot_cop) to that
                         source in place of the 30 C loop.

Both restate the deliveries of an exported plan (out/heat_network_v2/plans.json, the file the exergy
view reads); neither is an optimization. Not costed: wells and exploration, the ground loops of
ground-source heat pumps, the distribution pipes of a hot-water network, pumping. The reasoning, the
limits and the references are in docs/ground-heat.md.

Run   uv run python scripts/ground_heat.py
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from dcopt.heat import loss
from dcopt.heat.network import HOURS, Params
from dcopt.heat.v1 import KINDS, PROFILES

# Assumption: a hot-water line from a geothermal field runs at 80 C out and 40 C back. That is hot
# enough for every need in the model (the highest is 60 C) after the drop along the line and across a
# heat exchanger, and within the range of the pipes whose loss coefficients dcopt.heat.loss holds.
HOT_SUPPLY_C, HOT_RETURN_C = 80.0, 40.0
# Ground temperature for ground-source heat pumps: at a depth of about 10 m the ground is at the yearly
# mean air temperature, "北海道で10℃", and about 100 m down it is 2 to 4 K warmer (Ministry of the
# Environment, 地中熱とは？, https://www.env.go.jp/water/jiban/post_117.html).
GROUND_C = 10.0
GROUND_RISE_AT_100M_K = (2.0, 4.0)

# Where the nearest hot resources named in docs/ground-heat.md are: (latitude, longitude). The
# data-center block is 石狩市新港中央一丁目 by the address search of the Geospatial Information Authority
# of Japan (https://msearch.gsi.go.jp/address-search/AddressSearch); the places are the coordinates of
# the Japanese Wikipedia articles of the same names (read 2026-11-28). Japanese name, English name, point.
DATA_CENTER_BLOCK = (43.17971, 141.29475)
PLACES = {
    "jozankei": ("定山渓温泉", "Jozankei hot springs", (42.96444444, 141.16138889)),
    "toyoha": ("豊羽鉱山", "Toyoha mine", (42.97919444, 141.04452778)),
    "noboribetsu": ("登別温泉", "Noboribetsu hot springs", (42.49506, 141.14406)),
    "mori": ("森発電所", "Mori geothermal power station", (42.13, 140.46)),
}
EARTH_RADIUS_KM = 6371.0088


def straight_km(a: tuple[float, float], b: tuple[float, float] = DATA_CENTER_BLOCK) -> float:
    """Great-circle distance in km between two (latitude, longitude) points; a pipe route is longer."""
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    half = (math.sin((lat2 - lat1) / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(half))


def connected(sites: list[dict]) -> list[dict]:
    """The sites of an exported plan that receive heat (as dcopt.heat.exergy.balance counts them)."""
    return [s for s in sites if s.get("dc") is not None and sum(s["served"]) > 0]


# ------------------------------------------------------------------ hot water carried over a distance
def design_peak_mw(kind: str, annual_mwh: float, P: Params | None = None) -> float:
    """The peak the model sizes a user's pipes and heat pump for (the published convention of
    dcopt.heat.network.user_data): alpha x the kind's peak factor x the highest monthly mean of the
    demand in a normal year."""
    P = P or Params()
    monthly = [annual_mwh * share for share in PROFILES[KINDS[kind][2]]]
    return P.alpha * P.peak_factor[kind] * max(m / h for m, h in zip(monthly, HOURS, strict=True))


def plan_peak_mw(sites: list[dict], P: Params | None = None, heat_pump_only: bool = False) -> float:
    """Sum of the design peaks of a plan's connected users, as the model adds them along a shared
    pipe (no allowance for peaks that fall at different hours). With `heat_pump_only`, the users
    that need a heat pump on the loop."""
    P = P or Params()
    return sum(design_peak_mw(s["kind"], s["annual"], P) for s in connected(sites)
               if not heat_pump_only or P.cop(s["kind"]) is not None)


@dataclass(frozen=True)
class Line:
    """A buried two-pipe line of one nominal size, kept at temperature all year."""
    dn: int
    km: float
    capacity_mw: float     # heat it carries at its temperature difference
    investment: float      # yen
    annuity: float         # yen a year, at the model's rate and pipe life
    loss_mwh: float        # heat lost in a year, whatever the line carries
    loss_peak_mw: float    # loss in the month the ground is coldest


def line(dn: int, km: float, P: Params | None = None, supply_c: float = HOT_SUPPLY_C,
         return_c: float = HOT_RETURN_C) -> Line:
    """Cost and heat loss of `km` of line of size `dn` (one of the model's pipe sizes)."""
    P = P or Params()
    size = next(s for s in P.sizes if s.dn == dn)
    investment = size.yen_m * km * 1000
    monthly = loss.monthly_loss_mwh([(dn, km)], supply_c, return_c)
    return Line(dn, km, size.capacity_mw(supply_c - return_c), investment, investment * P.crf, sum(monthly),
                max(m / h for m, h in zip(monthly, HOURS, strict=True)))


def line_for(peak_mw: float, km: float, P: Params | None = None, supply_c: float = HOT_SUPPLY_C,
             return_c: float = HOT_RETURN_C) -> Line | None:
    """The smallest line of the model's sizes that carries `peak_mw` to the far end on top of its own
    loss; None when no size does."""
    P = P or Params()
    for size in sorted(P.sizes, key=lambda s: s.dn):
        candidate = line(size.dn, km, P, supply_c, return_c)
        if candidate.capacity_mw >= peak_mw + candidate.loss_peak_mw:
            return candidate
    return None


def pipe_investment(pipes: Iterable[tuple[int, float]], P: Params | None = None) -> float:
    """Yen for pipes given as (nominal size, km of route), at the model's cost per metre."""
    P = P or Params()
    yen_m = {s.dn: s.yen_m for s in P.sizes}
    return sum(yen_m[dn] * km * 1000 for dn, km in pipes)


# ------------------------------------------------------------------ heat pumps: on the loop, on the ground
def ground_cop(kind: str, P: Params | None = None, ground_c: float = GROUND_C) -> float | None:
    """COP of a ground-source heat pump serving this kind of user, by the model's own rule with the
    ground in place of the loop; None if the ground were warm enough to use directly."""
    P = P or Params()
    need = P.supply_c[kind]
    if need <= ground_c - P.direct_margin_k:
        return None
    return P.carnot_cop(need, ground_c - P.approach_k)


@dataclass(frozen=True)
class HeatPumps:
    """What a plan's users spend on heat pumps in a year, with the model's prices."""
    users: int = 0             # users with a heat pump
    capacity_mw: float = 0.0   # sum of their design peaks
    electricity: float = 0.0   # MWh a year
    electricity_yen: float = 0.0
    investment: float = 0.0    # yen
    annuity: float = 0.0       # yen a year, at the model's rate and heat-pump life

    @property
    def yearly_yen(self) -> float:
        return self.electricity_yen + self.annuity


def heat_pumps(sites: list[dict], P: Params | None = None, ground_c: float | None = None) -> HeatPumps:
    """Heat pumps for the plan's deliveries: on the data-center loop (`ground_c` None), or at every
    user on ground heat of the given temperature."""
    P = P or Params()
    users, capacity, electricity = 0, 0.0, 0.0
    for s in connected(sites):
        cop = P.cop(s["kind"]) if ground_c is None else ground_cop(s["kind"], P, ground_c)
        if cop is None:
            continue
        users += 1
        capacity += design_peak_mw(s["kind"], s["annual"], P)
        electricity += sum(s["served"]) / cop
    investment = P.hp_yen_per_mw_user * capacity
    return HeatPumps(users, capacity, electricity, electricity * 1000 * P.power_yen_kwh, investment,
                     investment * P.crf_hp)


def by_kind(sites: list[dict], P: Params | None = None, ground_c: float = GROUND_C) -> dict[str, dict]:
    """Per kind of connected user: users, heat (MWh a year) and the electricity on the loop and on
    ground heat."""
    P = P or Params()
    out: dict[str, dict] = {}
    for s in connected(sites):
        row = out.setdefault(s["kind"], {"users": 0, "heat": 0.0, "loop": 0.0, "ground": 0.0})
        heat = sum(s["served"])
        loop_cop, g_cop = P.cop(s["kind"]), ground_cop(s["kind"], P, ground_c)
        row["users"] += 1
        row["heat"] += heat
        row["loop"] += 0.0 if loop_cop is None else heat / loop_cop
        row["ground"] += 0.0 if g_cop is None else heat / g_cop
    return out


# ------------------------------------------------------------------ both comparisons for one plan
def summary(plan: dict, P: Params | None = None, km: float = 10.0) -> dict:
    """The figures of docs/ground-heat.md for one exported plan.

    Hot water: the line that carries the users' design peaks over `km`, what the plan's own pipes
    cost, the length of line that costs as much, and the length whose annuity equals what hot water
    saves (the heat pumps on the loop and their electricity). Ground heat: the heat pumps of every
    user on ground heat against those on the loop, and what would be left for ground loops before
    ground heat cost as much as the plan (the pipes' annuity less the extra spent on heat pumps,
    as an investment at the model's rate and pipe life)."""
    P = P or Params()
    sites = plan["sites"]
    pipes = [(p["dn"], p["km"]) for p in plan["pipes"]]
    peak = plan_peak_mw(sites, P)
    hot = line_for(peak, km, P) if peak > 0 else None      # nothing to carry: no line
    loop, ground = heat_pumps(sites, P), heat_pumps(sites, P, GROUND_C)
    invested = pipe_investment(pipes, P)
    out = {"users": len(connected(sites)), "heat": float(sum(sum(s["served"]) for s in connected(sites))),
           "peak_mw": peak, "pipe_km": sum(k for _, k in pipes), "pipe_investment": invested,
           "pipe_annuity": invested * P.crf, "loop": loop, "ground": ground, "line": hot,
           "ground_loop_budget": (invested * P.crf - (ground.yearly_yen - loop.yearly_yen)) / P.crf}
    if hot is not None:
        out["km_same_investment"] = invested / (hot.investment / km)
        out["km_paid_by_heat_pumps"] = loop.yearly_yen / (hot.annuity / km)
        out["loss_share"] = hot.loss_mwh / out["heat"]
    return out
