"""Export the GX-zone energy portfolio as an Excel workbook (out/gx_zone/gx_portfolio.xlsx).

One sheet for Ishikari Bay New Port plus a Sources sheet. The rows are the same records the GX
overlay page maps — every one carries its status, scale, location basis and source, so the
workbook can be read on its own.

Run: uv run python scripts/export_gx_zone.py && uv run python scripts/export_gx_portfolio_xlsx.py
"""
from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
GX = ROOT / "out" / "gx_zone" / "gx.json"
OUT = ROOT / "out" / "gx_zone" / "gx_portfolio.xlsx"

HEAD_FILL = PatternFill("solid", fgColor="0F1D2A")
GROUP_FILL = PatternFill("solid", fgColor="22384C")
HEAD_FONT = Font(color="FFC46B", bold=True, size=11)
GROUP_FONT = Font(color="FFC46B", bold=True, size=10)
THIN = Side(style="thin", color="22384C")
BORDER = Border(bottom=THIN)

HEADERS = ["Facility / plot", "Type", "Status", "Output (MW)", "Location basis", "Source", "Source URL"]

CITY_TITLES = {
    "ishikari": ("石狩湾新港地域（GX戦略地域）", "Ishikari Bay New Port (the GX strategic zone)"),
}
KIND_JA = {
    "wind_offshore": "洋上風力", "wind_onshore": "陸上風力", "solar": "太陽光", "biomass": "バイオマス",
    "storage": "蓄電池", "hydrogen": "水素", "fossil": "火力・LNG", "dc": "データセンター", "plot": "電力申込の用地",
}
KIND_EN = {
    "wind_offshore": "Offshore wind", "wind_onshore": "Onshore wind", "solar": "Solar", "biomass": "Biomass",
    "storage": "Battery storage", "hydrogen": "Hydrogen", "fossil": "Fossil power & LNG", "dc": "Data center", "plot": "Plot with pre-filed power",
}
STATUS_JA = {"operating": "稼働", "under_construction": "建設中", "planned": "計画", "plot": "道が電力申込済"}
STATUS_EN = {"operating": "Operating", "under_construction": "Under construction", "planned": "Planned",
             "plot": "Power pre-filed"}


def scale(row: dict, ja: bool) -> str:
    if row["kind"] == "plot":
        return f"{row['mw']} MW（{row['kv'] // 1000} kV）・連系 {row['year']} 以降" if ja \
            else f"{row['mw']} MW ({row['kv'] // 1000} kV), connection {row['year']}+"
    if row["kind"] == "dc":
        return f"IT負荷 {row['mw']['low']:g}–{row['mw']['high']:g} MW" if ja \
            else f"IT load {row['mw']['low']:g}–{row['mw']['high']:g} MW"
    return f"{row['mw']:g} MW" if row.get("mw") else ("出力未公表" if ja else "output not published")


def source_of(row: dict, ja: bool) -> str:
    s = row.get("source")
    if isinstance(s, dict):
        return s["ja" if ja else "en"]
    if isinstance(s, (list, tuple)) and len(s) == 2:
        return s[0 if ja else 1]
    return str(s)


def write_city_sheet(wb: Workbook, city: str, rows: list[dict], ja: bool) -> None:
    ws = wb.create_sheet(title=CITY_TITLES[city][0 if ja else 1][:31])
    ws.append(HEADERS)
    for c, _ in enumerate(HEADERS, 1):
        cell = ws.cell(row=1, column=c)
        cell.fill, cell.font, cell.border = HEAD_FILL, HEAD_FONT, BORDER
        cell.alignment = Alignment(horizontal="left", vertical="center")

    # group: renewables operating, renewables planned, fossil, DCs and plots
    is_re = lambda r: r["kind"] not in ("fossil", "dc", "plot")          # noqa: E731
    groups = [
        ("再エネ（稼働）" if ja else "Renewables (operating)", lambda r: is_re(r) and r["status"] == "operating"),
        ("再エネ（建設中・計画）" if ja else "Renewables (under construction, planned)", lambda r: is_re(r) and r["status"] != "operating"),
        ("火力・LNG（稼働）" if ja else "Fossil & LNG (operating)", lambda r: r["kind"] == "fossil"),
        ("データセンター（稼働）" if ja else "Data centers (operating)", lambda r: r["kind"] == "dc" and r["status"] == "operating"),
        ("データセンター（建設中・計画）" if ja else "Data centers (under construction, planned)", lambda r: r["kind"] == "dc" and r["status"] != "operating"),
        ("道が電力申込済みの用地" if ja else "Plots with pre-filed power", lambda r: r["kind"] == "plot"),
    ]
    out_row = 2
    for label, pred in groups:
        hit = [r for r in rows if pred(r)]
        if not hit:
            continue
        ws.cell(row=out_row, column=1, value=label)
        for c in range(1, 8):
            cell = ws.cell(row=out_row, column=c)
            cell.fill, cell.font = GROUP_FILL, GROUP_FONT
        out_row += 1
        for r in hit:
            name = r.get("name") if ja else r.get("name_en", r.get("name"))
            ws.append([name, (KIND_JA if ja else KIND_EN)[r["kind"]],
                       (STATUS_JA if ja else STATUS_EN).get(r["status"], r["status"]),
                       scale(r, ja), r["where"][0 if ja else 1], source_of(r, ja), r.get("url") or ""])
            for c in range(1, 8):
                cell = ws.cell(row=out_row, column=c)
                cell.border = BORDER
                cell.alignment = Alignment(vertical="top", wrap_text=(c in (1, 5)))
            # the source URL as a real hyperlink next to the row: the cell reads "source (short label)"
            url = r.get("url") or ""
            link = ws.cell(row=out_row, column=7)
            if url:
                link.hyperlink = url
                link.font = Font(color="8FC1F0", underline="single")
            out_row += 1
    widths = [42, 16, 14, 24, 44, 30, 46]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def write_summary_sheet(wb: Workbook, data: dict, ja: bool) -> None:
    ws = wb.create_sheet(title="合計" if ja else "Summary", index=0)
    ws.append(["地域" if ja else "Area", "区分" if ja else "Bucket", "MW", "内訳" if ja else "Of which"])
    for c in range(1, 5):
        cell = ws.cell(row=1, column=c)
        cell.fill, cell.font, cell.border = HEAD_FILL, HEAD_FONT, BORDER
    rows = []
    for city in ("ishikari",):
        es = data["energy"]
        re_op = sum(e["mw"] for e in es if e["kind"] != "fossil" and e["status"] == "operating" and e["mw"])
        re_pl = sum(e["mw"] for e in es if e["kind"] != "fossil" and e["status"] != "operating" and e["mw"])
        fo = sum(e["mw"] for e in es if e["kind"] == "fossil" and e["mw"])
        dcs = data["dcs"]
        plots = data["reserved"]
        label = CITY_TITLES[city][0 if ja else 1]
        rows.append([label, "再エネ（稼働）" if ja else "Renewables (operating)", round(re_op, 1),
                     "洋上風力・陸上風力・太陽光・バイオマス" if ja else "offshore + onshore wind, solar, biomass"])
        rows.append([label, "再エネ（建設中・計画）" if ja else "Renewables (planned)", round(re_pl, 1),
                     "厚田風力・REゾーン屋根置き太陽光ほか" if ja else "Atsuta wind, RE-zone rooftop potential, among others"])
        rows.append([label, "火力（稼働）" if ja else "Fossil (operating)", round(fo, 1),
                     "ガス" if ja else "gas"])
        rows.append([label, "データセンター（稼働）" if ja else "Data centers (operating)",
                     sum(d["mw"]["high"] for d in dcs if d["status"] == "operating"),
                     "IT負荷の上限値の合計" if ja else "sum of the IT-load upper bounds"])
        rows.append([label, "データセンター（建設中・計画）" if ja else "Data centers (planned)",
                     sum(d["mw"]["high"] for d in dcs if d["status"] != "operating"),
                     "IT負荷の上限値の合計" if ja else "sum of the IT-load upper bounds"])
        if plots:
            rows.append([label, "道が電力申込済みの用地" if ja else "Plots with pre-filed power",
                         sum(p["mw"] for p in plots), "系統接続の申込を道が先に確保（DC未進出）" if ja
                         else "grid applications Hokkaido pre-filed; no DC yet"])
    for r in rows:
        ws.append(r)
    for i, w in enumerate([40, 34, 10, 52], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def write_sources_sheet(wb: Workbook, data: dict, ja: bool) -> None:
    ws = wb.create_sheet(title="出典" if ja else "Sources")
    ws.append(["出典" if ja else "Source", "URL"])
    for c in range(1, 3):
        cell = ws.cell(row=1, column=c)
        cell.fill, cell.font, cell.border = HEAD_FILL, HEAD_FONT, BORDER
    src = data["sources"]
    rows = [
        ("経済産業省 GX戦略地域認定" if ja else "METI, the GX strategic zone certification", src["meti"]),
        ("石狩市のGX戦略地域ページ" if ja else "Ishikari City's zone page", src["ishikari"]),
        ("北海道の公募要領（電力申込の用地）" if ja else "Hokkaido's recruitment guidelines (the pre-filed plots)", src["kobo"]),
        ("TSH GX事業情報プラットフォーム" if ja else "TSH GX Information Platform", src["gxpf"]),
        ("丸紅 プレスリリース（洋上風力第2 83MW）" if ja else "Marubeni press release (offshore wind II, 83 MW)", src["marubeni"]),
        ("北海道電力 プレスリリース（洋上風力112MW）" if ja else "Hokkaido Electric press release (offshore wind, 112 MW)", src["hokuden"]),
        ("石狩市 脱炭素先行地域計画" if ja else "Ishikari leading-area plan", src["city_plan"]),
        ("© OpenStreetMap contributors (ODbL) — 風車・太陽光・火力・変電所の位置" if ja
         else "© OpenStreetMap contributors (ODbL) — turbine, solar, fossil and grid positions", "https://www.openstreetmap.org/copyright"),
    ]
    for r in rows:
        ws.append(r)
    ws.column_dimensions["A"].width = 60
    ws.column_dimensions["B"].width = 70


def main() -> None:
    ja = True                                            # both languages: two workbooks
    data = json.loads(GX.read_text(encoding="utf-8"))
    for r in data["reserved"]:
        r.setdefault("kind", "plot")
        r.setdefault("status", "plot")
        r.setdefault("url", "https://www.openstreetmap.org/copyright")   # OSM rows: link the attribution
    for e in data["energy"]:
        e.setdefault("url", "https://www.openstreetmap.org/copyright")
    for ja, suffix in ((True, "ja"), (False, "en")):
        wb = Workbook()
        wb.remove(wb.active)
        write_summary_sheet(wb, data, ja)
        write_city_sheet(wb, "ishikari", [*data["energy"], *data["dcs"], *data["reserved"]], ja)
        write_sources_sheet(wb, data, ja)
        path = OUT.with_name(f"gx_portfolio_{suffix}.xlsx")
        wb.save(path)
        print(f"{path.name}: {sum(1 for _ in wb[wb.sheetnames[1]].rows)} rows in the first city sheet")


if __name__ == "__main__":
    main()
