"""Data accountability: the register in data/register.toml is complete and true, the committed data
is byte-for-byte what data/SHA256SUMS pins, and the committed JMA years reproduce JMA's published
normals. See docs/data-accountability.md."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dcopt.common import provenance as prov
from dcopt.heat import weather as W

ROOT = Path(__file__).resolve().parents[1]
DATASETS = prov.register()
REQUIRED = ("id", "title", "storage", "terms", "paths", "licence", "sources", "made_by", "processing", "used_by",
            "checks", "refresh")
# files under data/ that describe the data rather than being data
DATA_DOCS = {"data/README.md", "data/register.toml", "data/SHA256SUMS", "data/jma/README.md"}


def tracked(prefix: str) -> set[str]:
    out = subprocess.run(["git", "ls-files", prefix], cwd=ROOT, capture_output=True, text=True, check=True)
    return set(out.stdout.split())


# -------------------------------------------------------------------------------------- the register
@pytest.mark.parametrize("d", DATASETS, ids=[d["id"] for d in DATASETS])
def test_every_dataset_says_where_how_and_under_which_terms(d):
    assert all(d.get(k) not in (None, "") for k in REQUIRED if k != "sources"), d["id"]
    assert d["storage"] in {"git", "code", "local"}, d["id"]
    for s in d["sources"]:
        assert s.startswith("https://") or (ROOT / s.split("#")[0]).exists(), (d["id"], s)
    if d["storage"] == "git" and not d["licence"].startswith("MIT"):
        assert d.get("attribution"), f"{d['id']}: data under other terms must say how to credit it"


@pytest.mark.parametrize("d", DATASETS, ids=[d["id"] for d in DATASETS])
def test_every_named_file_exists(d):
    for p in d.get("code", []) + d["used_by"] + d["checks"]:
        assert (ROOT / p).exists(), (d["id"], p)
    if d["storage"] == "code":
        assert all((ROOT / p).is_file() for p in d["paths"]), d["id"]
    if d["storage"] == "git":
        assert all(any(ROOT.glob(p)) for p in d["paths"]), d["id"]
    for word in d["made_by"].split():
        if word.endswith(".py") and "*" not in word:
            assert (ROOT / word).exists(), (d["id"], word)


def test_ids_are_unique():
    ids = [d["id"] for d in DATASETS]
    assert len(ids) == len(set(ids))


def test_local_data_is_git_ignored_and_not_committed():
    for d in DATASETS:
        if d["storage"] == "local":
            for p in d["paths"]:
                ignored = subprocess.run(["git", "check-ignore", "-q", p + "probe"], cwd=ROOT, check=False).returncode == 0
                assert ignored, f"{p} must be git-ignored"
                assert not tracked(p), f"{p} has committed files"


def test_every_committed_data_file_is_registered():
    registered = {p.as_posix() for p in prov.committed_files()}
    unlisted = tracked("data") - registered - DATA_DOCS
    assert not unlisted, f"add these to data/register.toml: {sorted(unlisted)}"


# ------------------------------------------------------------------------------------------ integrity
def test_committed_data_matches_the_pinned_checksums():
    assert prov.verify() == [], ("committed data differs from data/SHA256SUMS. If the change is intended, "
                                 "run `uv run python -m dcopt.common.provenance --write` and say why in the commit")


def test_verify_notices_a_changed_file(tmp_path, monkeypatch):
    sums = tmp_path / "SHA256SUMS"
    sums.write_text(prov.SUMS.read_text(encoding="utf-8").replace("c", "d", 1), encoding="utf-8")
    monkeypatch.setattr(prov, "SUMS", sums)
    assert prov.verify() == ["changed: data/curated/ishikari_data_centers.csv"]


def test_stamp_ties_a_result_to_code_and_data():
    s = prov.stamp(solver="highs")
    assert s["data_fingerprint"] == prov.fingerprint() and len(s["data_fingerprint"]) == 16
    assert s["data_problems"] == [] and s["solver"] == "highs"
    assert "numpy" in s["packages"] and s["python"]


# ------------------------------------------------------------------- the data against its own source
def test_committed_jma_years_reproduce_the_published_normals():
    """JMA publishes 1991-2020 monthly normals (v1.TEMP, v1.SNOW). The committed daily data, averaged
    the same way, must land on them; this catches a parser or download error in any of those 30 years."""
    years = W.load_years(1991, 2020)
    check = W.validate_normals(years)
    assert check["ok"], check
    assert check["max_abs_temp_c"] <= 0.1              # docs/formulations/heat.md: about 0.05 C
    assert check["max_abs_snow_cm"] <= 8.0             # and about 7.5 cm in the worst month
    assert check["daily_constants_dev"] <= 0.01        # HDD18_N, HDD15_N, SNOW_N within 1 %


def test_committed_years_are_complete():
    for y in range(W.YEARS[0], W.YEARS[1] + 1):
        wy = W.weather_year_from_csv(y, W.year_csv(y))
        assert len(wy.t_day) in (365, 366), y
        assert wy.n_missing_t <= 5, f"{y}: {wy.n_missing_t} days filled in"


# ------------------------------------------------------------------------------------ lineage graph
def test_lineage_graph_is_connected_and_every_dataset_is_checked():
    nodes, edges = prov.lineage()
    assert all(a in nodes and b in nodes for a, _, b in edges)
    for d in DATASETS:
        assert any(r == "CHECKS" and b == d["id"] for _, r, b in edges), d["id"]
        if d["storage"] == "git":
            assert ("sums", "PINS", d["id"]) in edges


def test_cypher_export_is_one_statement_per_node_and_edge():
    nodes, edges = prov.lineage()
    lines = [x for x in prov.cypher().splitlines() if not x.startswith("//")]
    assert len(lines) == len(nodes) + len(edges) and all(x.endswith(";") for x in lines)


def test_lineage_diagram_in_the_docs_is_current():
    assert prov.doc_diagram() in prov.DOC.read_text(encoding="utf-8"), \
        "run `uv run python -m dcopt.common.provenance --write` to refresh docs/data-accountability.md"
