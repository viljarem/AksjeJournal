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
        "vol_sma50": [[xi, round(float(v))] for xi, v in zip(x, frame["vol_sma50"]) if pd.notna(v)],
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


def trade_markers(analysis: Analysis, transactions: list[dict]) -> list[dict]:
    """Kjøp og salg som punkter i chartet, plassert på handelskursen.

    Handler på dager uten børshandel flyttes til neste børsdag, slik at de havner på en kursstolpe.
    """
    dates = analysis.frame["date"]
    markers = []
    for tx in transactions:
        when = pd.Timestamp(str(tx["traded_on"])[:10])
        later = dates[dates >= when]
        markers.append(
            {
                "x": _ms(later.iloc[0] if len(later) else when),
                "date": _ms(when),
                "price": float(tx["price"]),
                "buy": tx["side"] == "buy",
                "quantity": float(tx["quantity"]),
                "fee": float(tx.get("fee") or 0),
                "comment": tx.get("comment") or "",
            }
        )
    return sorted(markers, key=lambda m: m["x"])


@st.fragment
def stock_chart(
    ticker: str,
    title: str,
    analysis: Analysis,
    annotations: list,
    transactions: list[dict] | None = None,
    height: int = 640,
) -> None:
    """Viser chartet. Tegninger lagres automatisk i Supabase når de endres."""
    payload = chart_payload(analysis)
    payload["trades"] = trade_markers(analysis, transactions or [])
    # Chartet bygges på nytt når handlene endres.
    payload["chart_key"] += "-" + ",".join(
        f"{m['x']}:{m['price']}:{m['quantity']}:{m['buy']}:{m['comment']}" for m in payload["trades"]
    )
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
        **payload,
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
