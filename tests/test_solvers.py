"""HiGHS and Gurobi find the same optimum on small instances, and with the optional tie-break on
(Params.tie_yen_m) the same build too (skipped without gurobipy or a licence)."""
from dataclasses import replace

import pytest
from synthetic import SCENS, equidistant_two_dc, small_two_dc, tiny

from dcopt.heat.network import Params, solve

gp = pytest.importorskip("gurobipy")

TIE = 0.01                                   # yen per metre per year; the tie-break is off by default


@pytest.fixture(scope="module", autouse=True)
def gurobi_licence():
    try:
        env = gp.Env(empty=True)
        env.setParam("OutputFlag", 0)
        env.start()
        env.dispose()
    except Exception as exc:                                    # noqa: BLE001 - any licence problem skips
        pytest.skip(f"Gurobi licence not available: {exc}")


@pytest.mark.parametrize("make", [tiny, small_two_dc, equidistant_two_dc], ids=["tiny", "two_dc", "equidistant"])
@pytest.mark.parametrize("mode", ["ambient", "central"])
@pytest.mark.parametrize("objective", ["expected", "worst"])
@pytest.mark.parametrize("tie", [0.0, TIE], ids=["default", "tie_break"])
def test_highs_and_gurobi_agree(make, mode, objective, tie):
    inst = make()
    P = Params(mode=mode, mip_rel_gap=0.0, time_limit=60, tie_yen_m=tie)
    highs = solve(inst, replace(P, solver="highs"), SCENS, objective=objective)
    gurobi = solve(inst, replace(P, solver="gurobi"), SCENS, objective=objective)
    value = (lambda p: p.expected_net) if objective == "expected" else (lambda p: float(p.net.min()))
    assert value(gurobi) == pytest.approx(value(highs), rel=1e-5, abs=1.0)
    if tie > 0:
        # the same build, not just the same value: with the tie-break on, both solvers send a user that
        # two data centers can serve at the same cost to the same one (without it they may differ)
        assert gurobi.assign.tolist() == highs.assign.tolist()
        assert [b[:2] for b in gurobi.built] == [b[:2] for b in highs.built]
