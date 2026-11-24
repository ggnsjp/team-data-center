"""The Warm Ishikari page renders and the optimized network beats picking pairs one by one."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from dcopt.common.geo import missing_map_data

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(bool(missing_map_data()), reason="run the Ishikari data fetch first")


def test_heat_page_renders():
    at = AppTest.from_file(str(ROOT / "app/pages/1_Warm_Ishikari.py"), default_timeout=600).run()
    assert not at.exception
    net = next(m for m in at.metric if m.label.startswith("年間の純便益"))
    assert float(net.value.replace(",", "")) > 0
    assert len(at.dataframe) >= 1


def test_network_beats_pairwise():
    from dcopt.heat.v1 import Assumptions, design, ishikari_sites, pairwise
    A = Assumptions()
    dc, sites = ishikari_sites()
    opt, pw = design(dc, sites, A, k=3), pairwise(dc, sites, A)
    assert opt.annual_net >= pw.annual_net - 1e-6
    assert all(u <= w + 1e-6 for u, w in zip(opt.supply_used, opt.waste_heat))
