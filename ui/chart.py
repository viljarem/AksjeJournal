"""Python-siden av chartet: bygger data til Highcharts-komponenten og lagrer tegninger."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from core import db
from core.indicators import Analysis
from core.settings import supabase_configured

_component = components.declare_component(
    "stock_chart", path=str(Path(__file__).parent / "stock_chart")
)


def _ms(value) -> int:
    return int(pd.Timestamp(value).value // 1_000_000)


def _line(x: list[int], values: pd.Series) -> list[list[float]]:
    return [[xi, round(float(v), 4)] for xi, v in zip(x, values) if pd.notna(v)]


def chart_payload(analysis: Analysis) -> dict:
    frame = analysis.frame
    x = [_ms(d) for d in frame["date"]]
    o, h, l, c, v = (frame[col].to_numpy(dtype=float) for col in ["open", "high", "low", "close", "volume"])
    return {
        "chart_key": f"{x[0]}-{x[-1]}-{len(x)}-{c[-1]}",
        "ohlc": [
            [x[i], round(o[i], 4), round(h[i], 4), round(l[i], 4), round(c[i], 4)] for i in range(len(x))
        ],
        "volume": [[x[i], v[i], 1 if c[i] >= o[i] else 0] for i in range(len(x))],
        "sma50": _line(x, frame["sma50"]),
        "sma150": _line(x, frame["sma150"]),
        "sma200": _line(x, frame["sma200"]),
        "breakouts": [
            {
                "x": _ms(b.date),
                "pivot_x": _ms(b.pivot_date),
                "pivot": round(b.pivot_price, 4),
                "rel_vol": None if pd.isna(b.rel_vol) else round(b.rel_vol, 2),
                "with_volume": b.with_volume,
            }
            for b in analysis.breakouts
        ],
        "active_pivot": (
            {"x": _ms(analysis.active_pivot.date), "price": round(analysis.active_pivot.price, 4)}
            if analysis.active_pivot
            else None
        ),
        "periods": [
            [_ms(start), None if end is None else _ms(end)] for start, end in analysis.template_periods()
        ],
    }


@st.fragment
def stock_chart(ticker: str, title: str, analysis: Analysis, annotations: list, height: int = 640) -> None:
    """Viser chartet. Tegninger lagres automatisk i Supabase når de endres."""
    can_save = supabase_configured()
    saved = st.session_state.setdefault("chart_saved_nonce", {})
    failed = st.session_state.setdefault("chart_error_nonce", {})

    value = _component(
        ticker=ticker,
        title=title,
        height=height,
        can_save=can_save,
        annotations=annotations,
        saved_nonce=saved.get(ticker),
        error_nonce=failed.get(ticker),
        key=f"chart-{ticker}",
        default=None,
        **chart_payload(analysis),
    )

    if not (can_save and value and value.get("ticker") == ticker):
        return
    nonce = value["nonce"]
    if nonce in (saved.get(ticker), failed.get(ticker)):
        return  # allerede behandlet
    try:
        db.save_drawings(ticker, value["annotations"])
        saved[ticker] = nonce
    except Exception:
        failed[ticker] = nonce
    st.rerun(scope="fragment")
