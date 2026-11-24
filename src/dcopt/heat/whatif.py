"""The live what-if panel's vocabulary: the knobs the LLM may change, and nothing else.

The panel on the Warm Ishikari page takes free text in either language, asks the LLM to map
it onto THIS module's knob list, and clamps everything into the sliders' ranges before the
deterministic model re-runs. The LLM never computes results: it chooses inputs and explains
the numbers the model produced.
"""
import json
from decimal import ROUND_HALF_UP, Decimal

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
            "Return ONLY a JSON object {\"changes\": {<knob id>: <new value>}} with the knobs the "
            "request implies (empty object when it changes nothing). Keep other values out. "
            "Numbers in the units shown; booleans as true/false.")


def parse_patch(text: str, current: dict, *, llm_chat) -> dict:
    """Free text -> {knob id: clamped new value}. Raises WhatifError when unusable."""
    raw = llm_chat([{"role": "user", "content": parse_prompt(current, text)}], max_tokens=1200,
                   json_mode=True)
    try:
        changes = json.loads(raw)["changes"]
    except (ValueError, KeyError, TypeError):
        raise WhatifError("the model did not return usable JSON") from None
    if not isinstance(changes, dict):
        raise WhatifError("the model did not return a changes object")
    out: dict = {}
    for key, value in changes.items():
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
    return out


def explain_prompt(question: str, changed: dict, before: dict, after: dict, lang: str) -> str:
    """The message asking the model to explain what the model computed, in the UI language.

    `before`/`after` are the page's own result summaries (same keys); the model may cite only
    these numbers and the knob diff.
    """
    ja = lang == "ja"
    diff = "\n".join(f"- {BY_ID[k][1] if ja else BY_ID[k][2]}: {before.get(k, '—')} → {v}"
                     for k, v in changed.items()) or ("- 変更なし / no change" if ja else "- no change")
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
