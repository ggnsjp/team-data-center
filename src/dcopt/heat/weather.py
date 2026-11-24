"""Weather-year scenarios: real Sapporo weather, year by year, for the heat-network model.

The v2 model spreads each user's annual demand over the months with profiles built from the
JMA climate normals for Sapporo, 1991-2020 (v1.PROFILES). This module adds the weather years:
for each year it reads JMA's daily observations (mean temperature, snowfall) and the year
becomes one scenario whose demand is higher in a cold winter, lower in a mild one, and whose
monthly shape follows that year's own weather. The rules mirror the normals profiles of v1,
keyed by the profile name KINDS[kind][2] — but the degree-day indices and the monthly shares
are computed from the DAILY observations (the monthly-mean shortcut is exact only when a whole
month sits on one side of the base temperature):

  profile     annual scale s(y)                          monthly shares
  building    HDD18(y) / HDD18(normals)                  the year's daily HDD18, by month
  greenhouse  HDD15(y) / HDD15(normals)                  the year's daily HDD15, by month
  school      as building                                daily HDD18, August x 0.3
  pool        0.5 + 0.5 x HDD18(y)/HDD18(normals)        0.5 x days/365 + 0.5 x the year's daily HDD18
  snow        snowfall(y) / snowfall(normals)            the year's monthly snowfall totals
  flat        1.0 (fish farm, factory)                   days

The normals in the denominators are the daily-climatology constants below (computed once from
the fetched 1991-2020 data, the same numbers v1's TEMP/SNOW page reports as monthly values);
`validate_normals` re-checks them against whatever data is in the cache. Beyond the monthly
recourse, a year also carries a design-day peak: for the temperature-driven kinds the worst
DAY of the year sets the pipe design load (the design-day method of district heating), while
snow-melting stays monthly (melt is a multi-day process) and flat kinds have no peak day.

Data   JMA 過去の気象データ検索 (the daily view of the same station 47412 that JMA_SOURCE cites),
       fetched once per month into data/cache/jma/ (git ignored), one CSV per year.
Run    `uv run python -m dcopt.heat.weather 1976 2025` fetches and validates the years.
"""
from __future__ import annotations

import re
import time
import urllib.request
from calendar import monthrange
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from dcopt.common.geo import CACHE
from dcopt.heat.v1 import DAYS, KINDS, SNOW, TEMP

PREC_NO, BLOCK_NO = 14, 47412          # Sapporo, the station JMA_SOURCE cites
URL = ("https://www.data.jma.go.jp/obd/stats/etrn/view/daily_s1.php"
       "?prec_no={prec}&block_no={block}&year={year}&month={month}&day=&view=p1")
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36")
DELAY_S = 0.5                          # politeness delay between JMA requests
CACHE_DIR = CACHE / "jma"

# Daily-climatology normals, Sapporo 47412, 1991-2020: sum over the calendar year of the
# per-calendar-day mean of the fetched daily observations (computed from data/cache/jma,
# 2026-11-24; matches v1's monthly TEMP exactly and SNOW within 2 %). These are the
# denominators that make a normals-like year scale to 1.0.
HDD18_N = 3464.328                     # sum of daily max(0, 18 - T_day), C x days
HDD15_N = 2686.048                     # same at 15 C (greenhouses)
SNOW_N = 486.15                        # mean seasonal snowfall total, cm


def _norm(x) -> tuple[float, ...]:
    s = float(sum(x))
    return tuple(v / s for v in x)


def _get(url: str, timeout: float = 90) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _row_cells(row: str) -> list[tuple[str, int, int]]:
    """(text, colspan, rowspan) of every cell of one <tr>, tags stripped, whitespace cleaned."""
    out = []
    for m in re.finditer(r"<t(d|h)([^>]*)>(.*?)</t\1>", row, re.S):
        attrs = m.group(2)
        cs = re.search(r'colspan="?(\d+)', attrs)
        rs = re.search(r'rowspan="?(\d+)', attrs)
        text = re.sub(r"<[^>]+>", "", m.group(3)).replace("\u3000", " ").strip()
        out.append((text, int(cs.group(1)) if cs else 1, int(rs.group(1)) if rs else 1))
    return out


_NUM = re.compile(r"^[\s(]*(−|-)?\s*(\d+(?:\.\d+)?)[\s)*+!$%#(\]]*$")
_FLAGS = "()*+!$%#[]"


def _num(s: str) -> float | None:
    """A numeric cell: '--' (no snow) and 'x' (no observation) become None; the value keeps its
    sign and any JMA quality-flag suffix (e.g. '12.2 )' means partial but the value stands)."""
    t = s.strip()
    if t in ("", "--", "---", "×", "x"):
        return None
    m = _NUM.match(t.replace("−", "-"))
    if m is not None:
        return float((m.group(1) or "") + m.group(2))
    core = "".join(ch for ch in t if ch not in _FLAGS).strip()   # a missing marker with a flag
    if core in ("", "--", "---", "×", "x"):
        return None
    raise ValueError(f"non-numeric cell: {s!r}")


def _value(cells, index: int) -> float | None:
    """One parsed data cell; _num owns every parsing rule, this only adds the column context."""
    if index >= len(cells):
        return None
    text = cells[index][0]
    try:
        return _num(text)
    except ValueError as e:
        raise ValueError(f"non-numeric cell at column {index}: {text!r}") from e


def parse_month(html: str) -> dict[str, list[float | None] | int]:
    """Daily values of one month page: {'t_mean': [...], 'snow': [...], 'days': n} indexed by day-1.

    The page is a 21-column table with a multi-row header (groups with colspan, sublabels with
    rowspan). The columns are located through that header by the standard grid fill, so the parser
    survives layout changes: temperature average is the group 気温 subcolumn 平均, snowfall the
    group 雪 subcolumn 降雪. Data rows are the rows whose first cell is the day number.
    """
    rows = re.findall(r'<tr class="mtx"[^>]*>.*?</tr>', html, re.S)
    parsed = [(_row_cells(r), r) for r in rows]
    data = [cells for cells, _ in parsed if cells and cells[0][0].isdigit()]
    header = [cells for cells, _ in parsed if not (cells and cells[0][0].isdigit())]
    if not data or not header:
        raise ValueError("unexpected JMA page layout: header or data rows missing")
    ncol = len(data[0])
    if any(len(cs) != ncol for cs in data):
        raise ValueError(f"unexpected JMA page layout: data rows of unequal length ({ncol} expected)")
    grid: list[list[str | None]] = [[None] * ncol for _ in header]
    for ri, cells in enumerate(header):
        col = 0
        for text, cs, rs in cells:
            while col < ncol and grid[ri][col] is not None:
                col += 1
            for dr in range(rs):
                for dc in range(cs):
                    if ri + dr < len(header) and col + dc < ncol:
                        grid[ri + dr][col + dc] = text
            col += cs
    label = []
    for i in range(ncol):
        g = grid[0][i] or ""
        sub = next((grid[r][i] for r in range(1, len(header)) if grid[r][i] and grid[r][i] != g), "")
        label.append(f"{g}/{sub}")            # rowspan echoes the group into lower rows: skip it
    t_mean_i = next(i for i, lb in enumerate(label) if lb.startswith("気温") and lb.endswith("/平均"))
    snow_i = next(i for i, lb in enumerate(label) if lb.startswith("雪") and lb.endswith("/降雪"))
    t_mean: list[float | None] = [None] * 31
    snow: list[float | None] = [None] * 31
    for cs in data:
        day = int(cs[0][0])
        if not 1 <= day <= 31:
            continue
        t_mean[day - 1] = _value(cs, t_mean_i)
        snow[day - 1] = _value(cs, snow_i)
    return {"t_mean": t_mean[:max(int(cs[0][0]) for cs in data)],
            "snow": snow[:max(int(cs[0][0]) for cs in data)],
            "days": len(data)}


def fetch_month(year: int, month: int, delay: float = DELAY_S) -> dict:
    """Fetch and parse one month; retry once, then give up (the caller records the gap)."""
    url = URL.format(prec=PREC_NO, block=BLOCK_NO, year=year, month=month)
    for attempt in (1, 2):
        try:
            return parse_month(_get(url))
        except Exception as e:                              # noqa: BLE001 - report and retry once
            if attempt == 2:
                raise RuntimeError(f"JMA {year}-{month:02d}: {e}") from e
            time.sleep(2 * delay)
    raise RuntimeError("unreachable")


def year_csv(year: int) -> Path:
    return CACHE_DIR / f"sapporo_{BLOCK_NO}_daily_{year}.csv"


def fetch_year(year: int, delay: float = DELAY_S, force: bool = False) -> Path:
    """Fetch 12 months of daily data and write one tidy CSV per year; skips an existing file."""
    out = year_csv(year)
    if out.exists() and not force:
        return out
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fmt = lambda v: "" if v is None else f"{v:g}"          # noqa: E731 - a None prints as empty
    lines = ["month,day,t_mean_c,snow_cm"]
    t_missing = 0
    for month in range(1, 13):
        d = fetch_month(year, month, delay)
        for i, (t, s) in enumerate(zip(d["t_mean"], d["snow"])):
            lines.append(f"{month},{i + 1},{fmt(t)},{fmt(s)}")
        t_missing += sum(v is None for v in d["t_mean"])
        time.sleep(delay)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def fetch_years(start: int, end: int, delay: float = DELAY_S, force: bool = False) -> list[Path]:
    return [fetch_year(y, delay, force) for y in range(start, end + 1)]


@dataclass(frozen=True)
class WeatherYear:
    """One year of weather at daily resolution, with the monthly aggregates the model runs on."""
    year: int
    t_day: tuple[float, ...]        # daily mean temperature (C), 365 or 366 entries
    snow_day: tuple[float, ...]     # daily snowfall (cm)
    t_month: tuple[float, ...]      # monthly mean temperature (C)
    snow_month: tuple[float, ...]   # monthly snowfall totals (cm)

    @classmethod
    def from_daily(cls, year: int, t_day, snow_day) -> WeatherYear:
        """Monthly means and totals from daily series (calendar-true month lengths, leap years included)."""
        t_day, snow_day = tuple(t_day), tuple(snow_day)
        t_month, snow_month, i = [], [], 0
        for m in range(12):
            n = monthrange(year, m + 1)[1]
            t_month.append(sum(t_day[i:i + n]) / n)
            snow_month.append(sum(snow_day[i:i + n]))
            i += n
        if i != len(t_day) or i != len(snow_day):
            raise ValueError(f"{year}: the daily series ({len(t_day)}/{len(snow_day)} days) "
                             f"does not match the calendar ({i} days)")
        return cls(year, t_day, snow_day, tuple(t_month), tuple(snow_month))

    def weights(self, profile: str) -> tuple[float, ...]:
        """The profile's unnormalized daily demand weights implied by this year's weather."""
        if profile == "snow":
            return self.snow_day
        if profile == "flat":
            return tuple(1.0 for _ in self.t_day)
        base = 15.0 if profile == "greenhouse" else 18.0
        w = [max(0.0, base - t) for t in self.t_day]
        if profile == "school":
            i = 0
            for m in range(12):
                n = monthrange(self.year, m + 1)[1]
                if m == 7:
                    w[i:i + n] = [0.3 * v for v in w[i:i + n]]     # the August break
                i += n
        if profile == "pool":
            s = sum(w) or 1.0
            w = [0.5 / len(w) + 0.5 * v / s for v in w]
        return tuple(w)

    @property
    def hdd18(self) -> float:
        return sum(max(0.0, 18.0 - t) for t in self.t_day)

    @property
    def hdd15(self) -> float:
        return sum(max(0.0, 15.0 - t) for t in self.t_day)

    @property
    def hdd18_index(self) -> float:
        return self.hdd18 / HDD18_N

    @property
    def hdd15_index(self) -> float:
        return self.hdd15 / HDD15_N

    @property
    def snow_index(self) -> float:
        return sum(self.snow_day) / SNOW_N

    def scale(self, profile: str) -> float:
        """How much of this kind's annual demand the year asks for, relative to the normals year."""
        if profile == "building" or profile == "school":
            return self.hdd18_index
        if profile == "greenhouse":
            return self.hdd15_index
        if profile == "pool":
            return 0.5 + 0.5 * self.hdd18_index
        if profile == "snow":
            return self.snow_index
        return 1.0                                        # flat

    def shares(self, profile: str) -> tuple[float, ...]:
        """The year's monthly shares (they sum to 1), from its daily weather."""
        if profile == "flat":
            return _norm(DAYS)
        w = self.weights(profile)
        out, i = [], 0
        for m in range(12):
            n = monthrange(self.year, m + 1)[1]
            out.append(sum(w[i:i + n]))
            i += n
        return _norm(out)

    def daily_peak_mw(self, kind: str, annual_mwh: float) -> float | None:
        """The design-day demand (MW) implied by the year's daily weather, or None for kinds whose
        peak stays monthly: snow-melting is a multi-day process and flat kinds have no peak day.

        The model does not use this yet: with the all-or-nothing pipe-size convention (a pipe
        must carry the user's full peak or the user stays off), sizing for the worst day of 50
        years while mean-built plans keep their own mild sizing makes cross-plan comparisons
        apples-to-oranges. It becomes usable when the deliverable capacity is tied to the BUILT
        pipe size instead of alpha x the scenario peak."""
        profile = KINDS[kind][2]
        if profile not in ("building", "school", "greenhouse", "pool"):
            return None
        w = self.weights(profile)
        return annual_mwh * max(w) / sum(w) / 24.0        # the worst day's mean power

    def monthly_demand(self, kind: str, annual_mwh: float) -> np.ndarray:
        """The year's monthly demand (MWh) of one user of this kind with the normals-year annual demand."""
        profile = KINDS[kind][2]
        return np.array([annual_mwh * self.scale(profile) * s for s in self.shares(profile)])


def weather_year_from_csv(year: int, path: Path) -> WeatherYear:
    """One WeatherYear from a tidy daily CSV: monthly mean temperature, monthly snowfall total."""
    t_day, snow_day = [], []
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        month, _day, temp, snow = line.split(",")
        if not temp:
            raise ValueError(f"{path}: missing daily mean temperature (row: {line})")
        t_day.append(float(temp))
        snow_day.append(float(snow) if snow else 0.0)  # a missing snow day is a snow-free day
    return WeatherYear.from_daily(year, t_day, snow_day)


def load_years(start: int, end: int) -> list[WeatherYear]:
    """The cached weather years; run fetch_years first (or `python -m dcopt.heat.weather`)."""
    return [weather_year_from_csv(year, year_csv(year)) for year in range(start, end + 1)]


def validate_normals(years: list[WeatherYear], span: tuple[int, int] = (1991, 2020)) -> dict:
    """Check the fetched data three ways: the monthly means/totals against v1's sourced constants
    (TEMP, SNOW, the JMA normals page), and the daily degree-day/snowfall sums against this
    module's climatology constants (HDD18_N, HDD15_N, SNOW_N). Small convention offsets are
    expected; anything beyond 1.5 C, 20 % of the season's snowfall or 3 % of the daily constants
    fails the check."""
    lo, hi = span
    sel = [w for w in years if lo <= w.year <= hi]
    if len(sel) != hi - lo + 1:
        return {"years": len(sel), "ok": False, "note": f"need every year {lo}-{hi}"}
    t = np.mean([[v for v in w.t_month] for w in sel], axis=0)
    s = np.mean([[v for v in w.snow_month] for w in sel], axis=0)
    dt = float(np.max(np.abs(t - np.array(TEMP))))
    ds = float(np.max(np.abs(s - np.array(SNOW))))
    n18 = float(np.mean([w.hdd18 for w in sel]))
    n15 = float(np.mean([w.hdd15 for w in sel]))
    ns = float(np.mean([sum(w.snow_day) for w in sel]))
    dn = max(abs(n18 - HDD18_N) / HDD18_N, abs(n15 - HDD15_N) / HDD15_N, abs(ns - SNOW_N) / SNOW_N)
    ok = dt <= 1.5 and ds <= 0.2 * float(sum(SNOW)) and dn <= 0.03
    return {"years": len(sel), "ok": bool(ok), "max_abs_temp_c": round(dt, 2), "max_abs_snow_cm": round(ds, 2),
            "daily_constants_dev": round(dn, 4),
            "temp_norm": [round(v, 1) for v in t], "snow_norm": [round(v, 1) for v in s]}


if __name__ == "__main__":
    import sys
    a, b = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (1976, 2025)
    fetch_years(a, b)
    print(validate_normals(load_years(a, b)) if a <= 1991 and b >= 2020 else "fetched; normals not in range")
