# Waste heat, geothermal heat or ground heat?

[日本語](ground-heat.ja.md)

> **All numbers are model estimates** from public data and stated assumptions, not measured values. Pipe costs, heat-pump performance, the temperatures each user needs, several demands and several sites are assumptions (see [data-sources.md](data-sources.md) and [input-evidence.md](input-evidence.md)). Wells, exploration and ground loops are not costed here, so this page does not say which source is cheaper.

This page is for a town or a heat user who weighs a connection to a data-center heat network against heat from the ground. A question that is often asked is whether geothermal heat would not be the better source. The page puts three sources side by side and restates the published plan of theme 1 for each. The tables are the output of `uv run python scripts/ground_heat.py`.

**The answer in short.**

- **Hot geothermal water is better heat** than the 30 °C waste heat of a data center: it needs no heat pump. **What decides is distance.** Heat is costly to move, hot resources are where the geology puts them, and the data centers stand next to the users. With the model's own pipe costs, a line that carries hot water to the plan's users costs 2,704 M yen per 10 km and loses, per 10 km, 17 % of the heat it delivers. At 7.0 km the line alone costs as much as the plan's whole network. What hot water saves on heat pumps pays for 4.3 km of it. The nearest hot resource that a source names, in the mountains south-west of Sapporo, lies about 26 to 30 km from the data centers in a straight line. A line that carries a whole city's heat is a different case, which this page does not assess.
- **Shallow ground heat is under every building,** so it needs no network. It is colder than the waste heat, about 10 °C in Hokkaido, so every use needs a heat pump: for the plan's deliveries, 2.4 times the electricity. It fits small users far from a data center.
- **No source is better everywhere.** Which one fits a user depends on where the user is, how warm the heat has to be and how much of it is needed.

## 1. Three sources

| | Data-center waste heat | Hot geothermal or hot-spring water (地熱・温泉熱) | Shallow ground heat (地中熱) |
|---|---|---|---|
| Temperature | about 30 °C (the model's assumption) | from about 50 °C up to steam (the classes of the resource maps start at 53 °C [7]) | about 10 °C in Hokkaido [4] |
| Where | at the data centers, next to the users of the port area | where the geology has it | under every building |
| To use it | a pipe network, and a heat pump for needs above 27 °C | wells, and a line to the users | boreholes or wells, and a heat pump for every use |
| Exergy of 1 kWh of heat in January | 0.110 kWh (at 30 °C) | 0.236 kWh (at 80 °C) | 0.047 kWh (at 10 °C) |

The two Japanese words are easily confused. The Ministry of the Environment explains them as follows [4]: 地熱 (geothermal heat) comes from the Earth's interior, and what is used is mainly heat of several hundred °C from several kilometres down, for power generation; 地中熱 (ground heat) is the comparatively cool heat, about 10 to 20 °C, of the ground from 10 to several hundred metres down, which comes mainly from the sun. The last row of the table is the exergy of [exergy.md](exergy.md): the share of the heat that could do work, with the January mean of −3.2 °C as the surroundings.

## 2. Hot geothermal heat

### What speaks for it

- **It is hotter, so it is better heat.** Water at 80 °C serves every use in the model through a heat exchanger, with no heat pump and no electricity for a temperature lift. It carries about twice the exergy of water at 30 °C. It could also serve needs above 60 °C, such as steam for a hospital, which the model leaves out ([exergy.md](exergy.md), section 3).
- **Direct use is established.** A worldwide review counts 16.0 % of the geothermal heat used directly as space heating (91 % of that in district heating), 3.5 % as greenhouse heating, 1.3 % as heating of aquaculture ponds, and 0.2 % as snow melting and cooling [1]. These are the uses the plan serves.
- **Hokkaido uses it where the sources are.** The prefecture's guidebook says that geothermal and hot-spring heat has been put to use in the regions with hot sources, the south, the east and Kamikawa, and that elsewhere it is little used beyond bathing [8]. Three examples:
  - *Teshikaga.* Two nursing homes, one of them run by the town, take their heating and hot water from a source about 1.8 km away. The water leaves the source at 82 to 83 °C and arrives at 70 to 74 °C; part of it also melts snow [8].
  - *Sobetsu.* The town built a vegetable-growing estate on hot-spring heat in 1980 to 1982. Water of 65 °C that flows out by itself 2.5 km away heats 28 greenhouses that grow tomatoes [8].
  - *Mori.* In the basin where the Mori geothermal power station stands (25,000 kW, in operation since November 1982 [9]), greenhouses grow cucumbers and tomatoes on geothermal heat; a note of 1983 counts 242 of them [10].

### What decides: distance

In these examples the heat is used close to its source: 1.8 km away in Teshikaga, 2.5 km away in Sobetsu [8], and at Mori within one basin about 2.5 km across [10]. Moving heat takes an insulated two-pipe line, and both its cost and its heat loss grow with every metre, whatever the line carries. The model already holds what is needed to put numbers on this: a cost per metre for each pipe size (an assumption from quotes of 2019, [data-sources.md](data-sources.md)), the heat each size carries, and published loss coefficients for buried pre-insulated pipes with the ground temperature of Sapporo (`src/dcopt/heat/loss.py`).

**The line assumed here.** Water leaves the field at 80 °C and comes back at 40 °C, hot enough for the model's hottest need (60 °C). The line is two single pipes of the middle of three insulation classes, buried 1.2 m deep and kept at temperature all year.

| Size | Cost (yen/m) | Carries at 10 K, as the loop (MW) | Carries at 40 K, as the hot line (MW) | Yen per metre for each MW carried | 10 km: investment (M yen) | Annuity (M yen/yr) | Heat loss (MWh/yr) |
|---|---|---|---|---|---|---|---|
| DN50 | 84,233 | 0.09 | 0.36 | 231,532 | 842.3 | 43.0 | 1,568 |
| DN80 | 121,473 | 0.25 | 1.02 | 119,561 | 1,214.7 | 62.0 | 1,848 |
| DN100 | 146,300 | 0.54 | 2.16 | 67,660 | 1,463.0 | 74.6 | 1,932 |
| DN150 | 208,367 | 1.41 | 5.64 | 36,967 | 2,083.7 | 106.3 | 2,497 |
| DN200 | 270,433 | 2.72 | 10.89 | 24,822 | 2,704.3 | 138.0 | 2,641 |
| DN250 | 332,500 | 4.62 | 18.48 | 17,991 | 3,325.0 | 169.6 | 2,589 |

The fifth column divides the cost of a metre by the heat the line carries at 40 K. The annuity spreads the investment over 30 years at 3 %, as the model does for its pipes. The loss does not depend on how much heat flows: it is the same in a warm year and in a cold one.

**The line for the plan's users.** The 13 users of the published plan take 15,147 MWh a year. The peaks the model sizes their pipes for add up to 6.3 MW (added as the model adds them along a shared pipe, with no allowance for peaks at different hours). The smallest size that carries this on top of its own loss is DN200.

| Distance (km) | Size | Investment (M yen) | Annuity (M yen/yr) | Heat loss (MWh/yr) | Loss / heat delivered |
|---|---|---|---|---|---|
| 5 | DN200 | 1,352.2 | 69.0 | 1,321 | 9 % |
| 10 | DN200 | 2,704.3 | 138.0 | 2,641 | 17 % |
| 20 | DN200 | 5,408.7 | 275.9 | 5,282 | 35 % |
| 30 | DN200 | 8,113.0 | 413.9 | 7,923 | 52 % |
| 50 | DN200 | 13,521.7 | 689.9 | 13,206 | 87 % |

The field has to supply the loss on top of the heat delivered. At 60 °C out and 30 °C back, the temperatures of the model's 60 °C network, the same size is needed and the loss is 1,849 MWh a year per 10 km.

**Against the plan.**

- The plan's whole network, 7.8 km of pipe from two data centers to the 13 users, costs 1,880 M yen (the plan's pipe list at the model's cost per metre). **A line of 7.0 km costs as much,** and at its end a network that distributes the heat among the users is still needed.
- What hot water saves is the heat pumps. The plan has them at 11 users (2.8 MW): an investment of 420 M yen, or 28.2 M yen a year, and 1,267 MWh of electricity, 31.7 M yen a year. Together 59.9 M yen a year, which pays the annuity of **4.3 km** of line.
- So with the model's inputs a hot source has to lie within a few kilometres of the users to start level with the data centers next door, and that is before its wells are paid for.

Not in this comparison: wells and exploration; pumping; the distribution network of a hot-water system, which could use smaller pipes than the plan's (a pipe carries four times the heat at 40 K than at the loop's 10 K); the value of serving needs above 60 °C. A study of long-distance heat transmission notes that the feasible distance is usually estimated from experience or from a few parameters, and finds the largest economic distance with a cost model that varies the distance, the supply temperature and market prices [2]. This page stays with the first step of such a calculation.

**The same in Hokkaido's own experience.** The Teshikaga line above loses about 10 °C over its 1.8 km [8]. In the prefecture's survey of all 179 municipalities, one answered that a survey for large-scale geothermal power is under way in its area, but that the site is too far from the town for the heat to be used [8].

### Where the hot resources are

The Hokkaido government publishes three maps of geothermal resources by temperature class, estimated by the Geological Survey of Hokkaido [7].

- **120 °C and above.** On the two maps for 120 to 150 °C and for 150 °C and above, the coloured zones are few, scattered over the south-west, the centre and the east of the island. Neither map shows a zone at the head of Ishikari Bay, where the port area lies. The maps are small and name no places.
- **53 to 120 °C.** On this map a band of high values runs across the Ishikari lowland, from Sapporo to Tomakomai. The report warns about exactly this band. The area has not been rated as suitable for low-temperature binary power, the use this class is estimated for. Its values are high because the basement lies deep, so that the layer counted as reservoir is thick even where the temperature is low, and they include cases such as water of 53 °C from a well 2,000 m deep, which the report calls unrealistic for a power project [7]. For heat rather than power, this means at most lukewarm water from deep wells in the lowland where the users are. What such wells would cost and yield is a question apart from distance, and this page does not cost it.

**The nearest place that a source names** is the Jozankei–Toyoha area, in the mountains south-west of Sapporo.

- *Jozankei* is a hot-spring resort. By the figures of the city's tourism association, 56 sources give 8,600 litres a minute of water at 60 to 80 °C [12].
- *Toyoha,* about 8 km from Jozankei, was surveyed for a geothermal power station of 40,000 kW. From fiscal 2011, four survey wells of 1,700 to 1,800 m were drilled, and three of them were tested for steam by January 2014. The steam fell short of the 20 to 30 tonnes an hour that had been assumed, and the fault taken to be its source was not found. In March 2014 the drilling planned for the following year was cancelled, the start of generation planned for fiscal 2022 was withdrawn, and the survey was suspended [11]. At a hearing in December 2015 the plan itself was described as still continuing [11]. What happened after that was not checked for this page.

**How far that is.** From the block of the data centers in the port area, Jozankei is about 26 km away in a straight line and Toyoha about 30 km; a pipe route is longer. For orientation, the hot springs of Noboribetsu are 77 km away and the Mori power station 135 km. The line is the one of the section above, for the plan's users:

| Place | Straight line (km) | Size | Investment (M yen) | Annuity (M yen/yr) | Heat loss (MWh/yr) | Loss / heat delivered |
|---|---|---|---|---|---|---|
| Jozankei hot springs | 26 | DN200 | 7,031.3 | 358.7 | 6,867 | 45 % |
| Toyoha mine | 30 | DN200 | 8,113.0 | 413.9 | 7,923 | 52 % |
| Noboribetsu hot springs | 77 | DN200 | 20,823.4 | 1,062.4 | 20,337 | 134 % |
| Mori geothermal power station | 135 | DN200 | 36,508.5 | 1,862.6 | 35,655 | 235 % |

A line of 26 to 30 km costs 7,031 M yen to 8,113 M yen, about four times the plan's whole network. Its annuity, 359 to 414 M yen a year, is about four times the plan's expected net benefit of 93.8 M yen a year. It would lose 45 % to 52 % of the heat it delivers. All of this comes before the wells, and the survey at Toyoha shows that wells do not always find what was expected.

*How the distances were measured.* They are great-circle distances, our calculation. The block of the data centers is 石狩市新港中央一丁目, located with the address search of the Geospatial Information Authority of Japan (https://msearch.gsi.go.jp/address-search/AddressSearch). The places are the coordinates given in the Japanese Wikipedia articles on 定山渓温泉, 豊羽鉱山, 登別温泉 and 森発電所. The points are in `src/dcopt/heat/ground.py`.

**Long lines exist where the load is large.** Reykjavik brings hot water from the Nesjavellir plant through a pipeline about 25 km long and 800 to 900 mm in diameter, designed for 1,870 litres a second of water of up to 100 °C. In its first stage it carried 560 litres a second; the water took less than seven hours and cooled by less than 2 °C on the way [13]. The plant gives about 200 MW of heat [13], some thirty times the 6.3 MW of the plan's users. The size of the load is the point. A pipe's loss depends on its size and its temperature, not on how much flows through it, so the more heat a line carries, the smaller the share it loses, and the more users share its cost.

**What about a whole city?** For a city's heat, distance stops being the obstacle, because a larger pipe costs much less for each unit of heat it carries. In the table of pipe sizes above, a metre of the smallest line (DN50) costs 231,532 yen for each MW it carries and a metre of the largest (DN250) 17,991 yen, a thirteenth; the ratio is the same at any temperature difference. The Reykjavik line, about 25 km long for about 200 MW of heat, is the example [13]. What decides then is no longer the distance. It is whether a resource of that size is proven (the survey at Toyoha was suspended when the steam fell short [11]) and whether a network exists that distributes the heat to the buildings. This page does not assess a project of that scale.

### Other differences

- **Time and risk before the first heat.** A geothermal field has to be found and drilled. At Mori, full-scale surveys began in 1972 and the station started in November 1982; its deepest production well reaches 2,500 m [10]. At Toyoha, four wells and three years of drilling and tests ended in a suspended survey [11]. The data centers of the port area are running or being built, and the heat of those that run is rejected today.
- **What the supply depends on.** Waste heat depends on a data center's operator and its load; the plan's scenarios vary the IT load, and a robust plan with 7 users is published next to the expected one with 13. Geothermal heat depends on the reservoir and its wells; in the prefecture's survey, one municipality reports that many of its wells are more than 30 years old and failing with age [8].

## 3. Shallow ground heat

About 10 m down, the ground stays at the yearly mean air temperature all year: 10 °C in Hokkaido, and 2 to 4 °C more about 100 m down [4]. A heat pump lifts this heat to the temperature of the use. The ground is tapped by a closed loop (antifreeze circulating through pipes in boreholes) or by an open loop (groundwater pumped from a well and returned). An open loop gives more heat per well, but needs groundwater and a place where pumping is allowed [4].

Hokkaido has more ground-heat systems than any other prefecture: 932 at the end of March 2024, of which 869 use heat pumps [5]. Two systems in Tobetsu, a town on the Ishikari plain, show the scale [6]. The town's document names the Ishikari plain among the areas where the use of aquifers is especially promising.

| | Closed loop: roadside station (built 2016–17) | Open loop: nursery school (completed 2024) |
|---|---|---|
| Heat pump | 59.6 kW heating, 62 kW cooling | 148.4 kW heating, 138.4 kW cooling, and 10 kW for snow melting |
| Ground side | 11 boreholes of 100 m | 2 wells of 80 m |

### Temperature decides the electricity

The model's heat-pump rule (half of the Carnot COP between source and need, capped at 8, with a 5 K approach; [exergy.md](exergy.md), section 3) is applied here to ground at 10 °C in place of the 30 °C loop.

| Kind of user | Supply (°C) | COP on the loop (30 °C) | COP on ground heat (10 °C) | With ground at 14 °C |
|---|---|---|---|---|
| Fish farm | 22 | direct, no heat pump | 8.00 | 8.00 |
| Snow melting | 25 | direct, no heat pump | 7.45 | 8.00 |
| Pool | 40 | 8.00 | 4.47 | 5.05 |
| Greenhouse, school, public building | 45 | 7.95 | 3.98 | 4.42 |
| Bath, hospital, hotel, factory | 60 | 4.76 | 3.03 | 3.27 |

The supply temperatures are the model's assumptions. The two uses that take the loop's heat directly need a heat pump on ground heat at these temperatures. In practice some snow-melting systems circulate water at ground temperature with no heat pump at all [4]; the model's road heating assumes water at 25 °C.

### The published plan on ground heat

The same deliveries, each user with a ground-source heat pump of its own (MWh a year):

| Kind | Users | Heat | Supply (°C) | Electricity on the loop | Electricity on ground heat |
|---|---|---|---|---|---|
| Fish farm (assumed) | 1 | 5,003 | 22 | 0 | 625 |
| Snow melting (assumed) | 1 | 2,400 | 25 | 0 | 322 |
| Pool, sports centre | 3 | 2,397 | 40 | 300 | 536 |
| Hotel | 2 | 1,996 | 60 | 419 | 659 |
| Public building | 4 | 1,604 | 45 | 202 | 403 |
| Hospital | 1 | 1,499 | 60 | 315 | 495 |
| School | 1 | 248 | 45 | 31 | 62 |
| **All** | 13 | 15,147 | | 1,267 | 3,103 |

Ground heat needs 3,103 MWh of electricity where the loop needs 1,267: **2.4 times as much.** With the ground at 14 °C it is 2,889 MWh.

In money, with the model's own prices and nothing else:

| | Users with a heat pump | Capacity (MW) | Electricity (MWh/yr) | Electricity (M yen/yr) | Investment (M yen) | Its annuity (M yen/yr) | Sum (M yen/yr) |
|---|---|---|---|---|---|---|---|
| On the loop (the plan) | 11 | 2.80 | 1,267 | 31.7 | 420.1 | 28.2 | 59.9 |
| On ground heat | 13 | 6.26 | 3,103 | 77.6 | 939.7 | 63.2 | 140.7 |

- Ground heat spends 80.8 M yen a year more on heat pumps and their electricity.
- It needs none of the plan's pipes, which cost 95.9 M yen a year.
- **The ground loops are not costed:** we have no verified unit cost for boreholes or wells. On the items above, the two come out even if the ground loops of all 13 users cost 295 M yen together. A reader with a quote can compare. For scale: the plan's peaks, 6.3 MW, are about a hundred times the heating capacity of the roadside station in Tobetsu with its 11 boreholes [6].

### What to weigh

- **For ground heat.** No network, so neither distance nor a data center matters; cooling in summer with the same system [4]; and practice in Hokkaido [5, 6].
- **Against it: electricity.** For the plan's deliveries it needs 2.4 times the electricity of the loop (above), so its cost follows the price of electricity. In the prefecture's survey one municipality reports that it stopped the ground-source heat pump of a pool when electricity prices rose, and another raises the concern that in a very cold region more heat is taken from the ground than is returned, so that the ground cools from year to year [8].
- **Together.** Storing heat in aquifers bridges the gap between the periods of highest supply and highest demand; almost all systems in operation store heat at low temperature, and the method suits large users such as public and commercial buildings and district heating [3]. A data center has heat to spare in summer. The two could complement each other; this is not modelled.

## 4. Where each fits

What speaks for the waste heat is said above in pieces. It is warmer than the ground, so it needs less electricity (section 3). It stands next to the users, so it needs no long line (section 2). And it is there and otherwise rejected: the four data centers of the port area in the model, one of them planned, offer 95.7 GWh a year at the model's assumptions, of which the published plan delivers 15.1 GWh.

| | Data-center waste heat | Hot geothermal water | Shallow ground heat |
|---|---|---|---|
| Fits | large users and clusters near a data center, low-temperature needs most of all | users close to a hot source; needs above 60 °C | small users, far from both |
| Paid for mainly in | the network, and heat pumps for hotter needs | wells, and the line to the users | ground loops, and heat pumps with their electricity for every use |
| Depends on | the data center's operator and load | finding and keeping the resource | the price of electricity |

The model compares waste heat with today's kerosene boilers only. It does not yet let each user choose among the three.

## 5. Limits

- **A restatement, not an optimization.** The deliveries of the published plan are kept and the source is swapped. A plan optimized for hot water or for ground heat would connect other users.
- **Not costed:** wells and exploration, ground loops, pumping, and the distribution network of a hot-water system.
- **The line is simple.** One size for the whole length, sized for the sum of the users' peaks; 80 and 40 °C are assumptions; the loss coefficients are those of standard district-heating pipes.
- **The plan's caveats carry over.** About half of its heat goes to two assumed sites, a fish farm (33 %) and road heating (16 %). The supply temperatures and the heat-pump rule are assumptions.
- **The ground is taken at its undisturbed temperature** less the model's 5 K approach. A loop that cools the ground around it does worse.
- **The resource maps are estimates** by a volumetric method and are overstated in places, as their authors say [7].

## 6. Next

- Let the optimization choose per user among waste heat, ground heat and, where a resource is known, hot water.
- Unit costs of boreholes and wells in Hokkaido, from quotes.
- Seasonal storage of summer waste heat in the ground or in an aquifer.
- Needs above 60 °C, split out as on the exergy page.

## 7. Reproduce

```
uv run python scripts/export_heat_network_v2.py     # the plans, if out/heat_network_v2/plans.json is missing
uv run python scripts/ground_heat.py                # the tables of this page (--lang ja for Japanese headings)
```

The calculation is `src/dcopt/heat/ground.py`; `tests/test_ground.py` checks it by hand on small cases and, when the export is present, that this page quotes its figures.

## References

For [1] to [3] the abstract was read, and the statements above rest on it. [4] to [12] are public documents and pages that were opened and read; [7] includes three maps, which were looked at. [13] is a short-course paper, read in full for the passage used.

1. Lund, J.W., Toth, A.N. (2021). Direct utilization of geothermal energy 2020 worldwide review. *Geothermics*, 90, 101915. https://doi.org/10.1016/j.geothermics.2020.101915
2. Kavvadias, K.C., Quoilin, S. (2018). Exploiting waste heat potential by long distance heat transmission: Design considerations and techno-economic assessment. *Applied Energy*, 216, 452-465. https://doi.org/10.1016/j.apenergy.2018.02.080
3. Fleuchaus, P., Godschalk, B., Stober, I., Blum, P. (2018). Worldwide application of aquifer thermal energy storage – A review. *Renewable and Sustainable Energy Reviews*, 94, 861-876. https://doi.org/10.1016/j.rser.2018.06.057
4. 環境省. 地中熱とは？ (Ministry of the Environment, "What is ground heat?"): ground temperature, the difference between 地熱 and 地中熱, closed and open loops. https://www.env.go.jp/water/jiban/post_117.html (accessed 2026-11-28).
5. 環境省. 地中熱利用状況調査, 令和6年度調査結果 (Ministry of the Environment, survey of ground-heat use, results of the FY2024 survey: installations to the end of March 2024, by prefecture). https://www.env.go.jp/water/jiban/survey.html (accessed 2026-11-28).
6. 当別町 経済部ゼロカーボン推進室. 当別町のゼロカーボン（地中熱利用編） (Tobetsu Town, zero-carbon office: ground-heat systems in the town). https://www.town.tobetsu.hokkaido.jp/uploaded/attachment/29001.pdf (accessed 2026-11-28).
7. 北海道立総合研究機構 地質研究所 (2016). 平成27年度地熱・温泉熱開発可能性調査業務 報告書 (Hokkaido Research Organization, Geological Survey of Hokkaido: survey of the potential for developing geothermal and hot-spring heat). The report and the three maps (地熱資源量図) are on the Hokkaido government's page https://www.pref.hokkaido.lg.jp/kz/gxs/guid.html (accessed 2026-11-28).
8. 北海道 (2017). 地熱・温泉熱課題解決ガイドブック (Hokkaido Government, guidebook on solving the problems of geothermal and hot-spring heat use; a survey of all 179 municipalities and case studies). On the same page as [7].
9. 環境省. 全国の地熱・温泉発電所一覧（運転が開始されているもの） (Ministry of the Environment, list of geothermal and hot-spring power stations in operation; source: Japan Geothermal Association, December 2016). https://www.env.go.jp/nature/onsen/council/chinetsukaisei/chinetsukaisei1/sanko5.pdf
10. 川村政和 (1983). 北海道に初めての森地熱発電所 (Kawamura, M., Mori, the first geothermal power station in Hokkaido). 地質ニュース, 352, 22. https://www.gsj.jp/data/chishitsunews/83_12_02.pdf
11. 環境省. 「平成27年度地熱発電と温泉地の共生事例調査委託業務」ヒアリングメモ（札幌市） (Ministry of the Environment, commissioned study of fiscal 2015 on geothermal power and hot-spring resorts: memo of a hearing with the City of Sapporo on 22 December 2015). https://www.env.go.jp/nature/onsen/pdf/2-5_p_36.pdf
12. 札幌観光協会. 定山渓温泉. ようこそさっぽろ (Sapporo Tourism Association, the city's tourism site: Jozankei hot springs). https://www.sapporo.travel/spot/facility/jozankei_onsen/ (accessed 2026-11-28).
13. Gunnlaugsson, E. (2003). Reykjavik Energy – District heating in Reykjavik and electrical production using geothermal energy. Geothermal Training Programme, IGC2003 Short Course, Orkustofnun, Reykjavik, September 2003, 67-78 (a short-course paper). https://orkustofnun.is/gogn/unu-gtp-report/UNU-GTP-2003-01-06.pdf

**Further reading.** Not used for a statement on this page; the bibliographic records were checked.

- Self, S.J., Reddy, B.V., Rosen, M.A. (2013). Geothermal heat pump systems: Status review and comparison with other heating options. *Applied Energy*, 101, 341-348. https://doi.org/10.1016/j.apenergy.2012.01.048
- Sarbu, I., Sebarchievici, C. (2014). General review of ground-source heat pump systems for heating and cooling of buildings. *Energy and Buildings*, 70, 441-454. https://doi.org/10.1016/j.enbuild.2013.11.068
- Rybach, L., Eugster, W.J. (2010). Sustainability aspects of geothermal heat pump operation, with experience from Switzerland. *Geothermics*, 39(4), 365-369. https://doi.org/10.1016/j.geothermics.2010.08.002
- Nagano, K., Katsura, T., Takeda, S. (2006). Development of a design and performance prediction tool for the ground source heat pump system. *Applied Thermal Engineering*, 26(14-15), 1578-1592. https://doi.org/10.1016/j.applthermaleng.2005.12.003
