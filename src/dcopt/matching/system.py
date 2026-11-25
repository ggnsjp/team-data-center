"""What an added load, and added solar and wind, change in the area's records.

The yearly and slot-by-slot counts (score.py) say which energy a data center may call its own. This
module asks the other question: with the data center there, what did the area's plants do
differently? It replays the published slots with a simple rule and nothing else changed:

    * Solar and wind produce what the weather gives. Hydro, biomass, geothermal, pumped storage,
      batteries and the interconnection stay as recorded.
    * Thermal plants cover what is left. They can turn down to `floor_mw` and no further; in a slot
      where solar or wind was already curtailed they are taken to be at their limit.
    * An added load first uses output that was being curtailed in that slot; the rest raises
      thermal output.
    * Added solar and wind first lower thermal output down to the floor; the rest is curtailed.

It is a replay of one year's slots, not a dispatch model: no network limits, no change in exports,
pumping or plant commitment, and one floor for the whole year. Read the results as the direction
and rough size of the effect.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from dcopt.matching.records import SLOT_H, curtailed_renewable, thermal


def gwh(mw: np.ndarray) -> float:
    return float(np.sum(mw) * SLOT_H / 1000.0)


def absorbed_gwh(df: pd.DataFrame, load: np.ndarray) -> float:
    """Curtailed solar and wind energy that the load could have used in the same slots, GWh: the
    most an added load can claim of renewable output that existed and was thrown away."""
    return gwh(np.minimum(np.asarray(load, dtype=float), curtailed_renewable(df).to_numpy()))


def thermal_floor(df: pd.DataFrame) -> float:
    """How far thermal plants were turned down when solar or wind was being curtailed: the low end
    (10th percentile) of thermal output in those slots. Without any curtailed slot, the lowest 1 %
    of the year.

    The low end and not the median, because output is also curtailed for reasons other than an
    area-wide surplus (the records do not give the reason): in fiscal 2025 solar or wind was
    curtailed at thermal outputs between 325 and 2,104 MW. The low end is close in both years
    (514 and 540 MW)."""
    th, cut = thermal(df), curtailed_renewable(df) > 0
    return float(th[cut].quantile(0.10)) if cut.any() else float(th.quantile(0.01))


@dataclass(frozen=True)
class Replay:
    thermal_gwh: float            # thermal generation over the period
    curtailed_gwh: float          # solar and wind curtailed
    base_thermal_gwh: float       # the same two numbers in the records as published
    base_curtailed_gwh: float
    added_load_gwh: float
    added_renewable_gwh: float    # what the added solar and wind could have produced
    floor_mw: float
    thermal_mw: np.ndarray        # per slot
    curtailed_mw: np.ndarray

    @property
    def thermal_change_gwh(self) -> float:
        return self.thermal_gwh - self.base_thermal_gwh

    @property
    def used_renewable_gwh(self) -> float:
        """Added solar and wind output that was used (not curtailed), GWh."""
        return self.added_renewable_gwh - (self.curtailed_gwh - self.base_curtailed_gwh) \
            if self.curtailed_gwh >= self.base_curtailed_gwh else self.added_renewable_gwh

    @property
    def thermal_per_added_load(self) -> float:
        """Extra thermal generation per unit of added load (1: all of it came from thermal plants)."""
        return self.thermal_change_gwh / self.added_load_gwh if self.added_load_gwh else float("nan")


def replay(df: pd.DataFrame, added_load: np.ndarray | float = 0.0,
           added_renewable: np.ndarray | float = 0.0, floor_mw: float | None = None) -> Replay:
    """Replay the slots with an added load and added solar and wind output (both MW per slot)."""
    n = len(df)
    th, cut = thermal(df).to_numpy(), curtailed_renewable(df).to_numpy()
    floor = thermal_floor(df) if floor_mw is None else float(floor_mw)
    load = np.broadcast_to(np.asarray(added_load, dtype=float), (n,))
    ren = np.broadcast_to(np.asarray(added_renewable, dtype=float), (n,))
    net = load - ren                                           # > 0: more to cover; < 0: more to place
    room = np.where(cut > 0, 0.0, np.maximum(th - floor, 0.0))  # how far thermal can still turn down
    take = np.minimum(np.maximum(net, 0.0), cut)               # curtailed output the added load uses
    down = np.minimum(np.maximum(-net, 0.0), room)             # thermal output the added renewables replace
    th2 = th + np.maximum(net, 0.0) - take - down
    cut2 = cut - take + np.maximum(-net, 0.0) - down
    return Replay(gwh(th2), gwh(cut2), gwh(th), gwh(cut), gwh(load), gwh(ren), floor, th2, cut2)


def scaled_fleet(df: pd.DataFrame, solar_factor: float = 1.0, wind_factor: float = 1.0) -> np.ndarray:
    """Added output per slot when today's solar and wind fleets grow by these factors, counting
    what they could have produced (actual plus curtailed)."""
    return ((solar_factor - 1.0) * (df["solar"] + df["solar_curtailed"]).to_numpy()
            + (wind_factor - 1.0) * (df["wind"] + df["wind_curtailed"]).to_numpy())


def break_even_load(df: pd.DataFrame, added_renewable: np.ndarray, floor_mw: float | None = None,
                    hi: float = 5000.0) -> float:
    """The flat added load (MW) at which thermal generation over the period equals today's, given
    the added solar and wind. Below it thermal generation falls; above it, it rises."""
    base = replay(df, 0.0, 0.0, floor_mw).thermal_gwh
    lo = 0.0
    if replay(df, hi, added_renewable, floor_mw).thermal_gwh <= base:
        return hi
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if replay(df, mid, added_renewable, floor_mw).thermal_gwh > base:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)
