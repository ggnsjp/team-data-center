"""experiments/temperature_bands: the part of each user's heat that a 60 C supply can serve."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from synthetic import instance

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "temperature_bands" / "summary.json"


def _experiment():
    spec = importlib.util.spec_from_file_location("temperature_bands", ROOT / "experiments" / "temperature_bands" / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_cases_take_out_the_published_shares():
    cases = _experiment().CASES
    assert cases["published"] == {}
    assert cases["hospital steam 37 %"] == {"hospital": 0.63, "hotel": 0.74, "factory": 0.61}
    assert cases["hospital steam 49 %"] == {"hospital": 0.51, "hotel": 0.74, "factory": 0.61}


def test_servable_cuts_only_the_named_kinds_and_can_drop_the_assumed_sites():
    exp = _experiment()
    inst = instance([(0, 0)], [("h", "hospital", (500, 0), 1500.0), ("p", "pool", (0, 500), 800.0),
                               ("f", "aquaculture", (300, 300), 5000.0)])
    cut = {u.key: u.annual_mwh for u in exp.servable(inst, {"hospital": 0.51}).users}
    assert cut == pytest.approx({"h": 765.0, "p": 800.0, "f": 5000.0})
    today = {u.key: u.annual_mwh for u in exp.servable(inst, {"hospital": 0.51}, drop_assumed=True).users}
    assert today == pytest.approx({"h": 765.0, "p": 800.0, "f": 0.0})
    assert [u.annual_mwh for u in inst.users] == [1500.0, 800.0, 5000.0]          # the input is left as it was


@pytest.mark.skipif(not RESULTS.exists(), reason="experiments/temperature_bands/run.py has not run")
@pytest.mark.parametrize("name", ["README.md", "README.ja.md", "docs/input-evidence.md", "docs/input-evidence.ja.md"])
def test_the_documents_quote_the_results(name):
    r = json.loads(RESULTS.read_text(encoding="utf-8"))["results"]
    text = (ROOT / name).read_text(encoding="utf-8")
    for case in ("hospital steam 37 %", "hospital steam 49 %"):
        assert f"{r[case]['published plan']['pipes kept']:.1f}" in text, (name, case)
        assert f"{r[case]['published plan']['plan made again']['net_m']:.1f}" in text, (name, case)
