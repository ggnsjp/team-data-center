"""Theme 4 figure for the README: one week slot by slot, and the same year counted three ways.

Drawn from the 30-minute area records (downloaded on first use), for a constant load and a contract
for exactly its yearly use with the area's solar and wind mix. Every number in the figure is computed
here by dcopt.matching.

Run: uv run python scripts/render_matching_figure.py [--lang ja] [--fy 2025] [--mw 100]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from render_readme_animation import C, use_japanese_fonts

from dcopt.matching import records, score, system

ROOT = Path(__file__).resolve().parents[1]
MATCH, OTHER, CONTRACT = "#4cc9f0", "#33405f", "#ffc46b"
W_PX, H_PX, DPI = 1000, 500, 100

TEXT = {
    "en": {
        "title": "The same year, counted three ways",
        "sub": "A data center drawing a constant {mw:.0f} MW, with a solar and wind contract for exactly its yearly use.\n"
               "Hokkaido area, fiscal year {fy}, 30-minute records.",
        "week": "The week with the lowest match: {a} to {b} ({share:.0f} % matched)",
        "legend": ["matched in the same slot", "supplied by other plants", "output of the contract"],
        "bars": "Share of its electricity that is renewable",
        "rows": ["By the year", "By the 30-minute slot", "On the grid:\nexisting plants", "On the grid:\nnew plants built"],
        "note": "On the grid: 1 minus the extra thermal generation per unit of energy used, in a replay of the records.\n"
                "Data: Hokkaido Electric Power Network, area supply and demand records. Estimates.",
        "date": "%b %-d", "out": "renewable-matching.png",
    },
    "ja": {
        "title": "同じ1年を、3つの数え方で",
        "sub": "一定の {mw:.0f} MW を使うデータセンターが、年間の使用量と同じ量の太陽光・風力を契約した場合。\n"
               "北海道エリア、{fy}年度、30分ごとの需給実績。",
        "week": "一致がいちばん低い週：{a}〜{b}（一致 {share:.0f} %）",
        "legend": ["同じコマに届いた再エネ", "ほかの電源が賄った分", "契約の発電量"],
        "bars": "使った電力のうち再エネと言える割合",
        "rows": ["年間の量で数える", "30分ごとに数える", "系統で数える：\n既存の発電所から買う", "系統で数える：\n新しい発電所を建てる"],
        "note": "系統で数える：実績をなぞる再計算で、1 −（増えた火力の発電量 ÷ 使用量）。\n"
                "データ：北海道電力ネットワーク「北海道エリアの需給実績」。数値は試算です。",
        "date": "%-m/%-d", "out": "renewable-matching-ja.png",
    },
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=["en", "ja"], default="en")
    ap.add_argument("--fy", type=int, default=2025)
    ap.add_argument("--mw", type=float, default=100.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    t = TEXT[args.lang]
    if args.lang == "ja":
        use_japanese_fonts()
    else:
        plt.rcParams["font.family"] = "DejaVu Sans"

    df = records.load_fiscal_year(args.fy)
    n = len(df)
    load = score.flat_load(n, args.mw)
    gen = score.contracted(df, load, 1.0)
    got = np.minimum(load, gen)
    sc = score.score(load, gen)
    existing = 1.0 - system.replay(df, load, 0.0).thermal_per_added_load
    new = 1.0 - system.replay(df, load, gen).thermal_per_added_load
    days = n // 48
    week = np.convolve(got.reshape(days, 48).sum(axis=1), np.ones(7), mode="valid")
    d0 = int(np.argmin(week))
    sl = slice(d0 * 48, (d0 + 7) * 48)
    idx = df.index[sl]

    fig = plt.figure(figsize=(W_PX / DPI, H_PX / DPI), dpi=DPI)
    fig.patch.set_facecolor(C["land"])
    fig.text(0.035, 0.925, t["title"], color=C["ink"], fontsize=17, fontweight="bold", va="center")
    fig.text(0.035, 0.835, t["sub"].format(mw=args.mw, fy=args.fy), color=C["ink2"], fontsize=9.5, va="center",
             linespacing=1.5)

    ax = fig.add_axes([0.065, 0.2, 0.555, 0.46])
    ax.set_facecolor(C["land"])
    x = mdates.date2num(idx.to_pydatetime())
    ax.fill_between(x, 0, got[sl], step="post", color=MATCH, lw=0)
    ax.fill_between(x, got[sl], load[sl], step="post", color=OTHER, lw=0)
    ax.step(x, gen[sl], where="post", color=CONTRACT, lw=1.6)
    ax.set_xlim(x[0], x[-1] + 1 / 48)
    ax.set_ylim(0, max(1.05 * gen[sl].max(), 1.6 * args.mw))
    ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter(t["date"]))
    ax.tick_params(colors=C["ink2"], labelsize=8.5, length=0)
    ax.set_ylabel("MW", color=C["ink2"], fontsize=9)
    ax.grid(axis="y", color=C["bar"], lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(C["muted"])
    share = 100 * got[sl].sum() / load[sl].sum()
    fig.text(0.065, 0.75, t["week"].format(a=f"{idx[0]:{t['date']}}", b=f"{idx[-1]:{t['date']}}", share=share),
             color=C["ink"], fontsize=10.5, va="center")
    handles = [plt.Rectangle((0, 0), 1, 1, color=MATCH), plt.Rectangle((0, 0), 1, 1, color=OTHER),
               plt.Line2D([0], [0], color=CONTRACT, lw=2)]
    leg = ax.legend(handles, t["legend"], loc="upper left", bbox_to_anchor=(-0.01, 1.15), ncol=3, frameon=False,
                    fontsize=8.5, handlelength=1.3, columnspacing=1.4, borderaxespad=0)
    for txt in leg.get_texts():
        txt.set_color(C["ink2"])

    bx = fig.add_axes([0.79, 0.2, 0.14, 0.46])
    bx.set_facecolor(C["land"])
    vals = [min(sc.volume, 1.0), sc.matched, existing, new]
    ys = np.arange(len(vals))[::-1]
    bx.barh(ys, [1.0] * len(vals), height=0.5, color=C["bar"], lw=0)
    bx.barh(ys, vals, height=0.5, color=[CONTRACT, MATCH, MATCH, MATCH], lw=0)
    for y, v in zip(ys, vals):
        bx.text(1.04, y, f"{100 * v:.0f} %", color=C["ink"], fontsize=11.5, va="center", ha="left")
    bx.set_yticks(ys)
    bx.set_yticklabels(t["rows"], color=C["ink"], fontsize=9, linespacing=1.3)
    bx.set_xlim(0, 1)
    bx.set_xticks([])
    bx.tick_params(length=0, pad=6)
    for side in ("top", "right", "left", "bottom"):
        bx.spines[side].set_visible(False)
    fig.text(0.655, 0.75, t["bars"], color=C["ink"], fontsize=10.5, va="center")
    fig.text(0.035, 0.07, t["note"], color=C["muted"], fontsize=8, va="center", linespacing=1.5)

    out = Path(args.out) if args.out else ROOT / "docs" / "img" / t["out"]
    fig.savefig(out, dpi=DPI, facecolor=fig.get_facecolor())
    print(f"{out}  by year {100 * sc.volume:.0f} %, by slot {100 * sc.matched:.1f} %, "
          f"existing plants {100 * existing:.1f} %, new plants {100 * new:.1f} %; week from {idx[0].date()} ({share:.0f} %)")


if __name__ == "__main__":
    main()
