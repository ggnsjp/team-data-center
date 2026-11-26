# The GX zone's energy portfolio — Ishikari

A briefing document: what the Ishikari side of Hokkaido's GX strategic zone (data-center cluster
type, certified 2026-09-11) already has, what is planned, and what still runs on fossil fuel. Every
number carries its source. Prepared for the "GX overlay" page of the Team Data Center app; checked
2026-11-26.

---

## Ishikari Bay New Port (石狩湾新港地域, Ishikari City)

### Page 1 — what exists and what is planned

**Renewables operating**

| Facility | Output | Location | Source |
|---|---|---|---|
| 石狩湾新港地域洋上風力発電施設 (offshore wind) | **112 MW** | offshore in Ishikari Bay (coordinates not published) | Hokkaido Electric press release — operation from Jul 2024, subsidiary-owned |
| 石狩湾新港第2洋上風力発電所 (offshore wind) | **83 MW** (3.45 MW × 24 turbines) | offshore Ishikari | Marubeni press release 2024-03-28 — SPC owned by Marubeni + Mitsui & Co., operation from Mar 2024 |
| Onshore wind turbines around the New Port | **> 60 MW** (38 turbines mapped in OpenStreetMap) | around 新港西・新港中央 | Ishikari decarbonization-leading-area plan (rev. 2025-07-04), p. 3; © OpenStreetMap (ODbL) |
| 北ガス石狩風力発電所 (Hokkaido Gas wind farm) | 2,350 kW | 石狩市新港中央4丁目 | TSH GX Information Platform |
| Solar plants mapped in OSM (named ones) | ≈ 12 MW total (e.g. IMC Solar 1.95 MW; Yusen Cargo's 新港南 and 新港西 plants, 1.92 MW each; ソーラーファーム石狩 1.2 MW; 石狩太陽光発電所 250 kW; plus 40+ smaller entries) | Ishikari city | © OpenStreetMap contributors (ODbL); total sums the mapped entries |
| 石狩蓄電所 (battery storage) | 30,000 kW | 石狩市花川東641番1・674番1 | TSH GX platform — R3 Storage Stations GK |

**Renewables planned or under construction**

| Facility | Output | Location | Status | Source |
|---|---|---|---|---|
| （仮称）北海道厚田風力発電事業 (onshore wind) | **64,500 kW** | Ishikari, 厚田 district | planned, Tokyu Land | TSH GX platform |
| 木質バイオマス発電 (woody-biomass plants) | — (plan stage) | Ishikari (forest residue; the city is ~74 % forest) | plan named in the city's decarbonization plan | leading-area plan |
| Offshore wind "promising zone" | — | the coast from 石狩湾新港 to 厚田 is a designated "promising area" under the renewables-sea-area law; promotion-zone designation expected | the city plan (p. 3) |
| RE zone rooftop solar potential | ≈ 30 MW potential | the RE zone (≈ 100 ha) inside the port area | leading-area plan |

**Data centers operating**

| Facility | IT load | Location | Notes | Source |
|---|---|---|---|---|
| Sakura Internet Ishikari Data Center | not published (up to ~3,000 racks in 3 buildings; campus receiving capacity 30 MW per MIC material) | 新港中央 (OSM way 1578710709) | operating since 2011; container-type direct-liquid-cooled building added 2025 | curated CSV; dc-builmen roundup |
| KCCS ZED Ishikari (zero-emission DC) | 2–3 MW, 400 racks | 新港中央1丁目 | operating since Oct 2024; 100 % renewables; already uses its waste heat for floor and road heating | cloud.watch.impress; env.go.jp |
| Ishikari Renewable Energy Data Center No. 1 (Tokyu Land et al.; Broadband Tower operates the 石狩新港 site inside it) | 15,000 kVA; ≥ 10 MW supplied from Aug 2026 | 石狩市新港中央1丁目722番1 | completed 2026-03-27; 1,140 racks; IOWN APN link to Otemachi | bbtower release; Nikkei 2026-06-10 |

**Data centers planned**

| Facility | Scale | Location | Status | Source |
|---|---|---|---|---|
| NTT-ME JPDC AI Container Village | up to 14 container units × 2 MW (IT ~1.5 MW each) on ~50,000 m² | 石狩市新港中央1丁目728 | planned; first unit earliest Apr 2027 (city site: "early as Feb 2027"); groundbreaking May 2026 | NTT-ME release; Ishikari City page |
| **Hokkaido's pre-filed grid applications — 5 plots, 590 MW total** (see below) | 590 MW of reserved grid capacity | the port area | operators chosen in the Oct 20 – Dec 4, 2026 call; preferred negotiator from Jan 2027 | Hokkaido recruitment guidelines |

**The pre-filed plots (石狩, 590 MW)** — industrial land with a grid-connection application that Hokkaido Electric Power Network has already accepted into its queue; the winning operator inherits the application. **No data center stands on any of them yet.**

| Lot | Reserved power | Connection target | Area / state | Price |
|---|---|---|---|---|
| 新港中央1丁目720-2 | 40 MW (66 kV) | from Nov 2031 | 18,552 m², graded, on sale | 13,000 yen/m² |
| 新港中央1丁目40-10 (part) | 75 MW (66 kV) | from Dec 2031 | 48,263 m², works under way, parcels from FY2028 | TBD at sale |
| 新港中央1丁目40-10 (part) | 15 MW (66 kV) | from Nov 2031 | 10,520 m², same lot, second parcel | TBD at sale |
| 新港南2丁目737 | 160 MW (66 kV, 2 × 80 MW) | from Oct 2031 | 50,822 m², graded, on sale | 13,000 yen/m² |
| 新港東2丁目123-40/41 | **300 MW (275 kV)** | after Dec 2032 | 120,842 m², works under way, parcels from autumn 2027 | TBD at sale |

*Why the 66 kV splits into two plots: one 66 kV underground cable supplies roughly 100 MW at most, per the guideline's own note.*

**Fossil still running (Ishikari side)**

| Facility | Output | Fuel | Source |
|---|---|---|---|
| 石狩湾新港発電所 (Hokkaido Electric) | **569,400 kW** | gas (fired Feb 2019) | OSM way 931796255 (operator, output, fuel, start date); the plant's own page |
| 石狩LNG基地 (Hokkaido Gas) | LNG receiving/storage base — not a plant, but the gas plant's fuel terminal | LNG | OSM way 962283251 |

### Page 2 — how it adds up

| Bucket | MW | Of which |
|---|---|---|
| Renewables operating | **≈ 290** | offshore wind 195 + onshore wind 62 + solar ≈ 12 + Hokkaido Gas wind 2.35 + storage counted separately |
| Renewables planned / under construction | **≈ 95** | Atsuta wind 64.5 + RE-zone rooftop potential ≈ 30 |
| Battery storage operating | 30 | 石狩蓄電所 |
| Data centers operating | ≈ 10–25 MW IT | Sakura (up to 30 MW receiving), KCCS 2–3 MW, No. 1 ≥ 10 MW |
| Data centers planned | up to ~28 MW firm (NTT-ME) + **590 MW reserved grid** | the pre-filed plots |
| Fossil running | **569 MW** gas + LNG base | 石狩湾新港発電所 |

The grid behind it (OpenStreetMap, not checked against the operator's data): 石狩変電所 (66 kV),
the 石狩湾新港発電所 275 kV switching station, and the 石狩湾新港発電所線 corridor — the 275 kV
hook the future 300 MW site hangs off.

Waste-heat footnote: the theme-1 model of this app optimizes the existing data centers' heat — an
18.5 km pipe network serving 24 users (33,021 MWh/yr, ¥160 M net in the base case).

---

## Where every number comes from

| Source | What it supplied | URL |
|---|---|---|
| METI press release (2026-09-11) | the GX strategic zone certification itself | https://www.meti.go.jp/press/2026/09/20260911006.html |
| Ishikari City zone page | certification, 3 existing DCs, the recruitment window | https://www.city.ishikari.hokkaido.jp/sangyo/yuchi/1007457.html |
| Hokkaido recruitment guidelines (Oct 2026) | the six plots, MW, kV, connection years, areas, prices | https://www.pref.hokkaido.lg.jp/kz/ssg/272100.html |
| TSH GX Information Platform | 北ガス風力, 厚田風力, 石狩蓄電所, 苫東バイオマス, TJDソーラー, the storage and hydrogen projects | https://tsh-gxpf.jp/en/business/ |
| Marubeni press release (2024-03-28) | 石狩湾新港第2洋上風力 83 MW | https://www.marubeni.com/ja/news/2024/release/00092/ |
| Hokkaido Electric press release | 石狩湾新港地域洋上風力 112 MW, Jul 2024 | https://www.hokkaido-electric.co.jp/pressrelease/detail/4319 |
| Ishikari leading-area plan (rev. 2025-07-04) | 60+ MW onshore wind, the biomass plan, the RE zone, the offshore promising area | https://www.city.ishikari.hokkaido.jp/_res/projects/default_project/_page_/001/002/422/senko20250704.pdf |
| dc-builmen roundup (2026-11-14) | NTT-ME dates, Sakura campus capacity | https://dc-builmen.com/ (the roundup covers both cities of the zone; the URL names the other) |
| © OpenStreetMap contributors (ODbL) | turbine positions, solar-plant footprints, fossil plants, the LNG base, the grid | https://www.openstreetmap.org/copyright |

**Honesty notes carried from the map:** offshore wind farms have no published turbine coordinates,
so the map draws them at a bay representative point; the solar-plant totals sum OpenStreetMap's
entries (which undercount — not every roof is mapped); the "pre-filed" plots are land with a
reserved grid connection, not projects; one substation in OSM is unnamed; the grid layer is not
checked against Hokkaido Electric Power Network's own equipment data.
