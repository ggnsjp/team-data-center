# Heat as a business: what the facilities can pay and what the network needs

[日本語](heat-business.ja.md)

> **All numbers are model estimates** from public data and stated assumptions, not measured values. The heat demand of each facility, the kerosene prices, the performance and cost of heat pumps, the pipe costs and two of the sites are assumptions (see [data-sources.md](data-sources.md) and [input-evidence.md](input-evidence.md)). This page shows kinds of facilities, not individual ones: what a given facility gains depends on its own fuel bills.

This page is for a town, the operators of the data centers and the managers of facilities who weigh the heat network of theme 1 as a business. Its aim is simple to state: **lower the winter heating bills of buildings that burn kerosene.** It asks whether one price for heat exists at which a facility pays less for its heating than with kerosene and the network still pays for its pipes, and how that depends on the price of kerosene and on who joins. The tables are the output of `uv run python scripts/heat_business.py`.

**The answer in short.**

- **On today's facilities alone** (3 pools and sports centres, 5 public buildings, 2 hotels, 1 hospital and 2 schools; 6.0 km of pipe) the network needs at least 7,352 yen per MWh of heat, the same as 60.6 yen per litre of kerosene replaced. The plan breaks even when the facilities pay about 125 yen per litre for kerosene. Above that it earns money, 32.6 M yen a year at the retail price in Hokkaido (156.8 yen/L); below it, it loses, 10.0 M yen a year at 115 yen/L.
- **So the first thing to find out is the price that large users pay for kerosene.** No official series exists; the nearest product, heavy oil A delivered by large lorry in Hokkaido, cost 136.8 yen per litre with tax in September 2026 ([input-evidence.md](input-evidence.md)).
- **Users that take the loop's heat without a heat pump change the picture.** The fish farm and the road heating of the published plan, both assumed sites, gain at any kerosene price above 52 yen per litre, and they lower the network's price for everyone, to 6,331 yen per MWh. With them the plan breaks even at about 85 yen per litre; with the road heating and a fish farm of the scale documented in Hokkaido, at about 118 (section 3). Whether such users can be brought to the port area is the question for the demand outlook.
- **Facilities with heat pumps gain least.** Their own heat pump costs them 5,757 to 9,944 yen per MWh in electricity and annuity before they pay for any heat.
- **The hospital and the hotels need some heat above 60 °C** that the network cannot give: in published data 37 to 49 % of a hospital's heat is steam and about a quarter of a hotel's is cooking ([input-evidence.md](input-evidence.md)). This page counts all of it as servable. Without that share, the 13-building network on today's facilities no longer pays (it loses 0.7 to 2.7 M yen a year with its pipes kept); the best plan found connects two pools near a data center with 1.5 km of pipe, 7.2 M yen a year, and breaks even at about 99 yen per litre of kerosene (`experiments/temperature_bands`).

## 1. How the window is built

The model values a MWh delivered as the kerosene it replaces: 13,948 yen at 115 yen per litre and 19,018 yen at 156.8 (a litre gives 8.2 kWh of heat in a boiler of 85 %). A facility that needs heat above the loop's 30 °C has a heat pump of its own: it pays the electricity (25 yen per kWh) and the investment (150 M yen per MW, spread over 20 years at 3 %). The network pays for the pipes, spread over 30 years at 3 %. The model pays nothing to the data centers for their heat and counts no cost at the data centers.

Split this account at one price for heat, the same for every user:

| Per MWh | |
|---|---|
| The most a facility can pay | its kerosene cost, less its own heat pump's electricity and annuity |
| The least the network needs | the pipes' annuity, divided by all the heat they deliver |

Between the two lies the **window**: a price in it leaves the facility and the network no worse off than today. The window of a kind of facility opens when kerosene costs more than the facility's own costs and the network's price together, counted in litres of kerosene. Summed over all users, the room in the windows is the plan's net benefit: at the mean kerosene price of the scenarios (135.9 yen per litre) it is 93.9 M yen a year for the published plan, which the model gives as 93.8 M yen (the export rounds pipe lengths to 10 m).

## 2. Today's facilities alone

The plan with the assumed sites left out, as in the sensitivity study of the README: the best plan the model's search found, 11.4 M yen a year. The search ends 52 % short of its upper bound (23.7 M yen a year), so a better plan may exist.

| Kind | Users | Heat (MWh/yr) | Supply (°C) | Own heat pump: electricity (yen/MWh) | Own heat pump: annuity (yen/MWh) | Most it can pay, kerosene 115 yen/L (yen/MWh) | Most it can pay, kerosene 156.8 yen/L (yen/MWh) | Window opens above (yen/L of kerosene) |
|---|---|---|---|---|---|---|---|---|
| Pool, sports centre | 3 | 2,397 | 40 | 3,125 | 2,632 | 8,191 | 13,260 | 108 |
| Public building | 5 | 2,005 | 45 | 3,143 | 5,196 | 5,609 | 10,678 | 129 |
| Hotel | 2 | 1,996 | 60 | 5,253 | 2,634 | 6,061 | 11,131 | 126 |
| Hospital | 1 | 1,499 | 60 | 5,253 | 4,691 | 4,004 | 9,073 | 143 |
| School | 2 | 496 | 45 | 3,143 | 5,251 | 5,554 | 10,623 | 130 |

Pipes 6.0 km, an investment of 1,209.5 M yen, 61.7 M yen a year; heat delivered 8,393 MWh a year. **The least price the network needs is 7,352 yen per MWh, or 60.6 yen per litre of kerosene.**

- **Pools and sports centres** have the widest window: at 40 °C their heat pumps run at a COP of 8. Their window opens above 108 yen per litre.
- **Hotels, public buildings and schools** follow at 126 to 130 yen per litre; **the hospital**, which needs 60 °C, at 143.
- At 115 yen per litre no window is open but the pools'; at 156.8 all are.

## 3. With users that need no heat pump

**The published plan** adds two assumed sites, a fish farm (5,000 MWh a year) and road heating in the port area (2,400 MWh). Both take the loop's heat at 22 and 25 °C without a heat pump. They carry 75.2 of the plan's 93.9 M yen a year at the mean kerosene price, and the heat they take through the same trunk pipes lowers the network's price for everyone.

| Kind | Users | Heat (MWh/yr) | Supply (°C) | Own heat pump: electricity (yen/MWh) | Own heat pump: annuity (yen/MWh) | Most it can pay, kerosene 115 yen/L (yen/MWh) | Most it can pay, kerosene 156.8 yen/L (yen/MWh) | Window opens above (yen/L of kerosene) |
|---|---|---|---|---|---|---|---|---|
| Fish farm (assumed) | 1 | 5,003 | 22 | 0 | 0 | 13,948 | 19,018 | 52 |
| Snow melting (assumed) | 1 | 2,400 | 25 | 0 | 0 | 13,948 | 19,018 | 52 |
| Pool, sports centre | 3 | 2,397 | 40 | 3,125 | 2,632 | 8,191 | 13,260 | 100 |
| Hotel | 2 | 1,996 | 60 | 5,253 | 2,634 | 6,061 | 11,131 | 117 |
| Public building | 4 | 1,604 | 45 | 3,143 | 5,196 | 5,609 | 10,678 | 121 |
| Hospital | 1 | 1,499 | 60 | 5,253 | 4,691 | 4,004 | 9,073 | 134 |
| School | 1 | 248 | 45 | 3,143 | 5,251 | 5,554 | 10,623 | 121 |

Pipes 7.8 km, an investment of 1,879.7 M yen, 95.9 M yen a year; heat delivered 15,147 MWh a year. **The least price the network needs is 6,331 yen per MWh, or 52.2 yen per litre of kerosene.** Every window of today's facilities opens about 8 yen per litre earlier than in section 2, because the network's price is lower by that much.

**A middle step.** A fish farm of 5,000 MWh a year is above anything documented in Hokkaido; the surplus-heat system of Shikaoi (a sturgeon farm and three other users) takes about 1,000 MWh a year ([input-evidence.md](input-evidence.md)). With the fish farm at that size, the plan keeps the road heating and also connects a new greenhouse site (assumed, 3,999 MWh a year at 45 °C, with a heat pump of its own): 14 users and 9.2 km of pipe, 2,274.2 M yen. The network then needs 7,662 yen per MWh, more than on today's facilities alone, because the plan builds more pipe. The greenhouse's own heat pump is costly too: its window opens only above 148 yen per litre. Still, the plan as a whole breaks even at about 118 yen per litre, lower than today's facilities alone: what lowers the break-even is the heat that the fish farm and the road heating take without a heat pump.

## 4. Three steps of demand

| Step | Users | Pipes (km) | Heat (MWh/yr) | Least price the network needs (yen/MWh) | Per litre of kerosene (yen) | Breaks even above (yen/L of kerosene) | Surplus at 115 yen/L (M yen/yr) | at 135.9 | at 156.8 |
|---|---|---|---|---|---|---|---|---|---|
| Today's facilities alone | 13 | 6.0 | 8,393 | 7,352 | 60.6 | 125 | −10.0 | 11.3 | 32.6 |
| + road heating, a fish farm of 1,000 MWh a year and a new greenhouse site (all assumed) | 14 | 9.2 | 15,143 | 7,662 | 63.2 | 118 | −6.0 | 32.4 | 70.7 |
| The published plan (fish farm 5,000 MWh a year) | 13 | 7.8 | 15,147 | 6,331 | 52.2 | 85 | 55.5 | 93.9 | 132.3 |

The steps are the demand outlook in its simplest form. The kerosene price at which the whole plan pays falls from step to step, because more of the heat goes to users that need no heat pump. The network's price per MWh does not fall in the same way: it falls when added heat flows through pipes that are built anyway, as in the published plan, and it rises when the plan builds more pipe to reach more users, as in the middle step. **A subsidy also lowers the break-even:** with a third of the pipes and heat pumps paid by a subsidy, the plan on today's facilities breaks even at about 94 yen per litre instead of 125 (a rough figure: the plan is kept, not optimized again). The national subsidy for zero-emission data centers (fiscal 2026) does not list waste-heat supply among its items ([data-sources.md](data-sources.md)).

## 5. CO₂ and the fish farm

The model counts the CO₂ of the kerosene replaced, less that of the heat pumps' electricity. It does not count a user's other emissions, such as those of a fish farm's feed or of the pumps that move its water, so connecting to the network does not make a user zero-emission: what the network replaces is the fuel for heating. This holds for every number on this page and in the README.

## 6. What a business plan still needs

The window says that a price exists. It does not say who takes the investment and the risk.

- **Who builds, owns and runs the pipes:** a data-center operator, a heat company, the town, or several together.
- **The price each facility pays for kerosene today,** from its bills; this page uses two prices for all.
- **Contracts against the data centers' load.** The plan's scenarios vary the IT load; a contract has to say what happens when a data center's heat falls short. The model's cautious answer is its robust plan, with 7 users.
- **Costs outside the model:** any payment to the data centers for their heat, equipment at the data centers, operation and maintenance, pumping, metering and billing.
- **Users that need no heat pump** (section 3): who they could be, at what size, and on what land.

## 7. Limits

- **One price for all users.** Prices by kind, or a fixed charge plus a price per MWh, move the split between users and network, not the total.
- **Kinds, not facilities.** Each facility's demand is an estimate by type (a hospital 1,500 MWh a year, a hotel 1,000, a pool 800, a public building 400, a school 250); real bills will differ.
- **Expected deliveries.** The windows use each user's expected heat over the scenarios.
- **The plans are not certified optimal.** The searches end 52 % (today's facilities), 37 % (the middle step) and 17 % (the published plan) short of their upper bounds.
- **Heat above 60 °C is counted as servable.** The answer in short says what changes without it.
- **The heat pumps are the users'.** If the network owned them, the same costs would sit on the network's side of the window.

## 8. Reproduce

```
uv run python scripts/export_heat_network_v2.py     # the published plans, if out/heat_network_v2/plans.json is missing
uv run python scripts/export_heat_business.py       # the plan on today's facilities and the middle step (a few minutes)
uv run python scripts/heat_business.py              # the tables of this page (--lang ja for Japanese headings)
```

The calculation is `src/dcopt/heat/business.py`; `tests/test_heat_business.py` checks it by hand on a small plan and, when the exports are present, that this page quotes its figures.
