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
    at = AppTest.from_file(PAGE, default_timeout=120)
    at.session_state["app_lang"] = lang
    at.run()
    assert not at.exception
    table = at.dataframe[0].value
    assert 1 <= len(table) <= 5
    assert list(table.iloc[:, 0]) == list(range(1, len(table) + 1))
    # The weather years surface on the page: a coverage column and, for the opened partner,
    # the coldest/mildest-year metrics from the proposal's weather block.
    label = "寒冬年の最弱月" if lang == "日本語" else "Coldest year, weakest month"
    assert label in table.columns
    if any(v != "—" for v in table[label]):
        ja = lang == "日本語"
        coldest = next(m for m in at.metric
                       if ("一番寒い年" if ja else "Coldest year") in m.label)
        assert 1976 <= int(coldest.value) <= 2025
        assert any(("最も温暖な年" if ja else "Mildest year") in m.label for m in at.metric)
