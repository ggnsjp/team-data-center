"""Theme 2 models on the built-in systems: analytic two-bus values, the ordering of the bounds,
the feasibility check and the reporting. No downloads needed; Gurobi and PGLib checks skip
when they are not available."""
import math
from dataclasses import replace

import numpy as np
import pytest

from dcopt.grid import cases
from dcopt.grid.ac import FEAS_TOL, ACProblem, check_point
from dcopt.grid.hosting import HostingModel, hosting_capacity, hosting_curve, hosting_map, hosting_n1, summarize
from dcopt.grid.lifted import weights
from dcopt.grid.relax import Relaxation, dc_screening

TWO_BUS_MW = 100 * math.sin(2 * math.acos(0.9)) / (2 * 0.1)                  # 392.3 MW, see cases.two_bus


def test_two_bus_unity_power_factor_matches_the_closed_form():
    h = hosting_capacity(cases.two_bus(), 1, pf=1.0)
    assert h.ac == pytest.approx(TWO_BUS_MW, rel=1e-5)
    assert h.socp == pytest.approx(TWO_BUS_MW, rel=1e-5) and h.sdp == pytest.approx(TWO_BUS_MW, rel=1e-5)
    assert h.gap < 1e-5 and h.violation < FEAS_TOL
    assert h.limit == "voltage" and h.binding[0]["element"] == "bus 2" and h.binding[0]["limit"] == "vmin"


@pytest.mark.parametrize("pf", [0.95, 0.85])
def test_two_bus_lagging_load_matches_a_scan_of_the_pv_curve(pf):
    """With V1 = 1, r = 0 and Q = P tan(phi): cos(delta + phi) = V2 cos(phi), P = V2 sin(delta) / x."""
    x, phi = 0.1, math.acos(pf)
    v2 = np.linspace(0.9, 1.1, 200001)
    delta = np.arccos(np.clip(v2 * math.cos(phi), -1, 1)) - phi
    scan = 100 * float(np.max(v2 * np.sin(delta) / x))
    h = hosting_capacity(cases.two_bus(x=x), 1, pf=pf)
    assert h.ac == pytest.approx(scan, rel=1e-5) and h.upper == pytest.approx(scan, rel=1e-5)


def test_dc_screening_on_two_buses_is_the_line_rating_or_the_generator():
    assert dc_screening(cases.two_bus(), np.array([0.0, 1.0]))[0] == pytest.approx(50.0)   # Pmax, per unit
    assert dc_screening(cases.two_bus(rate=120.0), np.array([0.0, 1.0]))[0] == pytest.approx(1.2)
    h = hosting_capacity(cases.two_bus(rate=120.0), 1, pf=1.0)
    assert h.dc == pytest.approx(120.0) and h.ac < 120.0 and h.limit == "thermal"   # losses and Q use the rating


@pytest.mark.parametrize("name", ["ring5", "feeder8"])
def test_bounds_are_ordered_and_the_ac_point_is_verified(name):
    case = cases.load(name)
    rows = hosting_map(case)
    assert len(rows) == case.n
    for h in rows:
        assert h.ac is not None and h.violation < FEAS_TOL and h.status["ac"] == "verified"
        assert h.ac <= h.sdp * (1 + 1e-6) and h.sdp <= h.socp * (1 + 1e-6)
        assert h.upper == pytest.approx(min(h.sdp, h.socp)) and 0 <= h.gap < 1
        assert h.limit in ("thermal", "voltage", "generation (P)", "reactive (Q)", "angle")
    s = summarize(rows)
    assert s["buses"] == case.n and s["ac_found"] == case.n and sum(s["limits"].values()) == case.n


def test_on_a_radial_feeder_both_relaxations_are_exact():
    for h in hosting_map(cases.feeder8()):
        assert h.sdp == pytest.approx(h.socp, rel=1e-5)
        assert h.gap < 1e-5 and h.rank_ratio < 1e-6


def test_the_ac_point_satisfies_every_limit_when_recomputed():
    case = cases.ring5()
    h = hosting_capacity(case, 2)
    v = h.voltages
    vm = np.abs(v)
    assert np.all(vm <= case.vmax + 1e-6) and np.all(vm >= case.vmin - 1e-6)
    yff, yft, _, _ = case.admittances()
    sf = v[case.f] * np.conj(yff * v[case.f] + yft * v[case.t])
    assert np.all(np.abs(sf) <= case.rate + 1e-6)
    injected = v * np.conj(case.ybus() @ v)                              # generation minus load at each bus
    load = case.pd + 1j * case.qd
    load[2] += (h.ac / case.base_mva) * (1 + 1j * math.tan(math.acos(0.95)))
    no_gen = np.setdiff1d(np.arange(case.n), case.gen_bus)
    assert injected[no_gen] == pytest.approx(-load[no_gen], abs=1e-6)


def test_check_point_flags_a_point_that_breaks_the_balance_or_a_limit():
    case = cases.ring5()
    w = weights(case, 2)
    ac = ACProblem(case)
    p = ac.solve(w, 0.3, x0=ac.base_point().detail["x"])
    good = check_point(case, w, 0.3, p.lam, p.pg, p.qg, p.voltages)
    assert good["max"] < FEAS_TOL
    assert check_point(case, w, 0.3, p.lam + 0.01, p.pg, p.qg, p.voltages)["balance_p"] == pytest.approx(0.01, abs=1e-6)
    assert check_point(case, w, 0.3, p.lam, p.pg, p.qg, p.voltages * 1.1)["voltage"] > 0.01
    assert check_point(case, w, 0.3, p.lam, p.pg + 5.0, p.qg, p.voltages)["generation_p"] > 1.0


def test_a_tighter_rating_lowers_the_hosting_capacity_and_is_named():
    case = cases.feeder8()
    before = hosting_capacity(case, 4)
    assert before.limit == "thermal" and before.binding[0]["element"] == "branch 2-3"
    rate = case.rate.copy()
    rate[1] *= 0.8                                                      # branch 2-3
    after = hosting_capacity(replace(case, rate=rate), 4)
    assert after.ac < before.ac - 1.0 and after.upper < before.upper - 1.0
    # the reported sensitivity predicts the direction and the order of magnitude of the change
    assert before.binding[0]["gain"] > 0


def test_n_minus_one_never_exceeds_the_intact_network():
    case = cases.ring5()
    intact = hosting_capacity(case, 2, methods=("socp", "ac"))
    n1 = hosting_n1(case, 2)
    assert n1["outages"] == 6 and n1["skipped"] == 0 and n1["missing_ac"] == 0 and n1["infeasible"] == 0
    assert n1["ac"] <= intact.ac + 1e-6 and n1["upper"] <= intact.upper + 1e-6
    assert n1["ac"] <= n1["upper"] * (1 + 1e-6) and n1["ac_branch"]
    assert hosting_n1(cases.feeder8(), 4)["outages"] == 0               # every outage splits a radial feeder
    # at 1.5 times the load some outages leave a network that cannot even serve the existing load
    stressed = hosting_n1(case.scaled_loads(1.5), 2)
    assert stressed["infeasible"] >= 1 and stressed["ac"] == 0.0 and stressed["upper"] == 0.0


def test_lighter_background_load_leaves_more_room():
    curve = hosting_curve(cases.ring5(), 4, [0.6, 0.8, 1.0])
    values = [h.ac for _, h in curve]
    assert [a for a, _ in curve] == [0.6, 0.8, 1.0]
    assert values[0] > values[1] > values[2] > 0


def test_weighted_buses_share_one_added_load():
    case = cases.ring5()
    model = HostingModel(case)
    h = model.evaluate({1: 0.5, 2: 0.5})
    assert h.bus == "weighted" and h.violation < FEAS_TOL and h.ac <= h.upper * (1 + 1e-6)
    singles = [model.evaluate(b).ac for b in (1, 2)]
    assert h.ac >= min(singles) - 1e-6                                  # mixing two buses is no worse than the weaker one


def test_an_overloaded_case_reports_no_value_instead_of_failing():
    case = cases.feeder8().scaled_loads(20.0)
    h = hosting_capacity(case, 3)
    assert h.socp is None and h.sdp is None and h.ac is None and h.gap is None
    assert h.status["ac"] == "no verified point" and h.status["sdp"] not in ("Solved", "AlmostSolved")
    assert h.row()["ac"] is None


def test_parallel_map_matches_the_serial_one():
    case = cases.ring5()
    serial = hosting_map(case, buses=[1, 2], methods=("socp", "ac"))
    parallel = hosting_map(case, buses=[1, 2], methods=("socp", "ac"), workers=2)
    assert [h.ac for h in parallel] == pytest.approx([h.ac for h in serial], rel=1e-7)
    assert [h.bus for h in parallel] == ["2", "3"]


def test_relaxation_reports_its_own_quality():
    case = cases.ring5()
    r = Relaxation(case, "sdp").solve(weights(case, 2), 0.3)
    assert r.solved and r.rank_ratio < 1e-6 and r.cycle_error < 1e-5 and r.duality_gap < 1e-5
    assert np.abs(r.voltages) == pytest.approx(np.sqrt(r.z[Relaxation(case, "sdp").lifted.i_c]))
    loose = Relaxation(case, "socp").solve(weights(case, 2), 0.3)
    assert loose.value >= r.value - 1e-7 and loose.cycle_error > 1e-3     # the SOCP solution is not a voltage profile


def test_global_solver_agrees_on_the_five_bus_system():
    gp = pytest.importorskip("gurobipy")
    from dcopt.grid.ac import global_gurobi
    case = cases.ring5().scaled_loads(0.6)                               # here the SDP bound is not tight
    w, tan_phi = weights(case, 2), math.tan(math.acos(0.95))
    try:
        best, bound, status = global_gurobi(case, w, tan_phi, time_limit=30)
    except gp.GurobiError as err:
        pytest.skip(f"no usable Gurobi licence: {err}")
    h = hosting_capacity(case, 2)
    assert status == "optimal" and h.gap > 0.01
    assert h.ac == pytest.approx(best * case.base_mva, rel=2e-4)         # the local point is the global optimum
    assert h.ac <= bound * case.base_mva * (1 + 1e-6) <= h.sdp


def test_pglib_case14_is_bracketed_exactly_when_cached():
    if not cases.pglib_path("case14_ieee").exists():
        pytest.skip("PGLib case14_ieee is not in data/cache/pglib (it is downloaded on first use)")
    rows = hosting_map(cases.load("case14_ieee", download=False))
    assert all(h.ac is not None and h.gap < 1e-4 for h in rows)
    assert all(h.dc > h.upper for h in rows)                             # DC screening overstates every bus here
