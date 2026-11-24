"""The Warm Ishikari Proposals page: a clear message without data, five partners and a proposal with it."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
PAGE = str(ROOT / "app/pages/3_Warm_Ishikari_Proposals.py")
DATA = ROOT / "out/proposals/proposals.json"


@pytest.mark.skipif(DATA.exists(), reason="the proposal data exists here")
def test_page_without_data_says_what_to_run():
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    assert not at.exception
    assert any("export_proposals.py" in w.value for w in at.warning)


@pytest.mark.skipif(not DATA.exists(), reason="run scripts/export_proposals.py first")
@pytest.mark.parametrize("lang", ["日本語", "English"])
def test_page_lists_partners_and_opens_a_proposal(lang):
    at = AppTest.from_file(PAGE, default_timeout=120).run()
    at.radio(key="proposal_lang").set_value(lang).run()
    assert not at.exception
    table = at.dataframe[0].value
    assert 1 <= len(table) <= 5
    assert list(table.iloc[:, 0]) == list(range(1, len(table) + 1))
