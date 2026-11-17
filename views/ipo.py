"""Nye noteringer: aksjer med for kort historikk til Minervinis trend template."""

import streamlit as st

from core import config
from ui.common import require_screen
from ui.tables import screen_table

market, screen = require_screen()
st.title(f"Nye noteringer · {config.MARKETS[market].name}")
st.caption(
    f"Aksjer med færre enn {config.MIN_BARS_TEMPLATE} børsdager med kurshistorikk. "
    "De har for lite data til trend template og vises derfor ikke i Minervini-screeneren."
)

new = screen[screen["n_bars"] < config.MIN_BARS_TEMPLATE].sort_values("first_date", ascending=False)
screen_table(
    new,
    ["symbol", "name", "segment", "first_date", "n_bars", "close", "chg_1d", "since_first",
     "perf_1m", "perf_3m", "from_high", "rel_vol", "turnover_m", "status", "pivot_price", "to_pivot"],
    key=f"ipo-{market}",
)
if not new.empty:
    st.caption("Velg en rad for å åpne aksjen med chart.")
