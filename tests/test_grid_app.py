"""The grid hosting-capacity page renders on a built-in system (no download) in both languages."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("lang, label", [("日本語", "受け入れ可能"), ("English", "Hostable")])
def test_grid_page_renders(lang, label):
    at = AppTest.from_file(str(ROOT / "app/pages/5_Grid_Hosting.py"), default_timeout=300)
    at.session_state["app_lang"] = lang
    at.session_state["grid_case"] = "ring5"
    at.run()
    assert not at.exception
    hostable = next(m for m in at.metric if m.label.startswith(label))
    upper = next(m for m in at.metric if "SDP" in m.label)
    assert 0 < float(hostable.value.replace(",", "")) <= float(upper.value.replace(",", "")) + 0.05
    assert len(at.dataframe) >= 1                      # the binding limits


def test_grid_page_studies_run():
    at = AppTest.from_file(str(ROOT / "app/pages/5_Grid_Hosting.py"), default_timeout=300)
    at.session_state["app_lang"] = "English"
    at.session_state["grid_case"] = "feeder8"
    at.run()
    for toggle in at.toggle:
        toggle.set_value(True)
    at.run()
    assert not at.exception
    assert len(at.dataframe) >= 3                      # binding limits, load levels, every bus
