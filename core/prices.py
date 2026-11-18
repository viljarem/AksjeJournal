"""Kurshenting fra Yahoo Finance (yfinance).

Kursene er splittjustert, men ikke utbyttejustert, slik at pivot-nivåer og
52-ukers topp/bunn stemmer med kursene som faktisk ble handlet.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

import pandas as pd
import yfinance as yf

from core.config import HISTORY_YEARS

PRICE_COLUMNS = ["ticker", "date", "open", "high", "low", "close", "volume"]
_FIELDS = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}


def _download(tickers: Sequence[str], period: str) -> dict[str, pd.DataFrame]:
    """Laster ned dagskurser og returnerer én ryddet tabell per ticker som har data."""
    raw = yf.download(
        list(tickers),
        period=period,
        interval="1d",
        auto_adjust=False,
        group_by="ticker",
        threads=True,
        progress=False,
    )
    out: dict[str, pd.DataFrame] = {}
    if raw is None or raw.empty:
        return out
    if not isinstance(raw.columns, pd.MultiIndex):
        raw = pd.concat({tickers[0]: raw}, axis=1)
    available = set(raw.columns.get_level_values(0))
    for ticker in tickers:
        if ticker not in available:
            continue
        frame = raw[ticker]
        if not set(_FIELDS).issubset(frame.columns):
            continue
        frame = frame[list(_FIELDS)].rename(columns=_FIELDS).dropna(subset=["close"])
        if frame.empty:
            continue
        frame = frame.reset_index(names="date")
        frame["date"] = pd.to_datetime(frame["date"]).dt.tz_localize(None).dt.normalize()
        frame = frame.drop_duplicates("date", keep="last").sort_values("date")
        frame["volume"] = frame["volume"].fillna(0)
        out[ticker] = frame
    return out


def download_history(
    tickers: Sequence[str],
    period: str = f"{HISTORY_YEARS}y",
    batch_size: int = 100,
    log: Callable[[str], None] = print,
) -> tuple[pd.DataFrame, list[str]]:
    """Henter dagskurser for alle tickere for en Yahoo-periode (f.eks. "1mo" eller "5y").

    Returnerer (kurser i langt format, tickere uten data).
    """
    tickers = list(dict.fromkeys(tickers))
    frames: dict[str, pd.DataFrame] = {}

    for start in range(0, len(tickers), batch_size):
        batch = tickers[start : start + batch_size]
        frames.update(_download(batch, period))
        log(f"  hentet {min(start + batch_size, len(tickers))}/{len(tickers)} tickere")

    missing = [t for t in tickers if t not in frames]
    if missing:
        # Ett nytt forsøk: Yahoo svarer av og til tomt på enkeltaksjer i en stor forespørsel.
        time.sleep(3)
        log(f"  prøver {len(missing)} tickere uten data på nytt")
        for start in range(0, len(missing), batch_size):
            frames.update(_download(missing[start : start + batch_size], period))
        missing = [t for t in tickers if t not in frames]

    if not frames:
        return pd.DataFrame(columns=PRICE_COLUMNS), missing

    prices = pd.concat(
        [frame.assign(ticker=ticker) for ticker, frame in frames.items()], ignore_index=True
    )
    return prices[PRICE_COLUMNS], missing


def with_quote(history: pd.DataFrame, quote: pd.Series | None) -> pd.DataFrame:
    """Historikken med dagens (uferdige) candle fra en fersk kurs lagt til eller oppdatert."""
    if quote is None or pd.isna(quote["last"]) or pd.isna(quote["date"]):
        return history
    day = pd.Timestamp(quote["date"])
    if day < history["date"].iloc[-1]:
        return history
    today = pd.DataFrame(
        [
            {
                "date": day,
                "open": quote["open"],
                "high": quote["high"],
                "low": quote["low"],
                "close": quote["last"],
                "volume": quote["volume"],
            }
        ]
    )
    base = history[history["date"] < day].assign(date=lambda d: d["date"].astype("datetime64[ns]"))
    return pd.concat([base, today], ignore_index=True)


def fetch_quotes(tickers: Sequence[str]) -> pd.DataFrame:
    """Siste kurs for et lite utvalg tickere (forsinket ca. 15 minutter hos Yahoo).

    Returnerer en tabell indeksert på ticker med last, open, prev_close,
    chg_open (% siden åpning), chg_day (% siden forrige sluttkurs) og date.
    """
    columns = ["last", "open", "high", "low", "volume", "prev_close", "chg_open", "chg_day", "date"]
    rows = {}
    if tickers:
        for ticker, frame in _download(tickers, "5d").items():
            last = frame.iloc[-1]
            prev_close = frame["close"].iloc[-2] if len(frame) > 1 else float("nan")
            rows[ticker] = {
                "last": last["close"],
                "open": last["open"],
                "high": last["high"],
                "low": last["low"],
                "volume": last["volume"],
                "prev_close": prev_close,
                "chg_open": (last["close"] / last["open"] - 1) * 100 if last["open"] else float("nan"),
                "chg_day": (last["close"] / prev_close - 1) * 100 if prev_close else float("nan"),
                "date": last["date"],
            }
    return pd.DataFrame.from_dict(rows, orient="index", columns=columns)
