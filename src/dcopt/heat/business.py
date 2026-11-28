"""The heat network as a business: what each kind of user could pay for heat, and what the network
needs (docs/heat-business.md).

The model values a MWh delivered to a user as the kerosene it replaces, less the electricity of the
user's own heat pump (dcopt.heat.network.user_data), and charges the annuities of the pipes and of
the users' heat pumps against the plan (Plan.annual_cost). Splitting that account at one price for
heat gives a price window for each kind of user:

  the most it can pay     its kerosene cost per MWh, less its own heat pump's electricity and
                          annuity per MWh (nothing to subtract for users that take the loop's heat
                          directly)
  the least the network needs   the pipes' annuity divided by all the heat delivered, if every user
                          pays the same price

(most - least) x heat, summed over the users at the scenarios' mean kerosene price, is the plan's
expected net benefit; computed from an export it differs only by the rounding of the export (pipe
lengths to 10 m). Ambient loop only, the published configuration: there the heat pumps stand at the
users.

Not in the model, so not here: any payment to the data centers for their heat, equipment at the data
centers, operation and maintenance, pumping, metering and billing.

Run   uv run python scripts/heat_business.py
"""
from __future__ import annotations

from dataclasses import dataclass

from dcopt.heat.ground import connected, design_peak_mw, pipe_investment
from dcopt.heat.network import Params, default_scenarios
from dcopt.heat.v1 import KEROSENE_KWH_PER_L

KEROSENE_LOW, KEROSENE_SURVEY = sorted({s.kerosene_yen_l for s in default_scenarios()})


def mean_kerosene() -> float:
    """The probability-weighted kerosene price of the published scenarios (yen/L)."""
    scens = default_scenarios()
    return sum(s.prob * s.kerosene_yen_l for s in scens) / sum(s.prob for s in scens)


def heat_per_litre(P: Params | None = None) -> float:
    """MWh of heat a litre of kerosene gives in the boiler that the network replaces."""
    P = P or Params()
    return KEROSENE_KWH_PER_L * P.boiler_eff / 1000


def per_litre(yen_per_mwh: float, P: Params | None = None) -> float:
    """A price for heat in yen per MWh, as yen per litre of kerosene it replaces."""
    return yen_per_mwh * heat_per_litre(P)


def _check(P: Params) -> None:
    if P.mode != "ambient":
        raise ValueError("the price window is defined for the ambient loop, where the heat pumps are the users'")


@dataclass(frozen=True)
class Network:
    """What the pipes of a plan cost, per year and per MWh of all the heat they deliver."""
    km: float
    investment: float      # yen
    annuity: float         # yen a year, after the subsidy share, at the model's rate and pipe life
    heat: float            # MWh a year delivered to all users
    yen_per_mwh: float     # the least price that pays for the pipes


def network(plan: dict, P: Params | None = None) -> Network:
    P = P or Params()
    _check(P)
    pipes = [(p["dn"], p["km"]) for p in plan["pipes"]]
    investment = pipe_investment(pipes, P)
    annuity = P.own * P.crf * investment
    heat = float(sum(sum(s["served"]) for s in connected(plan["sites"])))
    return Network(sum(k for _, k in pipes), investment, annuity, heat, annuity / heat if heat > 0 else float("nan"))


@dataclass(frozen=True)
class Window:
    """One kind of user in a plan at one kerosene price, per MWh it receives."""
    kind: str
    users: int
    assumed: bool          # the kind's sites are assumed (they do not exist today)
    heat: float            # MWh a year
    supply_c: float        # the temperature the kind needs
    cop: float | None      # its heat pump's COP on the loop; None: it takes the loop's heat directly
    kerosene: float        # yen per litre
    fuel: float            # yen per MWh: the kerosene the heat replaces
    electricity: float     # yen per MWh: its heat pump's electricity
    heat_pump: float       # yen per MWh: its heat pump's annuity
    most: float            # yen per MWh: the most it can pay for the network's heat
    least: float           # yen per MWh: the least the network needs at one price for all

    @property
    def margin(self) -> float:
        """yen per MWh left to the user (and the network) when the price is `least`."""
        return self.most - self.least

    @property
    def surplus(self) -> float:
        """yen a year."""
        return self.margin * self.heat

    @property
    def opens_at(self) -> float:
        """The kerosene price (yen per litre) above which the window is open: the user's own costs
        and the network's least price, as litres of kerosene."""
        return per_litre(self.least + self.electricity + self.heat_pump)


def windows(plan: dict, kerosene_yen_l: float, P: Params | None = None) -> list[Window]:
    """The price window of every kind of user connected in `plan`, largest heat first."""
    P = P or Params()
    _check(P)
    least = network(plan, P).yen_per_mwh
    fuel = P.fuel_yen_per_mwh(kerosene_yen_l)
    rows: dict[str, dict] = {}
    for s in connected(plan["sites"]):
        r = rows.setdefault(s["kind"], {"users": 0, "assumed": False, "heat": 0.0, "elec": 0.0, "hp": 0.0})
        heat, cop = float(sum(s["served"])), P.cop(s["kind"])
        r["users"] += 1
        r["assumed"] = r["assumed"] or bool(s.get("assumed"))
        r["heat"] += heat
        if cop is not None:
            r["elec"] += heat / cop * 1000 * P.power_yen_kwh
            r["hp"] += P.own * P.crf_hp * P.hp_yen_per_mw_user * design_peak_mw(s["kind"], s["annual"], P)
    out = []
    for kind, r in rows.items():
        elec, hp = r["elec"] / r["heat"], r["hp"] / r["heat"]
        out.append(Window(kind, r["users"], r["assumed"], r["heat"], P.supply_c[kind], P.cop(kind), kerosene_yen_l,
                          fuel, elec, hp, fuel - elec - hp, least))
    return sorted(out, key=lambda w: -w.heat)


def surplus(plan: dict, kerosene_yen_l: float, P: Params | None = None, assumed: bool | None = None) -> float:
    """yen a year over the kinds in the plan; `assumed` True or False keeps only those kinds."""
    return sum(w.surplus for w in windows(plan, kerosene_yen_l, P) if assumed is None or w.assumed == assumed)


def breakeven_kerosene(plan: dict, P: Params | None = None, assumed: bool | None = None) -> float:
    """The kerosene price (yen per litre) at which `surplus` is zero: above it, one price for heat
    exists at which the users and the network both come out even or ahead. The surplus is linear in
    the kerosene price (only the kerosene replaced depends on it)."""
    a, b = KEROSENE_LOW, KEROSENE_SURVEY
    sa, sb = surplus(plan, a, P, assumed), surplus(plan, b, P, assumed)
    return a - sa * (b - a) / (sb - sa)
