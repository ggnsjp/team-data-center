"""Exergy view of a plan: the Carnot factor, one MWh worked by hand, and the sums over a small plan."""
import json
from dataclasses import fields
from itertools import pairwise
from pathlib import Path

import pytest

from dcopt.heat import exergy as ex
from dcopt.heat.network import Params

ROOT = Path(__file__).resolve().parents[1]
PLANS = ROOT / "out" / "heat_network_v2" / "plans.json"
TEMPS = [-3.2, -2.7, 1.1, 7.3, 13.0, 17.0, 21.1, 22.3, 18.6, 12.1, 5.2, -0.9]     # Sapporo normals, as in the export


def test_carnot_factor():
    assert ex.carnot_factor(30.0, -3.2) == pytest.approx(1 - 269.95 / 303.15)      # 0.110: winter
    assert ex.carnot_factor(30.0, 22.3) == pytest.approx(0.0254, abs=1e-4)         # summer: a quarter of that
    assert ex.carnot_factor(22.0, 22.3) == 0.0                                     # nothing below the surroundings
    assert ex.carnot_factor(60.0, -3.2) > ex.carnot_factor(45.0, -3.2) > ex.carnot_factor(25.0, -3.2)


def test_one_mwh_to_a_public_building_in_january():
    f = ex.month_flows("public", 1.0, -3.2)
    cop = 0.5 * 318.15 / 20                                # 45 C from a 25 C source at half the Carnot COP
    assert Params().cop("public") == pytest.approx(cop)
    assert f.heat_exergy == pytest.approx(1 - 269.95 / 318.15)                     # 0.152 MWh
    assert f.electricity == pytest.approx(1 / cop)                                 # 0.126 MWh
    assert f.waste_heat == pytest.approx((1 - 1 / cop) * 1.02)                     # 0.892 MWh with 2 % loss
    assert f.waste_exergy == pytest.approx(f.waste_heat * (1 - 269.95 / 303.15))
    assert f.kerosene == pytest.approx(1 / 0.85)
    assert f.fuel_exergy == pytest.approx(10.17 / (9.7 * 0.85))                    # 1.233 MWh
    assert f.boiler_efficiency == pytest.approx(0.123, abs=1e-3)
    assert f.plan_efficiency == pytest.approx(0.678, abs=1e-3)


@pytest.mark.parametrize("kind", ["snow", "aquaculture"])
def test_direct_users_spend_no_electricity(kind):
    f = ex.month_flows(kind, 10.0, -3.2)
    assert Params().cop(kind) is None
    assert f.electricity == 0.0
    assert f.waste_heat == pytest.approx(10.2)                                     # the heat plus 2 % loss
    assert 0.7 < f.plan_efficiency < 1.0                                           # little is lost between 30 C and the need
    assert f.high_grade_cut == 1.0


def test_hotter_supply_holds_more_exergy_and_costs_more_electricity():
    P = Params()
    kinds = sorted(P.supply_c, key=lambda k: P.supply_c[k])
    flows = [ex.month_flows(k, 1.0, -3.2, P) for k in kinds]
    for cooler, hotter in pairwise(flows):
        assert hotter.heat_exergy >= cooler.heat_exergy
        assert hotter.electricity >= cooler.electricity
    assert all(f.plan_efficiency > f.boiler_efficiency for f in flows)


def test_balance_adds_up_and_skips_unconnected_sites():
    sites = [{"kind": "snow", "dc": "a", "served": [10.0] * 12},
             {"kind": "hospital", "dc": "a", "served": [5.0] * 12},
             {"kind": "hospital", "dc": "b", "served": [1.0] * 12},
             {"kind": "pool", "dc": None, "served": [0.0] * 12},              # not connected
             {"kind": "school", "dc": "a", "served": [0.0] * 12}]             # connected on paper, nothing delivered
    by = ex.balance(sites, TEMPS)
    assert set(by) == {"all", "snow", "hospital"}
    assert (by["all"].users, by["snow"].users, by["hospital"].users) == (3, 1, 2)
    assert by["all"].heat == pytest.approx(192.0)
    for f in fields(ex.Flows):
        assert getattr(by["all"], f.name) == pytest.approx(getattr(by["snow"], f.name) + getattr(by["hospital"], f.name))
    assert by["snow"].electricity == 0.0 and by["hospital"].electricity > 0.0
    assert 0.0 < by["all"].boiler_efficiency < by["all"].plan_efficiency < 1.0
    assert by["hospital"].quality > by["snow"].quality


def test_an_empty_plan_has_no_efficiency():
    a = ex.balance([], TEMPS)["all"]
    assert (a.users, a.heat, a.quality, a.boiler_efficiency, a.plan_efficiency, a.high_grade_cut) == (0, 0.0, 0.0, 0.0, 0.0, 0.0)


def test_the_resource_is_worth_most_in_winter():
    energy, exergy = ex.resource([100.0] * 12, TEMPS)
    assert energy == 1200.0
    assert exergy == pytest.approx(sum(100 * ex.carnot_factor(30.0, t) for t in TEMPS))
    assert 0.05 < exergy / energy < 0.08                                           # about 7 % over the year


def test_a_60_degree_network_spends_electricity_where_the_loop_spends_none():
    snow = ex.balance([{"kind": "snow", "dc": "a", "served": [10.0] * 12}], TEMPS)["all"]
    assert snow.electricity == 0.0
    assert ex.central_electricity(snow.heat) == pytest.approx(120.0 * 1.08 / (0.5 * 333.15 / 35))


@pytest.mark.skipif(not PLANS.exists(), reason="the exported plans are not here (scripts/export_heat_network_v2.py)")
@pytest.mark.parametrize("page, percent", [("exergy.md", "{:.1f} %"), ("exergy.ja.md", "{:.1f} %")])
def test_the_page_quotes_the_published_plan(page, percent):
    data = json.loads(PLANS.read_text(encoding="utf-8"))
    a = ex.balance(data["plans"]["expected"]["sites"], data["temp"])["all"]
    text = (ROOT / "docs" / page).read_text(encoding="utf-8")
    for value in (a.quality, a.boiler_efficiency, a.plan_efficiency):
        assert percent.format(100 * value) in text, f"{page} does not show {percent.format(100 * value)}"
    assert f"{a.heat:,.0f}" in text and f"{a.electricity:,.0f}" in text
