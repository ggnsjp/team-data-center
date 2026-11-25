"""Counting how renewable a load is: by the year, and slot by slot.

A data center uses L_t MW in slot t. Its contract with solar and wind plants delivers G_t MW in
the same slot. Three numbers describe the same year:

    volume    sum_t G_t / sum_t L_t                the yearly count: "100 % renewable" when it is 1
    matched   sum_t min(L_t, G_t) / sum_t L_t      the share of its use that was generated in the
                                                   same 30-minute slot
    surplus   sum_t max(G_t - L_t, 0) / sum_t L_t  contracted energy that others had to use

volume = matched + surplus, so a contract for exactly the yearly use leaves 1 - matched of the use
to the rest of the power system and sends the same amount back at other times.

Storage and shifting work inside the day (or longer, for a large store) and raise `matched`:
with_storage() runs a battery on the contract's own surplus; shifted() moves a share of each day's
work to the slots with more generation.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from dcopt.matching.records import SLOT_H, SLOTS_PER_DAY


def flat_load(n: int, mw: float = 1.0) -> np.ndarray:
    """A load that never changes: the working assumption for a data center until measured profiles
    are available."""
    return np.full(n, float(mw))


def fleet_solar_share(df: pd.DataFrame) -> float:
    """Solar's share of the area's solar-plus-wind energy over the table."""
    s, w = float(df["solar"].sum()), float(df["wind"].sum())
    return s / (s + w)


def shaped(series, load: np.ndarray) -> np.ndarray:
    """A source's output scaled to the load's energy over the period: what a contract for exactly
    the load's use delivers in each slot when the plant behaves like the area's whole fleet."""
    g = np.asarray(series, dtype=float)
    return g * (float(np.sum(load)) / float(np.sum(g)))


def contracted(df: pd.DataFrame, load: np.ndarray, volume: float = 1.0,
               solar_share: float | None = None) -> np.ndarray:
    """MW delivered per slot by a contract for `volume` times the load's energy over the period,
    `solar_share` of it from solar and the rest from wind (None: the area's own mix)."""
    a = fleet_solar_share(df) if solar_share is None else float(solar_share)
    return volume * (a * shaped(df["solar"], load) + (1.0 - a) * shaped(df["wind"], load))


def longest_run(mask: np.ndarray) -> int:
    """Length of the longest run of True."""
    if not mask.any():
        return 0
    edges = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    return int((np.flatnonzero(edges == -1) - np.flatnonzero(edges == 1)).max())


@dataclass(frozen=True)
class Score:
    volume: float            # contracted energy / energy used
    matched: float           # energy used that was covered in its own slot / energy used
    surplus: float           # contracted energy left over in its slot / energy used
    slots_covered: float     # share of slots covered in full
    longest_gap_h: float     # longest run of slots with less than `gap_below` of the load covered
    worst_week: float        # the lowest matched share over any 7 days in a row

    @property
    def unmatched(self) -> float:
        return 1.0 - self.matched


def score(load: np.ndarray, delivered: np.ndarray, contract: np.ndarray | None = None,
          gap_below: float = 0.1) -> Score:
    """Score a year. `delivered` is what reaches the load from the contract in each slot (the
    contract's own output, or that output after storage or shifting); `contract` is the contract's
    output when it differs from `delivered` (so that volume still counts everything generated)."""
    load = np.asarray(load, dtype=float)
    got = np.minimum(load, np.asarray(delivered, dtype=float))
    gen = np.asarray(delivered if contract is None else contract, dtype=float)
    used = float(load.sum())
    week = 7 * SLOTS_PER_DAY
    if len(load) >= week:
        c_got, c_load = np.cumsum(np.concatenate(([0.0], got))), np.cumsum(np.concatenate(([0.0], load)))
        worst = float(((c_got[week:] - c_got[:-week]) / (c_load[week:] - c_load[:-week])).min())
    else:
        worst = float(got.sum() / used)
    return Score(
        volume=float(gen.sum() / used),
        matched=float(got.sum() / used),
        surplus=float(np.maximum(gen - load, 0.0).sum() / used) if contract is None
        else float((gen.sum() - got.sum()) / used),
        slots_covered=float(np.mean(got >= load - 1e-9)),
        longest_gap_h=longest_run(got < gap_below * load) * SLOT_H,
        worst_week=worst,
    )


def with_storage(load: np.ndarray, gen: np.ndarray, power_mw: float, energy_mwh: float,
                 efficiency: float = 0.85, passes: int = 2) -> np.ndarray:
    """MW reaching the load per slot when a battery stores the contract's surplus and gives it back
    in the next slots that fall short.

    The battery charges only from the contract's own surplus, at up to `power_mw`, holds up to
    `energy_mwh` and returns `efficiency` of what it took in (split evenly between charging and
    discharging). Charging at the first surplus and discharging at the first shortfall delivers the
    most energy a single store can (tests compare it with the linear program). The year is run
    `passes` times so that the store starts as full as it ends.
    """
    load = np.asarray(load, dtype=float)
    gen = np.asarray(gen, dtype=float)
    if power_mw <= 0 or energy_mwh <= 0:
        return np.minimum(load, gen)
    one_way = float(efficiency) ** 0.5
    spare = np.maximum(gen - load, 0.0).tolist()
    short = np.maximum(load - gen, 0.0).tolist()
    out = np.zeros(len(load))
    soc = 0.0
    for _ in range(max(1, passes)):
        given = [0.0] * len(spare)
        for t, (up, down) in enumerate(zip(spare, short)):
            if up > 0.0:
                soc += one_way * SLOT_H * min(up, power_mw, (energy_mwh - soc) / (one_way * SLOT_H))
            elif down > 0.0 and soc > 0.0:
                d = min(down, power_mw, soc * one_way / SLOT_H)
                soc -= d * SLOT_H / one_way
                given[t] = d
        out = np.minimum(load, gen) + np.array(given)
    return out


def shifted(load: np.ndarray, gen: np.ndarray, flexible: float, headroom: float) -> np.ndarray:
    """Energy matched per day (MW-slots) when a share of each day's work may move within the day.

    `flexible` is the share of the day's energy that may be done at another time of the same day;
    `headroom` is the spare capacity it may use (0.25: the site can draw up to 125 % of its usual
    load). In slot t the load can then lie between (1 - flexible) L_t and (1 + headroom) L_t with
    the day's energy unchanged. The firm part is matched as before; the movable part goes to the
    slots where generation exceeds the firm part, up to the cap, and whatever does not fit there
    stays unmatched:

        matched_day = sum_t min(G_t, lo_t) + min( flexible * E_day, sum_t [min(G_t, hi_t) - min(G_t, lo_t)] )

    Running at 1 + headroom for part of the day means owning that much more equipment for the same
    work; the mean use of the equipment falls to 1 / (1 + headroom).
    """
    load = np.asarray(load, dtype=float)
    gen = np.asarray(gen, dtype=float)
    days = len(load) // SLOTS_PER_DAY
    L = load[: days * SLOTS_PER_DAY].reshape(days, SLOTS_PER_DAY)
    G = gen[: days * SLOTS_PER_DAY].reshape(days, SLOTS_PER_DAY)
    lo, hi = (1.0 - flexible) * L, (1.0 + headroom) * L
    firm = np.minimum(G, lo).sum(axis=1)
    room = (np.minimum(G, hi) - np.minimum(G, lo)).sum(axis=1)
    return firm + np.minimum(flexible * L.sum(axis=1), room)


def shifted_share(load: np.ndarray, gen: np.ndarray, flexible: float, headroom: float) -> float:
    """The matched share of the year under shifted()."""
    days = len(load) // SLOTS_PER_DAY
    return float(shifted(load, gen, flexible, headroom).sum() / np.sum(load[: days * SLOTS_PER_DAY]))
