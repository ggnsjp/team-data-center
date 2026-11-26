"""Consistency of the parameter tables, the curated data, the site filter and the documents."""
from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

from dcopt.heat import v1
from dcopt.heat.network import PEAK_FACTOR, SUPPLY_BASIS, SUPPLY_C, Params, assumptions_table, ishikari_sources

ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------------------------ parameter tables
@pytest.mark.parametrize("kind", sorted(v1.KINDS))
def test_every_kind_has_model_parameters(kind):
    assert kind in SUPPLY_C and kind in SUPPLY_BASIS and kind in PEAK_FACTOR
    assert SUPPLY_BASIS[kind].startswith("assumption")
    assert v1.KINDS[kind][2] in v1.PROFILES


def test_profiles_sum_to_one():
    for name, prof in v1.PROFILES.items():
        assert len(prof) == 12 and sum(prof) == pytest.approx(1.0), name
        assert min(prof) >= 0.0, name


def test_assumptions_table_lists_every_kind_and_parameter():
    keys = {r["key"] for r in assumptions_table(Params())}
    assert {f"supply_{k}" for k in v1.KINDS} <= keys
    assert {"recovery", "kerosene", "pipe_cost", "pipe_cap", "hp_capex", "peak"} <= keys
    for r in assumptions_table(Params()):
        assert r["basis"], r["key"]                              # every row says where it comes from


# ------------------------------------------------------------------------------------- curated data
def read_csv(name):
    with (ROOT / "data" / "curated" / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_curated_data_centers_name_their_sources():
    for r in read_csv("ishikari_data_centers.csv"):
        assert r["it_load_basis"].strip(), r["key"]
        assert all(u.startswith("https://") for u in r["sources"].split()), r["key"]


def test_curated_it_loads_match_the_model():
    dummy = v1.Site("sakura", "s", "s", "dc", 141.3, 43.18, 0.0, "test")
    model = {s.key: s.it_mw for s in ishikari_sources(dummy)}
    for r in read_csv("ishikari_data_centers.csv"):
        assert model[r["key"]] == {"low": float(r["it_load_mw_low"]), "high": float(r["it_load_mw_high"])}, r["key"]


# ------------------------------------------------------------------- named-facility filter, no map data
def test_named_facilities_skip_bus_stops_and_post_offices(tmp_path, monkeypatch):
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import Point, box

    town = box(141.25, 43.10, 141.40, 43.25)
    gpd.GeoDataFrame({"name": ["石狩市"]}, geometry=[town], crs=4326).to_file(tmp_path / "boundary.geojson")
    gpd.GeoDataFrame({"kind": ["telecom=data_center", "landuse=farmland"], "name": ["DC", None],
                      "area_m2": [1000.0, 50_000.0]},
                     geometry=[Point(141.30, 43.18), Point(141.31, 43.17)], crs=4326
                     ).to_file(tmp_path / "heat_candidates.geojson")
    names = ["石狩市役所", "石狩市役所前郵便局", "聚富会館前", "花川南コミュニティセンター", "石狩市民図書館",
             "スーパーホテル石狩", "ホテル前", "北斗重工株式会社 石狩第2工場", "中央バス札幌整備工場前",
             "石狩市役所 親船出張所", "石狩病院"]
    gpd.GeoDataFrame({"name": names}, geometry=[Point(141.30 + 0.001 * i, 43.17) for i in range(len(names))],
                     crs=4326).to_file(tmp_path / "named.geojson")
    gpd.GeoDataFrame({"kind": ["townhall"], "name": ["石狩市役所"]}, geometry=[Point(141.315, 43.171)],
                     crs=4326).to_file(tmp_path / "pois.geojson")
    monkeypatch.setattr(v1, "paths", lambda area: {"dir": tmp_path, "named": tmp_path / "named.geojson",
                                                   "pois": tmp_path / "pois.geojson",
                                                   "boundary": tmp_path / "boundary.geojson"})
    monkeypatch.setattr(v1, "snap", lambda lon, lat, area: 0)
    _, sites = v1.ishikari_sites()
    by_kind: dict[str, set] = {}
    for s in sites:
        by_kind.setdefault(s.kind, set()).add(s.name)
    assert by_kind["public"] == {"石狩市役所", "花川南コミュニティセンター", "石狩市民図書館"}
    assert by_kind["hotel"] == {"スーパーホテル石狩"}
    assert by_kind["factory"] == {"北斗重工株式会社 石狩第2工場"}
    assert by_kind["hospital"] == {"石狩病院"}
    assert {"aquaculture", "snow", "new_greenhouse"} <= set(by_kind)          # the labelled assumed sites
    assert all("assumed" in s.name_en or s.kind not in ("aquaculture", "snow", "new_greenhouse") for s in sites)


# ------------------------------------------------------------------------------------- documents
CITE = re.compile(r"\[(\d+(?:\s*[–-]\s*\d+)?(?:\s*,\s*\d+(?:\s*[–-]\s*\d+)?)*)\](?!\()")


def cited_numbers(text: str) -> set[int]:
    out: set[int] = set()
    for group in CITE.findall(text):
        for part in group.split(","):
            bounds = [int(x) for x in re.split(r"\s*[–-]\s*", part.strip())]
            out |= set(range(bounds[0], bounds[-1] + 1))
    return out


def test_citation_parser():
    assert cited_numbers("a [1] b [2, 4–6] c [10-11] [link](x) [x]") == {1, 2, 4, 5, 6, 10, 11}


@pytest.mark.parametrize("name, heading", [("README.md", "## References"), ("README.ja.md", "## 参考文献")])
def test_readme_citations_resolve(name, heading):
    text = (ROOT / name).read_text(encoding="utf-8")
    body, refs = text.split(heading, 1)
    refs = refs.split("\n## ", 1)[0]
    numbered = [int(m) for m in re.findall(r"^(\d+)\. ", refs, flags=re.MULTILINE)]
    assert numbered == list(range(1, len(numbered) + 1)), "references are numbered 1..N without gaps"
    assert len(numbered) == 77
    used = cited_numbers(body)
    assert used, "the body cites something"
    assert used <= set(numbered), f"citations without a reference: {sorted(used - set(numbered))}"


def _readme_parts(name: str, heading: str) -> tuple[str, str, dict[int, list[str]]]:
    """The body, the intro of the reference list, and each numbered reference's URLs."""
    body, refs = (ROOT / name).read_text(encoding="utf-8").split(heading, 1)
    refs = refs.split("\n## ", 1)[0]
    intro = re.split(r"^1\. ", refs, maxsplit=1, flags=re.MULTILINE)[0]
    urls = {int(n): re.findall(r"https?://\S+", line)
            for n, line in re.findall(r"^(\d+)\. (.*)$", refs, flags=re.MULTILINE)}
    return body, intro, urls


def test_both_readmes_cite_the_same_references():
    en_body, en_intro, en_urls = _readme_parts("README.md", "## References")
    ja_body, ja_intro, ja_urls = _readme_parts("README.ja.md", "## 参考文献")
    assert cited_numbers(en_body) == cited_numbers(ja_body), (
        f"only in README.md: {sorted(cited_numbers(en_body) - cited_numbers(ja_body))}; "
        f"only in README.ja.md: {sorted(cited_numbers(ja_body) - cited_numbers(en_body))}")
    assert en_urls == ja_urls, "the two reference lists point to the same sources, number by number"
    for name, intro in (("README.md", en_intro), ("README.ja.md", ja_intro)):
        assert cited_numbers(intro) == set(en_urls), f"{name}: the reference-list intro covers every reference"


def test_no_attribution_words_in_the_repository():
    skip = {".venv", "data", "out", "results", ".git", "__pycache__", ".pytest_cache", ".ruff_cache"}
    word = re.compile("cl" + "aude|anth" + "ropic", re.IGNORECASE)                 # split so this file passes its own test
    hits = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in skip for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix.lower() in {".gif", ".png", ".jpg", ".jpeg", ".woff2", ".pdf"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if word.search(text):
            hits.append(str(path.relative_to(ROOT)))
    assert not hits, f"attribution words in: {hits}"


MATH_PAGES = sorted([*(ROOT / "docs" / "formulations").glob("*.md"), *(ROOT / "docs").glob("exergy*.md")])


@pytest.mark.parametrize("page", MATH_PAGES, ids=lambda p: p.name)
def test_math_pages_render_on_github(page):
    text = page.read_text(encoding="utf-8")
    assert "$$" not in text, "use ```math blocks: GitHub escapes backslashes inside $$...$$"
    assert "\\{" not in text and "\\}" not in text, "use \\lbrace and \\rbrace"
    assert text.count("```") % 2 == 0, "every fenced block is closed"
    for m in re.finditer(r"(?<![$`])\$([^$\n]+)\$(?![$`])", text):
        assert not m.group(1).endswith(" "), f"space before a closing $: {m.group(0)[:40]}"
