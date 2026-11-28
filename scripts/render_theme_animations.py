"""Draw the animated README figures of themes 2 and 3 on the map of Ishikari.

  --theme grid     The transmission lines and substations around the data centers, one voltage class
                   after another, and beside the map the hosting-capacity bracket of one bus of a
                   public test system (there is no network model of this grid yet).
  --theme siting   The siting screen: a new data center tried at every candidate site, the pipe
                   networks of the three best sites, and the grid connection of the best one.

Inputs (not committed; rebuilt or downloaded by scripts):
  out/heat_story/base.json              base map from scripts/export_heat_story.py (OpenStreetMap, ODbL)
  out/heat_network_v2/plans.json        the data centers, from scripts/export_heat_network_v2.py
  out/siting/siting.json, networks.json candidate sites, values and pipe networks, from scripts/export_siting.py
  data/cache/ishikari/power.geojson     power lines and substations (OpenStreetMap), downloaded on first use
  data/cache/pglib                      the IEEE 118-bus system (PGLib-OPF, CC BY 4.0), downloaded on first use
  results/grid_hosting/case*.csv        optional, from experiments/grid_hosting/run.py: the count over all buses
Output: docs/img/grid-hosting-map.gif and docs/img/siting-map.gif; with --lang ja the names end in -ja
(needs a Japanese font, e.g. Noto Sans CJK JP). --stills also writes every frame the animation
holds on as a PNG, and --scale 3 draws at three times the size. For print, --bare draws only those
frames, as maps without the text panel (PNG only, no gif), at the --size given.

Run: uv run python scripts/render_theme_animations.py --theme grid|siting [--lang en|ja] [--stills] [--scale 3]
     uv run python scripts/render_theme_animations.py --theme siting --bare --size 800x620 --scale 6 --out /tmp/print
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.patches import Circle, Polygon, Rectangle
from PIL import Image
from render_readme_animation import DC_LABEL, DN_WIDTH, JA, LABEL_AT, C, Proj, cumlen, decode, use_japanese_fonts

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "out" / "heat_story" / "base.json"
PLANS = ROOT / "out" / "heat_network_v2" / "plans.json"
SITING = ROOT / "out" / "siting" / "siting.json"
NETWORKS = ROOT / "out" / "siting" / "networks.json"
HOSTING = ROOT / "results" / "grid_hosting"
OUT = ROOT / "docs" / "img"

W_PX, H_PX, DPI = 1000, 620, 100         # --scale multiplies all three; sizes in points keep their share of the picture
FX, FY = (0.43, 0.97), (0.09, 0.93)        # the part of the canvas the map content may use; the text panel covers the left
TX = 0.025                                 # left margin of the text panel, as a share of the width
BARE = False                               # --bare: maps for print, only the frames the animation holds on
NEW = "#5fe1ff"                            # a new data center, its pipes and the sites it serves
QUIET = "#c9d1e8"                          # context that is not the subject of a figure
KV = {66000: ("#4cc9f0", 1.3), 187000: ("#f472b6", 2.3), 275000: ("#ffb347", 3.6)}   # colour and line width by voltage class;
# lines that carry two classes on the same towers are drawn in both, the higher class underneath
STATION_EN = {"石狩変電所": "Ishikari substation", "西札幌変電所": "Nishi-Sapporo substation", "篠路変電所": "Shinoro substation",
              "石狩湾新港発電所": "Ishikari Bay New Port power station (LNG)"}
STATION_AT = {"石狩変電所": (0.35, 0.30, "left"), "西札幌変電所": (0.40, -0.05, "left"), "篠路変電所": (-0.40, 0.35, "right"),
              "石狩湾新港発電所": (0.35, 0.50, "left")}            # label offsets in km, chosen so that the labels stay apart
TEST_CASE, TEST_BUS = "case118_ieee", 58                           # the bus the README reports (bus "59")


def ease(t: float) -> float:
    return 0.5 - 0.5 * math.cos(math.pi * min(1.0, max(0.0, t)))


def view_for(xs, ys, pad: float = 0.0) -> np.ndarray:
    """The view (x0, x1, y0, y1 in km) that shows the points in the free part of the canvas."""
    x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
    w, h = (x1 - x0) / (FX[1] - FX[0]), (y1 - y0) / (FY[1] - FY[0])
    if w / h < W_PX / H_PX:
        w = h * W_PX / H_PX
    else:
        h = w * H_PX / W_PX
    vx0 = (x0 + x1) / 2 - (FX[0] + FX[1]) / 2 * w
    vy0 = (y0 + y1) / 2 - (FY[0] + FY[1]) / 2 * h
    return np.array([vx0, vx0 + w, vy0, vy0 + h])


def between(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    """A view on the way from a to b. The width changes by equal factors, so the zoom looks even."""
    wa, wb = a[1] - a[0], b[1] - b[0]
    w = wa * (wb / wa) ** t
    s = (w - wa) / (wb - wa) if abs(wb - wa) > 1e-9 else t
    x0, y0 = a[0] + (b[0] - a[0]) * s, a[2] + (b[2] - a[2]) * s
    return np.array([x0, x0 + w, y0, y0 + w * H_PX / W_PX])


class BaseMap:
    """The base map of the theme-1 figure as arrays in km, so that it can be drawn at any zoom."""

    def __init__(self, records: list[dict], pr: Proj, keep: np.ndarray):
        meta = next(r for r in records if r["layer"] == "meta")
        ext, scale = meta["extent"], meta["scale"]

        def km(seq) -> np.ndarray:
            pts = decode(seq, ext, scale)
            x, y = pr(pts[:, 0], pts[:, 1])
            return np.c_[x, y]

        def inside(xy: np.ndarray) -> bool:
            return bool(xy[:, 0].max() >= keep[0] and xy[:, 0].min() <= keep[1]
                        and xy[:, 1].max() >= keep[2] and xy[:, 1].min() <= keep[3])

        self.fills, self.roads, self.coast, self.city, self.labels = [], {}, [], [], []
        for r in records:
            layer = r["layer"]
            if layer in ("sea", "river"):
                self.fills += [(layer, km(ring)) for ring in r["rings"]]
            elif layer == "road":
                self.roads[r["class"]] = [s for s in map(km, r["lines"]) if inside(s)]
            elif layer in ("coast", "city"):
                setattr(self, layer, [s for s in map(km, r["lines"]) if inside(s)])
            elif layer == "label":
                x, y = pr(r["lon"], r["lat"])
                self.labels.append((float(x), float(y), r))

    def draw(self, ax, px_per_km: float, lang: str, names: tuple[str, ...]) -> None:
        k = min(1.0, px_per_km / 100)                                 # 1 at the scale of the theme-1 figure
        for layer, xy in self.fills:
            ax.add_patch(Polygon(xy, closed=True, lw=0, fc=C[layer], zorder=1))
        for c, segs in self.roads.items():
            fade = k ** (1.6 if c < 2 else 0.5)                       # small streets fade when the map is zoomed out
            ax.add_collection(LineCollection(segs, colors=C["road"], linewidths=[0.25, 0.4, 0.6, 0.9, 1.2][c] * (0.55 + 0.45 * k),
                                             alpha=[0.16, 0.22, 0.3, 0.42, 0.5][c] * fade, zorder=2))
        ax.add_collection(LineCollection(self.coast, colors=C["coast"], linewidths=0.8, zorder=2))
        ax.add_collection(LineCollection(self.city, colors=C["city"], linewidths=0.8, linestyles=(0, (4, 3)), zorder=2))
        for x, y, r in self.labels:
            if r["en"] in names:
                ax.text(x, y, r["ja"] if lang == "ja" else r["en"], color=C["label"], fontsize=8.5, ha="center", va="center",
                        style="italic" if r["kind"] in ("water", "sea") else "normal", alpha=0.85, zorder=3, clip_on=True)


class Stage:
    """Collects frames: each one is the base map at a view, with whatever the caller draws on top."""

    def __init__(self, base: BaseMap, lang: str, names: tuple[str, ...]):
        self.base, self.lang, self.names = base, lang, names
        self.frames: list[Image.Image] = []
        self.ms: list[int] = []
        self._cache: dict[tuple, np.ndarray] = {}

    def _figure(self, view: np.ndarray):
        fig = plt.figure(figsize=(W_PX / DPI, H_PX / DPI), dpi=DPI)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(view[0], view[1]); ax.set_ylim(view[2], view[3]); ax.set_aspect("equal"); ax.axis("off")
        fig.patch.set_facecolor(C["land"]); ax.set_facecolor(C["land"])
        return fig, ax

    def open(self, view: np.ndarray, names: tuple[str, ...] | None = None):
        names = self.names if names is None else names
        key = (*np.round(view, 4), names)
        if key not in self._cache:
            fig, ax = self._figure(view)
            self.base.draw(ax, W_PX / (DPI / 100) / (view[1] - view[0]), self.lang, names)
            fig.canvas.draw()
            self._cache[key] = np.asarray(fig.canvas.buffer_rgba()).copy()
            plt.close(fig)
        fig, ax = self._figure(view)
        ax.imshow(self._cache[key], extent=tuple(view), origin="upper", zorder=0)
        ax.set_xlim(view[0], view[1]); ax.set_ylim(view[2], view[3])
        return fig, ax

    def close(self, fig, ms: int) -> None:
        fig.canvas.draw()
        img = Image.frombuffer("RGBA", fig.canvas.get_width_height(), fig.canvas.buffer_rgba(), "raw", "RGBA", 0, 1)
        self.frames.append(img.convert("RGB"))
        self.ms.append(ms)
        plt.close(fig)

    def save(self, gif: Path, keys: list[str], stills: bool) -> None:
        gif.parent.mkdir(parents=True, exist_ok=True)
        if not BARE:
            picks = [self.frames[i] for i in np.linspace(0, len(self.frames) - 1, 6).astype(int)]
            sample = Image.new("RGB", (W_PX, H_PX * len(picks) + 80))    # frames and swatches the palette is built from
            for j, f in enumerate(picks):
                sample.paste(f, (0, H_PX * j))
            for j, hexc in enumerate(keys):                            # key colours keep palette entries of their own
                sample.paste(Image.new("RGB", (60, 80), hexc), (j * 60, H_PX * len(picks)))
            palette = sample.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
            pal = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in self.frames]
            pal[0].save(gif, save_all=True, append_images=pal[1:], duration=self.ms, loop=0, optimize=True, disposal=1)
            print("wrote", gif, f"{gif.stat().st_size / 1e6:.1f} MB,", len(self.frames), "frames,", f"{sum(self.ms) / 1000:.1f} s")
        if stills or BARE:
            held = [f for f, ms in zip(self.frames, self.ms) if ms >= 1000]
            for k, f in enumerate(held, start=1):
                f.save(gif.with_name(f"{gif.stem}-{k}.png"), optimize=True)
            print("wrote", len(held), "stills next to it")


def panel(fig, title: str, sub: list[str]) -> None:
    fig.patches.append(Rectangle((0, 0), 0.40, 1, transform=fig.transFigure, color=C["night"], alpha=0.86, zorder=1))
    fig.text(TX, 0.938, title, color=C["ink"], fontsize=14.2, weight="bold")
    for i, s in enumerate(sub):
        fig.text(TX, 0.900 - 0.031 * i, s, color=C["ink2"], fontsize=9.2)


def rows(fig, y: float, items: list[tuple], x: float = TX) -> float:
    """Lines of text from y downwards: (text, size, colour[, weight]). Returns the y below the last line."""
    for it in items:
        fig.text(x, y, it[0], color=it[2], fontsize=it[1], weight=it[3] if len(it) > 3 else "normal", va="top")
        y -= 1.62 * it[1] / (H_PX / DPI * 72)
    return y


def footer(fig, a: str, b: str) -> None:
    fig.text(0.5, 0.040, a, color=C["muted"], fontsize=7.3, ha="center")
    fig.text(0.5, 0.016, b, color=C["muted"], fontsize=7.3, ha="center")


def tag(ax, x: float, y: float, text: str, color: str = C["ink"], size: float = 8.5, ha: str = "left", weight: str = "normal"):
    ax.text(x, y, text, fontsize=size, ha=ha, va="center", color=color, weight=weight, zorder=12,
            bbox={"boxstyle": "round,pad=0.22", "fc": C["night"], "ec": "none", "alpha": 0.80})


def data_centers(ax, dcs: list[dict], pr: Proj, z: float, edge: str = C["heat"]) -> None:
    for d in dcs:
        x, y = pr(d["lon"], d["lat"])
        planned = d["status"] != "operating"
        ax.scatter([x], [y], s=420 * z * z, c=edge, alpha=0.05 if planned else 0.11, lw=0, zorder=9)
        ax.scatter([x], [y], s=62 * z * z, marker="s", c="none" if planned else C["core"], edgecolors=edge, lw=1.3,
                   linestyle="--" if planned else "-", zorder=10)


# ----------------------------------------------------------------------------------- theme 3: siting
def siting(records: list[dict], lang: str) -> Stage:
    ja = lang == "ja"
    data = json.loads(SITING.read_text(encoding="utf-8"))
    nets = json.loads(NETWORKS.read_text(encoding="utf-8"))
    key = f"{nets['mw']:g}"
    pr = Proj(141.30, 43.17)
    cands, users, dcs = data["candidates"], data["users"], data["data_centers"]
    for c in cands:
        c["x"], c["y"] = (float(v) for v in pr(c["lon"], c["lat"]))
        c["v"] = c["by_mw"][key]["value"] / 1e6
    by_id = {c["id"]: c for c in cands}
    vmax = max(c["v"] for c in cands)
    valued = sorted((c for c in cands if c["v"] > 0.005), key=lambda c: -c["v"])
    ux, uy = pr([u["lon"] for u in users], [u["lat"] for u in users])
    in_base = np.array([u["in_base_plan"] for u in users])

    def prepare(net: dict, root: int | None) -> None:
        for p in net["pipes"]:
            lon, lat = np.array(p["path"]).T
            p["xy"] = np.c_[pr(lon, lat)]
            p["cl"] = cumlen(p["xy"])
            p["off"] = 0.0
        if root is None:
            return
        reach, todo = {root: 0.0}, [p for p in net["pipes"] if p["new_heat"]]
        while todo:                                    # distance from the new data center to the start of each of its pipes
            ready = [p for p in todo if p["from"] in reach]
            if not ready:
                break
            for p in ready:
                p["off"] = reach[p["from"]]
                reach.setdefault(p["to"], p["off"] + float(p["cl"][-1]))
                todo.remove(p)
        net["reach"] = max((p["off"] + float(p["cl"][-1]) for p in net["pipes"] if p["new_heat"]), default=0.0)

    prepare(nets["base"], None)
    best = sorted(nets["sites"], key=lambda s: -s["value_in_export"])
    for s in best:
        prepare(s, s["sources"] - 1)
        c = by_id[s["id"]]
        if abs(s["value"] - s["value_in_export"]) > 0.05e6 or s["sites"] != c["by_mw"][key]["sites"]:
            print(f"note: the network of {s['id']} is not the plan behind the exported value; run export_siting.py --networks-only")
    subs = [s for s in (data.get("power") or {}).get("substations", []) if not s["generation"]]
    for s in subs:
        s["x"], s["y"] = (float(v) for v in pr(s["lon"], s["lat"]))
    top = by_id[best[0]["id"]]
    link = min((s for s in subs if s["kv"] >= 66000), key=lambda s: math.hypot(s["x"] - top["x"], s["y"] - top["y"]), default=None)

    dx, dy = pr([d["lon"] for d in dcs], [d["lat"] for d in dcs])
    wide = view_for([c["x"] for c in cands] + list(ux) + list(dx), [c["y"] for c in cands] + list(uy) + list(dy), pad=0.5)
    px, py = [], []
    for net in [nets["base"], *best]:
        for p in net["pipes"]:
            px += list(p["xy"][:, 0]); py += list(p["xy"][:, 1])
    px += list(dx) + [by_id[s["id"]]["x"] for s in best] + ([link["x"]] if link else [])
    py += list(dy) + [by_id[s["id"]]["y"] for s in best] + ([link["y"]] if link else [])
    close = view_for(px, py, pad=0.35)
    stage = Stage(BaseMap(records, pr, wide), lang, ())
    WIDE_NAMES, CLOSE_NAMES = ("Ishikari Bay", "Ishikari River", "Sapporo"), ("Ishikari Bay New Port", "Hanakawa")

    def label_spot(c: dict, net: dict) -> tuple[float, float, str]:
        """Where the label of the new data center has most room: the corner farthest from the pipes."""
        pts = np.vstack([np.c_[np.interp(np.arange(0, p["cl"][-1] + 0.05, 0.05), p["cl"], p["xy"][:, 0]),
                               np.interp(np.arange(0, p["cl"][-1] + 0.05, 0.05), p["cl"], p["xy"][:, 1])] for p in net["pipes"]])
        spots = [(-0.16, -0.22, "right"), (0.16, -0.22, "left"), (-0.16, 0.22, "right"), (0.16, 0.22, "left")]
        room = [np.hypot(pts[:, 0] - (c["x"] + ddx + (0.38 if ha == "left" else -0.38)), pts[:, 1] - (c["y"] + ddy)).min()
                if close[0] + 0.42 * (close[1] - close[0]) < c["x"] + ddx + (0.0 if ha == "left" else -0.85)
                and c["x"] + ddx + (0.85 if ha == "left" else 0.0) < close[1] - 0.1 else -1.0      # the label has to fit on the map
                for ddx, ddy, ha in spots]
        return spots[int(np.argmax(room))]

    from dcopt.siting.model import LINE_COST_M_YEN_KM, annuity
    # M yen a year per km of connection line: the middle of the published standard unit costs for a
    # two-circuit tower line, 66/77 kV class and 154/187 kV class (docs/input-evidence.md)
    line66, line187 = (annuity(0.03, 30) * LINE_COST_M_YEN_KM[k] for k in ("66", "187"))
    g66, g187 = top["grid_66"], top["grid_187"]
    solver = (nets.get("provenance") or {}).get("solver", "")
    T = {
        "title": "次のデータセンターをどこに建てるか" if ja else "Where should the next data center go?",
        "sub": ([f"{nets['mw']:g} MWの新しいデータセンターを、{len(cands)}か所の候補地で試します。", "そのつど、テーマ1の導管網モデルを解き直します。"] if ja else
                [f"A new {nets['mw']:g} MW data center is tried at {len(cands)} candidate sites.", "Each time, the heat network of theme 1 is solved again."]),
        "bars": "新設の排熱の価値（価値が出た候補地、百万円/年）" if ja else "Value of the new data center's heat, sites with value (M yen a year)",
        "legend": ([(NEW, "dot", "そこに新設したときの排熱の価値（面積）"), (C["heat"], "line", "既存のデータセンターの導管と需要家"),
                    (NEW, "line", "新設のデータセンターの導管と需要家"), (QUIET, "line", "送電線（66〜275 kV）と変電所 ◇")] if ja else
                   [(NEW, "dot", "value of a new data center's heat there (area)"), (C["heat"], "line", "pipes and users of the existing data centers"),
                    (NEW, "line", "pipes and users of the new data center"), (QUIET, "line", "transmission lines (66 to 275 kV), substations ◇")]),
        "foot": (("公開データと明示した仮定にもとづくモデルの推計値です。候補地は格子点で、用地の選定ではなく最初のふるい分けです。",
                  f"発見的な探索による下界（{'Gurobi' if solver == 'gurobi' else 'HiGHS'}で実行）。地図データ © OpenStreetMap contributors (ODbL)") if ja else
                 ("Model estimates from public data and stated assumptions. Candidate sites are grid points: a first screen, not a site search.",
                  f"Lower bounds from a heuristic search (run with {'Gurobi' if solver == 'gurobi' else 'HiGHS'}).  Map data © OpenStreetMap contributors (ODbL).")),
    }

    def man(v: float) -> str:                                          # M yen as 万円, to the 0.1 M yen the README reports
        return f"{round(v * 10) * 10:,}"

    def pipes(ax, net: dict, z: float, which: str, upto: float | None = None, alpha: float = 1.0) -> None:
        for p in net["pipes"]:
            new = bool(p.get("new_heat"))
            if (which == "new") != new and which != "all":
                continue
            xy = p["xy"]
            if upto is not None:
                d = upto - p["off"]
                if d <= 0:
                    continue
                if d < p["cl"][-1]:
                    i = int(np.searchsorted(p["cl"], d))
                    f = (d - p["cl"][i - 1]) / max(1e-9, p["cl"][i] - p["cl"][i - 1])
                    xy = np.vstack([xy[:i], xy[i - 1] + f * (xy[i] - xy[i - 1])])
            lw = DN_WIDTH.get(p["dn"], 2.0) * (0.45 + 0.55 * z)
            col, deep = (NEW, NEW) if new else (C["heat"], C["heat_deep"])
            ax.plot(xy[:, 0], xy[:, 1], color=deep, lw=lw * 3.0, alpha=0.17 * alpha, solid_capstyle="round", zorder=5)
            ax.plot(xy[:, 0], xy[:, 1], color=col, lw=lw, alpha=alpha, solid_capstyle="round", zorder=6)

    def heat_users(ax, z: float, connected: np.ndarray, new: np.ndarray, new_alpha: float = 1.0) -> None:
        rest = ~(connected | new)
        ax.scatter(ux[rest], uy[rest], s=9 * (0.5 + 0.5 * z), c=C["label"], alpha=0.55, lw=0, zorder=4)
        ax.scatter(ux[connected], uy[connected], s=34 * (0.4 + 0.6 * z), c=C["heat"], edgecolors=C["core"], lw=0.5, zorder=8)
        if new.any():
            ax.scatter(ux[new], uy[new], s=34 * (0.4 + 0.6 * z), c=NEW, edgecolors=C["core"], lw=0.5, alpha=new_alpha, zorder=8)

    def sites(ax, upto: int, current: dict | None = None, dim: float = 1.0, values: int = 0) -> None:
        for c in cands[:upto]:
            if c["v"] > 0.005:
                ax.scatter([c["x"]], [c["y"]], s=14 + 520 * c["v"] / vmax, c=NEW, alpha=0.50 * dim, edgecolors=C["core"], lw=0.6, zorder=7)
            else:
                ax.scatter([c["x"]], [c["y"]], s=11, facecolors="none", edgecolors=QUIET, lw=0.7, alpha=0.75 * dim, zorder=7)
        if current is not None:
            ax.scatter([current["x"]], [current["y"]], s=300, facecolors="none", edgecolors=C["core"], lw=1.6, zorder=11)
        for c in valued[:values]:
            tag(ax, c["x"] + 0.55, c["y"] + 0.45, f"{c['v']:.1f}", size=8.5)

    def grid_layer(ax, alpha: float) -> None:
        segs = {kv: [] for kv in KV}
        for ln in (data.get("power") or {}).get("lines", []):
            lon, lat = np.array(ln["path"]).T
            segs[ln["kv"]].append(np.c_[pr(lon, lat)])
        for kv, (_, lw) in KV.items():
            ax.add_collection(LineCollection(segs[kv], colors=QUIET, linewidths=lw * 0.75, alpha=0.75 * alpha, zorder=4))
        for s in subs:
            ax.scatter([s["x"]], [s["y"]], s=30, marker="D", c=C["night"], edgecolors=QUIET, lw=1.2, alpha=alpha, zorder=9)

    def bars(fig, shown: set, mark: str | None = None) -> None:
        ax = fig.add_axes([0.03, 0.115, 0.335, 0.175])
        ax.set_facecolor("none"); ax.set_zorder(2)
        cols = [C["core"] if c["id"] == mark else (NEW if c["id"] in shown else C["bar"]) for c in valued]
        ax.bar(range(len(valued)), [c["v"] for c in valued], color=cols, width=0.72)
        ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(False)
        fig.text(0.03, 0.115 + 0.175 + 0.012, T["bars"], color=C["ink2"], fontsize=8.3)

    def frame(view: np.ndarray, ms: int, head: str, head_col: str, body: list[tuple], draw, shown: set, mark: str | None = None,
              legend: int = 3) -> None:
        if BARE and ms < 1000:
            return
        scale = W_PX / (DPI / 100) / (view[1] - view[0])                 # pixels per km at the standard size
        fig, ax = stage.open(view, CLOSE_NAMES if scale > 75 else WIDE_NAMES if scale < 40 else ())
        z = min(1.0, scale / 100)
        draw(ax, z)
        data_centers(ax, dcs, pr, max(z, 0.55))
        if BARE:
            stage.close(fig, ms)
            return
        panel(fig, T["title"], T["sub"])
        fig.text(TX, 0.775, head, color=head_col, fontsize=20, weight="bold")
        rows(fig, 0.745, body)
        for j, (col, kind, text) in enumerate(T["legend"][:legend]):
            y = 0.475 - 0.034 * j
            if kind == "dot":
                fig.text(TX, y, "●", color=col, fontsize=10)
            else:
                fig.add_artist(plt.Line2D([TX, TX + 0.019], [y + 0.009, y + 0.009], transform=fig.transFigure, color=col, lw=2.6, zorder=3))
            fig.text(TX + 0.026, y, text, color=C["ink2"], fontsize=8.4)
        bars(fig, shown, mark)
        footer(fig, *T["foot"])
        stage.close(fig, ms)

    base, none = nets["base"], np.zeros(len(users), bool)
    b = data["base"]
    today = ("現在の計画" if ja else "Today's plan", C["heat"],
             [(f"{b['sites']}か所、導管{b['pipe_km']:.1f} km" if ja else f"{b['sites']} sites on {b['pipe_km']:.1f} km of pipe", 11, C["ink"]),
              (f"年{man(b['net'] / 1e6)}万円（純便益の期待値）" if ja else f"{b['net'] / 1e6:.1f} M yen a year (expected net benefit)", 9.5, C["ink2"])])

    def plan_today(ax, z):
        pipes(ax, base, z, "all")
        heat_users(ax, z, in_base, none)
        if BARE:                                                        # the print version names the data centers
            for d in dcs:
                x, y = pr(d["lon"], d["lat"])
                ddx, ddy, ha = LABEL_AT.get(d["key"], (0.15, 0.12, "left"))
                tag(ax, float(x) + ddx, float(y) + ddy, (JA["dc"] if ja else DC_LABEL).get(d["key"], d["key"]), size=8.5, ha=ha)

    frame(close, 1900, *today, plan_today, set(), legend=2)
    for i in range(7):                                                  # zoom out to all candidate sites
        frame(between(close, wide, ease((i + 1) / 7)), 80, *today, plan_today, set(), legend=2)
    seen: set = set()
    lead = None
    for i, c in enumerate(cands, start=1):                              # the sweep: one candidate site per frame
        seen.add(c["id"])
        lead = c if lead is None or c["v"] > lead["v"] else lead
        n = sum(1 for k in cands[:i] if k["v"] > 0.005)
        body = [(f"排熱に価値が出た候補地：{n}か所" if ja else f"Heat has value at {n} site{'s' if n != 1 else ''} so far", 11, C["ink"])]
        if lead["v"] > 0.005:
            body.append((f"これまでの最大：年{man(lead['v'])}万円（{lead['near']}付近）" if ja else
                         f"Best so far: {lead['v']:.1f} M yen a year (site {lead['id']})", 9.5, C["ink2"]))

        def sweep(ax, z, i=i, c=c):
            pipes(ax, base, z, "all", alpha=0.75)
            heat_users(ax, z, in_base, none)
            sites(ax, i, current=c)

        frame(wide, 70, f"{len(cands)}か所中 {i}か所目" if ja else f"Site {i} of {len(cands)}", NEW, body, sweep, set(seen))
    done = (f"{len(cands)}か所を評価" if ja else f"{len(cands)} sites tried", NEW,
            [(f"排熱に価値が出たのは{len(valued)}か所" if ja else f"The heat has value at {len(valued)} of them", 11, C["ink"]),
             (f"最大で年{man(vmax)}万円（現在の計画は年{man(b['net'] / 1e6)}万円）" if ja else
              f"up to {vmax:.1f} M yen a year on top of today's {b['net'] / 1e6:.1f}", 9.5, C["ink2"])])

    def swept(ax, z, labels=3):
        pipes(ax, base, z, "all", alpha=0.75)
        heat_users(ax, z, in_base, none)
        sites(ax, len(cands), values=labels)

    frame(wide, 1500, *done, swept, set(seen))
    for i in range(7):                                                  # zoom in on the best sites
        frame(between(wide, close, ease((i + 1) / 7)), 80, *done, lambda ax, z: swept(ax, z, 0), set(seen))
    ranks = ["1位", "2位", "3位"] if ja else ["Best site", "Second", "Third"]
    for k, s in enumerate(best):                                        # the networks of the three best sites
        c = by_id[s["id"]]
        connected = np.zeros(len(users), bool)
        new = np.zeros(len(users), bool)
        for u in s["users"]:
            (new if u["from_new"] else connected)[u["index"]] = True
        body = [(f"年＋{man(c['v'])}万円" if ja else f"+{c['v']:.1f} M yen a year", 13, C["ink"], "bold"),
                (f"新設から{s['sites_from_candidate']}か所へ熱を届けます。" if ja else
                 f"The new data center would supply {s['sites_from_candidate']} sites.", 9.5, C["ink2"]),
                (f"導管網の全体：{s['sites']}か所、{s['pipe_km']:.1f} km" if ja else
                 f"The whole network: {s['sites']} sites on {s['pipe_km']:.1f} km of pipe", 9.5, C["ink2"])]
        head = f"{ranks[k]}：{c['near']}付近" if ja else f"{ranks[k]}: {c['id']}"
        steps = 9
        for j in range(steps + 1):
            f = ease(j / steps)

            def grown(ax, z, s=s, c=c, f=f, connected=connected, new=new):
                sites(ax, len(cands), dim=0.22)
                pipes(ax, s, z, "old")
                pipes(ax, s, z, "new", upto=f * s["reach"] + 1e-6)
                heat_users(ax, z, connected, new, new_alpha=f)
                ax.scatter([c["x"]], [c["y"]], s=95, marker="s", c=NEW, edgecolors=C["core"], lw=1.2, zorder=11)
                ddx, ddy, ha = label_spot(c, s)
                tag(ax, c["x"] + ddx, c["y"] + ddy, "新設" if ja else "new data center", color=NEW, ha=ha, weight="bold")

            frame(close, 1500 if j == steps else 80, head, NEW, body, grown, set(seen), mark=c["id"])
    if link is not None:                                                # the grid connection of the best site
        s, c = best[0], top
        connected = np.zeros(len(users), bool)
        new = np.zeros(len(users), bool)
        for u in s["users"]:
            (new if u["from_new"] else connected)[u["index"]] = True
        cost66, cost187 = line66 * g66["substation_km"], line187 * g187["substation_km"]

        def left(cost: float) -> str:
            if c["v"] >= cost:
                return f"残り{man(c['v'] - cost)}万円" if ja else f"{c['v'] - cost:.1f} left"
            return "排熱の価値を超える" if ja else "above the heat value"

        body = [(f"66 kVまで{g66['substation_km']:.1f} km：接続線 年{man(cost66)}万円、{left(cost66)}" if ja else
                 f"66 kV substation, {g66['substation_km']:.1f} km: line {cost66:.1f} M yen/yr, {left(cost66)}", 9.8, C["ink"]),
                (f"187 kVまで{g187['substation_km']:.1f} km：接続線 年{man(cost187)}万円、{left(cost187)}" if ja else
                 f"187 kV, {g187['substation_km']:.1f} km: line {cost187:.1f} M yen/yr, {left(cost187)}", 9.5, C["ink2"]),
                ("接続線の単価は公表値の中央（4.1億円/km、5.1億円/km）。" if ja else
                 "Published unit costs, mid-range: 410, 510 M yen per km.", 8.6, C["muted"]),
                ("石狩の受け入れ余地はまだ計算できていません（テーマ2）。" if ja else
                 "There is no hosting capacity for Ishikari yet (theme 2).", 8.6, C["muted"])]
        steps = 5
        for j in range(steps + 1):
            a = ease(j / steps)

            def wired(ax, z, a=a, s=s, c=c, connected=connected, new=new):
                sites(ax, len(cands), dim=0.22)
                grid_layer(ax, a)
                pipes(ax, s, z, "all")
                heat_users(ax, z, connected, new)
                ax.scatter([c["x"]], [c["y"]], s=95, marker="s", c=NEW, edgecolors=C["core"], lw=1.2, zorder=11)
                ax.plot([c["x"], link["x"]], [c["y"], link["y"]], color=C["core"], lw=1.4, ls=(0, (4, 3)), alpha=a, zorder=10)
                if a > 0.99:
                    mx, my = (c["x"] + link["x"]) / 2, (c["y"] + link["y"]) / 2
                    tag(ax, mx + 0.14, my, f"{g66['substation_km']:.1f} km", size=8.5)
                    tag(ax, link["x"] + 0.16, link["y"] + 0.18, "66 kVの変電所" if ja else "66 kV substation", color=QUIET, size=8.0)

            frame(close, 3400 if j == steps else 90, "系統への接続" if ja else "Grid connection", C["ink"], body, wired, set(seen),
                  mark=c["id"], legend=4)
    return stage


# ------------------------------------------------------------------------------------- theme 2: grid
def grid(records: list[dict], lang: str) -> Stage:
    from shapely.geometry import Point

    from dcopt.grid import cases
    from dcopt.grid.hosting import hosting_capacity
    from dcopt.siting import gridmap

    ja = lang == "ja"
    power = gridmap.load_power()
    if power is None:
        raise SystemExit("the power lines could not be downloaded (data/cache/ishikari/power.geojson); try again later")
    import geopandas as gpd
    dcs = json.loads(PLANS.read_text(encoding="utf-8"))["dcs"]
    pr = Proj(141.30, 43.17)
    lon0, lat0 = float(np.mean([d["lon"] for d in dcs])), float(np.mean([d["lat"] for d in dcs]))
    cx, cy = (float(v) for v in pr(lon0, lat0))
    here = gpd.GeoSeries([Point(lon0, lat0)], crs=4326).to_crs(gridmap.METRIC_CRS).iloc[0]
    near = gridmap.connections(power, [(lon0, lat0)])[0]              # km to the nearest line of each class
    geo = power.to_crs(4326)
    stations = {}
    for i, r in power[(power["power"] == "substation") & (power["kv"] >= 66000)].iterrows():
        p = geo.geometry[i].representative_point()
        x, y = (float(v) for v in pr(p.x, p.y))
        stations[i] = {"name": r["name"] if isinstance(r["name"], str) else "", "kv": int(r["kv"]), "x": x, "y": y,
                       "plant": r.get("substation") == "generation", "km": float(r.geometry.distance(here)) / 1000}
    named = {s["name"]: s for s in stations.values() if s["name"] in STATION_AT}
    view = view_for([cx] + [s["x"] for s in named.values()], [cy] + [s["y"] for s in named.values()], pad=0.9)
    far = max(math.hypot(x - cx, y - cy) for x in view[:2] for y in view[2:])
    segs: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    wires = geo[geo["power"].isin(["line", "cable", "minor_line"])]
    for kv in KV:
        parts, dist = [], []
        for g, volts in zip(wires.geometry, wires["voltage"]):
            if kv not in {int(t) for t in str(volts).replace(",", ";").split(";") if t.strip().isdigit()}:
                continue
            for part in getattr(g, "geoms", [g]):
                lon, lat = np.array(part.coords).T
                xy = np.c_[pr(lon, lat)]
                d = np.hypot(xy[:, 0] - cx, xy[:, 1] - cy)
                for a in range(len(xy) - 1):
                    parts.append(xy[a:a + 2]); dist.append(max(d[a], d[a + 1]))
        segs[kv] = (np.array(parts), np.array(dist))
    h = hosting_capacity(cases.load(TEST_CASE), TEST_BUS, methods=("dc", "sdp", "ac"))
    total = above = 0
    for f in sorted(HOSTING.glob("case*.csv")):
        with f.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                total += 1
                above += bool(r["dc"] and r["upper"] and float(r["dc"]) > float(r["upper"]))
    stage = Stage(BaseMap(records, pr, view), lang, ("Sapporo", "Hanakawa"))

    def km(name: str) -> str:
        return f"{named[name]['km']:.1f}" if name in named else "?"

    T = {
        "title": "系統は新しい負荷をどれだけ受け入れられるか" if ja else "How much new load can the grid host?",
        "sub": (["テーマ2：交流の制約のもとで、母線が受け入れられる", "最大の負荷を、上と下からはさみます。"] if ja else
                ["Theme 2: the largest load a bus can take within the AC limits,", "bracketed from above and from below."]),
        "around": "石狩のデータセンター周辺の系統" if ja else "The grid around Ishikari's data centers",
        "kv": {66000: f"66 kV：石狩変電所まで{km('石狩変電所')} km" if ja else f"66 kV: Ishikari substation, {km('石狩変電所')} km away",
               187000: (f"187 kV：送電線まで{near['line_187_km']:.1f} km、西札幌変電所まで{km('西札幌変電所')} km" if ja else
                        f"187 kV: a line {near['line_187_km']:.1f} km away, a substation at {km('西札幌変電所')} km"),
               275000: (f"275 kV：送電線まで{near['line_275_km']:.1f} km、LNG火力発電所まで{km('石狩湾新港発電所')} km" if ja else
                        f"275 kV: a line {near['line_275_km']:.1f} km away, from the LNG plant at {km('石狩湾新港発電所')} km")},
        "ask": "ここに何MWつなげられるか" if ja else "How many megawatts can connect here?",
        "none": (["この系統の公開モデルは見つかっていません。", "石狩についての数字は、まだありません。"] if ja else
                 ["We found no public network model of this grid,", "so there is no number for Ishikari yet."]),
        "test": (f"手法の確認：公開の試験系統（IEEE 118母線系統、母線{h.bus}）" if ja else
                 f"The method on a public test system (IEEE 118-bus, bus {h.bus})"),
        "bars": (["DC潮流による簡易評価", "上限（半正定値緩和）", "下限（確認済みの交流の運転点）"] if ja else
                 ["DC screening", "Upper bound (semidefinite relaxation)", "Lower bound (checked AC operating point)"]),
        "between": (f"受け入れ余地は{h.ac:,.0f}〜{h.upper:,.0f} MWの間にあります。" if ja else
                    f"The capacity lies between {h.ac:,.0f} and {h.upper:,.0f} MW."),
        "count": ((f"{total}母線のうち{above}母線で、簡易評価が上限を超えました。" if ja else
                   f"DC screening is above the upper bound at {above} of {total} buses.") if total else ""),
        "dcs": "データセンター" if ja else "Data centers",
        "foot": (("送電線と変電所はOpenStreetMapの記載どおりで、系統運用者のデータとは照合していません。距離は4か所のデータセンターの中心から。",
                  "試験系統：PGLib-OPF（CC BY 4.0）。地図データ © OpenStreetMap contributors (ODbL)") if ja else
                 ("Lines and substations as mapped in OpenStreetMap, not checked against the grid operator's data. Distances from the middle of the four sites.",
                  "Test system: PGLib-OPF (CC BY 4.0).  Map data © OpenStreetMap contributors (ODbL).")),
    }
    order = [66000, 187000, 275000]

    def frame(ms: int, radius: dict, labels: bool = False, ask: float | None = None, grow: float | None = None,
              count: bool = False) -> None:
        if BARE and ms < 1000:
            return
        fig, ax = stage.open(view)
        for kv, r in radius.items():
            col, lw = KV[kv]
            parts, dist = segs[kv]
            on = parts[dist <= r] if len(parts) else parts
            over = 5.0 - kv / 1e6                                       # lower classes are drawn over higher ones
            ax.add_collection(LineCollection(on, colors=col, linewidths=lw + 4.0, alpha=0.13, capstyle="round", zorder=3.9))
            ax.add_collection(LineCollection(on, colors=col, linewidths=lw, alpha=1.0, capstyle="round", zorder=over))
            if r < far:
                ax.add_patch(Circle((cx, cy), r, fill=False, ec=col, lw=1.0, alpha=0.35, zorder=6))
            for s in stations.values():
                if s["kv"] == kv and math.hypot(s["x"] - cx, s["y"] - cy) <= r:
                    ax.scatter([s["x"]], [s["y"]], s=58 if s["plant"] else 40, marker="^" if s["plant"] else "D",
                               c=col if s["plant"] else C["night"], edgecolors=col, lw=1.5, zorder=9)
                    if s["name"] in named and (labels or r >= far):
                        ddx, ddy, ha = STATION_AT[s["name"]]
                        name = s["name"] if ja else STATION_EN[s["name"]]
                        tag(ax, s["x"] + ddx, s["y"] + ddy, f"{name}（{kv // 1000} kV）" if ja else f"{name}, {kv // 1000} kV", size=8.2, ha=ha)
        data_centers(ax, dcs, pr, 0.8, edge=C["core"])
        tag(ax, cx - 0.55, cy - 0.60, T["dcs"], size=8.6, ha="right", weight="bold")
        if ask is not None:
            ax.add_patch(Circle((cx, cy), 0.75 + 0.9 * ask, fill=False, ec=NEW, lw=2.0, alpha=0.9 * (1 - 0.75 * ask), zorder=10))
            ax.add_patch(Circle((cx, cy), 0.75, fill=False, ec=NEW, lw=1.6, alpha=0.9, zorder=10))
            tag(ax, cx + 0.95, cy - 0.75, "＋？MW" if ja else "+ ? MW", color=NEW, size=11.5, weight="bold")
        if BARE:
            stage.close(fig, ms)
            return
        panel(fig, T["title"], T["sub"])
        fig.text(TX, 0.795, T["around"], color=C["ink2"], fontsize=8.8, weight="bold")
        for j, kv in enumerate(order):
            if kv in radius:
                y = 0.757 - 0.035 * j
                fig.add_artist(plt.Line2D([TX, TX + 0.026], [y + 0.008, y + 0.008], transform=fig.transFigure, color=KV[kv][0],
                                          lw=KV[kv][1], zorder=3))
                fig.text(TX + 0.034, y, T["kv"][kv], color=C["ink"], fontsize=8.9)
        if ask is not None or grow is not None:
            fig.text(TX, 0.615, T["ask"], color=NEW, fontsize=12.5, weight="bold")
            rows(fig, 0.595, [(t, 9.2, C["ink2"]) for t in T["none"]])
        if grow is not None:
            fig.text(TX, 0.468, T["test"], color=C["ink2"], fontsize=8.6, weight="bold")
            bx = fig.add_axes([0.03, 0.215, 0.345, 0.24])
            bx.set_facecolor("none"); bx.set_zorder(2)
            vals = [h.dc, h.upper, h.ac]
            part = [min(1.0, grow / 0.4), min(1.0, max(0.0, (grow - 0.4) / 0.3)), min(1.0, max(0.0, (grow - 0.7) / 0.3))]
            style = [{"color": C["muted"]}, {"facecolor": "none", "edgecolor": C["ink"], "linewidth": 1.3}, {"color": C["ink"]}]
            for j in range(3):
                y = 2 - j
                if part[j] > 0:
                    bx.barh([y], [vals[j] * ease(part[j])], height=0.34, **style[j])
                    bx.text(vals[j] * ease(part[j]) + h.dc * 0.015, y, f"{vals[j]:,.0f} MW" if part[j] >= 1 else "", color=C["ink"],
                            fontsize=9, va="center")
                    bx.text(0, y + 0.40, T["bars"][j], color=C["ink2"], fontsize=8.2, va="center")
            bx.set_xlim(0, h.dc * 1.16); bx.set_ylim(-0.35, 2.72)
            bx.set_xticks([]); bx.set_yticks([])
            for sp in bx.spines.values():
                sp.set_visible(False)
            if grow >= 1:
                fig.text(TX, 0.172, T["between"], color=C["ink"], fontsize=9.6)
                if count and T["count"]:
                    fig.text(TX, 0.135, T["count"], color=C["ink2"], fontsize=9.0)
        footer(fig, *T["foot"])
        stage.close(fig, ms)

    frame(1500, {})
    shown: dict = {}
    for kv in order:                                                    # one voltage class after another, outwards from the data centers
        for j in range(1, 10):
            frame(80, {**shown, kv: far * ease(j / 9) ** 1.4 if j < 9 else far})
        shown[kv] = far
        frame(1300, dict(shown), labels=True)
    for j in range(4):
        frame(120, dict(shown), ask=j / 3)
    frame(1700, dict(shown), ask=0.0)
    for j in range(1, 13):
        frame(80, dict(shown), ask=0.0, grow=j / 12)
    frame(1600, dict(shown), ask=0.0, grow=1.0)
    frame(4200, dict(shown), ask=0.0, grow=1.0, count=True)
    return stage


def main() -> None:
    global W_PX, H_PX, DPI, BARE, FX, FY
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", required=True, choices=["grid", "siting"])
    ap.add_argument("--lang", default="en", choices=["en", "ja"])
    ap.add_argument("--out", default=str(OUT), help="folder for the gif")
    ap.add_argument("--stills", action="store_true", help="also write the frames the animation holds on, as PNG")
    ap.add_argument("--scale", type=float, default=1.0, help="size factor: 1 gives 1000 x 620 pixels")
    ap.add_argument("--bare", action="store_true", help="for print: maps without the text panel, held frames only, no gif")
    ap.add_argument("--size", default=f"{W_PX}x{H_PX}", help="width x height in pixels before --scale")
    args = ap.parse_args()
    BARE = args.bare
    if BARE:
        FX, FY = (0.05, 0.95), (0.06, 0.94)                               # no text panel: the map may use the whole canvas
    w, h = (int(v) for v in args.size.lower().split("x"))
    W_PX, H_PX, DPI = round(w * args.scale), round(h * args.scale), round(DPI * args.scale)
    if args.lang == "ja":
        use_japanese_fonts()
    records = json.loads(BASE.read_text(encoding="utf-8"))
    stage = (grid if args.theme == "grid" else siting)(records, args.lang)
    name = {"grid": "grid-hosting-map", "siting": "siting-map"}[args.theme] + ("-ja" if args.lang == "ja" else "")
    keys = [C["heat"], C["heat_deep"], C["core"], C["ink"], C["ink2"], NEW, QUIET, *(c for c, _ in KV.values())]
    stage.save(Path(args.out) / f"{name}.gif", keys, args.stills)


if __name__ == "__main__":
    main()
