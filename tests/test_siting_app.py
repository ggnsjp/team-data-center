"""The Siting page: a clear message without data, a choice and a map with it."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
PAGE = str(ROOT / "app/pages/6_Siting.py")
DATA = ROOT / "out/siting/siting.json"


@pytest.mark.skipif(DATA.exists(), reason="the siting data exists here")
def test_page_without_data_says_what_to_run():
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    assert not at.exception
    assert any("export_siting.py" in w.value for w in at.warning)


@pytest.mark.skipif(not DATA.exists(), reason="run scripts/export_siting.py first")
@pytest.mark.parametrize("lang", ["日本語", "English"])
def test_page_chooses_sites(lang):
    at = AppTest.from_file(PAGE, default_timeout=120)
    at.session_state["app_lang"] = lang
    at.run()
    assert not at.exception
    assert len(at.metric) == 4 and int(at.metric[0].value) > 10
    table = at.dataframe[0].value
    assert 1 <= len(table) <= 10 and table.iloc[:, 0].str.contains("★").sum() == 1      # one site chosen by default
    at.slider(key="siting_n").set_value(2)
    at.run()
    assert not at.exception
    assert at.dataframe[0].value.iloc[:, 0].str.contains("★").sum() == 2
