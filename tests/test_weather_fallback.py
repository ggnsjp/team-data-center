"""Weather years with and without the JMA data: only missing years are downloaded, politely, and every
failure (offline, a timeout, a blocked request, a changed page, partial or corrupt cache files) leaves
the app page and the experiment working. No test touches the network: a fake stands in for JMA."""
from __future__ import annotations

import json
import re
import runpy
import shutil
import sys
import urllib.error
from calendar import monthrange
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest
from synthetic import tiny

import dcopt.common.geo as geo
import dcopt.heat.network as network
import dcopt.heat.v1 as v1
from dcopt.heat import weather as W

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "app" / "pages" / "4_Warm_Ishikari_Weather.py"
RUN = ROOT / "experiments" / "weather_years" / "run.py"
W_YEARS = range(1976, 2026)

T = (-4.0, -3.5, 0.5, 7.0, 13.0, 17.5, 21.5, 22.5, 18.5, 12.0, 5.0, -1.0)   # a Sapporo-like year, C
S = (150, 120, 70, 5, 0, 0, 0, 0, 0, 1, 30, 110)                             # snowfall per month, cm


def daily_page(year: int, month: int) -> str:
    """One month in the layout of JMA's daily view: a two-row header (気温 > 平均, 雪 > 降雪) above one
    row per day; '--' marks a day without snow, as on the real pages."""
    head = ('<tr class="mtx"><th rowspan="2">日</th><th colspan="2">気温(℃)</th><th colspan="2">雪(cm)</th></tr>'
            '<tr class="mtx"><th>平均</th><th>最高</th><th>降雪</th><th>最深積雪</th></tr>')
    n = monthrange(year, month)[1]
    snow = f"{S[month - 1] / n:.1f}" if S[month - 1] else "--"
    rows = "".join(f'<tr class="mtx"><td>{d}</td><td>{T[month - 1]:.1f}</td><td>{T[month - 1] + 5:.1f}</td>'
                   f"<td>{snow}</td><td>--</td></tr>" for d in range(1, n + 1))
    return f"<html><body><table>{head}{rows}</table></body></html>"


class FakeJMA:
    """Stands in for weather._get: fails like an offline machine until a test sets `fail` to None,
    then serves daily pages (or `html` instead, a page whose layout has changed)."""

    def __init__(self):
        self.requests: list[tuple[int, int, float]] = []          # (year, month, timeout)
        self.fail: Exception | None = urllib.error.URLError("no network in tests")
        self.html: str | None = None

    def __call__(self, url: str, timeout: float = 90) -> str:
        year, month = map(int, re.search(r"year=(\d+)&month=(\d+)", url).groups())
        self.requests.append((year, month, timeout))
        if self.fail is not None:
            raise self.fail
        return self.html if self.html is not None else daily_page(year, month)


@pytest.fixture(autouse=True)
def jma(tmp_path, monkeypatch) -> FakeJMA:
    """Every test: the fake JMA, an empty cache in a temporary folder and no politeness pauses (the
    politeness test puts them back to check them)."""
    fake = FakeJMA()
    monkeypatch.setattr(W, "_get", fake)
    monkeypatch.setattr(W, "CACHE_DIR", tmp_path / "jma")
    monkeypatch.setattr(W, "DELAY_S", 0.0)
    return fake


# --------------------------------------------------------------------------------- the data layer
def test_only_missing_years_are_downloaded(jma):
    jma.fail = None
    have, missing = W.ensure_years([2001])
    assert [w.year for w in have] == [2001] and missing == {}
    assert len(jma.requests) == 12 and {t for _, _, t in jma.requests} == {W.TIMEOUT_S}
    jma.requests.clear()
    have, missing = W.ensure_years([2002, 2000, 2001])
    assert [w.year for w in have] == [2000, 2001, 2002] and missing == {}
    assert sorted({y for y, _, _ in jma.requests}) == [2000, 2002] and len(jma.requests) == 24
    assert have == W.load_years(2000, 2002)               # the same years the strict loader reads
    assert have[0].t_month[0] == pytest.approx(T[0]) and sum(have[0].snow_month) == pytest.approx(sum(S), rel=0.01)


@pytest.mark.parametrize("failure", [
    urllib.error.URLError("offline"),
    TimeoutError("timed out"),
    urllib.error.HTTPError("https://www.data.jma.go.jp/", 403, "Forbidden", None, None),
    "<html><body>メンテナンス中 / under maintenance</body></html>",
], ids=["offline", "timeout", "blocked", "changed-page"])
def test_failed_downloads_are_polite_and_reported_not_raised(jma, monkeypatch, failure):
    monkeypatch.setattr(W, "DELAY_S", 0.5)
    sleeps: list[float] = []
    monkeypatch.setattr(W.time, "sleep", sleeps.append)
    if isinstance(failure, str):
        jma.fail, jma.html = None, failure
    else:
        jma.fail = failure
    have, missing = W.ensure_years(range(1976, 1981))
    assert have == [] and sorted(missing) == [1976, 1977, 1978, 1979, 1980]
    # MAX_FAILURES years tried, ATTEMPTS tries of their first page each; the other years never asked for
    assert len(jma.requests) == W.MAX_FAILURES * W.ATTEMPTS
    assert {y for y, _, _ in jma.requests} == {1976, 1977}
    assert missing[1976].startswith("download failed: JMA 1976-01")
    assert all(missing[y].startswith("not requested") for y in (1978, 1979, 1980))
    # never a tight loop: a pause before every retry and before the next year's first request
    assert len(sleeps) >= len(jma.requests) - 1 and min(sleeps) >= W.DELAY_S
    assert not W.CACHE_DIR.exists() or not any(W.CACHE_DIR.iterdir())     # nothing half-written


def test_a_download_cut_off_mid_year_leaves_no_file(monkeypatch):
    def cut_off(url, timeout=90):
        year, month = map(int, re.search(r"year=(\d+)&month=(\d+)", url).groups())
        if month >= 5:
            raise urllib.error.URLError("connection reset")
        return daily_page(year, month)
    monkeypatch.setattr(W, "_get", cut_off)
    have, missing = W.ensure_years([2001])
    assert have == [] and "JMA 2001-05" in missing[2001]
    assert not W.year_csv(2001).exists() and not list(W.CACHE_DIR.glob("*.part"))


def test_partial_and_corrupt_cache_files_never_crash(jma):
    jma.fail = None
    W.ensure_years([2001])
    good = W.year_csv(2001).read_text(encoding="utf-8").splitlines()
    W.year_csv(2002).write_text("\n".join(good[:40]) + "\n", encoding="utf-8")             # cut off in February
    no_feb = "\n".join(",".join([m, d, "" if m == "2" else t, s]) for m, d, t, s in (r.split(",") for r in good))
    W.year_csv(2003).write_text(no_feb + "\n", encoding="utf-8")                          # February without data
    W.year_csv(2005).write_bytes(b"\x00\xff\xfe not a csv \x81")                          # not text at all
    W.year_csv(2006).write_text("", encoding="utf-8")                                     # empty
    years = [2001, 2002, 2003, 2005, 2006, 2007]
    have, missing = W.load_cached(years)
    assert [w.year for w in have] == [2001]
    assert all(missing[y].startswith("cache file unusable") for y in (2002, 2003, 2005, 2006))
    assert missing[2007] == "not downloaded yet"
    with pytest.raises(ValueError):
        W.load_years(2001, 2002)                          # the strict loader still raises, as documented
    # offline: no exception, the good year stays usable, the bad files are left as they are
    jma.fail = urllib.error.URLError("offline")
    have, missing = W.ensure_years(years)
    assert [w.year for w in have] == [2001] and sorted(missing) == [2002, 2003, 2005, 2006, 2007]
    assert W.year_csv(2002).read_text(encoding="utf-8").count("\n") == 40
    # online again: the partial and corrupt years are downloaded afresh
    jma.fail = None
    have, missing = W.ensure_years(years)
    assert [w.year for w in have] == years and missing == {}


def test_missing_years_are_summarized_by_reason():
    lines = W.describe_missing({1976: "a", 1977: "a", 1978: "a", 1990: "a", 1980: "b"})
    assert lines == ["1976-1978, 1990: a", "1980: b"]
    assert W.year_spans([1990, 1979, 1978, 1980, 1979]) == "1978-1980, 1990" and W.year_spans([]) == ""


# ------------------------------------------------------------------------------------- the experiment
class Stop(Exception):
    """Raised where the experiment would start the map and solver work, which these tests skip."""


def run_experiment(monkeypatch):
    def stop():
        raise Stop
    monkeypatch.setattr(sys, "argv", [str(RUN)])
    monkeypatch.setattr(geo, "use_overpass_mirror", lambda *a, **k: None)
    monkeypatch.setattr(v1, "ishikari_sites", stop)
    runpy.run_path(str(RUN), run_name="__main__")


def test_experiment_without_any_weather_year_stops_with_a_message(jma, monkeypatch, capsys):
    with pytest.raises(SystemExit) as e:
        run_experiment(monkeypatch)
    assert "no weather years available" in str(e.value.code) and W.COMMAND in str(e.value.code)
    out = capsys.readouterr().out
    assert "weather years missing: 50 of 50" in out
    assert "1978-2025: not requested after 2 failed downloads in a row" in out


def test_experiment_reports_missing_years_and_goes_on_with_the_rest(jma, monkeypatch, capsys):
    jma.fail = None
    W.ensure_years([1984, 2000])
    jma.fail = urllib.error.URLError("offline")
    with pytest.raises(Stop):
        run_experiment(monkeypatch)
    out = capsys.readouterr().out
    assert "weather years missing: 48 of 50" in out
    assert "1978-1983, 1985-1999, 2001-2025: not requested" in out
    assert "continuing with the 2 available years" in out and "weather years 1976-2025: 2;" in out


# --------------------------------------------------------------------------------------- the app page
@pytest.fixture
def page(tmp_path, monkeypatch) -> Path:
    """The weather page in a scratch copy of the repo layout (so it has its own results/ folder), on a
    small synthetic network instead of the Ishikari map: it runs anywhere in a few seconds."""
    copy = tmp_path / "repo" / "app" / "pages" / PAGE.name
    copy.parent.mkdir(parents=True)
    shutil.copy(PAGE, copy)
    inst = tiny()
    monkeypatch.setattr(geo, "use_overpass_mirror", lambda *a, **k: None)
    monkeypatch.setattr(geo, "missing_map_data", lambda *a, **k: [])      # the synthetic network stands in
    monkeypatch.setattr(v1, "ishikari_sites", lambda: (inst.users[0], inst.users))
    monkeypatch.setattr(network, "build_instance", lambda sources, users, area="ishikari": inst)
    st.cache_resource.clear()
    yield copy
    st.cache_resource.clear()


def write_results(page: Path, run: str, content) -> None:
    folder = page.parents[2] / "results" / "weather_years" / run
    folder.mkdir(parents=True)
    text = content if isinstance(content, str) else json.dumps(content)
    (folder / "results.json").write_text(text, encoding="utf-8")


def results(years: list[int], missing: dict | None = None) -> dict:
    """A results.json of the experiment's shape, over the given weather years."""
    def plan(base):
        return {"sites": 18, "km": 11.7, "expected": base, "worst": base - 3e6, "unmet_expected": 0.56,
                "unmet_worst": 0.57, "per_scenario": [base + 1e6 * i for i in range(len(years))]}
    return {"git_commit": "abc1234", "weather_years": years, "missing_years": missing or {},
            "published_replication": {"rp": 93.8e6, "eev": 79.0e6, "vss": 14.8e6},
            "stages": {"a": {"plans": {"rp": plan(130e6), "eev": plan(140e6), "published-4-plan": plan(120e6),
                                       "published-mean-plan": plan(110e6)}}}}


def subheaders(at) -> list[str]:
    return [s.value for s in at.subheader]


def test_page_with_the_shipped_years_never_asks_jma(page, jma, monkeypatch):
    monkeypatch.setattr(W, "CACHE_DIR", W.ROOT / "data" / "jma")         # the 50 years in the repo
    at = AppTest.from_file(str(page), default_timeout=120).run()
    assert not at.exception and not at.warning and not at.code and jma.requests == []
    assert "1984年の気象で導管網を作り直すと" in subheaders(at)
    assert any("暖房度日指数 1.14" in c.value for c in at.caption)       # 1984, the coldest of the 50


def test_page_downloads_only_the_selected_year(page, jma):
    jma.fail = None
    at = AppTest.from_file(str(page), default_timeout=120).run()
    assert not at.exception and not at.warning
    assert {y for y, _, _ in jma.requests} == {1984} and len(jma.requests) == 12
    assert [p.name for p in W.CACHE_DIR.iterdir()] == [W.year_csv(1984).name]
    assert "1984年の気象で導管網を作り直すと" in subheaders(at)
    assert any("実験結果がまだありません" in i.value for i in at.info)       # no experiment run: a notice
    at.select_slider[0].set_value(2000).run()
    assert not at.exception and not at.warning
    assert {y for y, _, _ in jma.requests} == {1984, 2000} and len(jma.requests) == 24


def test_page_offline_with_an_empty_cache_shows_the_normals(page, jma):
    at = AppTest.from_file(str(page), default_timeout=120).run()
    assert not at.exception
    [warning] = at.warning
    assert "1984年の気象データ" in warning.value and "平年値" in warning.value
    assert [c.value for c in at.code] == [W.COMMAND]
    assert "平年値の気象で導管網を作り直すと" in subheaders(at)
    assert len(at.metric) == 5 and at.metric[4].value == "—"
    assert len(jma.requests) == W.ATTEMPTS                  # one page, ATTEMPTS tries, then it gives up
    at.session_state["app_lang"] = "English"
    at.run()
    assert not at.exception
    [warning] = at.warning
    assert "The 1984 weather data" in warning.value and "climate normals" in warning.value
    assert [c.value for c in at.code] == [W.COMMAND]
    assert "Re-optimizing the network for the climate normals" in subheaders(at)
    assert len(jma.requests) == W.ATTEMPTS                  # a rerun does not ask JMA again
    jma.fail = None                                         # back online: the button fetches the year
    at.button(key="weather_retry").click().run()
    assert not at.exception and not at.warning and not at.code
    assert "Re-optimizing the network for 1984" in subheaders(at) and W.year_csv(1984).exists()


def test_page_offline_falls_back_to_the_nearest_cached_year(page, jma):
    jma.fail = None
    W.ensure_years([1990, 2010])
    jma.fail = urllib.error.URLError("offline")
    at = AppTest.from_file(str(page), default_timeout=120).run()
    at.session_state["app_lang"] = "English"
    at.run()
    assert not at.exception
    [warning] = at.warning
    assert "The 1984 weather data" in warning.value and "Showing 1990 instead" in warning.value
    assert "Re-optimizing the network for 1990" in subheaders(at)
    assert not W.year_csv(1984).exists()


def test_page_reads_the_experiment_results_and_survives_bad_ones(page, jma):
    jma.fail = None
    write_results(page, "20261201-000000", results([1983, 1984, 1985]))
    at = AppTest.from_file(str(page), default_timeout=120).run()
    assert not at.exception and not at.warning and not at.info
    assert len(at.dataframe) == 2                           # stage A's plans and the users connected in 1984
    assert at.metric[4].value == "131.0"                    # the experiment's plan in 1984
    write_results(page, "20261202-000000", '{"git_commit": "abc12')               # cut off mid-write
    at.run()
    assert not at.exception and at.metric[4].value == "—"
    assert any("20261202-000000/results.json` を読み込めません" in w.value for w in at.warning)
    write_results(page, "20261203-000000", {"stages": {"b": {"plans": {}}}})       # another shape
    at.run()
    assert not at.exception and at.metric[4].value == "—"
    assert any("形式が想定と違う" in w.value for w in at.warning)


def test_page_says_when_the_experiment_ran_on_fewer_years(page, jma):
    jma.fail = None
    kept = [1983, 1984, 1985]
    write_results(page, "20261201-000000",
                  results(kept, {str(y): "download failed: offline" for y in W_YEARS if y not in kept}))
    at = AppTest.from_file(str(page), default_timeout=120).run()
    at.session_state["app_lang"] = "English"
    at.run()
    assert not at.exception
    [warning] = at.warning
    assert "This run used 3 weather years (missing: 1976-1982, 1986-2025)" in warning.value
    assert at.metric[4].value == "131.0"
