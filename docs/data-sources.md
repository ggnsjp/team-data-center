# Data sources

This page lists every value the models use, with its source, or marks it as an assumption. Values were checked on 2026-11-23 unless noted.

**For the assumptions, see [input-evidence.md](input-evidence.md)** ([日本語](input-evidence.ja.md)): the range found in published sources for each one, where the model's value sits in it, and how far the published results move when the value moves to the end of the range.

## Data centers in Ishikari

| Item | Value | Source |
|---|---|---|
| Ishikari Renewable Energy Data Center No. 1: operator | 合同会社石狩再エネデータセンター第1号. Set up by Flower Communications; Tokyu Land and Flower manage the project; Broadband Tower manages the building | https://www.bbtower.co.jp/ir/pr/docs/20251128_ishikari_release.pdf |
| No. 1: location | 石狩市新港中央1丁目722番1 (lot number) | https://prtimes.jp/main/html/rd/p/000000693.000006953.html |
| No. 1: power and size | 15,000 kVA receiving; at least 10 MW from August 2026; 6 halls, 1,140 racks | the source above; https://cloud.watch.impress.co.jp/docs/news/2097920.html |
| No. 1: start of service | 1 August 2026, on 100 % renewable power | https://www.tv-tokyo.co.jp/plus/external-pr/entry/269543.html |
| No. 1: IT load, waste-heat plan | not published | — |
| Sakura Internet Ishikari Data Center: size | 3 buildings, up to about 3,000 racks (2015 plan; the full plan is 5 buildings, about 6,800 racks). Capacity in MW not published | https://www.sakura.ad.jp/corporate/corp/datacenter/ ; https://cloud.watch.impress.co.jp/docs/news/723209.html |
| Sakura: heat reuse in its 2011 design | Server exhaust heat preheats the offices and warms water for snow-melting pipes around the building | https://nikkenren.com/kenchiku/sb/pdf/223/12-024.pdf |
| KCCS ZED Ishikari | Operating since 1 October 2024; 2–3 MW, 400 racks; waste heat used for underfloor heating and road heating | https://cloud.watch.impress.co.jp/docs/news/1627835.html ; https://www.env.go.jp/content/900514282.pdf |
| NTT-ME container data centers (planned) | Up to 14 units of 2 MW (IT load about 1.5 MW each); first unit in April 2027 at the earliest | https://cloud.watch.impress.co.jp/docs/news/2057156.html |

## Prices and costs

| Item | Value | Source |
|---|---|---|
| Kerosene, Hokkaido, survey of 16 November 2026 | 156.8 yen/L at the station; 160.1 yen/L delivered. National averages: 144.2 and 154.9 yen/L | https://www.enecho.meti.go.jp/statistics/petroleum_and_lpgas/pl007/xlsx/261118.xlsx |
| Kerosene, conservative value used in the model | 115 yen/L | Assumption: bulk buyers pay less than the 18 L retail price |
| Pre-insulated two-pipe heat network: direct cost per metre of route (2019 quotes) | Steel 25A–250A about 40,000–250,000 yen/m; plastic about 20,000–150,000 yen/m; overhead adds about 33 % | https://ynu.repo.nii.ac.jp/record/12712/files/tachibana_masaya-thesis.pdf (values read from charts) |

## Prototype model parameters (theme 1)

| Parameter | Value | Source or assumption |
|---|---|---|
| IT load of one data center | 10 MW | Assumption |
| Recoverable share of IT heat at 30–35 °C | 0.6 | Assumption |
| Heat-pump COP (to about 60 °C) | 4.0 | Assumption |
| Boiler efficiency (kerosene) | 0.85 | Assumption |
| Heating value of kerosene | 9.7 kWh/L | Assumption, between the standard net value (9.55 kWh/L) and gross value (10.17 kWh/L); see [input-evidence.md](input-evidence.md) |
| CO2 from kerosene | 2.50 kg/L | Ministry of the Environment list of emission factors (see *CO₂ factors and policy scenarios* below) |
| Heat-pump electricity | 25 yen/kWh | Assumption |
| Pipe, installed, both directions | 100,000 yen per metre of street | Assumption; compare with the range above |
| Annuity | 3 %, 30 years | Assumption |
| Heated greenhouse demand in Hokkaido | 0.40 MWh/m² per year | Assumption |
| Snow melting | 0.12 MWh/m² per year | Assumption: about 0.25 kWh/m² per cm of snowfall × 479 cm |

## CO₂ factors and policy scenarios

Checked on 2026-11-25. The carbon prices and subsidy rates are scenario values for the model. They are listed here to show where the scenario levels come from; they do not state that a scheme applies to a given project.

| Item | Value | Source |
|---|---|---|
| CO₂ from kerosene | 2.50 t-CO₂/kL (36.5 GJ/kL × 0.0187 t-C/GJ × 44/12). The earlier edition gave 2.49 | 環境省, 算定・報告・公表制度における算定方法・排出係数一覧 (current edition): https://policies.env.go.jp/earth/ghg-santeikohyo/files/calc/ichiran_2025r.pdf |
| Electricity, Hokkaido Electric Power, FY2024 results | 0.526 kg-CO₂/kWh for the standard plans (menu F); 0.518 for the company as a whole; plans A–E are 0 | 環境省・経済産業省, 電気事業者別排出係数（特定排出者の温室効果ガス排出量算定用）R6年度実績, published 2026-01-09: https://policies.env.go.jp/earth/ghg-santeikohyo/files/calc/r08_denki_coefficient_rev4.pdf |
| Electricity, national level for FY2030 | 0.25 kg-CO₂/kWh | 地球温暖化対策計画（2025-02-18 閣議決定）関連資料2, p. 77: https://www.env.go.jp/content/000290553.pdf |
| Emissions trading scheme (GX-ETS), reference prices for FY2026 | upper 4,300 yen/t-CO₂; lower 1,700 yen/t-CO₂. Later years are not fixed yet | 経済産業省告示第27号 (2026-03-30): https://www.meti.go.jp/policy/energy_environment/global_warming/torihikikakaku.pdf |
| J-Credit prices, Tokyo Stock Exchange carbon credit market | last trades: energy saving 4,399 yen/t (2026-11-18); renewable electricity 4,700 yen/t (2026-11-24); renewable heat 5,300 yen/t (2026-10-01) | 日本取引所グループ, カーボン・クレジット市場日報: https://www.jpx.co.jp/equities/carbon-credit/daily/index.html |
| Tax for climate change mitigation | 289 yen/t-CO₂, levied upstream as 760 yen/kL on petroleum; about 0.76 yen/L of kerosene | 環境省: https://www.env.go.jp/policy/tax/about.html |
| Fossil-fuel levy | from FY2028; the unit price is not set yet | GX推進機構: https://www.gxa.go.jp/carbon-trade-levy/ |
| Subsidy for decarbonization equipment at data centers (FY2025 supplementary budget) | rate 1/2 (storage 1/3), up to 1 billion yen per project. Equipment that supplies waste heat from a data center to users outside it is eligible: heat exchangers, heat pumps, heat pipes, storage tanks. The three rounds of FY2026 are closed | 環境省, 地域共生を目指したデータセンター脱炭素化設備導入支援事業: https://www.env.go.jp/content/000356389.pdf ; guidelines: https://rcespa.jp/wordpress/wp-content/uploads/1_R07hosei_DC2_kouboyouryou_20260901.pdf |
| Grant for decarbonization-leading areas (Ishikari City is one, with Tokyu Land) | as a rule 2/3; heat-use equipment and heat pipes up to 2/3. Data-center waste heat is not named in its list of unused heat | 環境省, 地域脱炭素推進交付金 (FY2026): https://policies.env.go.jp/policy/roadmap/assets/grants/chiiki-datsutanso-kofukin-R8.pdf |
| Subsidy for zero-emission data centers (FY2026) | rate 1/3; waste-heat supply is not among its items | 環境省 (via 地域循環共生社会連携協会): https://rcespa.jp/wordpress/wp-content/uploads/1_R08_DC2_kouboyouryou_20260917-2.pdf |

## Power-system benchmark data (theme 2)

| Item | Value | Source |
|---|---|---|
| PGLib-OPF benchmark systems | six cases with typical operating conditions: case14_ieee, case30_ieee, case39_epri, case57_ieee, case118_ieee, case300_ieee (master branch on 2026-11-25). License CC BY 4.0. Downloaded by the code into `data/cache/pglib/`; not committed | IEEE PES Task Force on Benchmarks for Validation of Emerging Power System Algorithms: https://github.com/power-grid-lib/pglib-opf ; https://arxiv.org/abs/1908.02788 |
| Built-in systems (two buses, a five-bus ring, an eight-bus feeder) | illustrative values in a realistic per-unit range; not a real network | Our own data, in `src/dcopt/grid/cases.py` |
| A network model of the Hokkaido grid | none found in public. HEPCO Network publishes configuration data for 187 kV and above and 30-minute supply and demand; OpenStreetMap has the lines and substations around Ishikari with their voltage classes | to be built: see the open questions in `docs/formulations/grid.md` |

## Siting (theme 3)

| Item | Value | Source or assumption |
|---|---|---|
| Transmission lines, voltage classes and substations around Ishikari | as mapped; 275, 187 and 66 kV classes | OpenStreetMap (© OpenStreetMap contributors, ODbL), downloaded into `data/cache/ishikari/power.geojson`; not checked against HEPCO Network's records |
| Cost of a grid connection line | 410 M yen per km to a 66 kV substation and 510 M yen per km to a 187 kV one, turned into an annuity at 3 % over 30 years (a slider in the app) | The middle of the standard unit costs for a two-circuit tower line, land excluded: 140 to 670 M yen/km (66/77 kV class) and 190 to 830 M yen/km (154/187 kV class). 電力広域的運営推進機関, 送変電設備の標準的な単価 (published 2026-03-10), as reproduced in https://www.occto.or.jp/assets/iinkai/kouikikeitouseibi_hyouka/11/hyouka_11_01_01.pdf . An earlier placeholder of 100 M yen/km was below this range |
| IT load of a new data center | 10 MW, and 60 % of it in the low-load scenarios | Assumption; the ratio is that of data center No. 1 in the model |
| Candidate sites | points of a 1.5 km grid inside the municipal boundary, moved to the nearest road | Generated; not a land survey |

## Climate

| Item | Source |
|---|---|
| Monthly mean temperature and snowfall, Sapporo (station 47412), normals 1991–2020 | JMA: https://www.data.jma.go.jp/obd/stats/etrn/view/nml_sfc_ym.php?prec_no=14&block_no=47412 |
| Daily mean temperature and snowfall, Sapporo (station 47412), 1976–2025, per weather year | JMA 過去の気象データ検索, the daily view of the same station: https://www.data.jma.go.jp/obd/stats/etrn/view/daily_s1.php?prec_no=14&block_no=47412 (fetched by `dcopt.heat.weather`, one CSV per year, committed under `data/jma/`) |

## Precedents

| Case | Source |
|---|---|
| White Data Center, Bibai: server heat warms snowmelt water to 25–28 °C for eel farming (since January 2024) | https://www.hokkaido-np.co.jp/movies/detail/6357590939112/ |
| Hokkaido University: recovering half of a supercomputer's heat gives 6–8 MWh/day, about the heating of 60–80 homes | https://hu-gxc.eng.hokudai.ac.jp/wp-content/uploads/2026/03/gxc2025_excellence_16-osawa.pdf |

## Model v2 parameters (theme 1)

Generated from `dcopt.heat.network.assumptions_table(Params())`. Values with two entries are ambient / central mode, or low / high case.

| Item | Value | Unit | Basis |
|---|---|---|---|
| Recoverable share of IT heat | 0.6 |  | assumption (as v1): 30-35 C capture |
| Waste-heat temperature | 30.0 | C | assumption: liquid or rear-door cooling |
| Ambient loop temperature | 30.0 | C | assumption |
| Central network supply | 60.0 | C | assumption: enough for hot water |
| Share of Carnot COP | 0.5 |  | assumption: 45-55 % typical |
| COP cap | 8.0 |  | assumption: manufacturer range for small lifts |
| Supply-return difference | 10 / 30 | K | assumption: ambient / central |
| Network heat loss | 2% / 8% |  | assumption: ambient / central |
| Kerosene price | 115 / 156.8 | yen/L | assumption (conservative bulk) / source: ANRE survey 2026-11-16, Hokkaido (https://www.enecho.meti.go.jp/statistics/petroleum_and_lpgas/pl007/xlsx/261118.xlsx) |
| Boiler efficiency replaced | 0.85 |  | assumption (as v1) |
| Electricity price | 25.0 | yen/kWh | assumption (as v1) |
| Kerosene CO2 factor | 2.50 | kg/L | source: https://policies.env.go.jp/earth/ghg-santeikohyo/files/calc/ichiran_2025r.pdf |
| Grid electricity CO2 | 0.526 | t/MWh | source: Hokkaido Electric Power, standard plans, FY2024 results (https://policies.env.go.jp/earth/ghg-santeikohyo/files/calc/r08_denki_coefficient_rev4.pdf) |
| Carbon price (scenario) | 0 | yen/t | scenario, zero by default: a price on the CO2 avoided, on top of today's fuel taxes |
| Investment subsidy (scenario) | 0 | | scenario, zero by default: share of the pipe and heat-pump investment |
| Pipe life, discount rate | 30 / 3% |  | assumption (as v1) |
| Heat-pump life | 20 | years | assumption |
| Heat-pump investment | 0 / 0 | yen/MW | user / central; off by default (to verify with makers) |
| Sized share of each user's peak | 1.0 |  | assumption |
| Peak factors | greenhouse 2.5, new_greenhouse 2.5, aquaculture 1.2, snow 3, pool 1.4, onsen 1.4, hospital 1.8, school 2 |  | assumption: greenhouses heat mostly at night (2.5); snow melting follows snowfall events (3.0); space heating 1.8-2.0; pools and baths are steady (1.4); fish farms very steady (1.2) |
| Pipe cost per metre | DN50 84,233, DN80 121,473, DN100 146,300, DN150 208,367, DN200 270,433, DN250 332,500 | yen/m | assumption: straight line through the 2019 quotes for small two-pipe pre-insulated steel networks (25A about 40,000, 250A about 250,000 yen per metre of route, direct cost) plus about 33 % overhead, read off the charts in https://ynu.repo.nii.ac.jp/record/12712/files/tachibana_masaya-thesis.pdf |
| Pipe capacity | DN50 0.09, DN80 0.25, DN100 0.54, DN150 1.41, DN200 2.72, DN250 4.62 | MW | water 990 kg/m3, 4.18 kJ/kgK, dT 10 K, velocities 1, 1.2, 1.5, 1.8, 2, 2.2 m/s (assumption), JIS G 3452 inner diameters |
| Supply temperature: Greenhouses (existing) | 45.0 | C | assumption: hot-water pipe heating in greenhouses runs at about 40-50 C |
| Supply temperature: New greenhouse site (assumed) | 45.0 | C | assumption: as existing greenhouses |
| Supply temperature: Land-based fish farm (assumed) | 22.0 | C | assumption: rearing water 15-28 C by species (eel 25-28 C in the Bibai case); 22 C as a middle value |
| Supply temperature: Snow melting (assumed) | 25.0 | C | assumption: low-temperature hydronic snow melting can run on 20-30 C water |
| Supply temperature: Pool / sports centre | 40.0 | C | assumption: pool water about 28-30 C plus hall heating about 40 C |
| Supply temperature: Hot spring / bath | 60.0 | C | assumption: hot water stored at 60 C or more against Legionella |
| Supply temperature: Hospital | 60.0 | C | assumption: hot water at 60 C or more; space heating 45-60 C |
| Supply temperature: School | 45.0 | C | assumption: low-temperature radiators or floor heating about 45 C |
