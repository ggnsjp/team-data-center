"""The Warm Ishikari Weather page: it explains a missing weather CSV instead of crashing."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
PAGE = str(ROOT / "app/pages/4_Warm_Ishikari_Weather.py")


def test_page_without_the_weather_csvs_says_what_to_run(monkeypatch, tmp_path):
    """Issue from PR #4: the page crashed when the weather CSVs were missing; now it shows the
    explanation (st.error) and the fetch command (st.code) and stops cleanly."""
    monkeypatch.setattr("dcopt.heat.weather.year_csv", lambda year: tmp_path / "missing.csv")
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    assert not at.exception
    assert any("data/jma" in e.value for e in at.error)
    assert any("python -m dcopt.heat.weather" in c.value for c in at.code)
