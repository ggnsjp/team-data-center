"""Synthetic area records in the layout of the operator's monthly files, for tests without a network.

Not collected by pytest (the file name does not start with test_); test modules import it. The
numbers are made up: a daily demand curve, a solar bell with cloudy days, wind as a slow random
walk, and coal covering what is left above a floor (below it, solar is curtailed).
"""
from __future__ import annotations

import calendar
from pathlib import Path

import numpy as np

from dcopt.matching import records

OLD = ["エリア需要", "原子力", "火力(LNG)", "火力(石炭)", "火力(石油)", "火力(その他)", "水力", "地熱", "バイオマス",
       "太陽光発電実績", "太陽光出力制御量", "風力発電実績", "風力出力制御量", "揚水", "蓄電池", "連系線", "その他", "合計"]
NEW = OLD[:6] + ["火力出力制御量"] + OLD[6:9] + ["バイオマス出力制御量"] + OLD[9:]
FLOOR = 500


def month_csv(year: int, month: int, seed: int = 0, new_layout: bool = False) -> bytes:
    rng = np.random.default_rng(seed * 10_000 + year * 100 + month)
    days = calendar.monthrange(year, month)[1]
    n = days * 48
    hour = np.tile(np.arange(48) / 2.0, days)
    winter = 0.5 * (1 + np.cos(2 * np.pi * (month - 1) / 12))                      # 1 in January, 0 in July
    demand = 3100 + 600 * winter + 450 * np.cos(2 * np.pi * (hour - 18) / 24) + rng.normal(0, 40, n)
    sky = np.repeat(rng.uniform(0.15, 1.0, days), 48)
    solar = 2000 * (0.45 + 0.55 * (1 - winter)) * sky * np.clip(np.sin(np.pi * (hour - 5.5) / 13), 0, None) ** 1.5
    walk = np.cumsum(rng.normal(0, 0.06, n))
    wind = 1000 * np.clip(0.35 + 0.3 * np.sin(walk) + 0.2 * np.sin(walk / 3 + 1), 0, 1)
    cols = {c: np.zeros(n) for c in NEW}
    cols["水力"], cols["地熱"], cols["バイオマス"] = np.full(n, 400.0), np.full(n, 15.0), np.full(n, 250.0)
    cols["火力(LNG)"], cols["火力(石油)"], cols["火力(その他)"] = np.full(n, 120.0), np.full(n, 60.0), np.full(n, 180.0)
    cols["連系線"], cols["蓄電池"] = np.full(n, -80.0), np.full(n, -2.0)
    cols["エリア需要"] = np.round(demand)
    cols["風力発電実績"] = np.round(wind)
    rest = cols["エリア需要"] - sum(cols[c] for c in NEW if c not in ("エリア需要", "合計", "火力(石炭)", "太陽光発電実績"))
    need = rest - np.round(solar)                                # what coal has to cover
    low = FLOOR - 360                                            # coal's share of the thermal floor
    cut = np.clip(low - need, 0, np.round(solar))                # curtail solar where coal would go below it
    cols["太陽光出力制御量"] = cut
    cols["太陽光発電実績"] = np.round(solar) - cut
    cols["火力(石炭)"] = rest - cols["太陽光発電実績"]
    cols["合計"] = cols["エリア需要"]
    names = NEW if new_layout else OLD
    lines = ["単位[MW平均],,,供給力" + "," * (len(names) - 2), "DATE,TIME," + ",".join(names)]
    for i in range(n):
        d, s = divmod(i, 48)
        lines.append(f"{year:04d}/{month:02d}/{d + 1:02d},{s // 2:02d}:{30 * (s % 2):02d},"
                     + ",".join(str(int(cols[c][i])) for c in names))
    return ("\r\n".join(lines) + "\r\n").encode("cp932")


def write_year(folder: Path, fy: int, seed: int = 0) -> None:
    """The twelve monthly files of a fiscal year, written where records.DIR points in the test."""
    folder.mkdir(parents=True, exist_ok=True)
    for y, m in records.fiscal_year(fy):
        (folder / records.month_path(y, m).name).write_bytes(month_csv(y, m, seed, new_layout=(y, m) >= (fy + 1, 1)))
