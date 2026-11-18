"""Felles, fargekodet tabell for screeningdata. Et klikk på en rad åpner aksjen."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core import config
from core.screener import STATUS_NEAR, STATUS_NO_VOLUME, STATUS_VOLUME
from ui.common import AMBER, BLUE, GREEN, nb, open_chart, pct, pct_color


def _date(value) -> str:
    return f"{value:%d.%m.%Y}"


def _times(value) -> str:
    return f"{nb(value, 2)}x"


# kolonne -> (overskrift, formatering, type fargekoding)
COLUMNS = {
    "symbol": ("Ticker", None, None),
    "name": ("Navn", None, None),
    "segment": ("Liste", None, None),
    "status": ("Signal", None, "status"),
    "score": ("Trend", lambda v: f"{v:.0f}/7", "score"),
    "close": ("Siste", nb, None),
    "chg_1d": ("I dag", pct, "pct"),
    "rel_vol": ("Rel. volum", _times, "rvol"),
    "turnover_m": ("Omsetning (mill.)", lambda v: nb(v, 1), None),
    "pivot_price": ("Pivot", nb, None),
    "to_pivot": ("Opp til pivot", lambda v: f"{nb(v, 1)} %", None),
    "base_depth": ("Basedybde", lambda v: f"{nb(v, 1)} %", None),
    "breakout_date": ("Bruddato", _date, None),
    "breakout_bars_ago": ("Dager siden brudd", lambda v: f"{v:.0f}", None),
    "breakout_pivot": ("Brutt pivot", nb, None),
    "breakout_rvol": ("Rel. volum ved brudd", _times, "rvol"),
    "breakout_gain": ("Siden brudd", pct, "pct"),
    "from_high": ("Fra 52u topp", pct, None),
    "above_low": ("Over 52u bunn", pct, None),
    "rs": ("RS", lambda v: f"{v:.0f}", "rs"),
    "perf_1m": ("1 mnd", pct, "pct"),
    "perf_3m": ("3 mnd", pct, "pct"),
    "perf_6m": ("6 mnd", pct, "pct"),
    "perf_12m": ("1 år", pct, "pct"),
    "template_since": ("7/7 siden", _date, None),
    "n_bars": ("Børsdager", lambda v: f"{v:.0f}", None),
    "first_date": ("Første børsdag", _date, None),
    "since_first": ("Siden første dag", pct, "pct"),
}

HELP = {
    "Signal": "Brudd de siste 5 børsdagene, eller kurs høyst 5 % under aktiv pivot.",
    "Dager siden brudd": "Børsdager siden sluttkursen brøt over pivoten. 0 = bruddet kom siste børsdag.",
    "Trend": "Antall oppfylte kriterier i Minervinis trend template.",
    "Rel. volum": "Dagens volum så langt delt på 50-dagers snittvolum.",
    "Siste": "Siste kurs fra Yahoo, ca. 15 minutter forsinket.",
    "RS": "Relativ styrke 1–99 mot resten av børsen (vektet 3–12 mnd utvikling).",
    "Opp til pivot": "Hvor mye kursen må stige for å nå pivoten.",
    "Basedybde": "Største fall fra pivoten så langt.",
    "Omsetning (mill.)": "Snitt daglig omsetning siste 50 dager.",
}


def _status_style(value) -> str:
    color = {STATUS_VOLUME: GREEN, STATUS_NO_VOLUME: AMBER, STATUS_NEAR: BLUE}.get(value)
    return f"background-color: {color}; color: white; font-weight: 600" if color else ""


def _score_style(value) -> str:
    if value == 7:
        return f"background-color: {GREEN}; color: white; font-weight: 600"
    if value == 6:
        return f"color: {GREEN}; font-weight: 600"
    return ""


def _rvol_style(value) -> str:
    if pd.notna(value) and value >= config.BREAKOUT_RVOL:
        return f"color: {GREEN}; font-weight: 600"
    return ""


def _rs_style(value) -> str:
    if pd.notna(value) and value >= 80:
        return f"color: {GREEN}; font-weight: 600"
    return ""


_STYLES = {"status": _status_style, "score": _score_style, "pct": pct_color, "rvol": _rvol_style, "rs": _rs_style}


def screen_table(df: pd.DataFrame, columns: list[str], key: str, height: int = 600) -> None:
    """Viser tabellen. Når en rad velges, åpnes aksjesiden."""
    if df.empty:
        st.info("Ingen aksjer passer akkurat nå.")
        return
    df = df.reset_index(drop=True)
    labels = {col: COLUMNS[col][0] for col in columns}
    styler = df[columns].rename(columns=labels).style
    styler = styler.format(
        {labels[col]: COLUMNS[col][1] for col in columns if COLUMNS[col][1]}, na_rep="–"
    )
    for col in columns:
        kind = COLUMNS[col][2]
        if kind:
            styler = styler.map(_STYLES[kind], subset=[labels[col]])

    event = st.dataframe(
        styler,
        hide_index=True,
        height=min(height, 38 * (len(df) + 1) + 3),
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            label: st.column_config.Column(help=HELP.get(label), pinned=label == "Ticker")
            for label in labels.values()
        },
        key=f"{key}-{st.session_state.get('table_nonce', 0)}",
    )
    fetched = st.session_state.get("live_time")
    if fetched:
        st.caption(
            f"Kurs og relativt volum hentet kl. {fetched} fra Yahoo (ca. 15 min forsinket). "
            "Signaler, trend og RS er fra siste dagsoppdatering."
        )
    else:
        st.caption("Fikk ikke hentet ferske kurser nå. Viser siste lagrede sluttkurs.")
    if event.selection.rows:
        open_chart(df.iloc[event.selection.rows[0]]["ticker"])
