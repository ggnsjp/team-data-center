"""The live what-if panel's vocabulary: the knobs the LLM may change, and nothing else.

The panel on the Warm Ishikari page takes free text in either language, asks the LLM to map
it onto THIS module's knob list, and clamps everything into the sliders' ranges before the
deterministic model re-runs. The LLM never computes results: it chooses inputs and explains
the numbers the model produced.
"""
import json
from decimal import ROUND_HALF_UP, Decimal

from dcopt.common import llm

M = 1e6

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
]
BY_ID = {k[0]: k for k in KNOBS}

# the LLM returns place "random" when the user asks for a random data center; the app draws the rest
RANDOM_PLACES = ("random", "ランダム", "random place", "random location", "random lat long",
                 "おまかせ", "どこでも")


class WhatifError(ValueError):
    """The LLM's answer could not be turned into knob changes; safe to show in the UI."""


def parse_prompt(current: dict, text: str) -> str:
    """The single user message asking the model to map free text onto the knob list."""
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
                v = float((Decimal(str(v)) / q).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * q)
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
    diff = "\n".join(f"- {(BY_ID[k][1] if ja else BY_ID[k][2]) if k in BY_ID else k}: "
                     f"{before.get(k, '—')} → {v}" for k, v in changed.items()) \
        or ("- 変更なし / no change" if ja else "- no change")
    if ja:
        head = ("あなたは熱供給ネットワークの結果を読み解く説明者です。以下の「変更」と「結果」だけ"
                "を使って、ユーザーの質問に3〜6文で答えてください。ここに挙げていない数値は"
                "絶対に使わないでください。")
    else:
        head = ("You explain what a district-heat network model computed. Use ONLY the numbers in "
                "'changes' and 'results' below; answer the user's question in 3-6 sentences and "
                "never introduce numbers of your own.")
    return (head + f"\n\nquestion: {question}\n\nchanges:\n{diff}\n\n"
            f"results: {json.dumps(after, ensure_ascii=False)}")


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
