"""v1.design: status and gap are reported, and a warm start from a nearby plan never makes the
answer worse. Without a start the model goes to scipy's milp as it always did; with one, to highspy.
Synthetic instance on a plane (straight-line distances x 1.3), no map data."""
from __future__ import annotations

import math
import os
import subprocess
import sys
import textwrap
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


DONE = "Optimization terminated successfully"        # scipy's words; the warm path reports in the same


def test_a_solve_without_a_start_goes_to_scipy_and_never_to_highspy(monkeypatch):
    real, asked = v1.milp, []

    def watched(c, **kw):
        asked.append(kw)
        return real(c, **kw)

    def never(*args, **kw):
        raise AssertionError("a solve without a start must not reach highspy")

    monkeypatch.setattr(v1, "milp", watched)
    monkeypatch.setattr(v1, "_highs", never)
    dc, ss = sites()
    d = design(dc, ss, A, k=3)
    pairs = v1.pairwise(dc, ss, A)
    assert len(asked) == 2 and not d.warm_start and not pairs.warm_start
    assert asked[0]["options"] == {"time_limit": 30.0, "mip_rel_gap": 0.005}      # the options it always had
    assert set(asked[0]) == {"constraints", "integrality", "bounds", "options"}
    assert d.status.startswith(DONE) and "HiGHS Status" in d.status              # scipy's own message


def test_a_solve_with_a_start_goes_to_highspy(monkeypatch):
    dc, ss = sites()
    base = design(dc, ss, A, k=3)
    monkeypatch.setattr(v1, "milp", lambda *args, **kw: pytest.fail("a solve with a start must not reach scipy"))
    warm = design(dc, ss, replace(A, subsidy=0.3), k=3, start=base)
    assert warm.warm_start and warm.status == DONE + ". (HiGHS, warm start)"


def test_cold_solve_reports_status_and_gap():
    dc, ss = sites()
    d = design(dc, ss, A, k=3)
    assert d.status.startswith(DONE) and 0.0 <= d.gap <= v1.MIP_REL_GAP and not d.warm_start
    assert d.connected and d.annual_net > 0
    assert all(u <= w + 1e-6 for u, w in zip(d.supply_used, d.waste_heat))


def test_warm_start_from_the_no_policy_plan_is_never_worse():
    dc, ss = sites()
    base = design(dc, ss, A, k=3)
    B = replace(A, carbon_yen_t=8000.0, subsidy=0.3)
    cold = design(dc, ss, B, k=3)
    warm = design(dc, ss, B, k=3, start=base)
    assert warm.warm_start and warm.status.startswith(DONE)      # one wording with and without a start
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


def same_plan(a: v1.Design, b: v1.Design) -> bool:
    return (a.edges == b.edges and a.connected == b.connected and a.annual_net == b.annual_net
            and np.array_equal(a.served, b.served))


def test_the_same_inputs_give_the_same_plan_whatever_was_solved_before(tmp_path):
    dc, ss = sites()
    B = replace(A, carbon_yen_t=8000.0, subsidy=0.3)
    fresh, _ = v1.cached_design(dc, ss, B, k=3, cache_dir=tmp_path / "fresh", warm_start=True)
    for other in (replace(A, kerosene_yen_l=140.0), replace(B, subsidy=0.6),
                  replace(A, it_load_mw=0.2, carbon_yen_t=3000.0)):
        v1.cached_design(dc, ss, other, k=3, cache_dir=tmp_path / "used", warm_start=True)
    later, hit = v1.cached_design(dc, ss, B, k=3, cache_dir=tmp_path / "used", warm_start=True)
    assert not hit and fresh.warm_start and later.warm_start
    assert same_plan(later, fresh)


def test_cases_without_a_policy_come_from_a_solve_without_a_start(tmp_path):
    dc, ss = sites()
    v1.cached_design(dc, ss, replace(A, subsidy=0.5), k=3, cache_dir=tmp_path, warm_start=True)   # solved before
    for case in (A, replace(A, kerosene_yen_l=140.0)):
        plan, _ = v1.cached_design(dc, ss, case, k=3, cache_dir=tmp_path, warm_start=True)
        assert not plan.warm_start and same_plan(plan, design(dc, ss, case, k=3))


def test_with_the_warm_start_off_every_plan_is_the_plan_of_a_solve_without_a_start(monkeypatch, tmp_path):
    monkeypatch.delenv(v1.WARM_START_ENV, raising=False)
    dc, ss = sites()
    for case in (A, replace(A, carbon_yen_t=8000.0, subsidy=0.3)):
        plan, _ = v1.cached_design(dc, ss, case, k=3, cache_dir=tmp_path)
        assert not plan.warm_start and same_plan(plan, design(dc, ss, case, k=3))


def test_a_policy_plan_is_never_worse_than_keeping_the_no_policy_plan(tmp_path):
    dc, ss = sites()
    for B in (replace(A, carbon_yen_t=8000.0, subsidy=0.3), replace(A, subsidy=0.6)):
        plan, _ = v1.cached_design(dc, ss, B, k=3, cache_dir=tmp_path, warm_start=True)
        base, hit = v1.cached_design(dc, ss, v1.no_policy(B), k=3, cache_dir=tmp_path, warm_start=True)
        assert hit and plan.warm_start and not base.warm_start
        assert plan.annual_net >= replace(base, A=B).annual_net - 1e-6 * abs(plan.annual_net)


def test_the_solve_asks_for_the_thread_count_of_the_process():
    """HiGHS keeps one thread count per process and fails a later solve that asks for another one,
    so v1 reads DCOPT_THREADS like the v2 solver call does. A fresh interpreter, because this
    process has already solved with the default count."""
    code = textwrap.dedent("""
        import numpy as np
        import scipy.sparse as sp
        from dcopt.heat import network, v1
        A = sp.csr_matrix(np.array([[1.0, 1.0]]))
        model = (np.array([1.0, 2.0]), A, np.array([3.0]), np.array([np.inf]), np.zeros(2), np.full(2, 4.0),
                 np.ones(2))
        x, status, _ = v1._highs(*model, 10.0)                                  # v1 first ...
        later = network._run(*model, network.Params(time_limit=10.0), None)    # ... then v2 in the same process
        print(status, [abs(round(float(v), 6)) for v in x], later["status"],
              [abs(round(float(v), 6)) for v in later["x"]])
    """)
    env = {**os.environ, "DCOPT_THREADS": "1", "DCOPT_SOLVER": "highs"}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stderr[-600:]
    assert out.stdout.split("\n")[-2] == "Optimal [3.0, 0.0] Optimal [3.0, 0.0]"
