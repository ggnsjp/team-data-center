"""The Warm Ishikari Weather page: it explains the one-time weather fetch instead of crashing."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
PAGE = str(ROOT / "app/pages/4_Warm_Ishikari_Weather.py")


def test_page_without_the_weather_cache_says_what_to_run(monkeypatch, tmp_path):
    """Issue from PR #4: the page crashed when data/cache/jma was missing; now it says what to run."""
    monkeypatch.setattr("dcopt.heat.weather.year_csv", lambda year: tmp_path / "missing.csv")
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    assert not at.exception
    assert any("dcopt.heat.weather" in e.value for e in at.error)
