"""Proposals (dcopt.heat.proposal): every number tagged, prices consistent with the pair's economics."""
import re
from dataclasses import replace

import pytest
from synthetic import SCENS, instance, tiny

from dcopt.heat.network import Params, pair_score, rank_partners, solve
from dcopt.heat.proposal import _kpis, proposal_data, render_html
from dcopt.heat.v1 import KEROSENE_KWH_PER_L

P0 = Params(mip_rel_gap=0.0, time_limit=60, k=3, dc_links=2)


@pytest.fixture(scope="module", params=["ambient", "central"])
def plan(request):
    return solve(tiny(), replace(P0, mode=request.param), SCENS)


def proposals(plan):
    for d in range(plan.inst.D):
        for i, r in enumerate(rank_partners(plan, d, top=5), 1):
            yield d, r, proposal_data(plan, d, r["u"], rank=i, loss=r["loss"])


def test_every_number_shows_its_source_or_is_marked(plan):
    """The idea starter's rule: every number shows its source or is clearly marked as an assumption."""
    for _, _, data in proposals(plan):
        rows = data["rows"]
        assert [r["no"] for r in rows] == list(range(1, len(rows) + 1))
        for r in rows:
            assert r["tag"] in ("source", "assumption", "calculated"), r
            assert r["basis"].strip(), r
            assert r["ja"].strip() and r["en"].strip()


def test_cards_point_at_rows_of_the_sheet(plan):
    for _, _, data in proposals(plan):
        if data["pair"] is None:
            continue
        nos = {r["no"] for r in data["rows"]}
        cards = _kpis(data, "en")
        assert len(cards) == 6
        for _, _, _, refs in cards:
            assert refs and set(refs) <= nos


def test_price_range_is_the_pair_gain_per_mwh(plan):
    """p_max - p_min = the pair's expected net benefit / heat, so a range exists exactly when the pair pays."""
    for d, r, data in proposals(plan):
        pr = data["pair"]
        if pr is None:
            continue
        ps = pair_score(plan.inst, plan.P, plan.scens, d, r["u"])
        assert pr["net"] == pytest.approx(ps["score"])
        assert (pr["p_max"] - pr["p_min"]) * pr["heat"] == pytest.approx(ps["score"], rel=1e-9, abs=1.0)
        assert (pr["p_max"] > pr["p_min"]) == (ps["score"] > 0)
        assert pr["p_mid"] == pytest.approx((pr["p_min"] + pr["p_max"]) / 2)


def test_central_partner_pays_only_the_price():
    """Central mode: the partner's ceiling is its avoided kerosene per MWh, between the two kerosene prices."""
    plan = solve(tiny(), replace(P0, mode="central"), SCENS)
    for _, _, data in proposals(plan):
        pr = data["pair"]
        if pr:
            lo, hi = pr["fuel_mwh"]
            assert lo - 1e-6 <= pr["p_max"] <= hi + 1e-6


def test_pair_numbers_add_up(plan):
    for _, _, data in proposals(plan):
        pr = data["pair"]
        if pr is None:
            continue
        assert pr["kerosene_l"] == pytest.approx(pr["heat"] * 1000 / (KEROSENE_KWH_PER_L * plan.P.boiler_eff))
        assert sum(pr["month"]) == pytest.approx(pr["heat"])
        assert all(m <= dm + 1e-6 for m, dm in zip(pr["month"], data["demand_month"]))
        assert 0 <= pr["share"] <= 1 + 1e-9
        assert pr["capex"] == pytest.approx(pr["pipe"] + pr["hp"])
        if pr["payback"] is not None:
            assert pr["payback"] == pytest.approx(pr["capex"] / pr["value"])


def test_partner_in_the_plan_reports_its_contribution(plan):
    for d, r, data in proposals(plan):
        rg = data["regional"]
        assert rg["in_plan"] == bool(plan.x[r["u"]] > 0.5)
        if r["in_plan"]:
            assert rg["served_by"] == plan.inst.sources[d].key
            assert rg["loss"] == pytest.approx(r["loss"])
            assert {"plan_heat", "plan_loss"} <= {row["key"] for row in data["rows"]}


@pytest.mark.parametrize("lang", ["en", "ja"])
def test_render_html(plan, lang):
    for _, _, data in proposals(plan):
        page = render_html(data, lang)
        assert page.startswith("<!doctype html>") and page.count('<section class="page') == 2
        assert not re.findall(r"\bnan\b|\bNone\b|\binf\b", page)
        assert (data["site"]["name"] if lang == "ja" else data["site"]["name_en"]) in page
        assert "OpenStreetMap contributors" in page


def test_no_dedicated_pipe_still_renders():
    inst = instance([(0, 0)], [("far", "greenhouse", (20_000, 0), 2000.0), ("near", "school", (500, 0), 300.0)])
    plan = solve(inst, P0, SCENS)
    data = proposal_data(plan, 0, 0)
    assert data["pair"] is None
    assert "cannot serve" in render_html(data, "en")


def test_bilingual_values_pick_the_language():
    from dcopt.heat.proposal import _bilingual
    assert _bilingual("石狩再エネデータセンター第1号 / Ishikari Renewable Energy Data Center No. 1", 0) == "石狩再エネデータセンター第1号"
    assert _bilingual("直接利用 / direct", 1) == "direct"
    assert _bilingual("6 / 10", 0) == "6 / 10"           # numbers are left alone


# ------------------------------------------------------------------------------------- weather block
def _weather_years() -> list:
    """Two synthetic years: 2001 mild (9 C all year), 2002 cold (winter months at -5 C)."""
    from calendar import monthrange
    from dcopt.heat import weather as W
    cold = [-5.0 if m in (0, 1, 11) else 0.0 if m in (2, 10) else 8.0 if m in (3, 9) else 18.0
            for m in range(12) for _ in range(monthrange(2002, m + 1)[1])]
    zero = [0.0] * 365
    return [W.WeatherYear.from_daily(2001, [9.0] * 365, zero), W.WeatherYear.from_daily(2002, cold, zero)]


def test_weather_block_band_coldest_and_coverage(plan):
    """The block derives everything from the given years: band bounds, extremes, and the pipe's
    cold-year coverage from the model's own duration-curve deliverable."""
    from dcopt.heat.proposal import weather_block
    from dcopt.heat.v1 import KINDS
    ys = _weather_years()
    for d, r, data in proposals(plan):
        w = weather_block(plan, data, years=ys)
        assert w is not None and w["span"] == [2001, 2002] and len(w["years"]) == 2
        scale = {y.year: y.scale(KINDS[data["site"]["kind"]][2]) for y in ys}
        assert scale[w["coldest"]["year"]] == max(scale.values())      # the extremes follow the kind's scale
        assert scale[w["mildest"]["year"]] == min(scale.values())
        annual = data["site"]["annual_mwh"]
        for row in w["years"]:
            # monthly_demand sums to annual x scale; abs covers the 3-decimal scale rounding
            assert row[2] == pytest.approx(annual * row[1], abs=1.6)
        assert all(lo <= hi for lo, hi in zip(w["band_min"], w["band_max"]))
        assert all(lo <= m <= hi for lo, m, hi in zip(w["band_min"], w["coldest"]["month"], w["band_max"]))
        pr = data["pair"]
        if pr:
            c = w["coverage"]
            assert c["dn"] == pr["dn"] and 0 < c["share_worst"] <= 1
        else:
            assert "coverage" not in w


@pytest.mark.parametrize("lang", ["en", "ja"])
def test_render_html_shows_the_weather_block(plan, lang):
    from dcopt.heat.proposal import weather_block
    for _, _, data in proposals(plan):
        w = weather_block(plan, data, years=_weather_years())
        assert w is not None
        data["weather"] = w
        page = render_html(data, lang)
        assert str(data["weather"]["coldest"]["year"]) in page and "47412" in page
        assert not re.findall(r"\bnan\b|\bNone\b|\binf\b", page)
