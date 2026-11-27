"""The Warm Ishikari page renders and the optimized network beats picking pairs one by one."""
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from dcopt.common.geo import missing_map_data
from dcopt.heat import v1

ROOT = Path(__file__).resolve().parents[1]
PAGE = str(ROOT / "app/pages/1_Warm_Ishikari.py")
pytestmark = pytest.mark.skipif(bool(missing_map_data()), reason="run the Ishikari data fetch first")


@pytest.fixture(autouse=True)
def own_plan_cache(monkeypatch, tmp_path):
    """Keep the tests' solved plans out of data/cache/ and start without remembered solves."""
    monkeypatch.setenv(v1.PLAN_CACHE_ENV, str(tmp_path / "plans"))
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def test_heat_page_renders():
    at = AppTest.from_file(PAGE, default_timeout=600).run()
    assert not at.exception
    net = next(m for m in at.metric if m.label.startswith("年間の純便益"))
    assert float(net.value.replace(",", "")) > 0
    assert len(at.dataframe) >= 1


def test_heat_page_survives_an_emptied_network():
    # the what-if "double the electricity price" with the assumed sites off connects nobody;
    # the monthly chart must render empty, not raise KeyError('month') (the 2026-11-25 capture crash)
    at = AppTest.from_file(str(ROOT / "app/pages/1_Warm_Ishikari.py"), default_timeout=600).run()
    at.session_state["power_yen_kwh"] = 40
    at.session_state["assumed_sites"] = False
    at.run()
    assert not at.exception


def test_moving_a_slider_alone_does_not_solve(monkeypatch):
    """The assumptions are a form: only Recalculate (再計算) starts a new solve."""
    real, calls = v1.design, []

    def counted(*args, **kw):                      # the real model, with a short time limit for speed
        calls.append(kw.get("links") is None)
        return real(*args, **{**kw, "time_limit": min(kw.get("time_limit", 30.0), 5.0)})

    monkeypatch.setattr(v1, "design", counted)
    at = AppTest.from_file(PAGE, default_timeout=600).run()
    assert not at.exception
    solved = len(calls)
    assert any(calls)                              # the default settings were optimized once
    users = next(m for m in at.metric if m.label.startswith("つながる需要家")).value

    at.slider(key="it_load").set_value(30).run()
    assert not at.exception
    assert len(calls) == solved                    # moved, not submitted: no solve
    assert next(m for m in at.metric if m.label.startswith("つながる需要家")).value == users

    at.slider(key="it_load").set_value(30)         # AppTest sends form values only with the submit
    at.button(key="recalculate").click().run()
    assert not at.exception
    assert any(calls[solved:])                     # Recalculate solves the new settings
    assert at.slider(key="it_load").value == 30


def test_a_discount_rate_of_zero_gives_a_plan(monkeypatch):
    """The undiscounted case: the slider allows 0 %, and the page used to stop with a division by zero."""
    real = v1.design
    monkeypatch.setattr(v1, "design", lambda *args, **kw: real(
        *args, **{**kw, "time_limit": min(kw.get("time_limit", 30.0), 5.0)}))
    at = AppTest.from_file(PAGE, default_timeout=600).run()
    assert not at.exception
    at.slider(key="discount_rate").set_value(0.0)
    at.button(key="recalculate").click().run()
    assert not at.exception
    assert at.slider(key="discount_rate").value == 0.0
    assert next(m for m in at.metric if m.label.startswith("年間の純便益"))


def test_the_page_gives_no_start_unless_the_warm_start_is_switched_on(monkeypatch):
    """With a policy set, no solve gets a start by default, as before. With DCOPT_WARM_START=1 the
    policy solve starts from the no-policy plan of the same settings and the caption says so."""
    real, starts = v1.design, []

    def recorded(*args, **kw):
        if kw.get("links") is None:                # the optimized plans, not the top-five-pairs plans
            starts.append(kw.get("start"))
        return real(*args, **{**kw, "time_limit": min(kw.get("time_limit", 30.0), 5.0)})

    def page():
        at = AppTest.from_file(PAGE, default_timeout=600)
        at.session_state["carbon_price"] = 8000
        at.run()
        assert not at.exception
        return [c.value for c in at.caption]

    monkeypatch.setattr(v1, "design", recorded)
    monkeypatch.delenv(v1.WARM_START_ENV, raising=False)
    captions = page()
    assert starts == [None, None]                  # the policy case and the no-policy case
    assert not any("政策なしの計画から探索を開始" in c for c in captions)

    del starts[:]
    monkeypatch.setenv(v1.WARM_START_ENV, "1")
    captions = page()
    assert len(starts) == 1 and starts[0] is not None       # the no-policy plan is the saved one
    assert starts[0].A == v1.no_policy(starts[0].A) and not starts[0].warm_start
    assert any("政策なしの計画から探索を開始" in c for c in captions)

    del starts[:]
    monkeypatch.delenv(v1.WARM_START_ENV)
    captions = page()                              # switched off again: the plan made without a start
    assert starts == [] and not any("政策なしの計画から探索を開始" in c for c in captions)


def test_network_beats_pairwise():
    from dcopt.heat.v1 import Assumptions, design, ishikari_sites, pairwise
    A = Assumptions()
    dc, sites = ishikari_sites()
    opt, pw = design(dc, sites, A, k=3), pairwise(dc, sites, A)
    assert opt.annual_net >= pw.annual_net - 1e-6
    assert all(u <= w + 1e-6 for u, w in zip(opt.supply_used, opt.waste_heat))
