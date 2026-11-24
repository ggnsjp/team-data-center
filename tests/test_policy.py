"""Policy scenarios: a carbon price, an investment subsidy and the electricity behind the heat pumps.

All on synthetic instances or plain numbers (no map data). The scenarios must leave every result
unchanged at their default (no carbon price, no subsidy).
"""
from __future__ import annotations

import json
import math
from dataclasses import replace

import numpy as np
import pytest
from synthetic import SCENS, small_shared, tiny

from dcopt.heat import whatif
from dcopt.heat.network import (
    KEROSENE_KG_CO2_PER_L,
    KEROSENE_KWH_PER_L,
    SUBSIDY_RATES,
    Params,
    pair_calculator,
    solve,
    user_data,
)
from dcopt.heat.v1 import GRID_SCENARIOS, Assumptions, Design

P0 = Params(mip_rel_gap=0.0, time_limit=60)


def close(a, b):
    return 1e-6 * max(1.0, abs(a), abs(b)) + 1.0


# ------------------------------------------------------------------------------------------ v1
def test_v1_defaults_carry_no_policy():
    A = Assumptions()
    assert A.carbon_yen_t == 0.0 and A.subsidy == 0.0
    assert A.carbon_yen_per_mwh == 0.0 and A.own_pipe_yen_m == A.pipe_yen_m
    assert A.value_yen_per_mwh == pytest.approx(A.fuel_yen_per_mwh - A.hp_yen_per_mwh)


def test_v1_carbon_price_adds_the_price_times_the_co2_avoided():
    A = Assumptions()
    B = replace(A, carbon_yen_t=5000.0)
    assert B.value_yen_per_mwh - A.value_yen_per_mwh == pytest.approx(5000.0 * A.co2_t_per_mwh)
    grid = replace(B, renewable_power=False)               # grid power avoids less, so the credit is smaller
    assert 0 < grid.carbon_yen_per_mwh < B.carbon_yen_per_mwh


def test_v1_co2_per_mwh_falls_with_the_electricity_factor():
    A = Assumptions()
    by = [A.co2_t_per_mwh_at(f) for _, _, f in GRID_SCENARIOS.values()]
    assert by == sorted(by, reverse=True) and by[0] == pytest.approx(A.co2_t_per_mwh)
    fuel = KEROSENE_KG_CO2_PER_L / (KEROSENE_KWH_PER_L * A.boiler_eff)
    assert A.co2_t_per_mwh_at(0.25) == pytest.approx(fuel - 0.25 / A.cop)


def _design(A: Assumptions) -> Design:
    served = np.zeros((1, 12))
    served[0, :] = 100.0                                   # 1,200 MWh a year through one 1 km pipe
    return Design(sites=[], edges=[(0, 1, 1000.0)], edge_flow={}, served=served, supply_used=np.zeros(12),
                  waste_heat=[0.0] * 12, A=A, status="test")


def test_v1_subsidy_lowers_the_projects_cost_but_not_the_investment():
    A = Assumptions()
    d0, d1 = _design(A), _design(replace(A, subsidy=0.5))
    assert d1.capex == d0.capex and d1.subsidy_yen == pytest.approx(0.5 * d0.capex)
    assert d1.own_capex == pytest.approx(0.5 * d0.capex)
    assert d1.payback_years == pytest.approx(0.5 * d0.payback_years)
    assert d1.annual_net - d0.annual_net == pytest.approx(0.5 * d0.capex * A.crf)


def test_v1_abatement_cost_ignores_the_policy_and_matches_the_net_benefit():
    A = Assumptions()
    d0, d1 = _design(A), _design(replace(A, carbon_yen_t=8000.0, subsidy=0.5))
    assert d0.abatement_yen_t == pytest.approx(-d0.annual_net / d0.co2_t)       # no policy: minus net per tonne
    assert d1.abatement_yen_t == pytest.approx(d0.abatement_yen_t)             # a property of the plan itself
    assert d1.carbon_value == pytest.approx(8000.0 * d1.co2_t)
    co2 = d0.co2_scenarios()
    assert co2["renewable"] >= co2["target2030"] >= co2["grid"] > 0


# ------------------------------------------------------------------------------------------ v2
def test_v2_carbon_price_enters_the_value_of_every_user():
    inst = tiny()
    ud0, ud1 = user_data(inst, P0, SCENS), user_data(inst, replace(P0, carbon_yen_t=6000.0), SCENS)
    assert np.allclose(ud1.v - ud0.v, 6000.0 * ud0.co2[:, None])
    assert np.allclose(ud1.co2, ud0.co2)


@pytest.fixture(scope="module")
def plans():
    inst = small_shared()
    return {name: solve(inst, replace(P0, **kw), SCENS) for name, kw in
            [("base", {}), ("carbon", {"carbon_yen_t": 10000.0}), ("subsidy", {"subsidy": 0.5})]}


def test_v2_policy_never_lowers_the_optimum(plans):
    base = plans["base"].expected_net
    for name in ("carbon", "subsidy"):
        assert plans[name].expected_net >= base - close(plans[name].expected_net, base)


def test_v2_subsidy_scales_the_annual_cost(plans):
    plan = plans["subsidy"]
    full = plan.P.crf * plan.capex_pipes + plan.P.crf_hp * plan.capex_hp
    assert plan.annual_cost == pytest.approx(0.5 * full)
    assert plan.subsidy_yen == pytest.approx(0.5 * plan.capex) and plan.own_capex == pytest.approx(0.5 * plan.capex)


def test_v2_carbon_value_is_part_of_the_value(plans):
    plan = plans["carbon"]
    assert np.allclose(plan.carbon_value, 10000.0 * plan.co2)
    assert (plan.value > plan.carbon_value).all() and (plans["base"].carbon_value == 0).all()


def test_v2_co2_scenarios_and_abatement_cost(plans):
    base = plans["base"]
    co2 = base.co2_scenarios()
    assert co2["renewable"] >= co2["target2030"] >= co2["grid"] > 0
    assert co2["grid"] == pytest.approx(float(base.p @ base.co2))              # ambient: user heat pumps on the grid
    assert base.abatement_yen_t == pytest.approx(-base.expected_net / float(base.p @ base.co2))
    assert plans["subsidy"].abatement_yen_t == pytest.approx(
        -(plans["subsidy"].expected_net - 0.5 * (plans["subsidy"].P.crf * plans["subsidy"].capex_pipes
                                                 + plans["subsidy"].P.crf_hp * plans["subsidy"].capex_hp))
        / float(plans["subsidy"].p @ plans["subsidy"].co2))


def test_pair_calculator_carries_the_policy_rows():
    inst = small_shared()
    rows = {r["key"]: r for r in pair_calculator(inst, P0, SCENS, 0, 0)}
    assert {"co2_power", "abatement", "payback_subsidy"} <= set(rows)
    assert all(rows[k]["tag"] == "calculated" for k in ("co2_power", "abatement", "payback_subsidy"))
    co2 = [float(x.replace(",", "")) for x in rows["co2_power"]["value"].split(" / ")]
    assert co2 == sorted(co2, reverse=True) and len(co2) == len(GRID_SCENARIOS)
    pay = [float(x) for x in rows["payback_subsidy"]["value"].split(" / ")]
    assert pay == sorted(pay, reverse=True) and len(pay) == len(SUBSIDY_RATES)
    assert pay[1] == pytest.approx(0.5 * rows["payback"]["value"], abs=0.11)   # half the investment, half the payback
    saving, co2_own = rows["saving"]["value"], rows["co2"]["value"]
    cost = P0.crf * rows["capex"]["value"] + P0.crf_hp * rows["hp"]["value"]
    assert rows["abatement"]["value"] == pytest.approx((cost - saving) / co2_own, rel=2e-3)
    assert math.isfinite(rows["abatement"]["value"])


# ----------------------------------------------------------------------------------- what-if
def test_whatif_knows_and_clamps_the_policy_knobs():
    canned = json.dumps({"changes": {"carbon_yen_t": 99999, "subsidy_pct": 90}, "clarify": ""})
    out = whatif.parse_patch("x", {}, llm_chat=lambda messages, **kw: canned)
    assert out["changes"] == {"carbon_yen_t": 20000, "subsidy_pct": 75}
    canned = json.dumps({"changes": {"carbon_yen_t": 1234, "subsidy_pct": "33.4"}, "clarify": ""})
    out = whatif.parse_patch("x", {}, llm_chat=lambda messages, **kw: canned)
    assert out["changes"] == {"carbon_yen_t": 1000, "subsidy_pct": 33}
