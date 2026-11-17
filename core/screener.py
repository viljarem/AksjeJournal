"""Bygger screeningtabellen: én rad per aksje med alt appen trenger."""

from __future__ import annotations

import numpy as np
import pandas as pd

from core import config
from core.indicators import CRITERIA, analyze

STATUS_VOLUME = "Brudd med volum"
STATUS_NO_VOLUME = "Brudd uten volum"
STATUS_NEAR = "Nær brudd"
STALE_DAYS = 7

_PERF_BARS = {"perf_1m": 21, "perf_3m": 63, "perf_6m": 126, "perf_9m": 189, "perf_12m": 252}


def _pct(new: float, old: float) -> float:
    if not old or np.isnan(old) or np.isnan(new):
        return np.nan
    return (new / old - 1) * 100


def summarize(ticker: str, df: pd.DataFrame) -> dict:
    """Én rad til screeningtabellen for en aksje."""
    analysis = analyze(df)
    frame = analysis.frame
    last = frame.iloc[-1]
    close = frame["close"]
    n = len(frame)

    row: dict = {
        "ticker": ticker,
        "date": last["date"],
        "close": last["close"],
        "chg_1d": _pct(last["close"], close.iloc[-2]) if n > 1 else np.nan,
        "volume": last["volume"],
        "vol_sma50": last["vol_sma50"],
        "rel_vol": last["rel_vol"],
        # Snitt daglig omsetning siste 50 dager, i millioner av aksjens valuta.
        "turnover_m": (close * frame["volume"]).tail(50).mean() / 1e6,
        "sma50": last["sma50"],
        "sma150": last["sma150"],
        "sma200": last["sma200"],
        "high_52w": last["high_52w"],
        "low_52w": last["low_52w"],
        "from_high": _pct(last["close"], last["high_52w"]),
        "above_low": _pct(last["close"], last["low_52w"]),
        "n_bars": n,
        "first_date": frame["date"].iloc[0],
        "since_first": _pct(last["close"], close.iloc[0]),
        "score": int(last["score"]),
    }
    for name, bars in _PERF_BARS.items():
        row[name] = _pct(last["close"], close.iloc[-1 - bars]) if n > bars else np.nan
    for col in CRITERIA:
        row[col] = bool(last[col])

    periods = analysis.template_periods()
    ongoing = periods and periods[-1][1] is None
    row["template_since"] = periods[-1][0] if ongoing else pd.NaT

    pivot = analysis.active_pivot
    row["pivot_price"] = pivot.price if pivot else np.nan
    row["pivot_date"] = pivot.date if pivot else pd.NaT
    row["to_pivot"] = _pct(pivot.price, last["close"]) if pivot else np.nan
    row["base_depth"] = pivot.base_depth if pivot else np.nan

    breakout = analysis.breakouts[-1] if analysis.breakouts else None
    bars_ago = int((frame["date"] > breakout.date).sum()) if breakout else None
    row["breakout_date"] = breakout.date if breakout else pd.NaT
    row["breakout_pivot"] = breakout.pivot_price if breakout else np.nan
    row["breakout_rvol"] = breakout.rel_vol if breakout else np.nan
    row["breakout_bars_ago"] = bars_ago if breakout else np.nan
    row["breakout_gain"] = _pct(last["close"], breakout.pivot_price) if breakout else np.nan

    if breakout and bars_ago < config.RECENT_BREAKOUT_BARS:
        row["status"] = STATUS_VOLUME if breakout.with_volume else STATUS_NO_VOLUME
    elif pivot and row["to_pivot"] <= config.NEAR_PIVOT_PCT:
        row["status"] = STATUS_NEAR
    else:
        row["status"] = ""
    return row


def _rs_rating(screen: pd.DataFrame) -> pd.Series:
    """Relativ styrke 1–99 innen markedet (3 mnd teller dobbelt, slik IBD gjør)."""
    weighted = (
        0.4 * screen["perf_3m"]
        + 0.2 * screen["perf_6m"]
        + 0.2 * screen["perf_9m"]
        + 0.2 * screen["perf_12m"]
    )
    return (weighted.rank(pct=True) * 98 + 1).round()


def build_screen(prices: pd.DataFrame, tickers: pd.DataFrame) -> pd.DataFrame:
    """Screeningtabell for et helt marked."""
    rows = [
        summarize(str(ticker), group.sort_values("date"))
        for ticker, group in prices.groupby("ticker", observed=True, sort=False)
        if len(group)
    ]
    screen = pd.DataFrame(rows)
    # Aksjer uten handel den siste uka (suspendert/strøket) skal ikke flagges som ferske signaler.
    stale = screen["date"] < screen["date"].max() - pd.Timedelta(days=STALE_DAYS)
    screen.loc[stale, "status"] = ""
    screen["rs"] = _rs_rating(screen)
    info = tickers[["ticker", "symbol", "name", "segment", "sector"]]
    screen = screen.merge(info, on="ticker", how="left")
    screen["symbol"] = screen["symbol"].fillna(screen["ticker"])
    screen["name"] = screen["name"].fillna(screen["ticker"])
    screen["updated_at"] = pd.Timestamp.now(tz="UTC").tz_localize(None)
    return screen.sort_values("symbol").reset_index(drop=True)
