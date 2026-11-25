"""The area supply-and-demand records of Hokkaido Electric Power Network: 30-minute values.

The operator publishes one CSV file per month from April 2024: the mean power in MW over each
30-minute slot, at the sending end, for the area demand and for each kind of supply. The files are
downloaded into data/cache/hepco_area/ (which git ignores) and are not part of this repository;
data/register.toml names the terms. Earlier years exist as hourly values in another layout and are
not read here.

Signs, as the columns add up to the area demand: pumped storage and batteries are positive when
they generate and negative when they charge; the interconnection is positive when the area imports.
The curtailed columns (output that solar, wind, biomass or thermal plants were told not to produce)
are not part of the sum.

Download: uv run python -m dcopt.matching.records 2024 2025      (fiscal years, April to March)
"""
from __future__ import annotations

import csv
import io
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from dcopt.common.geo import CACHE

PAGE = "https://www.hepco.co.jp/network/con_service/public_document/supply_demand_results/index.html"
URL = ("https://www.hepco.co.jp/network/con_service/public_document/supply_demand_results/csv/"
       "eria_jukyu_{y:04d}{m:02d}_01.csv")
SOURCE = ("北海道電力ネットワーク「北海道エリアの需給実績」 / Hokkaido Electric Power Network, "
          f"area supply and demand records: {PAGE}")
DIR = CACHE / "hepco_area"
FIRST = (2024, 4)            # the first month published as 30-minute values
SLOT_H = 0.5                 # hours in one slot
SLOTS_PER_DAY = 48
TIMEOUT_S = 30.0

# column heading in the files -> name used here (all in MW, mean over the slot)
NAMES = {
    "エリア需要": "demand", "原子力": "nuclear",
    "火力(LNG)": "lng", "火力(石炭)": "coal", "火力(石油)": "oil", "火力(その他)": "thermal_other",
    "火力出力制御量": "thermal_curtailed",
    "水力": "hydro", "地熱": "geothermal",
    "バイオマス": "biomass", "バイオマス出力制御量": "biomass_curtailed",
    "太陽光発電実績": "solar", "太陽光出力制御量": "solar_curtailed",
    "風力発電実績": "wind", "風力出力制御量": "wind_curtailed",
    "揚水": "pumped", "蓄電池": "battery", "連系線": "interconnection", "その他": "other", "合計": "total",
}
THERMAL = ["lng", "coal", "oil", "thermal_other"]
# the kinds of supply that add up to the area demand
SUPPLY = ["nuclear", *THERMAL, "hydro", "geothermal", "biomass", "solar", "wind",
          "pumped", "battery", "interconnection", "other"]
CURTAILED = ["solar_curtailed", "wind_curtailed", "biomass_curtailed", "thermal_curtailed"]
COLUMNS = ["demand", *SUPPLY, *CURTAILED, "total"]


def month_path(y: int, m: int) -> Path:
    return DIR / f"eria_jukyu_{y:04d}{m:02d}_01.csv"


def fiscal_year(fy: int) -> list[tuple[int, int]]:
    """The twelve months of a Japanese fiscal year: April of `fy` to March of the next year."""
    return [(fy, m) for m in range(4, 13)] + [(fy + 1, m) for m in range(1, 4)]


def read_month(raw: bytes | str) -> pd.DataFrame:
    """One monthly file as a table indexed by the start of each slot (Japan time), columns COLUMNS.

    Columns are found by their headings, so the two curtailment columns added in April 2026 and any
    change of order are handled; a column the file does not have is zero. Raises ValueError when
    the text is not one of these files.
    """
    text = raw.decode("cp932") if isinstance(raw, bytes) else raw
    rows = list(csv.reader(io.StringIO(text)))
    head = next((i for i, r in enumerate(rows) if r and r[0].strip() == "DATE"), None)
    if head is None:
        raise ValueError("no DATE heading: not a 30-minute area record file")
    cols = [c.strip() for c in rows[head]]
    unknown = [c for c in cols[2:] if c and c not in NAMES]
    if unknown:
        raise ValueError(f"unknown columns {unknown}: the layout has changed, update NAMES")
    body = [r for r in rows[head + 1:] if len(r) >= len(cols) and r[0].strip()]
    if not body:
        raise ValueError("no data rows")
    stamp = pd.to_datetime([f"{r[0].strip()} {r[1].strip()}" for r in body], format="%Y/%m/%d %H:%M")
    out = pd.DataFrame(0.0, index=stamp, columns=COLUMNS)
    for j, c in enumerate(cols):
        if c in NAMES:
            out[NAMES[c]] = np.array([float(r[j]) if r[j].strip() else np.nan for r in body])
    out.index.name = "slot"
    return out


def ensure_month(y: int, m: int, timeout: float = TIMEOUT_S) -> Path | None:
    """The cached file of a month, downloaded once. None when it is neither cached nor downloadable
    (offline, a month not published yet); nothing is raised."""
    path = month_path(y, m)
    if path.exists():
        return path
    if (y, m) < FIRST:
        return None
    try:
        req = urllib.request.Request(URL.format(y=y, m=m), headers={"User-Agent": "team-data-center"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        read_month(raw)                                  # only a file that reads is kept
    except (OSError, ValueError):
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(raw)
    tmp.replace(path)
    return path


def fetch_command(fy: int) -> str:
    return f"uv run python -m dcopt.matching.records {fy}"


def load(months: list[tuple[int, int]], download: bool = True) -> pd.DataFrame:
    """The records of the given months, in time order. FileNotFoundError names the months that are
    missing and the command that downloads them."""
    paths, missing = [], []
    for y, m in months:
        p = ensure_month(y, m) if download else (month_path(y, m) if month_path(y, m).exists() else None)
        (paths if p else missing).append(p or (y, m))
    if missing:
        names = ", ".join(f"{y}-{m:02d}" for y, m in missing)
        raise FileNotFoundError(f"area records not available for {names}. Download them with: "
                                f"{fetch_command(months[0][0] if months[0][1] >= 4 else months[0][0] - 1)}")
    return pd.concat([read_month(p.read_bytes()) for p in paths]).sort_index()


def load_fiscal_year(fy: int, download: bool = True) -> pd.DataFrame:
    return load(fiscal_year(fy), download=download)


def cached_fiscal_years() -> list[int]:
    """Fiscal years whose twelve months are all in the cache."""
    if not DIR.exists():
        return []
    have = {p.name[11:17] for p in DIR.glob("eria_jukyu_*_01.csv")}
    years = sorted({int(k[:4]) - (int(k[4:]) < 4) for k in have})
    return [fy for fy in years if all(f"{y:04d}{m:02d}" in have for y, m in fiscal_year(fy))]


def thermal(df: pd.DataFrame) -> pd.Series:
    return df[THERMAL].sum(axis=1)


def curtailed_renewable(df: pd.DataFrame) -> pd.Series:
    """Solar and wind output that was curtailed, MW."""
    return df["solar_curtailed"] + df["wind_curtailed"]


def check(df: pd.DataFrame) -> dict:
    """What a reader should know before trusting a table: its span, gaps and how well it adds up."""
    step = pd.Series(df.index).diff().dropna()
    gap = (df[SUPPLY].sum(axis=1) - df["demand"]).abs()
    return {
        "first": df.index[0], "last": df.index[-1], "slots": len(df),
        "expected_slots": round((df.index[-1] - df.index[0]).total_seconds() / 3600 / SLOT_H) + 1,
        "irregular_steps": int((step != pd.Timedelta(hours=SLOT_H)).sum()),
        "missing_values": int(df[["demand", *SUPPLY]].isna().sum().sum()),
        "max_imbalance_mw": float(gap.max()),          # rounding in the published integers
        "slots_off_by_more_than_2mw": int((gap > 2).sum()),
    }


def energy_gwh(series: pd.Series | np.ndarray) -> float:
    """MW per slot -> GWh over the whole table."""
    return float(np.nansum(np.asarray(series, dtype=float)) * SLOT_H / 1000.0)


def main(argv: list[str]) -> int:
    years = [int(a) for a in argv] or [2024, 2025]
    bad = 0
    for fy in years:
        got = 0
        for y, m in fiscal_year(fy):
            fresh = not month_path(y, m).exists()
            ok = ensure_month(y, m) is not None
            got += ok
            if ok and fresh:
                time.sleep(0.5)                          # be gentle with the operator's server
        print(f"fiscal year {fy}: {got}/12 months in {DIR}")
        bad += got < 12
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
