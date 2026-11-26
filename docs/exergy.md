# Exergy: the quality of heat, and what it says about the plan

[日本語](exergy.ja.md)

> **All numbers are model estimates** from public data and stated assumptions, not measured values. The temperatures each user needs, several demands and several sites are assumptions (see [data-sources.md](data-sources.md) and [input-evidence.md](input-evidence.md)).

This page is for whoever chooses the heat users and the network temperature. It explains what exergy is, shows where the heat-network model of theme 1 already follows it, and restates the published plan in exergy terms. The tables are the output of `uv run python scripts/exergy_balance.py`.

## 1. What exergy is

Energy is conserved, so "using up energy" cannot mean destroying it. What is used up is the ability to do work. **Exergy** is the name for that ability: the largest amount of work that a quantity of energy could deliver while it comes into balance with its surroundings [1, 2]. The word dates from 1956 [3]; in Japanese it is エクセルギー, also 有効エネルギー [4, 5].

Three forms of the same 1 kWh show the difference.

| 1 kWh of | Exergy | Why |
|---|---|---|
| electricity | 1 kWh | it can be turned into work completely |
| kerosene (heating value) | about 1 kWh | a fuel's chemical exergy is close to its heating value [1] |
| water at 30 °C, in January in Ishikari (−3.2 °C outdoors) | 0.11 kWh | only the temperature difference to the surroundings can drive an engine |
| water at 30 °C, in August (22.3 °C outdoors) | 0.025 kWh | the surroundings are almost as warm |

For heat $Q$ at absolute temperature $T$, with the surroundings at $T_0$, the exergy is the work of an ideal engine running between the two temperatures [1, 2]:

```math
E = Q \left(1 - \frac{T_0}{T}\right)
```

The bracket is the Carnot factor. It is zero when the heat is at the temperature of the surroundings, and it grows as the heat gets hotter.

The bound comes from the second law of thermodynamics: no engine working between two temperatures can exceed the efficiency of the reversible Carnot cycle. A standard problem book treats the efficiency of the Carnot cycle and maximum work in its chapter on the second law [6]. Exergy is this maximum work, measured against the surroundings [1, 2].

Two things follow.

- **Exergy is lost in every real process, even when no energy is lost.** A kerosene boiler that puts 85 % of the fuel's energy into 45 °C water keeps most of the energy and about 12 % of the exergy: a flame far hotter than the need has been used to make lukewarm water.
- **Using energy well means matching the quality of the supply to the quality of the need.** Low-temperature needs should be met from low-temperature sources, and high-quality energy (electricity, fuel) kept for what needs it. Research on district heating states this as a match between "the low quality building heating demand and the low quality heating supply from waste heat or renewable energy" [7]. Fourth-generation district heating lowers the network temperature, in Denmark from 80/40 °C to 50–55/25 °C [15], for lower grid losses and a better use of low-temperature heat sources [8, 9]. A study of Swedish and Danish systems finds that almost two thirds of the exergy in the heat supplied to today's networks is lost in distribution, and that their temperatures can come down [10].

## 2. Why it matters for data-center heat

The electricity a data center uses ends up as heat, but at a low temperature. A review of the recovery options names the difficulty: "the heat is of low quality" [11]. With the model's assumption of 30 °C, the waste heat on offer (the four Ishikari data centers together, averaged over the scenarios) is 95.7 GWh a year and holds 6.5 GWh of exergy (6.8 %): 11.0 % in January and 2.5 % in August.

Heat of this quality cannot make steam, and it is a poor source for anything hot. It is, however, the right quality for needs that are themselves close to the surroundings: melting snow, warming fish tanks, heating rooms and greenhouses. Where a need is hotter than the source, a heat pump lifts the temperature with electricity, and the electricity grows with the lift. Networks that run near ground temperature with heat pumps at the customers are reviewed in [14]. Case studies of data-center heat in district heating are [12] for Espoo, Finland, and [13] for an air-cooled data center in Barcelona, where the result depends on the cooling design. Domestic hot water, with its Legionella rules, is the known difficulty of low-temperature supply [15]. Exergy analysis has also been applied inside the data center, to its cooling system [16].

## 3. Where the model follows it

The model maximizes money, not exergy. But it treats heat by temperature and not only by quantity, in four places.

| Idea | In the model | Where |
|---|---|---|
| Every use has a temperature | A supply temperature per kind of user: fish farm 22 °C, snow melting 25 °C, pools 40 °C, greenhouses, schools and public buildings 45 °C, baths, hospitals, hotels and factories 60 °C. All are assumptions, each with its reasoning | `SUPPLY_C`, `SUPPLY_BASIS` in `src/dcopt/heat/network.py` |
| Use the heat directly when it is warm enough | Users that need 27 °C or less take the 30 °C loop water without a heat pump | `Params.cop`, `direct_margin_k` |
| A temperature lift costs electricity, by the second law | COP = 0.5 × the Carnot COP between the source and the need, capped at 8: 7.95 for 45 °C, 4.76 for 60 °C. The factor 0.5 is the heat pump's own exergy efficiency; large heat pumps typically reach 40 to 60 % of the theoretical value ([input-evidence.md](input-evidence.md)) | `Params.carnot_cop` |
| The network temperature is a decision, judged on the total | A 30 °C loop (10 K between supply and return, 2 % loss, heat pumps at the users) against a 60 °C network (30 K, 8 % loss, a heat pump at each data center, so smaller pipes but a lift for everyone). The loop earns 93.8 M yen a year and the 60 °C network 81.5 | `MODES`; results in [formulations/heat.md](formulations/heat.md) |

**What the model does not represent.** Heat above 60 °C: steam for hospitals, process heat for factories. The model takes the whole yearly demand of a hospital, a hotel or a factory as heat that 60 °C water can supply. In the published plan these users receive 23 % of the heat, so this is the first assumption to check on site. The other gaps are in section 5.

## 4. The published plan in exergy terms

**Definitions.**

- *Reference state:* the outdoor air, month by month (the monthly normals of Sapporo that the model uses).
- *Delivered heat* is valued at the temperature its user needs, $`E_u = Q_u (1 - T_0/T_u)`$. Heat sent hotter than needed does not count for more.
- *Electricity* counts in full. *Waste heat* counts at 30 °C. *Kerosene* counts at 10.17 kWh/L (an assumption, see section 5).
- *Exergy efficiency:* the exergy of the delivered heat divided by the exergy spent to deliver it.

```math
\psi_{\mathrm{boiler}} = \frac{\sum_u E_u}{E_{\mathrm{kerosene}}}
\qquad
\psi_{\mathrm{plan}} = \frac{\sum_u E_u}{W_{\mathrm{electricity}} + E_{\mathrm{waste\ heat}}}
```

**One MWh, worked by hand.** A public building needs 45 °C. In January the outdoor mean is −3.2 °C.

- The heat holds 1 − 269.95/318.15 = 0.152 MWh of exergy.
- *Boiler:* 1/0.85 = 1.176 MWh of kerosene, 121 litres, with 1.233 MWh of exergy. Efficiency 0.152/1.233 = 12.3 %.
- *Plan:* the heat pump lifts from 25 °C (the 30 °C loop less a 5 K approach) to 45 °C, so COP = 0.5 × 318.15/20 = 7.95 and it draws 0.126 MWh of electricity. The other 0.874 MWh, plus 2 % loss, is 0.892 MWh of waste heat, which holds 0.098 MWh of exergy. Efficiency 0.152/(0.126 + 0.098) = 67.8 %.

The same MWh for every kind of user:

| Kind | Supply (°C) | Exergy (MWh) | COP | Electricity (MWh) | Waste heat (MWh) | Boiler | Plan |
|---|---|---|---|---|---|---|---|
| Fish farm | 22 | 0.085 | direct | 0.000 | 1.020 | 6.9 % | 76.4 % |
| Snow melting | 25 | 0.095 | direct | 0.000 | 1.020 | 7.7 % | 84.7 % |
| Pool | 40 | 0.138 | 8.00 | 0.125 | 0.893 | 11.2 % | 61.9 % |
| Greenhouse, school, public building | 45 | 0.152 | 7.95 | 0.126 | 0.892 | 12.3 % | 67.8 % |
| Bath, hospital, hotel, factory | 60 | 0.190 | 4.76 | 0.210 | 0.806 | 15.4 % | 63.6 % |

**The three published plans** (MWh a year; ambient loop):

| Plan | Users | Heat | Its exergy | Share | Kerosene exergy | Boilers | Electricity | Waste-heat exergy | Plan | Electricity at 60 °C |
|---|---|---|---|---|---|---|---|---|---|---|
| Expected (published) | 13 | 15,147 | 1,533 | 10.1 % | 18,683 | 8.2 % | 1,267 | 1,172 | 62.9 % | 3,437 |
| Robust | 7 | 10,449 | 779 | 7.5 % | 12,889 | 6.0 % | 381 | 828 | 64.5 % | 2,371 |
| Today's kerosene price | 16 | 20,760 | 2,361 | 11.4 % | 25,607 | 9.2 % | 2,088 | 1,638 | 63.4 % | 4,711 |

**The published plan by kind of user:**

| Kind | Users | Heat (MWh) | Share | Supply (°C) | COP | Exergy / energy | Electricity (MWh) |
|---|---|---|---|---|---|---|---|
| Fish farm (assumed) | 1 | 5,003 | 33.0 % | 22 | direct | 4.3 % | 0 |
| Snow melting (assumed) | 1 | 2,400 | 15.8 % | 25 | direct | 8.8 % | 0 |
| Pool, sports centre | 3 | 2,397 | 15.8 % | 40 | 8.00 | 11.0 % | 300 |
| Hotel | 2 | 1,996 | 13.2 % | 60 | 4.76 | 16.4 % | 419 |
| Public building | 4 | 1,604 | 10.6 % | 45 | 7.95 | 13.6 % | 202 |
| Hospital | 1 | 1,499 | 9.9 % | 60 | 4.76 | 17.5 % | 315 |
| School | 1 | 248 | 1.6 % | 45 | 7.95 | 13.7 % | 31 |

**What the figures say.**

- The 15,147 MWh that the plan delivers hold 1,533 MWh of exergy, 10.1 %. The need is low in quality, like the source.
- Kerosene boilers spend 18,683 MWh of fuel exergy on that heat: an exergy efficiency of 8.2 %.
- The plan spends 1,267 MWh of electricity and 1,172 MWh of waste-heat exergy: 62.9 %. The high-grade input that has to be bought falls by 93 %.
- 49 % of the heat goes to the two users that need no heat pump, and 23 % to users at 60 °C, where the lift is largest.
- Sent through the 60 °C network, the same deliveries would need 3,437 MWh of electricity, 2.7 times as much, because every user would pay for a lift that only some need. This is the exergy reading of the result that the loop earns more.

## 5. Limits

- **The model's assumptions carry over.** Supply temperatures, yearly demands (several users are assumed) and the heat pump at half the Carnot COP are the model's inputs, not measurements.
- **Electricity is counted at the meter.** The exergy lost in generating it is outside the boundary, as is the refining and delivery of kerosene. As an illustration only, if the electricity came from a thermal plant at 40 % efficiency, the plan's efficiency on that wider boundary would be about 35 %, still four times the boilers'. This is not a figure for Hokkaido's grid.
- **The reference state is the monthly outdoor mean.** Daily swings are ignored. In summer, low-temperature uses show almost no exergy by this measure; a fish farm that heats cold source water is undervalued by it.
- **Heat is valued at one temperature,** the supply temperature, and not along the cooling from supply to return. Valuing the loop at the mean of its 30 and 20 °C would lower the waste-heat exergy and raise the plan's efficiency.
- **Pumping power is not in the model.** A loop with 10 K between supply and return moves about three times the water of a 30 K network, so the plan's efficiency would come out somewhat lower with it.
- **Kerosene's exergy is an assumption.** A fuel's chemical exergy is usually written as its net heating value times a ratio that depends on its composition [1]. We did not compute that ratio; we take the gross heating value, 10.17 kWh/L (1.065 times the net value; the standard values are in [input-evidence.md](input-evidence.md)). With the model's 9.7 kWh/L the boilers' efficiency would read 8.6 % instead of 8.2 %.
- **The 60 °C column fixes the deliveries.** It is not a plan optimized for that network; the optimized comparison is the 93.8 against 81.5 M yen in section 3.
- **Exergy does not replace the cost model.** It explains why the money result comes out as it does and shows where quality is wasted; the decision still rests on cost, risk and who pays.

## 6. Next

- Split the demand of hospitals, hotels and factories by temperature band (steam, hot water, room heating) and count only what the network can supply.
- Add thermal storage, which bridges the hours between a steady source and a peaky need, and pumping power.
- Let the network temperature vary beyond the two options, including a cascade from hotter to cooler users.
- Show the exergy efficiency next to the money figures in the app.

## 7. Reproduce

```
uv run python scripts/export_heat_network_v2.py     # the plans, if out/heat_network_v2/plans.json is missing
uv run python scripts/exergy_balance.py             # the tables of section 4
```

The calculation is `src/dcopt/heat/exergy.py`; `tests/test_exergy.py` checks the worked example by hand and, when the export is present, that this page quotes its figures.

## References

[1] to [6] are textbooks and the note that introduced the word; their bibliographic records were checked (for [6], also the chapter and section titles in the table of contents that the publisher puts online). For [7] to [16] the abstract was read, and the statements above rest on it.

1. Kotas, T.J. (1985). *The Exergy Method of Thermal Plant Analysis*. Butterworths. https://doi.org/10.1016/C2013-0-00894-8
2. Dincer, I., Rosen, M.A. (2021). *Exergy: Energy, Environment and Sustainable Development* (3rd ed.). Elsevier. https://doi.org/10.1016/C2016-0-02067-3
3. Rant, Z. (1956). Exergie, ein neues Wort für "technische Arbeitsfähigkeit". *Forschung auf dem Gebiete des Ingenieurwesens*, 22, 36-37 (in the section Rundschau). https://doi.org/10.1007/BF02592661
4. 宿谷昌則 編著 (2010). エクセルギーと環境の理論：流れ・循環のデザインとは何か（改訂版）. 井上書院. In English: Shukuya, M. (2013). *Exergy: Theory and Applications in the Built Environment*. Springer. https://doi.org/10.1007/978-1-4471-4573-8
5. 日本機械学会 (2002). 熱力学（JSMEテキストシリーズ）. 日本機械学会.
6. 久保亮五 編 (1998). 大学演習 熱学・統計力学（修訂版）. 裳華房 (Kubo, R., ed., problem book on thermodynamics and statistical mechanics, revised edition; written by Kubo, R., Ichimura, H., Usui, T., Hashitsume, N.): chapter 2 on the second law and entropy, section 2.4 on the efficiency of a general Carnot cycle and section 2.11 on maximum and minimum work. https://www.shokabo.co.jp/mybooks/ISBN978-4-7853-8032-8.htm In English, the thermodynamics part: Kubo, R., in cooperation with Ichimura, H., Usui, T., Hashitsume, N. (1968). *Thermodynamics: An Advanced Course with Problems and Solutions*. North-Holland.
7. Li, H., Svendsen, S. (2012). Energy and exergy analysis of low temperature district heating network. *Energy*, 45(1), 237-246. https://doi.org/10.1016/j.energy.2012.03.056
8. Lund, H., Werner, S., Wiltshire, R., Svendsen, S., Thorsen, J.E., Hvelplund, F., Mathiesen, B.V. (2014). 4th Generation District Heating (4GDH): Integrating smart thermal grids into future sustainable energy systems. *Energy*, 68, 1-11. https://doi.org/10.1016/j.energy.2014.02.089
9. Lund, H., Østergaard, P.A., Chang, M., Werner, S., Svendsen, S., Sorknæs, P., et al. (2018). The status of 4th generation district heating: Research and results. *Energy*, 164, 147-159. https://doi.org/10.1016/j.energy.2018.08.206
10. Gong, M., Werner, S. (2015). Exergy analysis of network temperature levels in Swedish and Danish district heating systems. *Renewable Energy*, 84, 106-113. https://doi.org/10.1016/j.renene.2015.06.001
11. Ebrahimi, K., Jones, G.F., Fleischer, A.S. (2014). A review of data center cooling technology, operating conditions and the corresponding low-grade waste heat recovery opportunities. *Renewable and Sustainable Energy Reviews*, 31, 622-638. https://doi.org/10.1016/j.rser.2013.12.007
12. Wahlroos, M., Pärssinen, M., Manner, J., Syri, S. (2017). Utilizing data center waste heat in district heating – Impacts on energy efficiency and prospects for low-temperature district heating networks. *Energy*, 140, 1228-1238. https://doi.org/10.1016/j.energy.2017.08.078
13. Oró, E., Taddeo, P., Salom, J. (2019). Waste heat recovery from urban air cooled data centres to increase energy efficiency of district heating networks. *Sustainable Cities and Society*, 45, 522-542. https://doi.org/10.1016/j.scs.2018.12.012
14. Buffa, S., Cozzini, M., D'Antoni, M., Baratieri, M., Fedrizzi, R. (2019). 5th generation district heating and cooling systems: A review of existing cases in Europe. *Renewable and Sustainable Energy Reviews*, 104, 504-522. https://doi.org/10.1016/j.rser.2018.12.059
15. Yang, X., Li, H., Svendsen, S. (2016). Energy, economy and exergy evaluations of the solutions for supplying domestic hot water from low-temperature district heating in Denmark. *Energy Conversion and Management*, 122, 142-152. https://doi.org/10.1016/j.enconman.2016.05.057
16. Shah, A.J., Carey, V.P., Bash, C.E., Patel, C.D. (2008). Exergy analysis of data center thermal management systems. *Journal of Heat Transfer*, 130(2), 021401. https://doi.org/10.1115/1.2787024

**Further reading.** Not used for a statement on this page; the bibliographic records were checked.

- Schmidt, D. (2009). Low exergy systems for high-performance buildings and communities. *Energy and Buildings*, 41(3), 331-336. https://doi.org/10.1016/j.enbuild.2008.10.005
- Torío, H., Angelotti, A., Schmidt, D. (2009). Exergy analysis of renewable energy-based climatisation systems for buildings: A critical view. *Energy and Buildings*, 41(3), 248-271. https://doi.org/10.1016/j.enbuild.2008.10.006
- Evola, G., Costanzo, V., Marletta, L. (2018). Exergy analysis of energy systems in buildings. *Buildings*, 8(12), 180. https://doi.org/10.3390/buildings8120180
