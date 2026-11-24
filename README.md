# Team Data Center

**Optimization for data centers in Ishikari, Hokkaido.** Where should their waste heat go? How much new load can the power grid host? Where should the next data center be built?

[日本語版 / Japanese](README.ja.md)

![Waste heat flowing from two Ishikari data centers to 16 sites, month by month](docs/img/heat-network-map.gif)

*Model v2 at today's kerosene price (156.8 yen/L [11]), heat pumps included. One shared network carries waste heat from two data centers in the Ishikari Bay New Port to 19 sites: public buildings, pools, schools, hotels, hospitals, a fish farm, a new greenhouse site and road heating. Line width shows the pipe size; brightness and particle speed show each month's flow, and snow falls in the snowy months. The bars show the heat delivered each month. Several sites and data-center positions are assumptions or placeholders ([Data and sources](#data-and-sources)). Map data © OpenStreetMap contributors (ODbL).*

## About

This project started at [Hack × Hokkaido Build Week 2026](https://www.hackhokkaido.com/), an AI build week in Sapporo (23–27 November 2026) [1]. There, international engineers and people from Hokkaido build prototypes for Hokkaido's problems from open data. Entries are public repositories under the MIT license.

We took the idea starter **"Warm Ishikari"**: a matchmaker and calculator for data-center waste heat. It maps heat sources and possible users (greenhouses, aquaculture, snow melting, public baths) and estimates the heat available, the distance and the saving. It then drafts a one-page proposal for each promising pair, with every number either sourced or marked as an assumption. We treat the task as an optimization problem and extend it into three research themes. The team plans to continue the research after the event.

## Why it matters

- **Data centers are arriving.** Ishikari Bay New Port hosts several data centers [6–10]. One of them, Ishikari Renewable Energy Data Center No. 1, started service on 1 August 2026 on 100 % renewable power [2, 4, 5]. Japan's "watt-bit" policy (2025) sets criteria for siting large data-center clusters near power supply [14].
- **Their heat is wasted while fuel is burned next door.** The waste heat of air-cooled servers (about 25–40 °C [16, 17]) is mostly released. Meanwhile, nearby greenhouses, pools, baths and snow melting burn kerosene, which cost 156.8 yen/L in Hokkaido in the government survey of 16 November 2026 [11].
- **Rules elsewhere already require reuse.** In the EU, data centers above 1 MW must use their waste heat unless a cost-benefit analysis shows it is not feasible [13]. We found no such rule in Japan [14].

## Three research themes

| | Question | Method | Status |
|---|---|---|---|
| 1. Waste-heat networks | Which users connect to which data center, along which streets, with which pipes? | Network-design MILP with monthly heat balances; stochastic and robust versions [23–26, 31–36] | Models v1 and v2, app and animated map |
| 2. Grid hosting capacity | How much data-center and heat-pump load can each grid location take? | AC optimal power flow with convex (SDP/SOCP) relaxations: certified upper bounds plus feasible points [37–47] | Planned |
| 3. Siting | Where should the next data center go? | Facility location using the results of themes 1 and 2 [48–52] | Planned |

## Results so far (theme 1)

All figures are annual net benefits in million yen, averaged over four scenarios: IT load low or high, crossed with kerosene at 115 or 156.8 yen/L. The net benefit is the value of the kerosene replaced, minus heat-pump electricity, minus the annualized cost of pipes and heat pumps. Pipe costs follow [15], heat-pump costs [16], kerosene prices [11], and monthly demand follows JMA climate normals [12]. There are 50 candidate sites: 40 from OpenStreetMap facility tags, plus 10 named public buildings, hotels and a factory. Demand per building type is an assumption.

### A shared network beats pair-by-pair matching

Matching each user to a data center on its own (the "five ranked partners" of the idea starter) reaches only **49–72 %** of what an optimized shared network earns at the two large data centers, and 77–86 % at the small ZED.

| Data center | Network temperature | Optimized network | Top-5 pairs | Pairs reach |
|---|---|---|---|---|
| No. 1 | ambient loop | 91.3 (13 sites, 8.7 km) | 65.3 (3 sites, 5.1 km) | 72 % |
| Sakura | ambient loop | 85.7 (13 sites, 8.7 km) | 58.4 (2 sites, 3.4 km) | 68 % |
| ZED | ambient loop | 58.2 (3 sites, 2.8 km) | 50.0 (3 sites, 4.1 km) | 86 % |
| No. 1 | central heat pump | 80.6 (15 sites, 8.2 km) | 40.4 (4 sites, 6.8 km) | 50 % |
| Sakura | central heat pump | 75.4 (13 sites, 7.1 km) | 37.2 (2 sites, 3.4 km) | 49 % |
| ZED | central heat pump | 39.9 (3 sites, 2.8 km) | 30.8 (4 sites, 5.6 km) | 77 % |

Three effects explain the gap:

1. **No duplicated pipes.** At No. 1 (ambient loop) the network serves 13 sites with 8.7 km of pipe; the five best pairs serve 3 sites with 5.1 km.
2. **Users that lose money alone pay off on a branch.** A pool 2.8 km from data center No. 1 loses about 8.5 M yen a year with its own pipe. Its heat is worth about 8.6 M yen a year after heat-pump costs, so it pays off on any branch shorter than about 1.4 km.
3. **Large pipes are cheaper per unit of heat.** Per megawatt carried, a metre of DN250 pipe costs about one seventh of a metre of DN80 (cost line from [15]).

### From ranked partners to a one-page proposal

The app keeps the idea starter's demo flow. Pick a data center, see five partners ranked by what each adds to the regional plan, and open a one-page proposal for any of them (page *Warm Ishikari Proposals*; data from `scripts/export_proposals.py`). The proposal shows:
- the dedicated pipe on the street map, and the shared network around it;
- the heat delivered month by month;
- what the partner adds to the shared network;
- a range of heat prices at which both sides gain.

A calculation sheet follows. It marks every number as a published source, an assumption or a calculation, and a test checks that no number is left unmarked.

- **No. 1's best partner is the fish farm** (an assumed site). A DN150 pipe of 2.5 km delivers 5,000 MWh a year, replaces 606 kL of kerosene and pays back in 6.3 years. In the regional plan the farm adds 82.4 M yen a year.
- **A price that works for both sides.** Suppose the supplier owns the pipe. Then any heat price between 5,280 and 16,483 yen/MWh leaves both sides better off. Splitting the gain equally gives 10,881 yen/MWh, against 19,018 yen/MWh for heat from kerosene at 156.8 yen/L. Such a range exists exactly when the pair pays for itself ([formulas](docs/formulations/heat-model.md#11-a-heat-price-for-a-pair)).
- **Some partners pay only inside the network.** A hospital and a hotel among No. 1's five partners lose 16.6 M and 7.8 M yen a year with a dedicated pipe. In the shared network they add 9.8 M and 8.6 M yen a year.

### Robust planning avoids leaning on uncertain data centers

- **The nominal plan (ambient loop, kerosene 115 yen/L).** With every data center at its nominal IT load, the best plan earns 66.0. It serves five sites from the small ZED and road heating from the planned NTT-ME center.
- **What can go wrong.** At ZED's published average load (0.9 MW, from the city's plan [6]) the plan earns 32.3. If NTT-ME is not built either, it loses money (−0.7).
- **The robust plan** allows at most one data center at its low IT load and is solved by column-and-constraint generation [31, 33]. It serves the same five sites from No. 1 and keeps **59.7 in every case**, giving up 9.7 % of the nominal value.
- **Central heat pump.** The nominal plan hangs twelve sites on ZED and loses money if ZED runs low (−1.4). The robust plan keeps 37.3, at a price of 1.8 %.

### Planning for uncertainty pays

With the ambient loop, the two-stage stochastic plan earns 93.8 in expectation. A plan built for the average scenario earns 79.0 on the same scenarios. The value of the stochastic solution is **14.8 per year**.

### The low-temperature loop wins once heat pumps are paid for

The stochastic plan with an ambient loop earns **93.8** in expectation, against **81.5** for a central heat pump feeding a 60 °C network. The ambient loop runs at about 30 °C with heat pumps at the users, and the fish farm and the road heating take the heat directly. At today's kerosene price, the ambient plan connects 16 sites with 10.7 km of pipe and earns 140.3 per year; this is the plan in the animation above.

### Caveats

- **Optimality.** The plans come from an LP-guided kernel search with HiGHS.
  - *Standard candidate links.* Gurobi 14.0, an optional backend, proves the optimum of the expected-value model in 71 s (ambient) and 255 s (central). The kernel-search plans are within 0.2 % and 0.8 % of that optimum. HiGHS alone ends at gaps of 18 % and 26 % after 300 s.
  - *Direct links from every user to every data center.* Gurobi reaches gaps of 1.5 % and 3.9 % within 600 s, and HiGHS 38 % and 36 %.
  - The headline plans also use direct links seeded from each data center's own plan.
  - To rerun the comparison: `uv run python experiments/solver_compare/run.py`.
- **Positions.** Two data-center positions are approximate and one is a placeholder.
- **Model scope.** The model balances energy month by month, and heat losses are a flat percentage. Distance-dependent losses are next.

Details: the full mathematical model, with every coefficient and worked numbers, is in [docs/formulations/heat-model.md](docs/formulations/heat-model.md); results are in [docs/formulations/heat.md](docs/formulations/heat.md).

## How it works

```mermaid
flowchart LR
  OSM["OpenStreetMap<br/>roads, buildings, farmland"] --> CAND["Candidate users<br/>and road distances"]
  SRC["Public sources<br/>data centers, prices, climate"] --> PAR["Parameters, each sourced<br/>or marked as an assumption"]
  CAND --> MILP["Network-design MILP<br/>(HiGHS)"]
  PAR --> MILP
  MILP --> PLANS["Plans: expected, worst case,<br/>minimum regret, robust"]
  PLANS --> APP["App, animated map<br/>and one-page proposals"]
```

**The model in one paragraph** (related work: [23–26]; robust methods: [31–36]).
- *Network.* Candidate links follow streets between data centers and users. Binary variables open a link with a pipe size, connect a user, and assign it to one data center.
- *Routing.* A strong multi-commodity flow formulation routes each user's heat from its data center.
- *Monthly balances.* Deliveries are limited by each user's demand and by each data center's waste heat.
- *Objective.* Maximize the value of the heat minus annualized costs.
- *Uncertainty.* The stochastic version shares one build across scenarios. The robust versions maximize the worst case, minimize the largest regret, or protect against a budgeted uncertainty set on IT loads.

## Quick start

```bash
uv sync
uv run python scripts/fetch_data.py --area ishikari    # map data from OpenStreetMap into data/cache (not committed)
uv run python scripts/export_heat_story.py             # base map and data for the animated map page
uv run python scripts/export_proposals.py              # ranked partners and proposals per data center (a few minutes)
uv run streamlit run app/streamlit_app.py              # the demo app
uv run pytest                                          # tests; those that need map data skip without it
```

**Experiments**
- Model v1 against v2: `uv run python experiments/heat_v2_compare/run.py`
- Robust sweep: `uv run python experiments/heat_ccg/run.py ambient`

**Redrawing the animation above**
1. `uv run python scripts/export_heat_network_v2.py`
2. `uv run python scripts/render_readme_animation.py --plan current` (add `--lang ja` for the Japanese version; it needs a Japanese font such as Noto Sans CJK JP)

## Repository layout

```
src/dcopt/heat      theme 1: model v1 (v1.py), v2 (network.py), proposals (proposal.py)
src/dcopt/grid      theme 2
src/dcopt/siting    theme 3
src/dcopt/common    shared code: road network, styles
app/                Streamlit app
web/heat_story/     animated map page
scripts/            data download, exports, figures
experiments/        reproducible experiments (outputs go to results/, not committed)
docs/               formulations, data sources, figures
data/curated/       small tables we compiled, each value with its source
tests/              unit tests on synthetic instances and app tests
```

## Data and sources

- **Every number has a source or is marked as an assumption.** The list, with URLs, is in [docs/data-sources.md](docs/data-sources.md). It covers the data centers in Ishikari, prices, pipe and heat-pump costs, climate normals and precedents.
- **Map data.**
  - Scripts download OpenStreetMap data (© OpenStreetMap contributors, ODbL [18]) into `data/raw/` and `data/cache/`. This data is not committed.
  - The animation is a produced work from OpenStreetMap data and is credited as such.
- **Weather.** Daily JMA observations for Sapporo, 1976–2025 [12], are committed in `data/jma/` under JMA's terms of use (Public Data Terms of Use 1.0: source credited, processing stated), not under the MIT license; see `data/jma/README.md`.
- **Hokkaido precedents.** Snow melting with data-center heat [19], the snow-cooled data center in Bibai and its eel farm [20, 21], and a bath heated by data-center waste heat [22].
- **Assumed sites.** The fish farm, the new greenhouses and the road-heating areas are assumptions, drawn as hollow markers.
- **Data-center positions.** The positions of No. 1 and ZED are approximate, and NTT-ME's site has not been published.

## Solvers

- **Open source by default.** HiGHS solves the MILPs; conic problems (theme 2) will use Clarabel or SCS.
- **Optional commercial solver.** Gurobi can be used when installed (`DCOPT_SOLVER=gurobi`), but no part of the code requires it. On this model it certifies plans that HiGHS cannot within the same time (see Caveats).

## Next research questions

- Certify optimality with a stronger pipe-sizing formulation (cut-set inequalities, Benders cuts) [23, 26].
- Co-optimize the network layout, the temperature level and where heat pumps go, at street scale.
- Model heat losses that depend on pipe length, size, temperature and flow.
- Share the cost of a common trunk fairly: the Shapley value against the least core [27, 28].
- Two-stage robust design when it is uncertain which planned data centers will be built [32–35].
- Certified grid hosting capacity from SDP/SOCP relaxations, for flexible data-center loads [37, 39, 42–47, 51].
- Siting that combines heat reuse, grid capacity, renewables, fiber and hazards [29, 30, 48–52].

## References

Facts and parameters [1–22], then related literature: waste-heat networks and data-center heat reuse [23–30], robust optimization [31–36], grid hosting capacity [37–47], siting and flexible loads [48–52].

1. Hack × Hokkaido Build Week 2026, AI build week in Sapporo, 23–27 November 2026. https://www.hackhokkaido.com/ (accessed 2026-11-24).
2. Broadband Tower (2025-11-28). Press release on Ishikari Renewable Energy Data Center No. 1 (in Japanese). https://www.bbtower.co.jp/ir/pr/docs/20251128_ishikari_release.pdf
3. PR TIMES (2026-04-22). Ishikari Renewable Energy Data Center No. 1: site in 石狩市新港中央1丁目 (in Japanese). https://prtimes.jp/main/html/rd/p/000000693.000006953.html
4. Impress Cloud Watch (2026-04-01). Ishikari Renewable Energy Data Center No. 1: 15,000 kVA receiving, at least 10 MW from August 2026, 1,140 racks (in Japanese). https://cloud.watch.impress.co.jp/docs/news/2097920.html
5. TV Tokyo Plus (2026-10-07). Service start on 1 August 2026 on 100 % renewable power (in Japanese). https://www.tv-tokyo.co.jp/plus/external-pr/entry/269543.html
6. 石狩市・東急不動産 (2025). 脱炭素先行地域 計画提案書「再エネの地産地活・脱炭素で地域をリデザイン」, revised 2025-07-04 (Ishikari City and Tokyu Land, decarbonization-leading-area plan). https://www.city.ishikari.hokkaido.jp/_res/projects/default_project/_page_/001/002/422/senko20250704.pdf
7. Sakura Internet. Ishikari Data Center (in Japanese). https://www.sakura.ad.jp/corporate/corp/datacenter/ ; Impress Cloud Watch (2015-09-30). https://cloud.watch.impress.co.jp/docs/news/723209.html
8. 日本建設業連合会 (2012). さくらインターネット石狩データセンター, building case sheet (in Japanese). https://nikkenren.com/kenchiku/sb/pdf/223/12-024.pdf
9. Impress Cloud Watch (2024). KCCS zero-emission data center Ishikari (in Japanese). https://cloud.watch.impress.co.jp/docs/news/1627835.html ; Ministry of the Environment. https://www.env.go.jp/content/900514282.pdf
10. Impress Cloud Watch (2025-10-23). NTT-ME container data centers in Ishikari (in Japanese). https://cloud.watch.impress.co.jp/docs/news/2057156.html
11. 資源エネルギー庁 (2026). 石油製品価格調査, survey of 2026-11-16 (Agency for Natural Resources and Energy, petroleum product prices). https://www.enecho.meti.go.jp/statistics/petroleum_and_lpgas/pl007/xlsx/261118.xlsx
12. 気象庁. 平年値（1991〜2020年）札幌 (Japan Meteorological Agency, climate normals, Sapporo). https://www.data.jma.go.jp/obd/stats/etrn/view/nml_sfc_ym.php?prec_no=14&block_no=47412 ; 同 日別値 (daily observations, same station): https://www.data.jma.go.jp/obd/stats/etrn/view/daily_s1.php?prec_no=14&block_no=47412
13. European Union (2023). Directive (EU) 2023/1791 on energy efficiency, Articles 12 and 26. https://eur-lex.europa.eu/eli/dir/2023/1791/oj
14. 総務省・経済産業省 (2025). ワット・ビット連携官民懇談会 取りまとめ1.0 (MIC and METI, public-private council on watt-bit coordination, summary 1.0). https://www.soumu.go.jp/main_content/001014454.pdf
15. Tachibana, M. (2023). Doctoral thesis, Yokohama National University: cost of small district-heating networks (values read from charts). https://ynu.repo.nii.ac.jp/record/12712/files/tachibana_masaya-thesis.pdf
16. Dansk Fjernvarme (2022). Inspirationskatalog for store varmepumper: Odense data-center heat pumps (COP, cost). https://danskfjernvarme.dk/media/eqbhcqlv/inspirationskatalog-for-store-varmepumper-2022.pdf
17. Berenschot (2020). Analyse restwarmte uit datacenters Hollands Kroon (waste heat from data centers). https://www.berenschot.nl/media/xtmabnee/cases-berenschot_-_analyse_restwarmte_uit_datacenters_hollands_kroon_-_eindrapport_1.pdf
18. OpenStreetMap contributors. Map data under the Open Database License (ODbL 1.0). https://www.openstreetmap.org/copyright
19. 堤拓哉・月館司・下ノ薗慧 (2019). 積雪寒冷条件を踏まえたデータセンターの設計に関する基礎的検討. 北海道立総合研究機構 調査研究報告 No.396 (design of data centers in snowy cold regions). https://www.hro.or.jp/upload/22910/396.pdf
20. 本間弘達 (2020). 雪冷熱エネルギーを利用したデータセンター. 電気設備学会誌 40(5), 296–299 (a data center using snow cold energy, Bibai). https://www.jstage.jst.go.jp/article/ieiej/40/5/40_296/_pdf/-char/ja
21. 北海道新聞 (2024-07-11). 雪うなぎ: eel farming with data-center heat in Bibai (in Japanese). https://www.hokkaido-np.co.jp/movies/detail/6357590939112/
22. 大沢飛智 (2026). データセンターと地域の新たな共生モデル —排熱利用型温浴施設「ビットの湯」—. Hokkaido University GX center poster. https://hu-gxc.eng.hokudai.ac.jp/wp-content/uploads/2026/03/gxc2025_excellence_16-osawa.pdf
23. Ljubić, I., Weiskircher, R., Pferschy, U., Klau, G.W., Mutzel, P., Fischetti, M. (2006). An Algorithmic Framework for the Exact Solution of the Prize-Collecting Steiner Tree Problem. *Mathematical Programming*, 105, 427–449. https://doi.org/10.1007/s10107-005-0660-x
24. Kuper, L., Metzger, M., Stursberg, P., Niessen, S. (2025). Computationally efficient topology design of district heating networks by price-collecting Steiner trees. *Energy*, 333, 137223. https://doi.org/10.1016/j.energy.2025.137223
25. Bordin, C., Gordini, A., Vigo, D. (2016). An optimization approach for district heating strategic network design. *European Journal of Operational Research*, 252(1), 296-307. https://doi.org/10.1016/j.ejor.2015.12.049
26. Lambert, J., Ceruti, A., Spliethoff, H. (2024). Benchmark of mixed-integer linear programming formulations for district heating network design. *Energy*, 308, 132885. https://doi.org/10.1016/j.energy.2024.132885
27. Megiddo, N. (1978). Cost allocation for steiner trees. *Networks*, 8(1), 1-6. https://doi.org/10.1002/net.3230080104
28. Caprara, A., Letchford, A.N. (2010). New techniques for cost sharing in combinatorial optimization games. *Mathematical Programming*, 124(1-2), 93-118. https://doi.org/10.1007/s10107-010-0357-7
29. Huang, P., Copertaro, B., Zhang, X., Shen, J., Löfgren, I., Rönnelid, M., et al. (2020). A review of data centers as prosumers in district energy systems: Renewable energy integration and waste heat reuse for district heating. *Applied Energy*, 258, 114109. https://doi.org/10.1016/j.apenergy.2019.114109
30. Wahlroos, M., Pärssinen, M., Manner, J., Syri, S. (2017). Utilizing data center waste heat in district heating – Impacts on energy efficiency and prospects for low-temperature district heating networks. *Energy*, 140, 1228-1238. https://doi.org/10.1016/j.energy.2017.08.078
31. Bertsimas, D., Sim, M. (2004). The Price of Robustness. *Operations Research*, 52(1), 35-53. https://doi.org/10.1287/opre.1030.0065
32. Ben-Tal, A., Goryashko, A., Guslitzer, E., Nemirovski, A. (2004). Adjustable robust solutions of uncertain linear programs. *Mathematical Programming*, 99(2), 351-376. https://doi.org/10.1007/s10107-003-0454-y
33. Zeng, B., Zhao, L. (2013). Solving two-stage robust optimization problems using a column-and-constraint generation method. *Operations Research Letters*, 41(5), 457-461. https://doi.org/10.1016/j.orl.2013.05.003
34. Atamtürk, A., Zhang, M. (2007). Two-Stage Robust Network Flow and Design Under Demand Uncertainty. *Operations Research*, 55(4), 662-673. https://doi.org/10.1287/opre.1070.0428
35. Majewski, D.E., Lampe, M., Voll, P., Bardow, A. (2017). TRusT: A Two-stage Robustness Trade-off approach for the design of decentralized energy supply systems. *Energy*, 118, 590-599. https://doi.org/10.1016/j.energy.2016.10.065
36. Aissi, H., Bazgan, C., Vanderpooten, D. (2009). Min–max and min–max regret versions of combinatorial optimization problems: A survey. *European Journal of Operational Research*, 197(2), 427-438. https://doi.org/10.1016/j.ejor.2008.09.012
37. Molzahn, D.K., Hiskens, I.A. (2019). A Survey of Relaxations and Approximations of the Power Flow Equations. *Foundations and Trends in Electric Energy Systems*, 4(1-2), 1-221. https://doi.org/10.1561/3100000012
38. Bai, X., Wei, H., Fujisawa, K., Wang, Y. (2008). Semidefinite programming for optimal power flow problems. *International Journal of Electrical Power & Energy Systems*, 30(6-7), 383-392. https://doi.org/10.1016/j.ijepes.2007.12.003
39. Lavaei, J., Low, S.H. (2012). Zero Duality Gap in Optimal Power Flow Problem. *IEEE Transactions on Power Systems*, 27(1), 92-107. https://doi.org/10.1109/TPWRS.2011.2160974
40. Jabr, R. (2006). Radial Distribution Load Flow Using Conic Programming. *IEEE Transactions on Power Systems*, 21(3), 1458-1459. https://doi.org/10.1109/TPWRS.2006.879234
41. Farivar, M., Low, S.H. (2013). Branch Flow Model: Relaxations and Convexification—Part I. *IEEE Transactions on Power Systems*, 28(3), 2554-2564. https://doi.org/10.1109/TPWRS.2013.2255317
42. Coffrin, C., Hijazi, H.L., Van Hentenryck, P. (2016). The QC Relaxation: A Theoretical and Computational Study on Optimal Power Flow. *IEEE Transactions on Power Systems*, 31(4), 3008-3018. https://doi.org/10.1109/TPWRS.2015.2463111
43. Kocuk, B., Dey, S.S., Sun, X.A. (2016). Strong SOCP Relaxations for the Optimal Power Flow Problem. *Operations Research*, 64(6), 1177-1196. https://doi.org/10.1287/opre.2016.1489
44. Molzahn, D. K., Lesieutre, B. C., DeMarco, C. L. (2013). A Sufficient Condition for Power Flow Insolvability With Applications to Voltage Stability Margins. *IEEE Transactions on Power Systems*, 28(3), 2592–2601. https://doi.org/10.1109/TPWRS.2012.2233765
45. Sogol Babaeinejadsarookolaee, Adam Birchfield, Richard D. Christie, Carleton Coffrin, Christopher DeMarco, Ruisheng Diao, et al. (2019). The Power Grid Library for Benchmarking AC Optimal Power Flow Algorithms. arXiv:1908.02788. https://arxiv.org/abs/1908.02788
46. Coffrin, C., Bent, R., Sundar, K., Ng, Y., Lubin, M. (2018). PowerModels. JL: An Open-Source Framework for Exploring Power Flow Formulations. *2018 Power Systems Computation Conference (PSCC)*. https://doi.org/10.23919/PSCC.2018.8442948
47. Haoxiang Wan, Jesus Silva-Rodriguez, Jonghwan Kwon, Xingpeng Li (2026). AC Assessment of DC Power Flow Screening for Data Center Hosting Capacity and Siting. arXiv:2611.19602 (preprint, not peer reviewed). https://arxiv.org/abs/2611.19602
48. Goiri, I., Le, K., Guitart, J., Torres, J., Bianchini, R. (2011). Intelligent Placement of Datacenters for Internet Services. *2011 31st International Conference on Distributed Computing Systems*. https://doi.org/10.1109/ICDCS.2011.19
49. Covas, M.T., Silva, C.A., Dias, L.C. (2013). Multicriteria decision analysis for sustainable data centers location. *International Transactions in Operational Research*, 20(3), 269–299. https://doi.org/10.1111/j.1475-3995.2012.00874.x
50. Kim, K., Yang, F., Zavala, V.M., Chien, A.A. (2017). Data Centers as Dispatchable Loads to Harness Stranded Power. *IEEE Transactions on Sustainable Energy*, 8(1), 208-218. https://doi.org/10.1109/TSTE.2016.2593607
51. Norris, T. H., Profeta, T., Patino-Echeverri, D., Cowie-Haskell, A. (2025). Rethinking Load Growth: Assessing the Potential for Integration of Large Flexible Loads in US Power Systems. Nicholas Institute, Duke University, NI R 25-01. https://nicholasinstitute.duke.edu/publications/rethinking-load-growth (figures as cited in the lead author's testimony of 2025-03-05)
52. Onodera, H., Shiraki, H., Matsuhashi, K. (2026). Strategic data center siting can mitigate trade-offs between decarbonization and digitalization in Japan. *Cell Reports Sustainability*, 3(9), 100823. https://doi.org/10.1016/j.crsus.2026.100823

## Team

Adam Curnow, Junko, Lia Vergou, Noriyuki Sugita, Paul Binder, Seiko Yamaguchi, Thomas Braam

## License and citation

The code is under the MIT license ([LICENSE](LICENSE)). Data from other sources keeps its own license. To cite this work, see [CITATION.cff](CITATION.cff).
