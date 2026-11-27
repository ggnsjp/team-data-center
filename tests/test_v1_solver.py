"""v1.design on HiGHS: status and gap are reported, and a warm start from a nearby plan never makes
the answer worse. Synthetic instance on a plane (straight-line distances x 1.3), no map data."""
from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from dcopt.heat import v1
from dcopt.heat.v1 import Assumptions, Site, design

PTS = [(0, 0), (600, 400), (1200, 0), (500, -700), (-800, 300), (1500, 900), (-400, -900), (2200, -300),
       (900, 1300)]
USERS = [("gh", "greenhouse", 2500.0), ("school", "school", 300.0), ("fish", "aquaculture", 1800.0),
         ("pool", "pool", 800.0), ("hosp", "hospital", 1500.0), ("onsen", "onsen", 2000.0),
         ("snow", "snow", 400.0), ("hotel", "hotel", 1000.0)]
DIST = np.array([[1.3 * math.dist(a, b) for b in PTS] for a in PTS])
# A small data center, so that waste heat binds in winter and the choice of users matters.
A = Assumptions(it_load_mw=0.4, pipe_yen_m=60_000.0)


@pytest.fixture(autouse=True)
def plane(monkeypatch):
    monkeypatch.setattr(v1, "road_distance_matrix", lambda nodes, area: DIST[np.ix_(nodes, nodes)])
    monkeypatch.setattr(v1, "road_path", lambda a, b, area: [])


def sites():
    dc = Site("dc", "DC", "DC", "dc", 0.0, 0.0, 0.0, "test", node=0)
    return dc, [Site(k, k, k, kind, 0.0, 0.0, mwh, "test", node=i + 1) for i, (k, kind, mwh) in enumerate(USERS)]


def tol(x: float) -> float:
    return v1.MIP_REL_GAP * abs(x) + 1.0


def test_cold_solve_reports_status_and_gap():
    dc, ss = sites()
    d = design(dc, ss, A, k=3)
    assert d.status == "Optimal" and 0.0 <= d.gap <= v1.MIP_REL_GAP and not d.warm_start
    assert d.connected and d.annual_net > 0
    assert all(u <= w + 1e-6 for u, w in zip(d.supply_used, d.waste_heat))


def test_warm_start_from_the_no_policy_plan_is_never_worse():
    dc, ss = sites()
    base = design(dc, ss, A, k=3)
    B = replace(A, carbon_yen_t=8000.0, subsidy=0.3)
    cold = design(dc, ss, B, k=3)
    warm = design(dc, ss, B, k=3, start=base)
    assert warm.warm_start and warm.status == "Optimal"
    assert warm.annual_net >= cold.annual_net - tol(cold.annual_net)
    assert warm.annual_net >= replace(base, A=B).annual_net - 1e-6 * abs(warm.annual_net)   # the start itself


def test_a_start_from_another_site_set_is_matched_by_key_or_ignored():
    dc, ss = sites()
    cold = design(dc, ss, A, k=3)
    few = design(dc, ss, A, k=3, kinds={"greenhouse", "aquaculture", "school"})   # fewer sites, other indices
    other_k = design(dc, ss, replace(A, kerosene_yen_l=140.0), k=2)                 # pipes the model may lack
    for start in (few, other_k, cold):
        warm = design(dc, ss, A, k=3, start=start)
        assert warm.annual_net >= cold.annual_net - tol(cold.annual_net)


def test_start_values_map_pipes_and_users_by_key():
    _, ss = sites()
    start = v1.Design(sites=[ss[2], ss[0]], edges=[(0, 2, 1.0), (2, 1, 1.0)], edge_flow={},
                      served=np.ones((2, 12)), supply_used=np.zeros(12), waste_heat=[0.0] * 12, A=A,
                      status="test")                      # dc - gh - fish, in a different order
    E = [(0, 1), (0, 3), (1, 3), (1, 2)]                 # node 1 = gh, 2 = school, 3 = fish
    vals = v1._start_values(start, ss[:3], E, lambda e: e, lambda u: 10 + u)
    assert [vals[e] for e in range(4)] == [1.0, 0.0, 1.0, 0.0]
    assert [vals[10 + u] for u in range(3)] == [1.0, 0.0, 1.0]
