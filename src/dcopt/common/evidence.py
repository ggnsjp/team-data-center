"""What published sources say about each input of the models, in Japanese and English.

docs/data-sources.md lists every value with its source or marks it as an assumption. This module
goes one step further for the assumptions: for each one it records the range found in published
sources, how the model's value sits in that range, and how far the published results move when the
value moves to the end of the range (experiments/input_sensitivity, experiments/heat_loss_check).

docs/input-evidence.md and docs/input-evidence.ja.md are written from this file:

    uv run python -m dcopt.common.evidence --write

tests/test_evidence.py keeps the two pages current and checks that every assumption of the
heat-network model has an entry here.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAGES = {"en": ROOT / "docs" / "input-evidence.md", "ja": ROOT / "docs" / "input-evidence.ja.md"}
CHECKED = "2026-11-26"
CHECKED_LAST = "2026-11-28"   # the entry on heat above 60 C

# how the model's value sits against the published ones: (Japanese, English)
VERDICT = {
    "measured": ("公表された実測値", "published measurement"),
    "inside": ("公表値の範囲内", "inside the published range"),
    "cautious": ("範囲内（控えめな側）", "inside the range, on the cautious side"),
    "optimistic": ("範囲内（楽観的な側）", "inside the range, on the optimistic side"),
    "low": ("公表値より低い", "below the published range"),
    "high": ("公表値より高い", "above the published range"),
    "none": ("公表値が見つからない", "no published value found"),
    "missing": ("モデルに入っていない", "not in the model"),
}
THEMES = {
    1: ("テーマ1：排熱の導管網", "Theme 1: waste-heat networks"),
    3: ("テーマ3：立地", "Theme 3: siting"),
    4: ("テーマ4：再エネの一致", "Theme 4: renewable matching"),
}


@dataclass(frozen=True)
class Item:
    theme: int
    keys: tuple[str, ...]              # rows of dcopt.heat.network.assumptions_table this covers (may be empty)
    name: tuple[str, str]              # (Japanese, English)
    model: tuple[str, str]             # the value in the model
    published: tuple[str, str]         # what published sources give
    verdict: str | tuple[str, str]     # a key of VERDICT, or its own (Japanese, English) wording
    effect: tuple[str, str]            # what moving the input does to the published result ("" when not computed)
    sources: tuple[tuple[str, str], ...]   # (title, URL), each opened and checked on CHECKED


S_HANDBOOK = ("Planungshandbuch Thermische Netze, Version 2.0 (EnergieSchweiz / Bundesamt für Energie, 2025)",
              "https://pubdb.bfe.admin.ch/de/publication/download/12410")
S_GROUND = ("八鍬利助 (1940). 札幌の地温に就て. 気象集誌 第2輯 18(1)",
            "https://www.jstage.jst.go.jp/article/jmsj1923/18/1/18_1_7/_pdf")
S_THESIS = ("橘雅哉 (2023). 小規模温水2管式地域熱供給配管網の経済的最適化に関する研究. 横浜国立大学 博士論文",
            "https://ynu.repo.nii.ac.jp/record/12712/files/tachibana_masaya-thesis.pdf")
S_DEFLATOR = ("国土交通省. 建設工事費デフレーター（2020年度基準）",
              "https://www.mlit.go.jp/statistics/details/content/002045708.pdf")
S_APPRAISAL = ("国土交通省 (2025). 公共事業評価の費用便益分析に関する技術指針（共通編）",
               "https://www.mlit.go.jp/tec/hyouka/public/250918_shishin/shishin/shishin250918.pdf")
S_GREENHOUSE = ("北海道立総合研究機構 北方建築総合研究所 (2017). 北海道における農業用温室を対象とした施設内環境解析及び"
                "構造形式に関する研究. 調査研究報告 No.376", "https://www.hro.or.jp/upload/22993/376.pdf")
S_ROAD = ("札幌市建設局土木部雪対策室. ロードヒーティングによる冬季路面管理におけるコスト縮減の取り組み",
          "https://www.hrr.mlit.go.jp/yukimirai-toyama/happyousann/03_rodo.pdf")
S_ROAD_HOURS = ("北海道立工業試験場. 2分割制御方式によるロードヒーティングシステムの開発. 報告 No.295",
                "https://www.hro.or.jp/upload/27505/0302TF0130.pdf")
S_SHIKAOI = ("北海道鹿追町 (2023). 再生可能エネルギーを活用したまちづくり：鹿追町環境保全センターの取組み",
             "https://www.env.go.jp/seisaku/list/ondanka_saisei/lowcarbon-h2-sc/events/PDF/230711_3_4.pdf")
S_LEGIONELLA = ("厚生労働省告示第264号. レジオネラ症を予防するために必要な措置に関する技術上の指針",
                "https://www.mhlw.go.jp/content/10900000/001492168.pdf")
S_HOSPITAL_HEAT = ("黒田英男・河村貢・浅谷貴樹・馳平心 (2009). 近年の総合病院におけるエネルギー消費実態調査. 空気調和・衛生工学会大会 "
                   "学術講演論文集 2009.2, 1159-1162",
                   "https://doi.org/10.18948/shasetaikai.2009.2.0_1159")
S_CBECS = ("U.S. Energy Information Administration (2022). 2018 Commercial Buildings Energy Consumption Survey, table E1: "
           "major fuels consumption by end use",
           "https://www.eia.gov/consumption/commercial/data/2018/ce/pdf/e1.pdf")
S_JRC_HEAT = ("Pardo, N., Vatopoulos, K., Krook-Riekkola, A., Moya, J.A., Perez, A. (2012). Heat and cooling demand and "
              "market perspective. JRC Report EUR 25381 EN, table 3.2.a",
              "https://publications.jrc.ec.europa.eu/repository/bitstream/JRC70962/ldna25381enn.pdf")
S_OCCTO = ("電力広域的運営推進機関 (2026). 送変電設備の標準的な単価の見直しについて（第11回 計画評価及び検証小委員会 資料1）",
           "https://www.occto.or.jp/assets/iinkai/kouikikeitouseibi_hyouka/11/hyouka_11_01_01.pdf")
S_WAHLROOS = ("Wahlroos, M., Pärssinen, M., Manner, J., Syri, S. (2017). Utilizing data center waste heat in district heating. "
              "Energy, 140, 1228-1238", "https://acris.aalto.fi/ws/portalfiles/portal/17305461/1_s2.0_S0360544217314548_main.pdf")
S_YUAN = ("Yuan, X., et al. (2023). Waste heat recoveries in data centers: A review. Renewable and Sustainable Energy Reviews, 188",
          "https://acris.aalto.fi/ws/portalfiles/portal/124210750/1_s2.0_S1364032123006342_main.pdf")
S_SITRA = ("Sitra (2019). District heating from data centre waste heat, Mäntsälä",
           "https://arkisto.sitra.fi/en/cases/district-heating-from-data-centre-waste-heat-mantsala/")
S_DEA = ("Danish Energy Agency and Energinet (2026). Technology Data: Generation of Electricity and District Heating, chapter 40 Heat pumps",
         "https://ens.dk/media/8614/download")
S_HEATING_VALUE = ("資源エネルギー庁 (2025). エネルギー源別標準発熱量・炭素排出係数（2023年度改訂）の解説",
                   "https://www.enecho.meti.go.jp/statistics/total_energy/pdf/shv2023_cmt.pdf")
S_HEAVY_OIL = ("資源エネルギー庁 (2026). 石油製品価格調査 A重油納入価格調査（令和8年9月分）",
               "https://www.enecho.meti.go.jp/statistics/petroleum_and_lpgas/pl007/xlsx/261030a.xlsx")
S_TARIFF = ("北海道電力 (2026). 電気料金の見直しについて（2026年11月1日実施、高圧・特別高圧）",
            "https://www.hepco.co.jp/hokudengas/pdf/price_revise_261101.pdf")
S_JDCC = ("日本データセンター協会 (2026). データセンター・電力問題（第10回 次世代電力系統ワーキンググループ 資料1-1）",
          "https://www.meti.go.jp/shingikai/enecho/denryoku_gas/saisei_kano/smart_power_grid_wg/pdf/010_01_01.pdf")
S_IEA = ("International Energy Agency (2025). Energy and AI, table A.1",
         "https://build-up.ec.europa.eu/system/files/2025-04/PChtNmAZVk_11_04_2025_145800.pdf")

S_RECORDS = ("北海道電力ネットワーク. 北海道エリアの需給実績（2024年4月以降は30分値）",
             "https://www.hepco.co.jp/network/con_service/public_document/supply_demand_results/index.html")
S_CURTAILMENT = ("資源エネルギー庁 (2026). 再生可能エネルギー出力制御の長期見通し等について（第12回 次世代電力系統ワーキンググループ 資料1-1）",
                 "https://www.meti.go.jp/shingikai/enecho/denryoku_gas/saisei_kano/smart_power_grid_wg/pdf/012_01_01.pdf")
S_GENERATION_COST = ("発電コスト検証ワーキンググループ (2025). 発電コスト検証に関するとりまとめ",
                     "https://www.enecho.meti.go.jp/committee/council/basic_policy_subcommittee/mitoshi/cost_wg/pdf/cost_wg_20250206_01.pdf")
S_STORAGE = ("経済産業省 (2025). 2024年度 定置用蓄電システム普及拡大検討会の結果とりまとめ",
             "https://www.meti.go.jp/shingikai/energy_environment/storage_system/pdf/20250307_1.pdf")

ITEMS: list[Item] = [
    # ------------------------------------------------------------------ theme 1: who takes the heat
    Item(1, (),
         ("仮定の施設（陸上養殖・道路融雪・温室の新設候補）", "Assumed sites (fish farm, road heating, new greenhouse sites)"),
         ("養殖1か所（年5,000 MWh）、道路融雪2か所（2万m²と3千m²）、温室の新設候補3か所（各4,000 MWh）",
          "one fish farm (5,000 MWh a year), two road-heating areas (20,000 and 3,000 m2), three new greenhouse sites "
          "(4,000 MWh each)"),
         ("いまは存在しない施設。公表中の計画が届ける熱（年15,100 MWh）の49 %は、養殖（33 %）と道路融雪（16 %）の2か所向け",
          "sites that do not exist today. Of the heat the published plan delivers (15,100 MWh a year), 49 % goes to two of "
          "them: the fish farm (33 %) and one road-heating area (16 %)"),
         ("仮定（存在しない施設）", "assumptions (the sites do not exist)"),
         ("養殖だけ外すと純便益は93.8から11.4（導管はそのまま）〜18.1（計画し直し）。仮定の施設をすべて外して計画し直すと11.4"
          "（13か所、6.0 km、百万円/年）",
          "without the fish farm the net benefit falls from 93.8 to 11.4 (pipes kept) or 18.1 (plan made again) M yen a "
          "year; without any assumed site the best plan found is worth 11.4 (13 sites, 6.0 km)"),
         ()),
    Item(1, (),
         ("陸上養殖の需要（仮定の施設）", "Fish-farm demand (an assumed site)"),
         ("1施設で年5,000 MWh", "5,000 MWh a year for one farm"),
         ("鹿追町の余剰熱利用（チョウザメの飼育を含む4施設）は全体で約2,400 Mcal/日、年に約1,000 MWh",
          "the surplus-heat system of Shikaoi (a sturgeon farm and three other users) takes about 2,400 Mcal a day in all, "
          "about 1,000 MWh a year"),
         "high",
         ("年1,000 MWhなら純便益は93.8から27.9〜32.4（百万円/年）、500 MWhなら19.6〜25.7",
          "at 1,000 MWh a year the net benefit falls from 93.8 to 27.9-32.4 M yen a year; at 500 MWh to 19.6-25.7"),
         (S_SHIKAOI,)),
    Item(1, (),
         ("道路融雪（ロードヒーティング）の需要", "Snow-melting (road heating) demand"),
         ("年0.12 MWh/m²（降雪1 cmあたり0.25 kWh/m² × 479 cm）", "0.12 MWh/m2 a year (0.25 kWh/m2 per cm of snowfall x 479 cm)"),
         ("札幌市の車道の設計熱量は250 W/m²。通電600時間（北海道立工業試験場の報告の想定）で年0.15 MWh/m²",
          "Sapporo designs roadways for 250 W/m2; over 600 hours of operation (the figure assumed in a report of the "
          "Hokkaido Industrial Research Institute) that is 0.15 MWh/m2 a year"),
         "low",
         ("年0.20 MWh/m²なら純便益は93.8から119.9（面積2万m²は仮定のまま）",
          "at 0.20 MWh/m2 the net benefit rises from 93.8 to 119.9 M yen a year (the area of 20,000 m2 stays an assumption)"),
         (S_ROAD, S_ROAD_HOURS)),
    Item(1, (),
         ("温室の暖房需要", "Greenhouse heat demand"),
         ("床面積あたり年0.40 MWh/m²（15 ℃以上を保つ想定）", "0.40 MWh per m2 of floor a year (kept above 15 C)"),
         ("旭川の標準年・設定15 ℃の計算で、連棟ハウス0.21、単棟パイプハウス0.35 MWh/m²（747〜1,243 MJ/m²）。札幌の気候ではこれより"
          "小さい",
          "calculated for Asahikawa's standard year at 15 C: 0.21 (multi-span houses) to 0.35 MWh/m2 (single-span pipe "
          "house), 747 to 1,243 MJ/m2; less in Sapporo's climate"),
         "high",
         ("公表中の計画は温室をつないでいないので、0.25や0.17に下げても変わらない（現在の灯油価格での計画は、新設候補1か所をつなぐ）",
          "none on the published plan, which connects no greenhouse, at 0.25 or 0.17 (the plan at today's kerosene price "
          "connects one new greenhouse site)"),
         (S_GREENHOUSE,)),
    Item(1, (),
         ("建物の年間の熱需要（病院・ホテル・学校・公共施設・プール）", "Yearly heat demand of buildings (hospital, hotel, school, public building, pool)"),
         ("1施設あたり：病院1,500、ホテル1,000、プール・運動施設800、公共施設400、学校250 MWh（床面積は見ていない）",
          "per site: hospital 1,500, hotel 1,000, pool or sports centre 800, public building 400, school 250 MWh (floor "
          "area is not used)"),
         ("北海道の建物の熱用の燃料等の消費（床面積あたり、年）：病院1,137、ホテル・旅館928、スポーツ施設688、官公庁368、"
          "小・中学校214 MJ/m²。モデルの値は床面積3,000〜5,000 m²程度の建物に当たる",
          "fuel and purchased heat for heating and hot water in Hokkaido buildings, per m2 of floor a year: hospitals "
          "1,137, hotels 928, sports facilities 688, government offices 368, primary and junior high schools 214 MJ/m2. "
          "The model's values correspond to buildings of about 3,000 to 5,000 m2"),
         "inside",
         ("すべての需要を0.7倍にすると純便益は28.4〜51.5、1.3倍で144.8（百万円/年）",
          "with every demand at 0.7 times the net benefit is 28.4-51.5 M yen a year; at 1.3 times, 144.8"),
         (("北海道立総合研究機構 北方建築総合研究所 (2021). エネルギー消費量に関する各種資料の調査と活用方法に関する研究. "
           "調査研究報告 No.419", "https://www.hro.or.jp/upload/22812/419.pdf"),)),
    Item(1, (),
         ("需要の月別の形", "Monthly shape of demand"),
         ("暖房は札幌の平年値の暖房度日（建物は18 ℃、温室は15 ℃が基準）、融雪は月別の降雪量、プール・浴場は半分が一定",
          "degree days from Sapporo's climate normals (base 18 C for buildings, 15 C for greenhouses), monthly snowfall "
          "for snow melting, half flat for pools and baths"),
         ("設定15 ℃の温室の月別の計算（旭川）では、12〜2月が年間の64 %。モデルの形では58 %",
          "calculated monthly loads of a 15 C greenhouse (Asahikawa) put 64 % of the year in December to February; the "
          "model's shape puts 58 % there"),
         "inside",
         ("", ""),
         (S_GREENHOUSE,)),
    Item(1, ("peak", "alpha"),
         ("ピーク係数（導管とヒートポンプの大きさを決める）", "Peak factors (they size pipes and heat pumps)"),
         ("最大月の平均に対する設計ピーク：温室2.5、融雪3.0、病院1.8、学校・公共施設2.0、プール・浴場・ホテル1.4、養殖・工場1.2。"
          "導管はピークの100 %に合わせる",
          "design peak over the mean of the peak month: greenhouse 2.5, snow melting 3.0, hospital 1.8, schools and "
          "public buildings 2.0, pools, baths and hotels 1.4, fish farm and factory 1.2; pipes sized for the whole peak"),
         ("原資料で確かめた値はまだない。昼間だけ使う建物は、終日使う建物よりピークが鋭い",
          "no value checked against a source yet; buildings used only in the daytime have sharper peaks than those used "
          "round the clock"),
         "none",
         ("学校と公共施設を3.0にして計画し直すと純便益は88.8（百万円/年）",
          "with 3.0 for schools and public buildings and the plan made again, the net benefit is 88.8 M yen a year"),
         ()),
    # ------------------------------------------------------------------ theme 1: temperatures
    Item(1, ("supply_onsen", "supply_hospital", "supply_hotel", "supply_factory"),
         ("給湯に必要な温度（浴場・病院・ホテル・工場）", "Temperature needed for hot water (baths, hospitals, hotels, factory)"),
         ("60 ℃", "60 C"),
         ("貯湯槽の湯温は60 ℃以上、末端の給湯栓で55 ℃以上（レジオネラ症の予防指針）。熱交換の温度差を見込むと60 ℃は下限。"
          "病院の蒸気（滅菌・加湿）は100 ℃未満の排熱では賄えない",
          "stored hot water at 60 C or more and 55 C or more at the tap (Legionella guideline); with an allowance for the "
          "heat exchanger 60 C is the minimum. Steam for hospitals (sterilizing, humidifying) cannot come from heat below 100 C"),
         "inside",
         ("", ""),
         (S_LEGIONELLA,)),
    Item(1, (),
         ("60 ℃を超える熱の割合（病院・ホテル・工場）", "Share of heat above 60 C (hospitals, hotels, factories)"),
         ("0 %：年間の熱需要のすべてを60 ℃の温水で賄えるとしている", "0 %: the whole yearly heat demand is taken as servable with water at 60 C"),
         ("病院：蒸気が熱の49 %（関東・北陸・関西の総合病院5件の実測、2007〜08年。暖房303、給湯91、蒸気383 MJ/m²年。給湯を文献値の335にすると37 %。"
          "蒸気には加湿も含む）。ホテル：厨房が暖房・給湯・厨房の26 %（米国の宿泊施設、2018年。洗濯の蒸気は分かれていない）。"
          "食品工場：100〜400 ℃の熱が有効熱の39 %（EU-27、2009年）。北海道のデータは見つからない",
          "hospitals: steam is 49 % of the heat (five general hospitals in Kanto, Hokuriku and Kansai, measured 2007-08: "
          "space heating 303, hot water 91, steam 383 MJ/m2 a year; 37 % with the paper's reference value of 335 for hot "
          "water; the steam includes humidification). Hotels: cooking is 26 % of space heating, water heating and cooking "
          "(US lodging, 2018; laundry steam is not separated). Food factories: heat at 100-400 C is 39 % of the useful "
          "heat (EU-27, 2009). No Hokkaido data found"),
         "low",
         ("病院37〜49 %、ホテル26 %、工場39 %を外すと、公表中の計画は導管をそのままで79.7〜81.7、計画し直すと88.2〜88.4"
          "（病院はつながらず、ホテルは1件。百万円/年）。今ある施設だけの計画は、導管をそのままで−0.7〜−2.7、計画し直すと"
          "プール2件・1.5 kmの7.2",
          "without 37-49 % for hospitals, 26 % for hotels and 39 % for factories, the published plan is worth 79.7-81.7 "
          "with its pipes kept and 88.2-88.4 made again (the hospital no longer connects, one hotel does; M yen a year). "
          "The plan on today's facilities alone loses 0.7-2.7 with its pipes kept; made again, it is two pools and 1.5 km, "
          "7.2"),
         (S_HOSPITAL_HEAT, S_CBECS, S_JRC_HEAT)),
    Item(1, ("supply_snow",),
         ("道路融雪に必要な温度", "Temperature needed for snow melting"),
         ("25 ℃", "25 C"),
         ("鋼板パネルの温水式では、外気−5 ℃付近なら10 ℃程度の温水で融雪でき、地下水や下水の熱でも可能",
          "with steel-plate panels, water at about 10 C melts snow at about -5 C outside; ground water and sewage heat suffice"),
         "cautious",
         ("", ""),
         (("北海道立工業試験場 (1995). 鋼板を使用したロードヒーティングシステムの開発. 報告 No.294",
           "https://www.hro.or.jp/upload/27482/0302TE0110.pdf"),)),
    Item(1, ("supply_aquaculture",),
         ("陸上養殖に必要な温度", "Temperature needed for the fish farm"),
         ("22 ℃", "22 C"),
         ("鹿追町のチョウザメの飼育では、10 ℃の水を余剰熱で19 ℃まで温めている", "the sturgeon farm of Shikaoi warms water from 10 C to 19 C with surplus heat"),
         "inside",
         ("", ""),
         (S_SHIKAOI,)),
    Item(1, ("supply_greenhouse", "supply_new_greenhouse", "supply_school", "supply_public", "supply_pool"),
         ("暖房に必要な温度（温室・学校・公共施設・プール）", "Temperature needed for space heating (greenhouses, schools, public buildings, pools)"),
         ("温室・学校・公共施設45 ℃、プール40 ℃", "45 C for greenhouses, schools and public buildings; 40 C for pools"),
         ("原資料で確かめた値はまだない。低温で暖房するには、床暖房や大きな放熱器など、それに合った設備が要る",
          "no value checked against a source yet; heating at these temperatures needs suitable emitters (floor heating, "
          "large radiators)"),
         "none",
         ("", ""),
         ()),
    # ------------------------------------------------------------------ theme 1: the heat source and the fuel replaced
    Item(1, ("recovery", "waste_c", "network_c", "central_c"),
         ("回収できる排熱の割合と温度", "Recoverable share of the IT heat and its temperature"),
         ("IT電力の60 %を30 ℃で回収。低温ループは30 ℃、集中方式は60 ℃で送る",
          "60 % of the IT electricity, recovered at 30 C; the ambient loop runs at 30 C, the central network at 60 C"),
         ("上限は消費電力の97 %。空冷の運用例（フィンランド・マンツァラ）では約3分の1。温度は、空冷の戻り空気25〜47 ℃、"
          "リアドア方式の戻り水20〜30 ℃、液冷の戻り水50〜60 ℃",
          "the ceiling is 97 % of the power consumed; an operating air-cooled case (Mäntsälä, Finland) captures about a "
          "third. Temperatures: return air 25-47 C, return water of rear-door cooling 20-30 C, of liquid cooling 50-60 C"),
         "inside",
         ("0.33で純便益は93.8から84.3（百万円/年）。0.9では変わらない（排熱は余っている）",
          "at 0.33 the net benefit goes from 93.8 to 84.3 M yen a year; at 0.9 nothing changes (waste heat is in surplus)"),
         (S_WAHLROOS, S_SITRA, S_YUAN)),
    Item(1, (),
         ("データセンターが実際に使う電力", "Power actually drawn by the data centers"),
         ("公表または仮定のIT負荷を、1年を通して一定に使う（低・高の2水準のシナリオ）",
          "the stated or assumed IT load, drawn evenly all year (two scenario levels, low and high)"),
         ("一般のデータセンターは「基本的に24時間365日変動のない電力利用」（スパコン・AI学習用は別）。ただし使う電力は、"
          "設備容量の約半分：世界平均の負荷率49 %（2024年）、国内のハウジングはラックの電力の50 %",
          "ordinary data centers draw power \"basically without variation, 24 hours a day and 365 days a year\" "
          "(supercomputers and AI training apart). But they use about half of their capacity: a world load factor of "
          "49 % in 2024; about 50 % of rack power in Japanese colocation"),
         ("一定という形は妥当、水準は公表値より高い", "the constant shape is supported; the level is above published values"),
         ("半分にすると純便益は93.8から80.4（百万円/年）", "at half the load the net benefit goes from 93.8 to 80.4 M yen a year"),
         (S_JDCC, S_IEA)),
    Item(1, ("carnot_eff", "cop_cap"),
         ("ヒートポンプの効率", "Heat-pump efficiency"),
         ("COP＝カルノーの理論値の50 %、上限8", "COP = 50 % of the Carnot value, capped at 8"),
         ("大型ヒートポンプの実際のCOPは理論値（ローレンツ）の40〜60 %。データセンターのヒートポンプのCOPは3.0〜6.3",
          "real COP of large heat pumps: typically 40 to 60 % of the theoretical (Lorenz) value; heat pumps at data "
          "centers reach COP 3.0 to 6.3"),
         "inside",
         ("0.43で純便益は89.8（百万円/年）。0.6では計画はほぼ変わらない",
          "at 0.43 the net benefit is 89.8 M yen a year; at 0.6 the plan hardly changes"),
         (S_DEA, S_WAHLROOS)),
    Item(1, ("power",),
         ("ヒートポンプの電気代", "Electricity price for the heat pumps"),
         ("25円/kWh", "25 yen/kWh"),
         ("北海道電力の高圧（2026年11月から、税込）：電力量料金21.69〜23.47円/kWh、基本料金2,970円/kW・月。"
          "これに燃料費等調整と再エネ賦課金が加わる",
          "Hokkaido Electric Power, high voltage, from November 2026 (tax included): energy charge 21.69 to 23.47 yen/kWh "
          "and basic charge 2,970 yen per kW a month; the fuel-cost adjustment and the renewable-energy levy come on top"),
         "low",
         ("30円/kWhで純便益は87.4、34円/kWhで82.4〜83.0（百万円/年）", "at 30 yen/kWh the net benefit is 87.4 M yen a year; at 34 yen/kWh 82.4-83.0"),
         (S_TARIFF,)),
    Item(1, ("boiler_eff",),
         ("灯油1 Lから得られる熱（発熱量とボイラー効率）", "Heat from a litre of kerosene (heating value and boiler efficiency)"),
         ("9.7 kWh/L（低位発熱量と表記）× 効率0.85 ＝ 8.2 kWh", "9.7 kWh/L (labelled as the lower heating value) x 0.85 = 8.2 kWh"),
         ("標準発熱量は高位36.60 MJ/L（10.17 kWh/L）、低位34.38 MJ/L（9.55 kWh/L）。9.7はどちらでもない。"
          "8.2 kWhは、高位基準で効率81 %、低位基準で86 %に当たる",
          "the standard heating values are 36.60 MJ/L gross (10.17 kWh/L) and 34.38 MJ/L net (9.55 kWh/L); 9.7 is "
          "neither. 8.2 kWh corresponds to an efficiency of 81 % on the gross basis or 86 % on the net basis"),
         ("発熱量の表記が不正確。効率と掛けた値は確認が必要", "the label of the heating value is inexact; the product still needs a measured boiler efficiency"),
         ("灯油1 Lの熱が7.6 kWhなら純便益は115.0、8.7 kWhなら80.7（百万円/年）",
          "with 7.6 kWh of heat per litre the net benefit is 115.0 M yen a year; with 8.7 kWh, 80.7"),
         (S_HEATING_VALUE,)),
    Item(1, ("kerosene",),
         ("灯油の価格（2つのシナリオ）", "Kerosene price (two scenarios)"),
         ("115円/L（大口を想定した控えめな値）と156.8円/L（北海道の店頭価格、2026年11月16日）",
          "115 yen/L (a cautious value for bulk buyers) and 156.8 yen/L (retail in Hokkaido, 16 November 2026)"),
         ("産業用の灯油の公的な価格調査はない。近い油種のA重油は、北海道の大型ローリー納入で124.4円/L（2026年9月、税抜。税込136.8円/L）",
          "there is no official price series for industrial kerosene. The nearest product, heavy oil A delivered by large "
          "lorry in Hokkaido, cost 124.4 yen/L in September 2026 before tax (136.8 with tax)"),
         ("低いほうのシナリオは現在の大口価格より低い（控えめ）", "the low scenario is below today's bulk prices (cautious)"),
         ("低いほうを135円/Lにすると純便益は112.2（百万円/年）", "with 135 yen/L in the low scenario the net benefit is 112.2 M yen a year"),
         (S_HEAVY_OIL,)),
    # ------------------------------------------------------------------ theme 1: the network
    Item(1, ("loss",),
         ("導管の熱損失", "Network heat loss"),
         ("運ぶ熱に対する一律の割合：低温ループ2 %、集中方式（60 ℃）8 %",
          "a flat share of the heat carried: 2 % for the ambient loop, 8 % for the central 60 C network"),
         ("損失は運ぶ熱ではなく、管の長さ・断熱・温度で決まる（1 mあたり U ×（水の平均温度 − 地温））。公表の係数と札幌の地温で"
          "公表中の計画の導管そのものを計算すると、届ける熱の2.7〜4.5 %（低温ループ）、6.2〜10.6 %（集中方式）",
          "the loss depends on length, insulation and temperatures, not on the heat carried (per metre: U x (mean water "
          "temperature - ground temperature)). With published coefficients and Sapporo's ground temperature, the published "
          "plan's own pipes lose 2.7 to 4.5 % of the heat delivered (ambient loop) and 6.2 to 10.6 % (central network)"),
         ("低温ループは公表値より低い、集中方式は範囲内", "ambient loop: below the published range; central network: inside"),
         ("低温ループを3.7〜4.5 %にすると純便益は93.8から92.0（百万円/年）。排熱が余っているので影響は小さい",
          "at 3.7 to 4.5 % for the ambient loop the net benefit goes from 93.8 to 92.0 M yen a year: waste heat is in "
          "surplus, so the effect is small"),
         (S_HANDBOOK, S_GROUND)),
    Item(1, ("pipe_cost",),
         ("導管の単価（往復2本、施工込み）", "Pipe cost per metre of route (two pipes, installed)"),
         ("DN50 8.4万円/m〜DN250 33.3万円/m（2019年の見積もりを直線で結び、間接費33 %を加算）",
          "DN50 84,000 to DN250 333,000 yen/m (a straight line through 2019 quotes, plus 33 % overhead)"),
         ("2019年の価格では国内の範囲内（100A：緑地13.3万円/m〜車道18.6万円/m）。建設工事費デフレーターは2019年度から2025年度に"
          "約22 %上昇",
          "inside the Japanese range in 2019 prices (100A: 133,000 yen/m in green areas to 186,000 under a roadway). The "
          "construction cost deflator rose about 22 % from fiscal 2019 to fiscal 2025"),
         ("2019年の価格では範囲内、現在の物価では低い", "inside the range in 2019 prices; low at today's prices"),
         ("1.22倍（2025年度の物価）で純便益は93.8から72.7（導管はそのまま）〜76.6（計画し直すと10か所・4.3 km）。1.5倍で45.8〜63.5",
          "at 1.22 times (fiscal 2025 prices) the net benefit falls from 93.8 to 72.7 (pipes kept) or 76.6 (plan made "
          "again: 10 sites, 4.3 km); at 1.5 times to 45.8-63.5"),
         (S_THESIS, S_DEFLATOR)),
    Item(1, ("pipe_cap", "dT"),
         ("導管の容量（設計流速と往き還りの温度差）", "Pipe capacity (design velocity and supply-return difference)"),
         ("流速1.0 m/s（DN50）〜2.2 m/s（DN250）、温度差10 K（低温ループ）／30 K（集中方式）",
          "1.0 m/s (DN50) to 2.2 m/s (DN250); 10 K (ambient loop) or 30 K (central network)"),
         ("区間ごとの設計では250〜300 Pa/m、長い区間の確認では150〜200 Pa/mが目安",
          "design rule: 250 to 300 Pa/m for single sections, 150 to 200 Pa/m as the check over longer runs"),
         "cautious",
         ("", ""),
         (S_HANDBOOK,)),
    Item(1, ("years",),
         ("導管の年数と割引率", "Pipe life and discount rate"),
         ("30年、3 %", "30 years, 3 %"),
         ("導管を含む配管網の計算上の使用年数は40年（スイスの計画手引き）、鋼管の償却年数40年（国内の学位論文）。"
          "公共事業評価の社会的割引率は4 %（比較のための参考値を置いてよい）",
          "service life for economic calculation of a distribution network with its pipes: 40 years (Swiss planning "
          "handbook); 40 years for steel pipes in the Japanese thesis. The social discount rate for public project "
          "appraisal in Japan is 4 % (reference values may be set for comparison)"),
         "inside",
         ("寿命40年で純便益は108.4。割引率4 %で78.3〜79.0、1 %で約122（百万円/年）",
          "with a life of 40 years the net benefit is 108.4 M yen a year; at a 4 % rate 78.3-79.0, at 1 % about 122"),
         (S_HANDBOOK, S_THESIS, S_APPRAISAL)),
    Item(1, ("hp_years",),
         ("ヒートポンプの年数", "Heat-pump life"),
         ("20年", "20 years"),
         ("熱源設備の計算上の使用年数は20年（スイスの計画手引き）", "service life for economic calculation of heat generation plant: 20 years (Swiss planning handbook)"),
         "inside",
         ("15年で純便益は86.8、25年で97.9（百万円/年）", "at 15 years the net benefit is 86.8 M yen a year; at 25 years 97.9"),
         (S_HANDBOOK,)),
    Item(1, (),
         ("貯湯槽（蓄熱）", "Hot-water storage"),
         ("なし（需要は月別、導管は設計ピークで決める）", "none (monthly demand; pipes sized for the design peak)"),
         ("昼夜の需要のずれは貯湯槽で吸収できる。モデルに入れると、ピーク係数で大きく取っている導管とヒートポンプを小さくできる",
          "a tank smooths the day-night mismatch; in the model it would let pipes and heat pumps be smaller than the peak "
          "factors now require"),
         "missing",
         ("", ""),
         ()),
    # ------------------------------------------------------------------ theme 3
    Item(3, (),
         ("系統への接続線の費用", "Cost of the grid connection line"),
         ("66 kVの変電所へは4.1億円/km、187 kVへは5.1億円/km（公表値の範囲の中央。アプリで変更可）。以前は仮の値として1億円/kmを使っていた",
          "410 M yen per km to a 66 kV substation and 510 M yen per km to a 187 kV one (the middle of the published "
          "ranges; a slider in the app). An earlier version used a placeholder of 100 M yen per km"),
         ("標準的な単価（2026年3月公表、土地代を除く）：鉄塔2回線の架空線で、66・77 kV級1.4〜6.7億円/km、154・187 kV級1.9〜8.3億円/km。"
          "1回線はその80〜95 %",
          "standard unit costs (published March 2026, land excluded): two-circuit tower lines cost 140 to 670 M yen/km in "
          "the 66/77 kV class and 190 to 830 M yen/km in the 154/187 kV class; one circuit is 80 to 95 % of that"),
         "inside",
         ("66 kVへの接続費を引いても排熱の価値が残る候補地は、範囲の下端（1.4億円/km）で6か所、中央で2か所（最良地点の残りは15.3百万円/年）、"
          "上端（6.7億円/km）で0か所。以前の1億円/kmでは9か所（同37.9）。187 kVへの接続では、範囲のどこでも残る候補地はない",
          "sites whose heat value exceeds a 66 kV connection: 6 at the low end of the range (140 M yen/km), 2 at the "
          "middle (the best site keeps 15.3 M yen a year), none at the high end (670). With the earlier 100 M yen/km it "
          "was 9 sites (37.9). For a 187 kV connection no site does anywhere in the range"),
         (S_OCCTO,)),
    # ------------------------------------------------------------------ theme 4
    Item(4, (),
         ("エリアの需要と電源別の供給（30分値）", "Area demand and supply by source, 30-minute values"),
         ("2024年度・2025年度、各17,520コマ。値は変えずに使用", "fiscal 2024 and 2025, 17,520 slots each, used unchanged"),
         ("送電端の実績（速報値）。欠けはなく、どのコマでも供給の合計が需要と一致する。実績から集計した太陽光・風力の抑制量"
          "（2024年度2.69 GWh・0.04 %、2025年度16.24 GWh・0.25 %）は、国の資料の値（269万kWh・0.04 %、1,624万kWh・0.25 %）と一致",
          "sending-end records (preliminary values); no gaps, and supply adds up to demand in every slot. The solar and wind "
          "curtailment summed from the records (2.69 GWh and 0.04 % in fiscal 2024, 16.24 GWh and 0.25 % in fiscal 2025) "
          "equals the government's figures (2.69 and 16.24 million kWh; 0.04 and 0.25 %)"),
         "measured",
         ("", ""),
         (S_RECORDS, S_CURTAILMENT)),
    Item(4, (),
         ("データセンターの負荷の形", "Shape of the data-center load"),
         ("1年を通して一定", "constant through the year"),
         ("一般のデータセンターは「基本的に24時間365日変動のない電力利用」（スパコン・AI学習用は別）。時間ごとの負荷を公表している"
          "商用データセンターは見つかっていない",
          "ordinary data centers draw power \"basically without variation, 24 hours a day and 365 days a year\" "
          "(supercomputers and AI training apart). No commercial data center was found that publishes its load by the hour"),
         "inside",
         ("一致率は負荷の大きさによらない（抑制分を使える割合だけが大きさで変わる）",
          "the matched share does not depend on the size of the load (only the share of curtailed output it can use does)"),
         (S_JDCC,)),
    Item(4, (),
         ("契約した太陽光・風力の発電の形", "Shape of the contracted solar and wind output"),
         ("エリア全体の太陽光・風力の実績と同じ形（30分ごと）", "the same as the area's whole solar and wind fleets, slot by slot"),
         ("実績から求めた値。1つの発電所はエリア全体より変動が大きいので、実際の契約の一致率はこれより低くなる",
          "derived from the records. One plant varies more than the whole area, so a real contract matches less"),
         ("実績から計算（楽観的な側）", "derived from the records (on the optimistic side)"),
         ("エリアの構成比で68〜69 %、太陽光だけで41 %、風力だけで72〜73 %", "68-69 % with the area's mix, 41 % with solar only, 72-73 % with wind only"),
         (S_RECORDS,)),
    Item(4, (),
         ("火力がこれ以上は下げられない出力", "Level below which thermal plants cannot turn down"),
         ("514 MW（2024年度）、540 MW（2025年度）。もう1つの場合として年間の最小値364 MW・325 MW",
          "514 MW (fiscal 2024) and 540 MW (fiscal 2025); second case: the lowest output of the year, 364 and 325 MW"),
         ("実績から求めた値：太陽光・風力が抑制されていたコマの火力出力のうち、下から10 %の位置。2025年度は火力が325〜2,104 MWの幅で"
          "抑制が起きており、エリア全体の余剰以外の理由も含まれるとみられる（実績には理由の記載がない）",
          "derived from the records: the 10th percentile of thermal output in the slots where solar or wind was curtailed. In "
          "fiscal 2025 curtailment occurred at thermal outputs between 325 and 2,104 MW, so causes other than an area-wide "
          "surplus seem to be included (the records do not give the cause)"),
         ("実績から計算", "derived from the records"),
         ("新しい発電所を建てる場合の火力の増減は、2つの下限で使用量の+0.2〜+2.4 %。太陽光・風力2倍のときの抑制は8〜12 %",
          "with new plants, thermal generation changes by +0.2 to +2.4 % of the energy used across the two floors; with "
          "twice the solar and wind, 8 to 12 % of their output is curtailed"),
         (S_RECORDS,)),
    Item(4, (),
         ("太陽光・風力の単価（LPの入力）", "Price of solar and wind energy (input of the linear program)"),
         ("太陽光10.9円/kWh、風力16.3円/kWh", "10.9 yen/kWh for solar, 16.3 yen/kWh for wind"),
         ("2023年に新設する場合の発電コスト（政策経費を含む）：事業用太陽光10.9円/kWh、陸上風力16.3円/kWh。政策経費を除くと10.0円と12.1円",
          "generation cost of a plant built in 2023, policy costs included: utility-scale solar 10.9, onshore wind 16.3 "
          "yen/kWh; 10.0 and 12.1 without policy costs"),
         "inside",
         ("", ""),
         (S_GENERATION_COST,)),
    Item(4, (),
         ("蓄電池の費用・寿命・効率（LPの入力）", "Battery cost, life and efficiency (inputs of the linear program)"),
         ("容量1 kWhあたり6万円、15年、往復効率85 %、容量は出力の3時間分以上", "60,000 yen per kWh of capacity, 15 years, 85 % round trip, at least 3 hours of its power"),
         ("補助事業での系統用蓄電システムの価格は平均5.4万円/kWh（2024年度、工事費は別）。寿命・効率・時間数は、原資料で確かめた値がまだない",
          "grid-scale battery systems in subsidy projects cost 54,000 yen/kWh on average (fiscal 2024, installation extra). "
          "No value checked against a source yet for the life, the efficiency and the duration"),
         ("価格は公表値にもとづく。ほかは仮定", "the price follows a published value; the rest are assumptions"),
         ("", ""),
         (S_STORAGE,)),
]


# what a reader should take away first: (Japanese, English), in order of weight
SUMMARY = [
    ("**仮定の施設が結果の大半を支えている。** 公表中の計画（純便益 年93.8百万円）が届ける熱の49 %は、仮定の養殖施設と道路融雪の2か所向け。"
     "仮定の施設をすべて外して計画し直すと、純便益は年11.4百万円（13か所、6.0 km）。養殖と融雪は22〜25 ℃で足り、排熱をヒートポンプなしで使える。"
     "既存の建物は45〜60 ℃が必要で、1件ごとにヒートポンプが要る。",
     "**The assumed sites carry most of the result.** Of the heat the published plan delivers (net benefit 93.8 M yen "
     "a year), 49 % goes to two assumed sites, a fish farm and a road-heating area. Without any assumed site the best "
     "plan found is worth 11.4 M yen a year (13 sites, 6.0 km). The fish farm and the road heating need only 22 to 25 C "
     "and take waste heat without a heat pump; existing buildings need 45 to 60 C and a heat pump each."),
    ("**需要の大きさがその次に効く。** すべての年間需要を0.7倍にすると28.4〜51.5、1.3倍で144.8。建物ごとの需要は床面積を使わない仮定で、"
     "公表されている原単位とは桁が合う程度の確認にとどまる。",
     "**The size of the demands comes next.** With every yearly demand at 0.7 times the net benefit is 28.4-51.5; at "
     "1.3 times, 144.8. The demand per building is an assumption that does not use floor area; published intensities "
     "confirm the order of magnitude and no more."),
    ("**費用は2019年の価格である。** 導管費を2025年度の物価（1.22倍）に直すと72.7〜76.6。割引率4 %で78.3〜79.0、導管の寿命40年で108.4。",
     "**Costs are in 2019 prices.** With pipe costs at fiscal 2025 prices (1.22 times) the net benefit is 72.7-76.6; "
     "at a 4 % discount rate 78.3-79.0; with a pipe life of 40 years 108.4."),
    ("**置き換える灯油の量と価格。** 灯油1 Lの熱が7.6〜8.7 kWhの範囲で115.0〜80.7、低いほうの灯油価格を135円/Lにすると112.2。"
     "電気代30〜34円/kWhで87.4〜82.4。",
     "**The kerosene replaced and its price.** Between 7.6 and 8.7 kWh of heat per litre the net benefit is 115.0 to "
     "80.7; with 135 yen/L in the low-price scenario 112.2; with electricity at 30 to 34 yen/kWh 87.4 to 82.4."),
    ("**排熱の量と熱損失の影響は小さい。** 排熱は余っているので、回収率0.33で84.3、データセンターの電力を半分にして80.4、"
     "熱損失を2 %から3.7〜4.5 %にして92.0。",
     "**The amount of waste heat and the heat loss matter least.** Waste heat is in surplus: a recovery share of 0.33 "
     "gives 84.3, half the data-center load 80.4, and a heat loss of 3.7 to 4.5 % instead of 2 % gives 92.0."),
]


# rows of assumptions_table that are devices of the computation, not inputs with a published value
NOT_INPUTS = {"tie"}


def covered_keys() -> set[str]:
    return {k for item in ITEMS for k in item.keys}


def render(lang: str) -> str:
    i = 0 if lang == "ja" else 1
    head = {
        "ja": ["# 入力の根拠：公表値との比較", "",
               f"モデルの入力のうち「仮定」としているものについて、公表されている値の範囲と、モデルの値がその中のどこにあるか、"
               f"値を範囲の端まで動かすと結果がどれだけ動くかをまとめます。出典は {CHECKED}〜{CHECKED_LAST} に原資料を開いて確認しました。"
               "すべての値の一覧は [data-sources.md](data-sources.md)（英語）にあります。", "",
               "このページは `src/dcopt/common/evidence.py` から作っています（`uv run python -m dcopt.common.evidence --write`）。"
               "[English](input-evidence.md)", ""],
        "en": ["# Evidence for the inputs: the model's values against published ones", "",
               f"For the inputs marked as assumptions: the range found in published sources, where the model's value sits "
               f"in it, and how far the results move when the value moves to the end of the range. Every source was opened "
               f"and checked between {CHECKED} and {CHECKED_LAST}. The list of all values is in [data-sources.md](data-sources.md).", "",
               "This page is written from `src/dcopt/common/evidence.py` (`uv run python -m dcopt.common.evidence --write`). "
               "[日本語](input-evidence.ja.md)", ""],
    }[lang]
    cols = {"ja": "| 入力 | モデルの値 | 公表されている値 | モデルの値の位置 | 結果への影響 | 出典 |",
            "en": "| Input | In the model | Published values | Where the model's value sits | Effect on the results | Sources |"}[lang]
    out = list(head)
    out += [{"ja": "## 結果をいちばん動かすもの（テーマ1）", "en": "## What moves the result most (theme 1)"}[lang], ""]
    out += [f"{n}. {line[i]}" for n, line in enumerate(SUMMARY, 1)]
    out += ["", {"ja": "数値は `experiments/input_sensitivity/run.py` と `experiments/heat_loss_check/run.py` によります。入力を1つずつ動かした結果で、"
                       "「a〜b」は、導管をそのままにした場合と計画し直した場合の幅です。",
                 "en": "The numbers come from `experiments/input_sensitivity/run.py` and `experiments/heat_loss_check/run.py`: "
                       "one input moved at a time; a range \"a-b\" spans the published pipes kept and the plan made again."}[lang], ""]
    for theme, names in THEMES.items():
        items = [x for x in ITEMS if x.theme == theme]
        if not items:
            continue
        out += [f"## {names[i]}", "", cols, "|---|---|---|---|---|---|"]
        refs: list[tuple[str, str]] = []
        for x in items:
            marks = []
            for s in x.sources:
                if s not in refs:
                    refs.append(s)
                marks.append(f"[{refs.index(s) + 1}]")
            verdict = VERDICT[x.verdict] if isinstance(x.verdict, str) else x.verdict
            out.append(f"| {x.name[i]} | {x.model[i]} | {x.published[i]} | {verdict[i]} | "
                       f"{x.effect[i] or '—'} | {' '.join(marks) or '—'} |")
        out.append("")
        out += [f"{n}. {title}. {url}" for n, (title, url) in enumerate(refs, 1)]
        out.append("")
    return "\n".join(out)


def write() -> None:
    for lang, path in PAGES.items():
        path.write_text(render(lang), encoding="utf-8")


def main(argv: list[str]) -> int:
    if "--write" in argv:
        write()
        return 0
    stale = [str(p) for lang, p in PAGES.items() if not p.exists() or p.read_text(encoding="utf-8") != render(lang)]
    print("stale: " + ", ".join(stale) if stale else "docs/input-evidence pages are current")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
