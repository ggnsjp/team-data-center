"""Small synthetic instances for the model tests: straight-line distances on a plane, no map data.

Not collected by pytest (the file name does not start with test_); test modules import it.
"""
from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

from dcopt.heat.network import Instance, Scenario, Source
from dcopt.heat.v1 import Site

SCENS = [Scenario("lo", "低", "low", 0.5, 115.0, "low"), Scenario("hi", "高", "high", 0.5, 156.8, "high")]


def instance(src_pts, users, it=None, road_factor: float = 1.3) -> Instance:
    """src_pts: [(x, y)] in metres. users: [(key, kind, (x, y), annual MWh)]. it: per data center
    {"low": MW, "high": MW} (default 0.3 / 0.6 MW, small enough that waste heat binds in winter)."""
    it = it or [{"low": 0.3, "high": 0.6}] * len(src_pts)
    sources = [Source(f"dc{i}", f"DC {i}", f"DC {i}", 0.0, 0.0, dict(it[i]), "operating", ("", ""), "test")
               for i in range(len(src_pts))]
    sites = [Site(k, k, k, kind, 0.0, 0.0, mwh, "test") for k, kind, _, mwh in users]
    pts = list(src_pts) + [p for _, _, p, _ in users]
    dist = np.array([[road_factor * math.dist(a, b) for b in pts] for a in pts])
    return Instance(sources, sites, dist, road=False)


def tiny() -> Instance:
    """Two data centers 2 km apart and five users around them (as in test_heatnet)."""
    return instance([(0, 0), (2000, 0)],
                    [("gh", "greenhouse", (600, 500), 2500.0), ("fish", "aquaculture", (1200, -700), 1800.0),
                     ("school", "school", (-800, 300), 300.0), ("snow", "snow", (2500, 600), 400.0),
                     ("hosp", "hospital", (3000, -400), 1500.0)],
                    it=[{"low": 0.3, "high": 0.6}, {"low": 0.1, "high": 0.4}])


def small_one_dc() -> Instance:
    """One data center and three users: small enough to enumerate every build."""
    return instance([(0, 0)],
                    [("gh", "greenhouse", (600, 400), 2500.0), ("school", "school", (1200, 0), 300.0),
                     ("fish", "aquaculture", (500, -700), 1800.0)])


def small_shared() -> Instance:
    """One data center with plenty of heat and three users close enough to share a trunk."""
    return instance([(0, 0)],
                    [("gh", "greenhouse", (600, 400), 2500.0), ("school", "school", (900, 200), 300.0),
                     ("fish", "aquaculture", (500, -500), 1800.0)],
                    it=[{"low": 2.0, "high": 3.0}])


def small_two_dc() -> Instance:
    """Two data centers and three users."""
    return instance([(0, 0), (1800, 0)],
                    [("gh", "greenhouse", (600, 400), 2500.0), ("pool", "pool", (1300, 300), 800.0),
                     ("fish", "aquaculture", (900, -600), 1800.0)],
                    it=[{"low": 0.3, "high": 0.6}, {"low": 0.2, "high": 0.5}])


def equidistant_two_dc() -> Instance:
    """Two identical data centers at the same distance from one user: every plan has a twin that
    swaps them, so only the tie-break decides which one serves the user."""
    return instance([(-300, 0), (300, 0)], [("fish", "aquaculture", (0, 400), 1800.0)])


def permuted_sources(inst: Instance, perm: list[int]) -> Instance:
    """The same instance with the data centers (keys kept) in the order perm: the columns of z permuted."""
    D = inst.D
    order = list(perm) + list(range(D, inst.n))
    return Instance([inst.sources[i] for i in perm], list(inst.users), inst.dist[np.ix_(order, order)].copy(),
                    inst.road)


def scaled_it(inst: Instance, factor: float) -> Instance:
    """The same instance with every data center's IT load multiplied by factor."""
    srcs = [replace(s, it_mw={k: v * factor for k, v in s.it_mw.items()}) for s in inst.sources]
    return Instance(srcs, list(inst.users), inst.dist.copy(), inst.road)


def complete_edges(inst: Instance) -> list[tuple[int, int]]:
    return [(a, b) for a in range(inst.n) for b in range(a + 1, inst.n)]
