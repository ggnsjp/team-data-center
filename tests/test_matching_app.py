"""The renewable-matching page: a clear message without the records, three counts with them."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from synthetic_records import write_year

from dcopt.matching import records

ROOT = Path(__file__).resolve().parents[1]
PAGE = str(ROOT / "app/pages/7_Matching.py")


def value(metric) -> float:
    return float(metric.value.replace("%", "").replace("+", "").replace("−", "-").replace(",", "").strip())


def test_page_without_records_says_what_to_run(tmp_path, monkeypatch):
    monkeypatch.setattr(records, "DIR", tmp_path / "none")
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    assert not at.exception
    assert any("dcopt.matching.records" in w.value for w in at.warning)
    assert len(at.metric) == 0


@pytest.mark.parametrize("lang", ["日本語", "English"])
def test_page_counts_the_year_three_ways(tmp_path, monkeypatch, lang):
    monkeypatch.setattr(records, "DIR", tmp_path)
    write_year(tmp_path, 2024)
    at = AppTest.from_file(PAGE, default_timeout=120)
    at.session_state["app_lang"] = lang
    at.run()
    assert not at.exception
    by_year, by_slot, existing, new = (value(m) for m in at.metric)
    assert by_year == 100 and 20 < by_slot < 100               # a contract for the yearly use does not match every slot
    assert 90 <= existing <= 100 and new < existing            # without new plants, thermal plants cover the added load
    at.slider(key="match_volume").set_value(2.0)
    at.slider(key="match_hours").set_value(4.0)
    at.run()
    assert not at.exception
    more = [value(m) for m in at.metric]
    assert more[0] == 200 and more[1] > by_slot and more[3] < new
    assert len(at.dataframe) == 0                              # the linear program runs only on request
