"""Draw the animated README figure: heat flowing from the data centers to their users, month by month.

Inputs (not committed, rebuilt by scripts):
  out/heat_story/base.json          base map from scripts/export_heat_story.py (OpenStreetMap, ODbL)
  out/heat_network_v2/plans.json    model v2 plans from scripts/export_heat_network_v2.py
Output: docs/img/heat-network-map.gif (and a still, docs/img/heat-network.png)

Run: uv run python scripts/render_readme_animation.py [--plan expected|robust]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.patches import Polygon, Rectangle  # noqa: E402
from PIL import Image  # noqa: E402

from dcopt.heat.v1 import SNOW  # noqa: E402  JMA normals 1991-2020, Sapporo: monthly snowfall (cm)

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "out" / "heat_story" / "base.json"
PLANS = ROOT / "out" / "heat_network_v2" / "plans.json"
OUT = ROOT / "docs" / "img"

W_PX, H_PX, DPI = 1000, 620, 100
C = {"night": "#0b1020", "land": "#121a2b", "sea": "#0b1626", "river": "#123049", "coast": "#2a4766",
     "road": "#7d8aa6", "city": "#46536e", "label": "#8792aa", "ink": "#e8ecf4", "ink2": "#aab3c5",
     "muted": "#6f7a91", "heat": "#ffc46b", "heat_deep": "#ff7a45", "core": "#fff4e0", "bar": "#2c3650"}
GROUP = {"greenhouse": "farm", "new_greenhouse": "farm", "aquaculture": "farm", "hospital": "building",
         "public": "building", "hotel": "building", "factory": "building",
         "school": "building", "pool": "building", "onsen": "building", "snow": "snow"}
GROUP_COLOR = {"farm": "#0ca30c", "building": "#d55181", "snow": "#3987e5"}
GROUP_LABEL = {"farm": "Greenhouses, fish farm", "building": "Buildings: public, pools, schools, hotels", "snow": "Snow melting"}
DN_WIDTH = {50: 1.8, 80: 2.2, 100: 2.6, 150: 3.4, 200: 4.2, 250: 5.0}
# Label offsets in km from each data center, chosen so the four labels do not overlap.
LABEL_AT = {"zed": (0.14, 0.13, "left"), "isrd1": (-0.16, 0.04, "right"), "sakura": (0.16, -0.12, "left"),
            "nttme": (0.10, -0.20, "left")}
KIND_WORDS = {"public": ("a public building", "public buildings"), "hotel": ("a hotel", "hotels"),
              "factory": ("a factory", "factories"), "pool": ("a pool", "pools"), "school": ("a school", "schools"), "hospital": ("a hospital", "hospitals"),
              "onsen": ("a bath", "baths"), "aquaculture": ("a fish farm", "fish farms"),
              "greenhouse": ("a greenhouse", "greenhouses"), "new_greenhouse": ("a new greenhouse", "new greenhouses"),
              "snow": ("road heating", "road heating")}
DC_LABEL = {"isrd1": "No. 1", "sakura": "Sakura", "zed": "ZED", "nttme": "NTT-ME (planned)"}
MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
               "October", "November", "December"]


def decode(seq: list[int], ext: list[float], scale: int) -> np.ndarray:
    pts = np.cumsum(np.array(seq, dtype=float).reshape(-1, 2), axis=0) / scale
    return pts + np.array(ext[:2])


class Proj:
    def __init__(self, lon0: float, lat0: float):
        self.lon0, self.lat0, self.kx = lon0, lat0, 111.32 * math.cos(math.radians(lat0))

    def __call__(self, lon, lat):
        return (np.asarray(lon) - self.lon0) * self.kx, (np.asarray(lat) - self.lat0) * 110.57


def view_box(plan: dict, dcs: list[dict], pr: Proj, aspect: float) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for p in plan["pipes"]:
        x, y = pr(*np.array(p["path"]).T)
        xs += list(x); ys += list(y)
    for s in plan["sites"]:
        if s["dc"]:
            x, y = pr(s["lon"], s["lat"]); xs.append(float(x)); ys.append(float(y))
    for d in dcs:
        x, y = pr(d["lon"], d["lat"]); xs.append(float(x)); ys.append(float(y))
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    # The network fills the area right of the text panel: x from 43 % to 97 % of the width, y from 9 % to 93 %.
    w, h = max(x1 - x0, 0.5) / 0.54, max(y1 - y0, 0.5) / 0.84
    if w / h < aspect:
        w = h * aspect
    else:
        h = w / aspect
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    vx0, vy0 = cx - 0.70 * w, cy - 0.51 * h
    return vx0, vx0 + w, vy0, vy0 + h


def draw_base(ax, base: list[dict], pr: Proj) -> None:
    meta = next(r for r in base if r["layer"] == "meta")
    ext, scale = meta["extent"], meta["scale"]
    for r in base:
        layer = r["layer"]
        if layer in ("sea", "river"):
            for ring in r["rings"]:
                pts = decode(ring, ext, scale)
                x, y = pr(pts[:, 0], pts[:, 1])
                ax.add_patch(Polygon(np.c_[x, y], closed=True, lw=0, fc=C[layer], zorder=1))
        elif layer in ("road", "coast", "city"):
            segs = []
            for line in r["lines"]:
                pts = decode(line, ext, scale)
                x, y = pr(pts[:, 0], pts[:, 1])
                segs.append(np.c_[x, y])
            if layer == "road":
                k = r["class"]
                ax.add_collection(LineCollection(segs, colors=C["road"], linewidths=[0.25, 0.4, 0.6, 0.9, 1.2][k],
                                                 alpha=[0.16, 0.22, 0.3, 0.42, 0.5][k], zorder=2))
            elif layer == "coast":
                ax.add_collection(LineCollection(segs, colors=C["coast"], linewidths=0.8, zorder=2))
            else:
                ax.add_collection(LineCollection(segs, colors=C["city"], linewidths=0.8, linestyles=(0, (4, 3)),
                                                 zorder=2))
    for r in base:
        if r["layer"] == "label":
            x, y = pr(r["lon"], r["lat"])
            style = "italic" if r["kind"] in ("water", "sea") else "normal"
            ax.text(float(x), float(y), r["en"], color=C["label"], fontsize=8.5, ha="center", va="center",
                    style=style, alpha=0.85, zorder=3, clip_on=True)


def cumlen(xy: np.ndarray) -> np.ndarray:
    return np.r_[0.0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]


def point_at(xy: np.ndarray, cl: np.ndarray, s: np.ndarray) -> np.ndarray:
    return np.c_[np.interp(s, cl, xy[:, 0]), np.interp(s, cl, xy[:, 1])]


def main() -> None:
    global W_PX, H_PX, DPI, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="expected", choices=["expected", "robust", "current"])
    ap.add_argument("--frames", type=int, default=12, help="frames per month")
    ap.add_argument("--width", type=int, default=W_PX, help="pixels; 1920 with --height 1080 --dpi 192 for slides")
    ap.add_argument("--height", type=int, default=H_PX)
    ap.add_argument("--dpi", type=int, default=DPI)
    ap.add_argument("--out", default=str(OUT), help="folder for heat-network.gif and .png")
    args = ap.parse_args()
    W_PX, H_PX, DPI, OUT = args.width, args.height, args.dpi, Path(args.out)
    base = json.loads(BASE.read_text(encoding="utf-8"))
    data = json.loads(PLANS.read_text(encoding="utf-8"))
    plan, dcs = data["plans"][args.plan], data["dcs"]
    pr = Proj(141.30, 43.17)
    aspect = W_PX / H_PX
    x0, x1, y0, y1 = view_box(plan, dcs, pr, aspect)

    # The static base map, drawn once.
    fig = plt.figure(figsize=(W_PX / DPI, H_PX / DPI), dpi=DPI)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal"); ax.axis("off")
    fig.patch.set_facecolor(C["land"]); ax.set_facecolor(C["land"])
    draw_base(ax, base, pr)
    fig.canvas.draw()
    background = np.asarray(fig.canvas.buffer_rgba()).copy()
    plt.close(fig)

    pipes = []
    for p in plan["pipes"]:
        x, y = pr(*np.array(p["path"]).T)
        xy = np.c_[x, y]
        pipes.append({"xy": xy, "cl": cumlen(xy), "dn": p["dn"], "monthly": np.array(p["monthly"], float)})
    peak = max(float(p["monthly"].max()) for p in pipes) or 1.0
    delivered = np.array(plan["delivered_month"], float)
    waste = np.array(plan["waste_month"], float)
    sites = plan["sites"]
    active = {s["dc"] for s in sites if s["dc"]}
    counts: dict[str, int] = {}
    for s in sites:
        if s["dc"]:
            counts[s["kind"]] = counts.get(s["kind"], 0) + 1
    words = [(KIND_WORDS[k][1] if n > 1 else KIND_WORDS[k][0]) if n < 3 or k == "snow" else f"{n} {KIND_WORDS[k][1]}"
             for k, n in sorted(counts.items(), key=lambda kv: -kv[1])]
    if len(words) > 4:                                                 # many kinds: name the three largest groups
        reach = f"{sum(counts.values())} sites\n" + ", ".join(words[:3]) + " and more"
    else:
        reach = ", ".join(words[:-1]) + " and " + words[-1] if len(words) > 1 else words[0]
    rng = np.random.default_rng(7)
    for p in pipes:
        p["phase"], p["pos"] = rng.uniform(0, 0.2), 0.0
    n_flakes = 900                                                   # snow drifting down the map in winter
    flakes = np.c_[rng.uniform(x0, x1, n_flakes), rng.uniform(y0, y1, n_flakes)]
    flake_v = rng.uniform(0.012, 0.035, n_flakes) * (x1 - x0) / 10
    flake_s = rng.uniform(1.5, 6.0, n_flakes) * (DPI / 100) ** 2
    snow_max = float(max(SNOW))

    frames: list[Image.Image] = []
    n_per = args.frames
    total = 12 * n_per
    for i in range(total):
        m, f = divmod(i, n_per)
        prev = (m - 1) % 12
        w = min(1.0, f / max(1, n_per // 3))                      # ease into the new month
        w = 0.5 - 0.5 * math.cos(math.pi * w)
        fig = plt.figure(figsize=(W_PX / DPI, H_PX / DPI), dpi=DPI)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.imshow(background, extent=(x0, x1, y0, y1), origin="upper", zorder=0)
        ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal"); ax.axis("off")
        sc = (DPI / 100) ** 2                                       # marker areas scale with resolution

        # Season: snow cover and falling snow follow the month's snowfall.
        snow_k = ((1 - w) * SNOW[prev] + w * SNOW[m]) / snow_max
        if snow_k > 0.01:
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, color="#dfe8f6", alpha=0.13 * snow_k, lw=0, zorder=1))
        flakes[:, 1] -= flake_v
        flakes[:, 0] += 0.004 * (x1 - x0) / 10 * np.sin(i / 6 + np.arange(n_flakes))
        wrap = flakes[:, 1] < y0
        flakes[wrap, 1] = y1
        flakes[wrap, 0] = rng.uniform(x0, x1, int(wrap.sum()))
        n_on = int(n_flakes * snow_k)
        if n_on:
            ax.scatter(flakes[:n_on, 0], flakes[:n_on, 1], s=flake_s[:n_on], c="#f2f6fc", alpha=0.6, lw=0, zorder=4)

        # Heat: brightness, width, particle size and speed all follow the month's flow in each pipe.
        for p in pipes:
            flow = (1 - w) * p["monthly"][prev] + w * p["monthly"][m]
            k = flow / peak
            kk = math.sqrt(k)
            lw = DN_WIDTH.get(p["dn"], 2.0) * DPI / 100
            ax.plot(p["xy"][:, 0], p["xy"][:, 1], color=C["heat"], lw=lw * 0.55, alpha=0.55,
                    solid_capstyle="round", zorder=5)                  # the pipe itself, every month
            for width, alpha in ((lw * (2.5 + 5 * k), 0.09), (lw * (1.4 + 1.8 * k), 0.24), (lw, 1.0)):
                ax.plot(p["xy"][:, 0], p["xy"][:, 1], color=C["heat_deep"] if width > lw else C["heat"],
                        lw=width, alpha=alpha * (0.2 + 0.8 * kk), solid_capstyle="round", zorder=5)
            L = p["cl"][-1]
            p["pos"] += (0.003 + 0.12 * k) * (x1 - x0) / 10            # km per frame
            if L > 0 and k > 0.003:
                spacing = 0.13 * (x1 - x0) / 10
                n = max(1, int(L / spacing))
                s = (p["phase"] + p["pos"] + np.arange(n) * spacing) % L
                pts = point_at(p["xy"], p["cl"], s)
                ax.scatter(pts[:, 0], pts[:, 1], s=(3 + 40 * k) * sc, c=C["core"], alpha=0.15 + 0.85 * kk, lw=0,
                           zorder=6)

        for st in sites:
            x, y = pr(st["lon"], st["lat"])
            g = GROUP.get(st["kind"], "building")
            size = (18 + 140 * math.sqrt(st["annual"] / 5000)) * sc
            if st["dc"]:
                own_peak = max(st["served"]) or 1                   # each site pulses with its own season
                share = ((1 - w) * st["served"][prev] + w * st["served"][m]) / own_peak
                ax.scatter([x], [y], s=size * (1.0 + 4.0 * share), c=GROUP_COLOR[g], alpha=0.06 + 0.26 * share, lw=0,
                           zorder=7)
                if st["assumed"]:
                    ax.scatter([x], [y], s=size, facecolors="none", edgecolors=GROUP_COLOR[g], lw=1.8 * DPI / 100,
                               alpha=0.35 + 0.65 * share, zorder=8)
                else:
                    ax.scatter([x], [y], s=size, c=GROUP_COLOR[g], edgecolors=C["core"], lw=0.6 * DPI / 100,
                               alpha=0.4 + 0.6 * share, zorder=8)
            else:
                ax.scatter([x], [y], s=10 * sc, c=GROUP_COLOR[g], alpha=0.35, lw=0, zorder=4)

        for d in dcs:
            x, y = pr(d["lon"], d["lat"])
            planned = d["status"] != "operating"
            ax.scatter([x], [y], s=520, c=C["heat"], alpha=0.12 if not planned else 0.05, lw=0, zorder=9)
            ax.scatter([x], [y], s=70, marker="s", c="none" if planned else C["core"],
                       edgecolors=C["heat"], lw=1.4, linestyle="--" if planned else "-", zorder=10)
            dx, dy, ha = LABEL_AT.get(d["key"], (0.15, 0.12, "left"))
            ax.text(float(x) + dx, float(y) + dy, DC_LABEL.get(d["key"], d["key"]), fontsize=8.5, ha=ha, va="center",
                    color=C["ink"] if d["key"] in active else C["muted"], zorder=11,
                    bbox=dict(boxstyle="round,pad=0.2", fc=C["night"], ec="none", alpha=0.75))

        # Text panel on the left, legend box on the right.
        fig.patches.append(Rectangle((0, 0), 0.40, 1, transform=fig.transFigure, color=C["night"], alpha=0.62,
                                     zorder=1))
        tx = 0.025
        fig.text(tx, 0.94, "Waste heat from Ishikari's data centers", color=C["ink"], fontsize=15, weight="bold")
        first, _, rest = reach.partition("\n")
        fig.text(tx, 0.905, f"One shared network to {first}, month by month", color=C["ink2"], fontsize=9.5)
        if rest:
            fig.text(tx, 0.875, rest[0].upper() + rest[1:], color=C["ink2"], fontsize=9.5)
        fig.text(tx, 0.80, MONTHS_LONG[m], color=C["heat"], fontsize=26, weight="bold")
        fig.text(tx, 0.755, f"Sapporo normals: {data['temp'][m]:+.1f} °C, {SNOW[m]} cm of snow",
                 color=C["ink2"], fontsize=9)
        fig.text(tx, 0.70, f"Heat delivered  {delivered[m]:,.0f} MWh", color=C["ink"], fontsize=11)
        used = delivered[m] / waste[m] if waste[m] else 0
        fig.text(tx, 0.665, f"Share of available waste heat used  {used:.0%}", color=C["ink2"], fontsize=9.5)

        # Monthly bars at the bottom left.
        bx, by, bw, bh = 0.025, 0.12, 0.30, 0.16
        bar_ax = fig.add_axes([bx, by, bw, bh])
        bar_ax.set_facecolor("none")
        bar_ax.set_zorder(2)
        colors = [C["heat"] if j == m else C["bar"] for j in range(12)]
        bar_ax.bar(range(12), delivered, color=colors, width=0.72)
        bar_ax.set_xticks(range(12), [s[0] for s in data["months"]], color=C["muted"], fontsize=7.5)
        bar_ax.set_yticks([])
        for sp in bar_ax.spines.values():
            sp.set_visible(False)
        bar_ax.tick_params(length=0)
        fig.text(bx, by + bh + 0.012, "Heat delivered per month (MWh)", color=C["ink2"], fontsize=8.5)

        # Legend at the bottom right.
        lx, ly = 0.025, 0.56
        fig.text(lx, ly + 0.04, "Legend", color=C["ink2"], fontsize=8.5, weight="bold")
        for j, (g, label) in enumerate(GROUP_LABEL.items()):
            yy = ly - 0.035 * j
            fig.text(lx, yy, "●", color=GROUP_COLOR[g], fontsize=10)
            fig.text(lx + 0.022, yy, label, color=C["ink2"], fontsize=8.5)
        yy = ly - 0.035 * 3
        fig.text(lx, yy, "○ assumed site   ■ data center   □ planned", color=C["ink2"], fontsize=8.5)
        fig.text(lx, yy - 0.035, "Line width: pipe size DN80 to DN250", color=C["ink2"], fontsize=8.5)

        fig.text(0.5, 0.04, f"Model v2: {plan['label']}, heat pumps included. Climate: JMA normals 1991-2020.",
                 color=C["muted"], fontsize=7.5,
                 ha="center")
        fig.text(0.5, 0.016, "Some sites and data-center positions are assumptions or placeholders.  "
                 "Map data © OpenStreetMap contributors (ODbL).",
                 color=C["muted"], fontsize=7.5, ha="center")
        fig.canvas.draw()
        img = Image.frombuffer("RGBA", fig.canvas.get_width_height(), fig.canvas.buffer_rgba(), "raw", "RGBA", 0, 1)
        frames.append(img.convert("RGB"))
        plt.close(fig)

    OUT.mkdir(parents=True, exist_ok=True)
    frames[n_per - 1].save(OUT / "heat-network.png", optimize=True)
    sample = Image.new("RGB", (W_PX, H_PX * 4 + 80))
    for j, idx in enumerate([n_per - 1, 3 * n_per - 1, 6 * n_per - 1, 9 * n_per - 1]):
        sample.paste(frames[idx], (0, H_PX * j))
    keys = [C["heat"], C["heat_deep"], C["core"], C["ink"], C["ink2"], *GROUP_COLOR.values(), "#f2f6fc"]
    for j, hexc in enumerate(keys):                          # key colours keep palette entries of their own
        sample.paste(Image.new("RGB", (60, 80), hexc), (j * 60, H_PX * 4))
    palette = sample.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pal_frames = [fr.quantize(palette=palette, dither=Image.Dither.NONE) for fr in frames]
    durations = [90] * len(pal_frames)
    pal_frames[0].save(OUT / "heat-network-map.gif", save_all=True, append_images=pal_frames[1:], duration=durations,
                       loop=0, optimize=True, disposal=1)
    print("wrote", OUT / "heat-network-map.gif", f"{(OUT / 'heat-network-map.gif').stat().st_size / 1e6:.1f} MB,",
          len(frames), "frames")


if __name__ == "__main__":
    main()
