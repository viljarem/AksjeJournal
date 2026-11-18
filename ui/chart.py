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


DEFAULT_SMAS = [
    {"id": 1, "period": 50, "color": "#2563eb"},
    {"id": 2, "period": 150, "color": "#d97706"},
    {"id": 3, "period": 200, "color": "#9333ea"},
]

DEFAULT_INDICATORS = {"bollinger": False, "rsi": False, "atr": False}


def bollinger(close: pd.Series, period: int = 20, width: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0)
    return mid - width * std, mid, mid + width * std


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI etter Wilder (eksponentielt glattet gjennomsnitt av opp- og nedgang)."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = gain / loss.replace(0, pd.NA)
    return (100 - 100 / (1 + rs)).fillna(100).where(gain.notna())


def atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range etter Wilder."""
    prev = frame["close"].shift()
    tr = pd.concat(
        [frame["high"] - frame["low"], (frame["high"] - prev).abs(), (frame["low"] - prev).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def indicator_payload(analysis: Analysis, indicators: dict) -> dict:
    frame = analysis.frame
    x = [_ms(d) for d in frame["date"]]
    out: dict = {}
    if indicators.get("bollinger"):
        lower, mid, upper = bollinger(frame["close"])
        out["bollinger"] = {"lower": _line(x, lower), "mid": _line(x, mid), "upper": _line(x, upper)}
    if indicators.get("rsi"):
        out["rsi"] = _line(x, rsi(frame["close"]))
    if indicators.get("atr"):
        out["atr"] = _line(x, atr(frame))
    return out


def indicator_editor() -> dict:
    """Meny for å slå indikatorer av og på. Returnerer gjeldende oppsett."""
    state = st.session_state
    if "indicators" not in state:
        stored = None
        if supabase_configured():
            try:
                stored = db.get_chart_indicators()
            except Exception:
                stored = None
        state["indicators"] = {**DEFAULT_INDICATORS, **(stored or {})}
    current = state["indicators"]

    with st.popover("Indikatorer", icon=":material/analytics:"):
        edited = {
            "bollinger": st.checkbox("Bollinger-bånd (20, 2σ)", current["bollinger"], key="ind_bollinger"),
            "rsi": st.checkbox("RSI (14) – eget panel", current["rsi"], key="ind_rsi"),
            "atr": st.checkbox("ATR (14) – eget panel", current["atr"], key="ind_atr"),
        }
        st.caption("Gjelder alle aksjer.")

    if edited != current:
        state["indicators"] = edited
        if supabase_configured():
            try:
                db.save_chart_indicators(edited)
            except Exception as error:
                st.warning(f"Oppsettet ble ikke lagret: {error}")
        st.rerun()
    return current


def sma_editor() -> list[dict]:
    """Meny for å legge til, fjerne og fargelegge SMA-linjer. Returnerer gjeldende oppsett."""
    state = st.session_state
    if "smas" not in state:
        stored = None
        if supabase_configured():
            try:
                stored = db.get_chart_smas()
            except Exception:
                stored = None
        state["smas"] = [dict(s) for s in (DEFAULT_SMAS if stored is None else stored)]
    smas = state["smas"]

    edited = []
    with st.popover("Glidende snitt", icon=":material/show_chart:"):
        for i, sma in enumerate(smas):
            labels = "visible" if i == 0 else "collapsed"
            cols = st.columns([3, 1, 1], vertical_alignment="bottom")
            period = cols[0].number_input(
                "Periode (dager)", 2, 500, int(sma["period"]), key=f"sma_period_{sma['id']}", label_visibility=labels
            )
            color = cols[1].color_picker(
                "Farge", sma["color"], key=f"sma_color_{sma['id']}", label_visibility=labels
            )
            if not cols[2].button("", icon=":material/close:", key=f"sma_remove_{sma['id']}", help="Fjern linja"):
                edited.append({"id": sma["id"], "period": int(period), "color": color})
        if st.button("Legg til linje", icon=":material/add:", key="sma_add"):
            new_id = max([s["id"] for s in smas], default=0) + 1
            edited.append({"id": new_id, "period": 20, "color": "#22d3ee"})
        st.caption("Gjelder alle aksjer. Screeningen bruker alltid SMA50, 150 og 200.")

    if edited != smas:
        state["smas"] = edited
        if supabase_configured():
            try:
                db.save_chart_smas(edited)
            except Exception as error:
                st.warning(f"Oppsettet ble ikke lagret: {error}")
        st.rerun()
    return smas


@st.fragment
def stock_chart(
    ticker: str,
    title: str,
    analysis: Analysis,
    annotations: list,
    transactions: list[dict] | None = None,
    smas: list[dict] | None = None,
    indicators: dict | None = None,
    height: int = 640,
) -> None:
    """Viser chartet. Tegninger lagres automatisk i Supabase når de endres."""
    payload = chart_payload(analysis)
    smas = DEFAULT_SMAS if smas is None else smas
    indicators = DEFAULT_INDICATORS if indicators is None else indicators
    x = [_ms(d) for d in analysis.frame["date"]]
    close = analysis.frame["close"]
    payload["smas"] = [
        {"period": s["period"], "color": s["color"], "data": _line(x, close.rolling(s["period"]).mean())}
        for s in smas
    ]
    payload["chart_key"] += "-" + ",".join(f"{s['period']}{s['color']}" for s in smas)
    payload["indicators"] = indicator_payload(analysis, indicators)
    payload["chart_key"] += "-" + ",".join(sorted(payload["indicators"]))
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
