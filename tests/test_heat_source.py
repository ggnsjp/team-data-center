"""The heat source is the data center the curated list names, found by its OpenStreetMap id, and
facility names are shown in English where OpenStreetMap has an English name (review issue #45)."""
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest

from dcopt.common import geo
from dcopt.heat import v1

ROOT = Path(__file__).resolve().parents[1]


def candidates(**columns):
    n = len(next(iter(columns.values())))
    return gpd.GeoDataFrame(columns, geometry=gpd.points_from_xy([141.30 + 0.01 * i for i in range(n)],
                                                                 [43.20 + 0.01 * i for i in range(n)]), crs=4326)


def test_the_curated_list_names_an_openstreetmap_object():
    src = v1.curated_source()
    assert src["element"] == "way" and src["id"] > 0
    assert src["name"] and src["name_en"] == "Sakura Internet Ishikari Data Center"


def test_the_heat_source_is_found_by_id_and_named_from_the_curated_list():
    src = v1.curated_source()
    cand = candidates(element=["way", "node", src["element"]], id=[1, src["id"], src["id"]],
                      name=["another data center", "a node with the same number", "an edited name"],
                      kind=["telecom=data_center", "amenity=school", "building=data_center"])
    dc = v1.heat_source(cand)
    assert (dc.lon, dc.lat) == pytest.approx((141.32, 43.22))        # the third row: the type and the id both match
    assert (dc.name, dc.name_en) == (src["name"], src["name_en"])    # both labels name the same operator
    assert dc.kind == "dc"


@pytest.mark.parametrize("cand", [
    candidates(element=["way"], id=[1], name=["another data center"], kind=["telecom=data_center"]),
    candidates(name=["a file without ids"], kind=["telecom=data_center"]),
], ids=["not in the data", "no ids"])
def test_a_missing_heat_source_says_what_to_do(cand):
    with pytest.raises(v1.HeatSourceMissing) as caught:
        v1.heat_source(cand)
    e = caught.value
    for message in (e.ja, e.en):
        assert geo.fetch_command(v1.AREA) in message and "location_ref" in message
    assert "OpenStreetMap way" in e.en and isinstance(e, LookupError)


def test_english_name_prefers_name_en_then_the_romanised_name():
    row = pd.Series({"name": "石狩病院", "name:en": "Ishikari Hospital", "name:ja-Latn": "Ishikari Byōin"})
    assert geo.english_name(row) == "Ishikari Hospital"
    assert geo.english_name(pd.Series({"name": "番屋の湯", "name:en": float("nan"), "name:ja-Latn": "Banya no Yu"})) == "Banya no Yu"
    assert geo.english_name(pd.Series({"name": "番屋の湯", "name:en": "  ", "name:ja-Latn": None})) == "番屋の湯"
    assert geo.english_name(pd.Series({"name": "番屋の湯"})) == "番屋の湯"       # a file fetched before the tags were kept


def test_the_fetch_keeps_the_english_and_romanised_names():
    assert geo.NAME_COLUMNS == ["name", "name:en", "name:ja-Latn"]
    source = (ROOT / "scripts/fetch_data.py").read_text(encoding="utf-8")
    assert source.count("*NAME_COLUMNS") == 3                       # facilities, named features, heat candidates


@pytest.mark.skipif(bool(geo.missing_map_data()), reason="run the Ishikari data fetch first")
def test_the_fetched_map_data_holds_the_curated_heat_source():
    dc, sites = v1.ishikari_sites()
    assert dc.name_en == "Sakura Internet Ishikari Data Center" and len(sites) > 10
    assert 141.2 < dc.lon < 141.4 and 43.1 < dc.lat < 43.3


# ---- the Overpass server ----

def test_one_setting_names_the_overpass_server(monkeypatch):
    monkeypatch.delenv("OVERPASS_URL", raising=False)
    assert geo.overpass_url() == geo.OVERPASS_MIRROR
    monkeypatch.setenv("OVERPASS_URL", "https://overpass-api.de/api/")
    assert geo.overpass_url() == "https://overpass-api.de/api"
    monkeypatch.setenv("OVERPASS_URL", "")
    assert geo.overpass_url() == geo.OVERPASS_MIRROR


def test_no_script_names_an_overpass_server_itself():
    host = geo.OVERPASS_MIRROR.split("/")[2]
    for script in sorted((ROOT / "scripts").glob("*.py")) + sorted((ROOT / "src").rglob("*.py")):
        if script.name == "geo.py":
            continue
        assert host not in script.read_text(encoding="utf-8"), script.name


@pytest.mark.parametrize("name", ["README.md", "README.ja.md"])
def test_the_readme_says_which_services_the_map_data_comes_from(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    assert "OVERPASS_URL" in text and geo.OVERPASS_MIRROR in text and "nominatim.openstreetmap.org" in text
