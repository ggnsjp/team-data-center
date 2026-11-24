"""The Warm Ishikari Weather page: it explains missing weather CSVs instead of crashing."""
import urllib.error
from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest
from synthetic import tiny

ROOT = Path(__file__).resolve().parents[1]
PAGE = str(ROOT / "app/pages/4_Warm_Ishikari_Weather.py")


def test_page_without_the_weather_csvs_says_what_to_run(monkeypatch, tmp_path):
    """Issue from PR #4: the page crashed when the weather CSVs were missing. Now it tries to download
    the chosen year; when that fails too (offline here), it explains what is missing (st.warning), shows
    the fetch command (st.code) and carries on with the climate normals (on a small synthetic network)."""
    def offline(url, timeout=90):
        raise urllib.error.URLError("no network in tests")
    inst = tiny()
    monkeypatch.setattr("dcopt.heat.weather.year_csv", lambda year: tmp_path / "missing.csv")
    monkeypatch.setattr("dcopt.heat.weather._get", offline)
    monkeypatch.setattr("dcopt.common.geo.use_overpass_mirror", lambda *a, **k: None)
    monkeypatch.setattr("dcopt.heat.v1.ishikari_sites", lambda: (inst.users[0], inst.users))
    monkeypatch.setattr("dcopt.heat.network.build_instance", lambda *a, **k: inst)
    st.cache_resource.clear()
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    st.cache_resource.clear()
    assert not at.exception
    assert any("data/jma" in w.value for w in at.warning)
    assert any("python -m dcopt.heat.weather" in c.value for c in at.code)
