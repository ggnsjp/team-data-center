"""Heat from the ground next to waste heat: a hot-water line by the kilometre, and ground-source heat
pumps under the model's own rule. Worked by hand on small cases; with the export, the pages' figures."""
import json
from pathlib import Path

import pytest
from synthetic import SCENS, tiny

from dcopt.heat import exergy as ex
from dcopt.heat import ground as gr
from dcopt.heat import loss
from dcopt.heat.network import Params, pipe_cost_yen_m, user_data

ROOT = Path(__file__).resolve().parents[1]
PLANS = ROOT / "out" / "heat_network_v2" / "plans.json"
TEMPS = [-3.2, -2.7, 1.1, 7.3, 13.0, 17.0, 21.1, 22.3, 18.6, 12.1, 5.2, -0.9]     # Sapporo normals, as in the export
# a plan small enough to add up by hand: road heating taken directly, a hospital with a heat pump, and
# a pool that is not connected
SITES = [{"kind": "snow", "annual": 1200, "dc": "a", "served": [300.0, 300.0, 200.0, 0, 0, 0, 0, 0, 0, 0, 100.0, 300.0]},
         {"kind": "hospital", "annual": 1500, "dc": "a", "served": [125.0] * 12},
         {"kind": "pool", "annual": 800, "dc": None, "served": [0.0] * 12}]
PLAN = {"sites": SITES, "pipes": [{"dn": 100, "km": 1.0}, {"dn": 50, "km": 0.5}]}


# ---------------------------------------------------------------------------- ground-source heat pumps
def test_ground_cop_follows_the_models_rule_with_the_ground_as_the_source():
    P = Params()
    assert gr.GROUND_C == 10.0 and P.approach_k == 5.0 and P.carnot_eff == 0.5
    assert gr.ground_cop("public") == pytest.approx(0.5 * 318.15 / 40)        # 45 C from 5 C: 3.98
    assert gr.ground_cop("hospital") == pytest.approx(0.5 * 333.15 / 55)      # 60 C: 3.03
    assert gr.ground_cop("pool") == pytest.approx(0.5 * 313.15 / 35)          # 40 C: 4.47
    assert gr.ground_cop("snow") == pytest.approx(0.5 * 298.15 / 20)          # 25 C: 7.45
    assert gr.ground_cop("aquaculture") == P.cop_cap                          # 22 C: the cap of 8


@pytest.mark.parametrize("kind", sorted(Params().supply_c))
def test_the_loop_never_needs_more_electricity_than_the_ground(kind):
    P = Params()
    on_loop, on_ground = P.cop(kind), gr.ground_cop(kind, P)
    assert on_ground is not None, "ground at 10 C is too cold for any of the model's uses without a heat pump"
    assert on_loop is None or on_loop >= on_ground
    warm = [gr.ground_cop(kind, P, gr.GROUND_C + rise) for rise in gr.GROUND_RISE_AT_100M_K]
    assert on_ground <= warm[0] <= warm[1] and (on_loop is None or warm[1] <= on_loop)


def test_ground_that_is_warm_enough_would_be_used_directly():
    assert gr.ground_cop("aquaculture", ground_c=25.0) is None                # 22 C needed, 25 C less the 3 K margin
    assert gr.ground_cop("snow", ground_c=25.0) is not None


def test_heat_pumps_of_a_small_plan_add_up_by_hand():
    P = Params()
    loop, ground = gr.heat_pumps(SITES, P), gr.heat_pumps(SITES, P, gr.GROUND_C)
    hospital_peak = gr.design_peak_mw("hospital", 1500)
    assert (loop.users, ground.users) == (1, 2)                               # the unconnected pool is left out
    assert loop.electricity == pytest.approx(1500 / (0.5 * 333.15 / 35))      # the hospital alone, COP 4.76
    assert ground.electricity == pytest.approx(1200 / (0.5 * 298.15 / 20) + 1500 / (0.5 * 333.15 / 55))
    assert loop.electricity_yen == pytest.approx(loop.electricity * 25_000)   # 25 yen/kWh
    assert loop.capacity_mw == pytest.approx(hospital_peak)
    assert ground.capacity_mw == pytest.approx(hospital_peak + gr.design_peak_mw("snow", 1200))
    assert loop.investment == pytest.approx(150e6 * hospital_peak) and loop.annuity == pytest.approx(loop.investment * P.crf_hp)
    assert loop.yearly_yen == pytest.approx(loop.electricity_yen + loop.annuity)
    assert loop.electricity == pytest.approx(ex.balance(SITES, TEMPS, P)["all"].electricity)   # as the exergy view counts it
    kinds = gr.by_kind(SITES, P)
    assert set(kinds) == {"snow", "hospital"} and kinds["snow"]["loop"] == 0.0
    assert sum(r["ground"] for r in kinds.values()) == pytest.approx(ground.electricity)
    assert sum(r["heat"] for r in kinds.values()) == pytest.approx(2700.0)


# ---------------------------------------------------------------------------- hot water over a distance
def test_design_peak_is_the_peak_the_model_sizes_for():
    inst, P = tiny(), Params()
    peak = user_data(inst, P, SCENS).peak
    for u, site in enumerate(inst.users):
        assert gr.design_peak_mw(site.kind, site.annual_mwh, P) == pytest.approx(peak[u])
    assert gr.plan_peak_mw(SITES, P) == pytest.approx(gr.design_peak_mw("snow", 1200) + gr.design_peak_mw("hospital", 1500))
    assert gr.plan_peak_mw(SITES, P, heat_pump_only=True) == pytest.approx(gr.design_peak_mw("hospital", 1500))


def test_a_line_costs_and_loses_in_proportion_to_its_length():
    P = Params()
    ten, twenty = gr.line(200, 10.0, P), gr.line(200, 20.0, P)
    assert ten.investment == pytest.approx(pipe_cost_yen_m(200) * 10_000)     # 270,433 yen/m
    assert ten.annuity == pytest.approx(ten.investment * P.crf)
    assert ten.loss_mwh == pytest.approx(loss.yearly_loss_mwh([(200, 10.0)], gr.HOT_SUPPLY_C, gr.HOT_RETURN_C))
    assert twenty.investment == pytest.approx(2 * ten.investment) and twenty.loss_mwh == pytest.approx(2 * ten.loss_mwh)
    assert twenty.capacity_mw == ten.capacity_mw
    assert ten.loss_peak_mw > ten.loss_mwh / 8760                             # the ground is coldest when the heat is needed


def test_hotter_water_carries_more_in_the_same_pipe_and_loses_more():
    P = Params()
    hot, central, loop = gr.line(150, 1.0, P), gr.line(150, 1.0, P, 60.0, 30.0), gr.line(150, 1.0, P, 30.0, 20.0)
    size = next(s for s in P.sizes if s.dn == 150)
    assert hot.capacity_mw == pytest.approx(4 * size.capacity_mw(10.0))       # 40 K against the loop's 10 K
    assert hot.capacity_mw > central.capacity_mw > loop.capacity_mw
    assert hot.loss_mwh > central.loss_mwh > loop.loss_mwh
    assert hot.investment == central.investment == loop.investment            # the cost is by size and length only


def test_line_for_picks_the_smallest_size_that_also_carries_its_own_loss():
    P = Params()
    dn150 = gr.line(150, 10.0, P)
    assert gr.line_for(5.0, 10.0, P).dn == 150                                # 5.0 MW and the loss fit in 5.64 MW
    assert dn150.capacity_mw > 5.5 and gr.line_for(5.5, 10.0, P).dn == 200    # 5.5 MW alone would fit, with the loss it does not
    assert gr.line_for(0.05, 1.0, P).dn == 50
    assert gr.line_for(30.0, 10.0, P) is None                                 # more than the largest size carries
    assert gr.line_for(4.0, 10.0, P, 30.0, 20.0).dn == 250 and gr.line_for(6.0, 10.0, P, 30.0, 20.0) is None   # at the loop's 10 K


def test_straight_lines_to_the_named_places():
    """Great-circle distances from the data-center block, as docs/ground-heat.md quotes them."""
    km = {key: gr.straight_km(point) for key, (_, _, point) in gr.PLACES.items()}
    assert {key: round(d) for key, d in km.items()} == {"jozankei": 26, "toyoha": 30, "noboribetsu": 77, "mori": 135}
    assert gr.straight_km(gr.PLACES["jozankei"][2], gr.PLACES["toyoha"][2]) == pytest.approx(9.6, abs=0.05)
    assert gr.straight_km(gr.DATA_CENTER_BLOCK) == 0.0
    assert gr.straight_km((0.0, 0.0), (0.0, 1.0)) == pytest.approx(111.195, abs=0.01)   # one degree on the equator
    assert gr.straight_km((43.0, 141.0), (44.0, 141.0)) == pytest.approx(gr.straight_km((44.0, 141.0), (43.0, 141.0)))


def test_summary_of_a_small_plan():
    P = Params()
    s = gr.summary(PLAN, P)
    invested = pipe_cost_yen_m(100) * 1000 + pipe_cost_yen_m(50) * 500
    assert (s["users"], s["heat"], s["pipe_km"]) == (2, 2700.0, 1.5)
    assert s["pipe_investment"] == pytest.approx(invested) and s["pipe_annuity"] == pytest.approx(invested * P.crf)
    hot = s["line"]
    assert hot.km == 10.0 and hot.capacity_mw >= s["peak_mw"] + hot.loss_peak_mw
    assert s["km_same_investment"] == pytest.approx(invested / (hot.investment / 10))
    assert s["km_paid_by_heat_pumps"] == pytest.approx(s["loop"].yearly_yen / (hot.annuity / 10))
    assert s["loss_share"] == pytest.approx(hot.loss_mwh / 2700.0)
    extra = s["ground"].yearly_yen - s["loop"].yearly_yen
    assert extra > 0
    assert s["ground_loop_budget"] == pytest.approx((invested * P.crf - extra) / P.crf)


def test_an_empty_plan():
    s = gr.summary({"sites": [], "pipes": []})
    assert (s["users"], s["heat"], s["peak_mw"], s["pipe_investment"]) == (0, 0.0, 0.0, 0.0)
    assert s["loop"] == gr.HeatPumps() and s["ground"] == gr.HeatPumps()


# ---------------------------------------------------------------------------- the pages and the READMEs
needs_export = pytest.mark.skipif(not PLANS.exists(),
                                  reason="the exported plans are not here (scripts/export_heat_network_v2.py)")


def _published():
    data = json.loads(PLANS.read_text(encoding="utf-8"))
    return gr.summary(data["plans"]["expected"]), data


@needs_export
def test_the_comparison_rests_on_the_plan_of_the_exergy_page():
    s, data = _published()
    a = ex.balance(data["plans"]["expected"]["sites"], data["temp"])["all"]
    assert s["users"] == a.users and s["heat"] == pytest.approx(a.heat)
    assert s["loop"].electricity == pytest.approx(a.electricity)
    assert s["pipe_km"] == pytest.approx(data["plans"]["expected"]["kpi"]["km"], abs=0.05)


@needs_export
@pytest.mark.parametrize("page, money", [("ground-heat.md", lambda yen: f"{yen / 1e6:,.0f} M yen"),
                                         ("ground-heat.ja.md", lambda yen: f"{yen / 1e8:.1f}億円")])
def test_the_page_quotes_the_computed_figures(page, money):
    s, _ = _published()
    loop, ground, hot = s["loop"], s["ground"], s["line"]
    text = (ROOT / "docs" / page).read_text(encoding="utf-8")
    quoted = [f"{s['heat']:,.0f}", f"{loop.electricity:,.0f}", f"{ground.electricity:,.0f}",
              f"{ground.electricity / loop.electricity:.1f}", f"{s['peak_mw']:.1f} MW", f"DN{hot.dn}",
              f"{hot.loss_mwh:,.0f}", f"{s['loss_share']:.0%}".replace("%", " %"), f"{s['km_same_investment']:.1f} km",
              f"{s['km_paid_by_heat_pumps']:.1f} km", money(hot.investment), money(s["pipe_investment"]),
              money(s["ground_loop_budget"]),
              money(gr.line_for(s["peak_mw"], 26.0).investment), money(gr.line_for(s["peak_mw"], 30.0).investment),
              f"{gr.line_for(s['peak_mw'], 26.0).loss_mwh / s['heat']:.0%}".replace("%", " %"),
              f"{gr.line_for(s['peak_mw'], 30.0).loss_mwh / s['heat']:.0%}".replace("%", " %"),
              f"{gr.ground_cop('public'):.2f}", f"{gr.ground_cop('hospital'):.2f}", f"{gr.ground_cop('snow'):.2f}"]
    for value in quoted:
        assert value in text, f"{page} does not show {value}"


@needs_export
@pytest.mark.parametrize("name", ["README.md", "README.ja.md"])
def test_the_readme_quotes_the_key_figures(name):
    s, _ = _published()
    text = (ROOT / name).read_text(encoding="utf-8")
    for value in (f"{s['km_same_investment']:.1f} km", f"{s['km_paid_by_heat_pumps']:.1f} km",
                  f"{s['ground'].electricity / s['loop'].electricity:.1f}"):
        assert value in text, f"{name} does not show {value}"
