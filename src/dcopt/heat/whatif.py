"""The live what-if panel's vocabulary: the knobs the LLM may change, and nothing else.

The panel on the Warm Ishikari page takes free text in either language, asks the LLM to map
it onto THIS module's knob list, and clamps everything into the sliders' ranges before the
deterministic model re-runs. The LLM never computes results: it chooses inputs and explains
the numbers the model produced.
"""
import json
import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from dcopt.common import llm

M = 1e6
# UI limit, not a model parameter: a what-if is one or two sentences, and a cap keeps a pasted
# document out of the prompt (assumption: 500 characters is ample for either language)
MAX_QUESTION_CHARS = 500

# id, ja label, en label, kind, lo, hi, step, unit note for the prompt
KNOBS = [
    ("it_load_mw", "データセンターのIT負荷（MW）", "data-center IT load (MW)", "float", 2.0, 50.0, 1.0, "MW"),
    ("recovery", "回収できる廃熱の割合", "share of heat recovered", "float", 0.3, 0.9, 0.05, "0-1"),
    ("cop", "ヒートポンプのCOP", "heat pump COP", "float", 2.5, 6.0, 0.1, "-"),
    ("kerosene_yen_l", "灯油価格（円/L）", "kerosene price (yen/L)", "int", 70, 170, 5, "yen per litre"),
    ("power_yen_kwh", "電気料金（円/kWh）", "electricity price (yen/kWh)", "int", 10, 40, 1, "yen per kWh"),
    ("pipe_cost", "導管の工事費（万円/m）", "pipe cost (10k yen per m)", "int", 3, 30, 1, "10k yen per metre"),
    ("years", "償却年数", "lifetime (years)", "int", 15, 40, 5, "years"),
    ("rate", "割引率（%）", "discount rate (%)", "float", 0.0, 8.0, 0.5, "percent"),
    ("renewable_power", "ヒートポンプは再エネ電力", "heat pumps on renewable power", "bool", None, None, None, "-"),
    ("assumed_sites", "仮定の候補地も含める（温室新設・陸上養殖・融雪）", "include assumed sites", "bool", None, None, None, "-"),
    ("k_pipes", "候補の導管（近い順に何本）", "candidate pipes per site", "int", 2, 4, 1, "count"),
    ("carbon_yen_t", "炭素価格（円/t-CO2）", "carbon price (yen per t-CO2)", "int", 0, 20000, 500, "yen per tonne of CO2"),
    ("subsidy_pct", "設備費の補助率（%）", "investment subsidy (%)", "int", 0, 75, 1, "percent of the investment"),
]
BY_ID = {k[0]: k for k in KNOBS}

# the LLM returns place "random" when the user asks for a random data center; the app draws the rest
RANDOM_PLACES = ("random", "ランダム", "random place", "random location", "random lat long",
                 "おまかせ", "どこでも")


class WhatifError(ValueError):
    """The LLM's answer could not be turned into knob changes; safe to show in the UI."""


def parse_prompt(current: dict, text: str) -> str:
    """The single user message asking the model to map free text onto the knob list."""
    text = text[:MAX_QUESTION_CHARS]
    lines = [f"{i} ({ja} / {en}, {kind}"
             + (f", {lo}–{hi}" if lo is not None else "")
             + (f", now {current[i]}" if i in current else "") + ")"
             for i, ja, en, kind, lo, hi, _, _ in KNOBS]
    return ("You map a what-if request onto the knobs of a district-heat network model. "
            "Available knobs:\n" + "\n".join(lines) +
            f"\n\nRequest: {text}\n\n"
            "Return ONLY a JSON object {\"changes\": {<knob id>: <new value>}, "
            "\"new_data_center\": null, \"clarify\": \"\"}. "
            "Put the knobs the request implies in changes (empty object when it names none); the app "
            "clamps values into each knob's range, so return the value the request implies even when "
            "it is outside the range. A request may also PROPOSE BUILDING A NEW DATA CENTER: then set "
            "new_data_center to {\"mw\": <IT load in MW>, \"place\": <the place as the user wrote it, "
            "or 'lat,lon'>} and leave changes empty unless the request also names a knob. A request "
            "may also ask for a RANDOM data center: then return new_data_center {\"mw\": <number or "
            "null>, \"place\": \"random\"} and do not ask anything — the app samples the actual place "
            "and MW. When a new "
            "data center is named but its MW or place is missing, leave new_data_center null and ask "
            "ONE short question in clarify, in the language of the request — the same for a request "
            "that could mean several knobs (for example 'the price': kerosene or electricity?). "
            "Never invent other keys.")


def parse_patch(text: str, current: dict, *, llm_chat) -> dict:
    """Free text -> {"changes": {knob: clamped value}, "new_dc": {mw, place} | None, "clarify": str}.

    Raises WhatifError when the model's answer is unusable after one retry with a larger budget
    (the reasoning model sometimes spends its whole budget thinking before any content).
    """
    prompt = [{"role": "user", "content": parse_prompt(current, text)}]
    raw, err, parsed = "", None, None
    for budget in (2000, 4000):
        try:
            raw = llm_chat(prompt, max_tokens=budget, json_mode=True)
        except llm.LLMError as e:
            err = e
            continue
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise WhatifError("the model did not return a JSON object")
            if isinstance(parsed.get("changes"), dict):
                break
            raise WhatifError("the model did not return a changes object")
        except (ValueError, TypeError):
            err = WhatifError("the model did not return usable JSON")
    else:
        raise err or WhatifError("the model did not return usable JSON")
    out: dict = {}
    for key, value in parsed["changes"].items():
        if key not in BY_ID:
            continue
        _, _, _, kind, lo, hi, step, _ = BY_ID[key]
        if kind == "bool":
            out[key] = bool(value)
        else:
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            if lo is not None:
                v = min(max(v, lo), hi)
            if step:
                q = Decimal(str(step))
                v = float((Decimal(str(v)) / q).quantize(Decimal(1), rounding=ROUND_HALF_UP) * q)
            out[key] = int(v) if kind == "int" else v
    ndc = parsed.get("new_data_center")
    new_dc = None
    if isinstance(ndc, dict) and ndc.get("place") is not None:
        place = str(ndc["place"]).strip()
        mw_raw = ndc.get("mw")
        try:
            mw = float(mw_raw) if mw_raw is not None else None
        except (TypeError, ValueError):
            mw = None
        if place.lower() in RANDOM_PLACES:
            new_dc = {"mw": min(max(mw, 0.5), 100.0) if mw is not None else None, "place": place}
        elif mw is not None:
            new_dc = {"mw": min(max(mw, 0.5), 100.0), "place": place}
    clarify = parsed.get("clarify")
    return {"changes": out, "new_dc": new_dc, "clarify": str(clarify) if clarify else None}


def explain_prompt(question: str, changed: dict, before: dict, after: dict, lang: str) -> str:
    """The message asking the model to explain what the model computed, in the UI language.

    `before`/`after` are the page's own result summaries (same keys); the model may cite only
    these numbers and the knob diff. Keys outside the knob vocabulary (for example a proposed
    data center) pass through as-is.
    """
    ja = lang == "ja"
    if ja:
        head = ("あなたは熱供給ネットワークの結果を読み解く説明者です。以下の「変更」と「結果」だけ"
                "を使って、ユーザーの質問に3〜6文で答えてください。ここに挙げていない数値は"
                "絶対に使わないでください。数値は算用数字で書き、漢数字は使わないでください。")
    else:
        head = ("You explain what a district-heat network model computed. Use ONLY the numbers in "
                "'changes' and 'results' below; answer the user's question in 3-6 sentences and "
                "never introduce numbers of your own. Write every number in digits, not in words.")
    return head + "\n\n" + explain_facts(question, changed, before, after, lang)


def explain_facts(question: str, changed: dict, before: dict, after: dict, lang: str) -> str:
    """The part of the explain prompt that carries numbers: the question, the changes, the results."""
    question = question[:MAX_QUESTION_CHARS]
    ja = lang == "ja"
    diff = "\n".join(f"- {(BY_ID[k][1] if ja else BY_ID[k][2]) if k in BY_ID else k}: "
                     f"{before.get(k, '—')} → {v}" for k, v in changed.items()) \
        or ("- 変更なし / no change" if ja else "- no change")
    return (f"question: {question}\n\nchanges:\n{diff}\n\n"
            f"results: {json.dumps(after, ensure_ascii=False)}")


# a number not glued to a letter (so the 2 in CO2 is not a number), with optional thousands commas
_NUMBER = re.compile(r"(?<![A-Za-z0-9.])\d+(?:,\d{3})*(?:\.\d+)?")


# Numbers written in kanji. They count when a unit follows: without that rule 二酸化炭素, 一方 and 十分
# would be read as 2, 1 and 10. A kanji run right after digits is a unit (93.8百万円), and 万, 億 and 兆
# are units here as they are after digits (3億円 is read as 3), so 三億円 is read as 3 as well.
_KANJI_DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_KANJI_POWERS = {"十": 10, "百": 100, "千": 1000}
_KANJI_RUN = "〇零一二三四五六七八九十百千"
_KANJI_MEASURE = r"[万億兆円倍割%]|パーセント|ポイント|キロ|メートル|メガ|ギガ|トン|km|m(?![a-z])|MW|GW|kW"
_KANJI_COUNTER = r"[件個台社基棟本回年度つ人日]|[かカヶケ箇]所|[かカヶケ箇]月|時間|種類"
_KANJI_NUMBER = re.compile(rf"(?<![0-9.,{_KANJI_RUN}])([{_KANJI_RUN}]+)"
                           rf"(?:(?P<measure>{_KANJI_MEASURE})|(?P<counter>{_KANJI_COUNTER}))")
_KANJI_FRACTION = re.compile(rf"(?<![0-9.,{_KANJI_RUN}])([{_KANJI_RUN}]+)分の([{_KANJI_RUN}]+)")


def _kanji_value(run: str) -> int:
    """千二百三十四 -> 1234, 十二 -> 12, 二〇二五 -> 2025."""
    if not any(ch in _KANJI_POWERS for ch in run):
        return int("".join(str(_KANJI_DIGITS[ch]) for ch in run))
    total, digit = 0, None
    for ch in run:
        if ch in _KANJI_POWERS:
            total += (1 if digit is None else digit) * _KANJI_POWERS[ch]
            digit = None
        else:
            digit = _KANJI_DIGITS[ch]
    return total + (digit or 0)


def digit_numbers(text: str) -> set[Decimal]:
    """Every number written in digits in `text`, normalised (full-width digits, commas, trailing zeros)."""
    out = set()
    for m in _NUMBER.finditer(unicodedata.normalize("NFKC", text)):
        try:
            out.add(Decimal(m.group().replace(",", "")).normalize())
        except InvalidOperation:
            continue
    return out


def kanji_numbers(text: str) -> set[Decimal]:
    """Every number written in kanji in `text`: a kanji numeral followed by a unit, and fractions (三分の一)."""
    text = unicodedata.normalize("NFKC", text)
    out = set()
    for m in _KANJI_NUMBER.finditer(text):
        if m.group(1) == "一" and m.group("counter"):
            continue                       # 一年, 一度, 一人, 一つ: words far more often than counts
        out.add(Decimal(_kanji_value(m.group(1))).normalize())
    for m in _KANJI_FRACTION.finditer(text):
        out.update(Decimal(_kanji_value(run)).normalize() for run in m.groups())
    return out


def numbers_in(text: str) -> set[Decimal]:
    """Every number written in `text`, in digits or in kanji."""
    return digit_numbers(text) | kanji_numbers(text)


def unsupported_numbers(answer: str, question: str, changed: dict, before: dict, after: dict,
                        lang: str) -> list[str]:
    """Numbers in the explanation that the model was not given (empty list = the answer passes).

    The output guardrail: the explanation may cite only the numbers in the question, the changes
    and the results it was shown; anything else (a rounding, a conversion, an invented figure)
    fails and the page shows the numbers-only summary instead. Numbers in kanji are read as well
    (三億円 as 3, 十二キロ as 12). Not read: quantities without a numeral (half, double, 半分, 倍増)
    and numbers spelled out in English words.
    """
    facts = explain_facts(question, changed, before, after, lang)
    # Digits in the answer must be digits the model was shown, or a number the user wrote in kanji.
    # A unit label such as 百万円 in a result key does not make 100 a permitted figure.
    in_digits = digit_numbers(facts) | kanji_numbers(question[:MAX_QUESTION_CHARS])
    in_kanji = in_digits | kanji_numbers(facts)
    extra = (digit_numbers(answer) - in_digits) | (kanji_numbers(answer) - in_kanji)
    return sorted(format(n, "f") for n in extra)


def numbers_only_summary(changed: dict, before: dict, after: dict, lang: str) -> str:
    """The fallback when an explanation fails the number check: the changes and results as bullets."""
    ja = lang == "ja"
    lines = [f"- {(BY_ID[k][1] if ja else BY_ID[k][2]) if k in BY_ID else k}: "
             f"{before.get(k, '—')} → {v}" for k, v in changed.items()]
    lines += [f"- {k}: {v}" for k, v in after.items()]
    return "\n".join(lines)


# The study area: the box the place lookup searches (dcopt.common.geo.geocode).
STUDY_AREA = {"lat": (43.05, 43.40), "lon": (141.05, 141.75)}
COORDINATE_EXAMPLE = "43.2, 141.3"                    # latitude first
_LATLON = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


def parse_latlon(text: str) -> tuple[float, float] | None:
    """`text` read as "latitude, longitude"; None when it is not a pair of numbers."""
    m = _LATLON.match(text)
    return (float(m[1]), float(m[2])) if m else None


def in_study_area(lat: float, lon: float) -> bool:
    (south, north), (west, east) = STUDY_AREA["lat"], STUDY_AREA["lon"]
    return south <= lat <= north and west <= lon <= east


def point_problem(lat: float, lon: float) -> str | None:
    """Why a point cannot be solved: "swapped" (longitude came first), "outside", or None if it is fine.

    The model snaps any point to the nearest road node, so a point far away would still get a plan;
    this check is what keeps such a plan from being shown.
    """
    if in_study_area(lat, lon):
        return None
    return "swapped" if in_study_area(lon, lat) else "outside"


def sample_random_dc() -> dict:
    """A random plausible data center for the panel: MW 2-50, a point inside the study area.

    The box matches the geocoder's Ishikari viewbox (inset); build_instance snaps the point to
    the nearest road node, so even a draw in the middle of a field lands on the real network.
    Each call draws fresh values — ask again for another draw.
    """
    import random
    return {"mw": round(random.uniform(2.0, 50.0), 1),
            "lat": round(random.uniform(43.10, 43.35), 4),
            "lon": round(random.uniform(141.15, 141.70), 4)}


def new_dc_summary(sources, users, mw: float, lat: float, lon: float,
                   *, time_limit: float = 60.0, build=None) -> dict:
    """The multi-DC engine (the experiments' machinery) with and without one assumed data center.

    Runs the same kernel search over the same four default scenarios as
    experiments/weather_years, once on the given sources and once with the assumed source
    appended — the only difference between the two numbers is the proposed data center. Each
    solve takes up to `time_limit` seconds; the page caches the whole result on (mw, lat, lon).
    """
    from dcopt.heat.network import Params, Source, build_instance, default_scenarios, solve_kernel

    new = Source("assumed-dc", "仮設データセンター（仮定）", "Assumed data center (assumption)", lon, lat,
                 {"low": mw, "high": mw}, "planned",
                 ("仮定：このパネルで提案された場所（地図に未登録）",
                  "Assumption: a place proposed in the panel (not mapped)"),
                 f"assumption: {mw:g} MW of IT load at ({lat:.4f}, {lon:.4f}), proposed in the what-if panel")

    def run(srcs) -> dict:
        inst = (build or build_instance)(srcs, users)
        scens = default_scenarios()
        plan = solve_kernel(inst, Params(mode="ambient", time_limit=time_limit), scens)
        return {"connected sites": len(plan.connected), "pipes (km)": round(plan.pipe_m / 1000, 1),
                "expected net (M yen/yr)": round(plan.expected_net / 1e6, 1)}

    before = run(sources)
    after = run(list(sources) + [new])
    return {"before": before, "after": after,
            "new_dc": f"assumed data center: {mw:g} MW at ({lat:.4f}, {lon:.4f})"}
