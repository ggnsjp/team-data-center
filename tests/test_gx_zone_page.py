"""The GX overlay page and its data: every marker carries a source, and the numbers match the
official documents (590 MW pre-filed by Hokkaido) and the curated CSV."""
import json
import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
GX = ROOT / "out" / "gx_zone" / "gx.json"
PLOT_CSV = ROOT / "data" / "curated" / "ishikari_gx_plots.csv"
PAGE = ROOT / "app/pages/8_GX_Overlay.py"
STORY_PAGE = ROOT / "web" / "gx_zone" / "index.html"

pytestmark = pytest.mark.skipif(not GX.exists(), reason="run scripts/export_gx_zone.py first")


def test_reserved_power_matches_the_prefecture_documents():
    data = json.loads(GX.read_text(encoding="utf-8"))
    assert sum(r["mw"] for r in data["reserved"]) == 590


def test_every_marker_has_a_source_and_a_location_basis():
    data = json.loads(GX.read_text(encoding="utf-8"))
    for dc in data["dcs"]:
        assert dc["source"] and dc["where"][0] and dc["where"][1]
    for r in data["reserved"]:
        assert r["source"] and r["where"][0] and r["where"][1]


def test_the_curated_data_centers_are_all_on_the_map():
    data = json.loads(GX.read_text(encoding="utf-8"))
    keys = {d["key"] for d in data["dcs"]}
    assert {"isrd1", "sakura", "zed", "nttme"} <= keys


def test_the_export_matches_the_curated_csv():
    import csv
    data = json.loads(GX.read_text(encoding="utf-8"))
    rows = {r["key"]: r for r in csv.DictReader(PLOT_CSV.open(encoding="utf-8"))}
    assert len(data["reserved"]) == len(rows) == 5
    for r in data["reserved"]:
        row = rows[r["key"]]
        assert r["mw"] == float(row["mw"]) and r["kv"] == int(row["kv"])
        assert abs(r["lon"] - float(row["lon"])) < 1e-9
        assert abs(r["lat"] - float(row["lat"])) < 1e-9


def test_web_page_knows_every_marker_status():
    table = re.search(r"const stCls = \{(.*?)\};", STORY_PAGE.read_text(encoding="utf-8")).group(1)
    for status in ("operating", "under_construction", "planned"):
        assert status in table


@pytest.mark.parametrize("lang", ["日本語", "English"])
def test_page_renders(lang):
    at = AppTest.from_file(str(PAGE), default_timeout=60)
    at.session_state["app_lang"] = lang
    at.run()
    assert not at.exception
    assert len(at.caption) >= 2


def test_the_energy_portfolio_is_ishikari_only():
    data = json.loads(GX.read_text(encoding="utf-8"))
    kinds = {e["kind"] for e in data["energy"]}
    assert {"wind_offshore", "wind_onshore", "solar", "fossil"} <= kinds
    for e in data["energy"]:
        assert e["city"] == "ishikari"
        assert e["source"] and e["where"][0] and e["where"][1]
    re_mw = sum(e["mw"] for e in data["energy"]
                if e["kind"] != "fossil" and e["status"] == "operating" and e["mw"])
    assert re_mw >= 250            # 195 offshore + 60 onshore + solar + storage
    fo_mw = sum(e["mw"] for e in data["energy"] if e["kind"] == "fossil" and e["mw"])
    assert fo_mw >= 569            # the Ishikariwan Shinko gas plant


def test_the_osm_node_layers_came_through():
    data = json.loads(GX.read_text(encoding="utf-8"))
    assert len(data["osm_wind"]) >= 30            # the mapped turbines around the port
    assert len(data["osm_solar_ishikari"]) >= 20
    assert all(k.startswith("osm_") is False or "ishikari" in k or k == "osm_wind"
               for k in data if k.startswith("osm_"))   # the only node layers are Ishikari's
