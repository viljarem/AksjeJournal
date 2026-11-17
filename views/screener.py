"""Komplett aksjeliste med fritt sammensatte filtre."""

import streamlit as st

from core import config
from ui.common import require_screen
from ui.tables import screen_table

market, screen = require_screen()
st.title(f"Screener · {config.MARKETS[market].name}")

# Felter det kan filtreres på: navn i menyen -> kolonne
FIELDS = {
    "Fra 52u topp (%)": "from_high",
    "Over 52u bunn (%)": "above_low",
    "Rel. volum (x SMA50)": "rel_vol",
    "Trend template (0–7)": "score",
    "RS (1–99)": "rs",
    "Kurs": "close",
    "I dag (%)": "chg_1d",
    "1 mnd (%)": "perf_1m",
    "3 mnd (%)": "perf_3m",
    "6 mnd (%)": "perf_6m",
    "1 år (%)": "perf_12m",
    "Omsetning (mill. per dag)": "turnover_m",
    "Opp til pivot (%)": "to_pivot",
    "Børsdager med historikk": "n_bars",
}
OPERATORS = ["minst", "høyst"]
PRESETS = {
    "Nær 52u topp med volum": [("Fra 52u topp (%)", "minst", -5.0), ("Rel. volum (x SMA50)", "minst", 1.0)],
    "Sterk trend": [("Trend template (0–7)", "minst", 6.0), ("RS (1–99)", "minst", 80.0)],
    "Sterke 6 mnd": [("6 mnd (%)", "minst", 30.0), ("Omsetning (mill. per dag)", "minst", 1.0)],
}

state = st.session_state


def add_filter(field: str, operator: str = "minst", value: float = 0.0) -> None:
    filter_id = state.get("filter_seq", 0) + 1
    state["filter_seq"] = filter_id
    state.setdefault("filter_ids", []).append(filter_id)
    state[f"filter_field_{filter_id}"] = field
    state[f"filter_op_{filter_id}"] = operator
    state[f"filter_value_{filter_id}"] = value


def remove_filter(filter_id: int) -> None:
    state["filter_ids"].remove(filter_id)


def apply_preset(name: str) -> None:
    state["filter_ids"] = []
    for field, operator, value in PRESETS[name]:
        add_filter(field, operator, value)


state.setdefault("filter_ids", [])

with st.container(border=True):
    top = st.columns([3, 2])
    search = top[0].text_input("Søk", placeholder="Ticker eller navn", key="screener_search")
    segments = sorted(screen["segment"].dropna().unique())
    chosen_segments = (
        top[1].multiselect("Liste", segments, placeholder="Alle", key=f"screener_segments_{market}")
        if len(segments) > 1
        else []
    )

    for filter_id in state["filter_ids"]:
        row = st.columns([4, 2, 2, 1], vertical_alignment="bottom")
        row[0].selectbox("Felt", list(FIELDS), key=f"filter_field_{filter_id}", label_visibility="collapsed")
        row[1].selectbox("Regel", OPERATORS, key=f"filter_op_{filter_id}", label_visibility="collapsed")
        row[2].number_input("Verdi", key=f"filter_value_{filter_id}", step=1.0, label_visibility="collapsed")
        row[3].button(
            "", icon=":material/close:", key=f"filter_remove_{filter_id}", help="Fjern filteret",
            on_click=remove_filter, args=(filter_id,),
        )

    actions = st.columns([2, 2, 2, 2, 2])
    actions[0].button("Legg til filter", icon=":material/add:", on_click=add_filter, args=(next(iter(FIELDS)),))
    for column, name in zip(actions[1:4], PRESETS):
        column.button(name, on_click=apply_preset, args=(name,), help="Erstatter filtrene med et ferdig oppsett.")
    if state["filter_ids"]:
        actions[4].button("Nullstill", on_click=lambda: state.update(filter_ids=[]))

result = screen
if search.strip():
    needle = search.strip().lower()
    result = result[
        result["symbol"].str.lower().str.contains(needle, regex=False)
        | result["name"].str.lower().str.contains(needle, regex=False)
    ]
if chosen_segments:
    result = result[result["segment"].isin(chosen_segments)]
for filter_id in state["filter_ids"]:
    column = FIELDS[state[f"filter_field_{filter_id}"]]
    value = state[f"filter_value_{filter_id}"]
    if state[f"filter_op_{filter_id}"] == "minst":
        result = result[result[column] >= value]
    else:
        result = result[result[column] <= value]

st.caption(f"**{len(result)}** av {len(screen)} aksjer. Velg en rad for å åpne aksjen med chart.")
screen_table(
    result.sort_values("symbol"),
    ["symbol", "name", "close", "chg_1d", "rel_vol", "from_high", "above_low", "score", "rs",
     "perf_1m", "perf_3m", "perf_6m", "perf_12m", "turnover_m", "status", "to_pivot", "n_bars"],
    key=f"screener-{market}",
    height=640,
)
