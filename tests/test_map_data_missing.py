"""Pages 1 and 4 without the Ishikari map data (a fresh clone, or a fetch still running): they say what
is missing and what to run instead of crashing with a traceback."""
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from dcopt.common import geo

ROOT = Path(__file__).resolve().parents[1]
HEAT = str(ROOT / "app/pages/1_Warm_Ishikari.py")
WEATHER = str(ROOT / "app/pages/4_Warm_Ishikari_Weather.py")


@pytest.fixture
def no_map(monkeypatch, tmp_path):
    monkeypatch.setattr(geo, "CACHE", tmp_path)
    st.cache_resource.clear()
    yield tmp_path / geo.DEFAULT_AREA
    st.cache_resource.clear()


def run(page):
    return AppTest.from_file(page, default_timeout=60).run()


def test_missing_map_data_lists_what_the_fetch_has_not_written_yet(no_map):
    assert len(geo.missing_map_data()) == 5
    no_map.mkdir()
    for name in ("boundary.geojson", "pois.geojson"):            # a fetch that stopped part-way
        (no_map / name).write_text("{}")
    assert sorted(f.name for f in geo.missing_map_data()) == ["heat_candidates.geojson", "named.geojson",
                                                              "study_drive.graphml"]
    for f in geo.missing_map_data():
        f.write_text("{}")
    assert geo.missing_map_data() == []


def test_heat_page_without_map_data_says_what_to_run(no_map):
    at = run(HEAT)
    assert not at.exception
    assert any("heat_candidates.geojson" in w.value for w in at.warning)
    assert [c.value for c in at.code] == [geo.fetch_command()]
    assert not at.metric                                          # stopped before the optimization


def test_weather_page_without_map_data_keeps_the_weather_and_says_what_to_run(no_map):
    at = run(WEATHER)
    assert not at.exception
    assert any("1984" in s.value for s in at.subheader)           # the weather section still renders
    assert any("study_drive.graphml" in w.value for w in at.warning)
    assert geo.fetch_command() in [c.value for c in at.code]
