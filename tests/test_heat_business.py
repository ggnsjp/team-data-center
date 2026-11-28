"""The price window of docs/heat-business.md: by hand on a small plan, and against the exported plans."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dcopt.heat import business as bz
from dcopt.heat.ground import design_peak_mw
from dcopt.heat.network import Params, pipe_cost_yen_m

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "out" / "heat_network_v2" / "plans.json"
TODAY = ROOT / "out" / "heat_business" / "plans.json"

SITES = [{"kind": "snow", "annual": 1200, "dc": "a", "assumed": True,
          "served": [300.0, 300.0, 200.0, 0, 0, 0, 0, 0, 0, 0, 100.0, 300.0]},
         {"kind": "hospital", "annual": 1500, "dc": "a", "assumed": False, "served": [125.0] * 12},
         {"kind": "pool", "annual": 800, "dc": None, "assumed": False, "served": [0.0] * 12}]
PLAN = {"sites": SITES, "pipes": [{"dn": 100, "km": 1.0}, {"dn": 50, "km": 0.5}], "kpi": {}}


def test_a_litre_of_kerosene_and_its_heat():
    P = Params()
    assert bz.heat_per_litre(P) == pytest.approx(9.7 * 0.85 / 1000)
    for kero in (115.0, 156.8):
        assert bz.per_litre(P.fuel_yen_per_mwh(kero), P) == pytest.approx(kero)
    assert (bz.KEROSENE_LOW, bz.KEROSENE_SURVEY) == (115.0, 156.8)
    assert bz.mean_kerosene() == pytest.approx((115.0 + 156.8) / 2)


def test_the_network_needs_its_annuity_over_all_the_heat():
    P = Params()
    n = bz.network(PLAN, P)
    invested = pipe_cost_yen_m(100) * 1000 + pipe_cost_yen_m(50) * 500
    assert n.investment == pytest.approx(invested) and n.annuity == pytest.approx(invested * P.crf)
    assert n.heat == 2700.0                                          # the unconnected pool is left out
    assert n.yen_per_mwh == pytest.approx(invested * P.crf / 2700.0)


def test_windows_by_hand():
    P = Params()
    rows = {w.kind: w for w in bz.windows(PLAN, 115.0, P)}
    assert set(rows) == {"snow", "hospital"}
    snow, hosp = rows["snow"], rows["hospital"]
    fuel = P.fuel_yen_per_mwh(115.0)
    assert snow.cop is None and snow.electricity == 0 and snow.heat_pump == 0 and snow.most == pytest.approx(fuel)
    cop = 0.5 * 333.15 / 35                                          # 60 C from the 30 C loop less 5 K
    assert hosp.cop == pytest.approx(cop) and hosp.electricity == pytest.approx(25_000 / cop)
    peak = design_peak_mw("hospital", 1500, P)
    assert hosp.heat_pump == pytest.approx(150e6 * peak * P.crf_hp / 1500)
    assert hosp.most == pytest.approx(fuel - 25_000 / cop - 150e6 * peak * P.crf_hp / 1500)
    assert hosp.least == snow.least == pytest.approx(bz.network(PLAN, P).yen_per_mwh)
    assert (snow.assumed, hosp.assumed) == (True, False)


def test_the_window_opens_at_its_kerosene_price():
    P = Params()
    for w in bz.windows(PLAN, 115.0, P):
        at = {v.kind: v for v in bz.windows(PLAN, w.opens_at, P)}[w.kind]
        assert at.margin == pytest.approx(0.0, abs=1e-6)
        assert {v.kind: v for v in bz.windows(PLAN, w.opens_at + 1, P)}[w.kind].margin > 0


def test_the_surplus_is_the_plans_account():
    """Kerosene saved, less the heat pumps' electricity and annuity, less the pipes' annuity."""
    P = Params()
    kero = bz.mean_kerosene()
    cop = 0.5 * 333.15 / 35
    value = P.fuel_yen_per_mwh(kero) * 2700.0 - 1500.0 / cop * 25_000
    costs = 150e6 * design_peak_mw("hospital", 1500, P) * P.crf_hp + bz.network(PLAN, P).annuity
    assert bz.surplus(PLAN, kero, P) == pytest.approx(value - costs)
    assert bz.surplus(PLAN, kero, P) == pytest.approx(bz.surplus(PLAN, kero, P, assumed=True)
                                                      + bz.surplus(PLAN, kero, P, assumed=False))


def test_a_subsidy_lowers_both_annuities():
    P = Params(subsidy=0.5)
    full = {w.kind: w for w in bz.windows(PLAN, 115.0, Params())}
    half = {w.kind: w for w in bz.windows(PLAN, 115.0, P)}
    assert half["hospital"].heat_pump == pytest.approx(full["hospital"].heat_pump / 2)
    assert half["hospital"].least == pytest.approx(full["hospital"].least / 2)


def test_only_the_ambient_loop():
    with pytest.raises(ValueError):
        bz.windows(PLAN, 115.0, Params(mode="central"))


# ------------------------------------------------------------------- against the exported plans
needs_published = pytest.mark.skipif(not PUBLISHED.exists(), reason="scripts/export_heat_network_v2.py has not run")
needs_today = pytest.mark.skipif(not TODAY.exists(), reason="scripts/export_heat_business.py has not run")


def _plan(path: Path, key: str) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["plans"][key]


@needs_published
def test_the_published_plan_adds_up_to_its_net_benefit():
    """At the mean kerosene price the windows add up to the expected net benefit, up to the export's
    rounding (pipe lengths to 10 m, heat to whole MWh a month)."""
    plan = _plan(PUBLISHED, "expected")
    assert bz.surplus(plan, bz.mean_kerosene()) / 1e6 == pytest.approx(plan["kpi"]["expected_net_m"], abs=0.15)


@needs_today
def test_the_plan_on_todays_facilities_adds_up_and_has_no_assumed_site():
    data = json.loads(TODAY.read_text(encoding="utf-8"))
    plan = data["plans"]["existing"]
    assert not any(w.assumed for w in bz.windows(plan, 115.0))
    assert bz.surplus(plan, bz.mean_kerosene()) / 1e6 == pytest.approx(plan["kpi"]["expected_net_m"], abs=0.15)
    here = data["plans"]["published_here"]["kpi"]
    assert here["expected_net_m"] == pytest.approx(_plan(PUBLISHED, "expected")["kpi"]["expected_net_m"], abs=0.15)


def test_the_breakeven_kerosene_price():
    P = Params()
    k = bz.breakeven_kerosene(PLAN, P)
    assert bz.surplus(PLAN, k, P) == pytest.approx(0.0, abs=1e-3)
    assert bz.surplus(PLAN, k + 1, P) > 0 > bz.surplus(PLAN, k - 1, P)


@needs_today
def test_the_middle_step_lies_between_the_two_plans():
    data = json.loads(TODAY.read_text(encoding="utf-8"))["plans"]
    if "documented_fish_farm" not in data:
        pytest.skip("export made before the middle step was added")
    today, mid, published = data["existing"], data["documented_fish_farm"], _plan(PUBLISHED, "expected")
    assert bz.breakeven_kerosene(published) < bz.breakeven_kerosene(mid) < bz.breakeven_kerosene(today)
    assert bz.network(published).yen_per_mwh < bz.network(today).yen_per_mwh


# ------------------------------------------------------------------- the pages and the READMEs
def _figures() -> dict[str, str]:
    data = json.loads(TODAY.read_text(encoding="utf-8"))
    today, mid, published = data["plans"]["existing"], data["plans"]["documented_fish_farm"], _plan(PUBLISHED, "expected")
    nt, npub = bz.network(today), bz.network(published)
    figures = {"least today": f"{nt.yen_per_mwh:,.0f}", "litre today": f"{bz.per_litre(nt.yen_per_mwh):.1f}",
               "least published": f"{npub.yen_per_mwh:,.0f}", "litre published": f"{bz.per_litre(npub.yen_per_mwh):.1f}",
               "breakeven today": f"{bz.breakeven_kerosene(today):.0f}", "breakeven middle": f"{bz.breakeven_kerosene(mid):.0f}",
               "breakeven published": f"{bz.breakeven_kerosene(published):.0f}",
               "breakeven today, subsidy": f"{bz.breakeven_kerosene(today, Params(subsidy=1 / 3)):.0f}",
               "gain today at 156.8": f"{bz.surplus(today, bz.KEROSENE_SURVEY) / 1e6:,.1f}",
               "loss today at 115": f"{-bz.surplus(today, bz.KEROSENE_LOW) / 1e6:,.1f}",
               "published at the mean": f"{bz.surplus(published, bz.mean_kerosene()) / 1e6:,.1f}"}
    for name, plan in (("today", today), ("published", published)):
        for w in bz.windows(plan, bz.KEROSENE_LOW):
            figures[f"{name} {w.kind} opens"] = f"| {w.opens_at:.0f} |"
    return figures


@needs_published
@needs_today
@pytest.mark.parametrize("page", ["heat-business.md", "heat-business.ja.md"])
def test_the_page_quotes_the_computed_figures(page):
    if "documented_fish_farm" not in json.loads(TODAY.read_text(encoding="utf-8"))["plans"]:
        pytest.skip("export made before the middle step was added")
    text = (ROOT / "docs" / page).read_text(encoding="utf-8")
    for what, value in _figures().items():
        assert value in text, f"{page} does not show {what} ({value})"


@needs_published
@needs_today
@pytest.mark.parametrize("name", ["README.md", "README.ja.md"])
def test_the_readme_quotes_the_key_figures(name):
    if "documented_fish_farm" not in json.loads(TODAY.read_text(encoding="utf-8"))["plans"]:
        pytest.skip("export made before the middle step was added")
    text = (ROOT / name).read_text(encoding="utf-8")
    figures = _figures()
    for what in ("least today", "litre today", "breakeven today", "breakeven published"):
        assert figures[what] in text, f"{name} does not show {what} ({figures[what]})"
