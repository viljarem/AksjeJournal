"""Minervini-screener: trend template, brudd over pivot og aksjer nær brudd."""

import streamlit as st

from core import config
from core.screener import STATUS_NEAR, STATUS_NO_VOLUME, STATUS_VOLUME
from ui.common import require_screen
from ui.tables import screen_table

market, screen = require_screen()
st.title(f"Minervini · {config.MARKETS[market].name}")

# Aksjer med for kort historikk vises under «Nye noteringer».
stocks = screen[screen["n_bars"] >= config.MIN_BARS_TEMPLATE]

views = {
    STATUS_VOLUME: stocks[stocks["status"] == STATUS_VOLUME],
    STATUS_NO_VOLUME: stocks[stocks["status"] == STATUS_NO_VOLUME],
    STATUS_NEAR: stocks[stocks["status"] == STATUS_NEAR],
    "7/7": stocks[stocks["score"] == 7],
    "Alle": stocks,
}

cols = st.columns(4)
cols[0].metric("7/7 i trend template", len(views["7/7"]))
cols[1].metric("Brudd med volum", len(views[STATUS_VOLUME]))
cols[2].metric("Brudd uten volum", len(views[STATUS_NO_VOLUME]))
cols[3].metric("Nær brudd", len(views[STATUS_NEAR]))

choice = st.segmented_control(
    "Vis",
    list(views),
    default="7/7",
    required=True,
    format_func=lambda name: f"{name} ({len(views[name])})",
    label_visibility="collapsed",
    key="minervini_view",
)

lead = ["symbol", "name", "status", "score", "close", "chg_1d", "rel_vol"]
tail = ["from_high", "rs", "perf_3m", "turnover_m"]
breakout_cols = ["breakout_date", "breakout_pivot", "breakout_rvol", "breakout_gain"]
pivot_cols = ["pivot_price", "to_pivot", "base_depth"]

if choice in (STATUS_VOLUME, STATUS_NO_VOLUME):
    st.caption(
        f"Sluttkurs over pivot de siste {config.RECENT_BREAKOUT_BARS} børsdagene. «Med volum» betyr "
        f"minst {config.BREAKOUT_RVOL:g}x snittvolumet (SMA50) på bruddagen."
    )
    table = views[choice].sort_values(["breakout_date", "breakout_rvol"], ascending=False)
    columns = lead + breakout_cols + tail
elif choice == STATUS_NEAR:
    st.caption(f"Kursen ligger høyst {config.NEAR_PIVOT_PCT:g} % under en aktiv pivot.")
    table = views[choice].sort_values("to_pivot")
    columns = lead + pivot_cols + tail
elif choice == "7/7":
    st.caption("Alle sju kriteriene i trend template er oppfylt. Sortert etter relativ styrke.")
    table = views[choice].sort_values("rs", ascending=False)
    columns = lead + ["template_since"] + pivot_cols[:2] + tail
else:
    table = views[choice].sort_values(["score", "rs"], ascending=False)
    columns = lead + pivot_cols[:2] + breakout_cols[:1] + tail

screen_table(table, columns, key=f"minervini-{market}-{choice}")
st.caption("Velg en rad (avkrysningsfeltet til venstre) for å åpne aksjen med chart.")
