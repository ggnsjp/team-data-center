"""Exergy view of a heat-network plan: how much of the heat could do work, and what each supply spends.

Energy counts heat by quantity. Exergy counts the part of it that could be turned into work, which
depends on how far the heat's temperature is from the surroundings: electricity is all exergy, and
water at 30 C in a Hokkaido winter about a tenth. This module restates an exported plan in those terms
and compares two ways of supplying the same heat: a kerosene boiler at every user, or the data
centers' waste heat, taken directly where the loop is warm enough and lifted by a heat pump elsewhere.

  Reference state    the outdoor air, month by month (the temperatures stored with the export, which
                     are the JMA normals of dcopt.heat.v1.TEMP)
  Heat Q at T        Q (1 - T0 / T), temperatures in kelvin; nothing when T is at or below T0
  Electricity        its energy
  Kerosene           litres x FUEL_EXERGY_KWH_PER_L (an assumption, see the constant)
  Efficiency         exergy of the delivered heat / exergy spent to deliver it

Delivered heat is valued at the temperature its user needs (Params.supply_c), in either network mode,
so heat sent hotter than needed does not count for more. The temperatures, the heat pumps and the
boiler are the model's own (dcopt.heat.network.Params): the figures describe the plan as the
optimization saw it. Pumping power is not in the model and not in these figures.

The reasoning, a worked example, the limits and the references are in docs/exergy.md.

Run   uv run python scripts/exergy_balance.py
"""
from __future__ import annotations

from dataclasses import dataclass, fields

from dcopt.heat.network import Params
from dcopt.heat.v1 import KEROSENE_KWH_PER_L

KELVIN = 273.15
# Assumption: the chemical exergy of kerosene equals its gross heating value, 36.60 MJ/L (the standard
# value cited in docs/input-evidence.md). That is 1.065 times the net value; docs/exergy.md gives the
# effect of taking the model's 9.7 kWh/L instead.
FUEL_EXERGY_KWH_PER_L = 10.17


def carnot_factor(t_c: float, t0_c: float) -> float:
    """Share of heat at t_c (C) that is exergy when the surroundings are at t0_c (C)."""
    return max(0.0, 1.0 - (t0_c + KELVIN) / (t_c + KELVIN))


@dataclass(frozen=True)
class Flows:
    """Yearly sums for a group of users, in MWh. Kerosene and its exergy are what boilers would burn
    for the same heat; electricity, waste heat and its exergy are what the plan spends."""
    users: int = 0
    heat: float = 0.0            # delivered to the users
    heat_exergy: float = 0.0     # at the temperature each user needs
    electricity: float = 0.0     # heat pumps
    waste_heat: float = 0.0      # drawn from the data centers
    waste_exergy: float = 0.0    # at the waste-heat temperature
    kerosene: float = 0.0        # fuel energy at the model's heating value
    fuel_exergy: float = 0.0

    def __add__(self, other: Flows) -> Flows:
        return Flows(*(getattr(self, f.name) + getattr(other, f.name) for f in fields(self)))

    @property
    def quality(self) -> float:
        """Exergy per unit of delivered heat."""
        return self.heat_exergy / self.heat if self.heat else 0.0

    @property
    def boiler_efficiency(self) -> float:
        """Exergy efficiency of supplying this heat from kerosene boilers."""
        return self.heat_exergy / self.fuel_exergy if self.fuel_exergy else 0.0

    @property
    def plan_efficiency(self) -> float:
        """Exergy efficiency of the plan: delivered exergy over electricity plus waste-heat exergy."""
        spent = self.electricity + self.waste_exergy
        return self.heat_exergy / spent if spent else 0.0

    @property
    def high_grade_cut(self) -> float:
        """Share by which the purchased high-grade input falls: fuel exergy replaced by electricity."""
        return 1.0 - self.electricity / self.fuel_exergy if self.fuel_exergy else 0.0


def month_flows(kind: str, mwh: float, t0_c: float, P: Params | None = None) -> Flows:
    """What `mwh` of heat delivered to one kind of user costs in a month with outdoor mean t0_c."""
    P = P or Params()
    per = P.per_kind(kind)
    litres_per_mwh = 1000.0 / (KEROSENE_KWH_PER_L * P.boiler_eff)
    return Flows(
        heat=mwh,
        heat_exergy=mwh * carnot_factor(P.supply_c[kind], t0_c),
        electricity=mwh * per["elec"],
        waste_heat=mwh * per["r"],
        waste_exergy=mwh * per["r"] * carnot_factor(P.waste_c, t0_c),
        kerosene=mwh / P.boiler_eff,
        fuel_exergy=mwh * litres_per_mwh * FUEL_EXERGY_KWH_PER_L / 1000.0,
    )


def balance(sites: list[dict], temps_c: list[float], P: Params | None = None) -> dict[str, Flows]:
    """Exergy balance of one exported plan: "all" and one entry per kind of connected user.

    `sites` are the plan's sites as exported (kind, dc, served: MWh per month); a site without a data
    center, or without deliveries, is not connected and is left out."""
    P = P or Params()
    out: dict[str, Flows] = {"all": Flows()}
    for site in sites:
        if site.get("dc") is None or sum(site["served"]) <= 0:
            continue
        flows = Flows(users=1)
        for mwh, t0 in zip(site["served"], temps_c, strict=True):
            flows = flows + month_flows(site["kind"], mwh, t0, P)
        out[site["kind"]] = out.get(site["kind"], Flows()) + flows
        out["all"] = out["all"] + flows
    return out


def resource(waste_month: list[float], temps_c: list[float], P: Params | None = None) -> tuple[float, float]:
    """The waste heat on offer in a year and its exergy, both in MWh."""
    P = P or Params()
    return sum(waste_month), sum(w * carnot_factor(P.waste_c, t0) for w, t0 in zip(waste_month, temps_c, strict=True))


def central_electricity(heat: float, P: Params | None = None) -> float:
    """Electricity (MWh) if the same heat went through the 60 C network with one central heat pump.

    A comparison on fixed deliveries, not a plan optimized for that network."""
    P = P or Params()
    return heat * (1 + P.loss_central) / P.carnot_cop(P.central_c, P.waste_c - P.approach_k)
