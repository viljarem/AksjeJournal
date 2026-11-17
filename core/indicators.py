"""Teknisk analyse per aksje: Minervinis trend template, pivoter og brudd.

Samme analyse brukes både av screeneren og av chartet, slik at tabell og
graf alltid viser de samme pivotene og 7/7-periodene.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from core import config

CRITERIA = [f"c{i}" for i in range(1, 8)]

CRITERIA_TEXT = {
    "c1": "Kurs over SMA150 og SMA200",
    "c2": "SMA150 over SMA200",
    "c3": "SMA200 stigende siste måned",
    "c4": "SMA50 over SMA150 og SMA200",
    "c5": "Kurs over SMA50",
    "c6": f"Kurs minst {config.ABOVE_LOW_PCT:.0f} % over 52-ukers bunn",
    "c7": f"Kurs høyst {config.WITHIN_HIGH_PCT:.0f} % under 52-ukers topp",
}


@dataclass(frozen=True)
class Pivot:
    date: pd.Timestamp
    price: float
    base_depth: float  # største fall under pivoten så langt, i prosent


@dataclass(frozen=True)
class Breakout:
    date: pd.Timestamp
    close: float
    pivot_date: pd.Timestamp
    pivot_price: float
    rel_vol: float
    with_volume: bool
    base_depth: float
    base_bars: int


@dataclass
class Analysis:
    frame: pd.DataFrame  # én rad per børsdag med glidende snitt, kriterier og score
    breakouts: list[Breakout] = field(default_factory=list)
    active_pivot: Pivot | None = None

    def template_periods(self) -> list[tuple[pd.Timestamp, pd.Timestamp | None]]:
        """Perioder med 7/7: (første dag med 7/7, første dag uten 7/7 – eller None om den pågår)."""
        full = self.frame["score"].to_numpy() == 7
        dates = self.frame["date"].to_numpy()
        periods: list[tuple[pd.Timestamp, pd.Timestamp | None]] = []
        start = None
        for i, is_full in enumerate(full):
            if is_full and start is None:
                start = pd.Timestamp(dates[i])
            elif not is_full and start is not None:
                periods.append((start, pd.Timestamp(dates[i])))
                start = None
        if start is not None:
            periods.append((start, None))
        return periods


def trend_template(df: pd.DataFrame) -> pd.DataFrame:
    """Legger til glidende snitt, 52-ukers topp/bunn, relativt volum og de 7 kriteriene."""
    out = df.reset_index(drop=True).copy()
    close = out["close"]

    out["sma50"] = close.rolling(50).mean()
    out["sma150"] = close.rolling(150).mean()
    out["sma200"] = close.rolling(200).mean()
    out["high_52w"] = out["high"].rolling(config.BARS_52W, min_periods=1).max()
    out["low_52w"] = out["low"].rolling(config.BARS_52W, min_periods=1).min()
    out["vol_sma50"] = out["volume"].rolling(50).mean()
    out["rel_vol"] = (out["volume"] / out["vol_sma50"]).where(out["vol_sma50"] > 0)

    out["c1"] = (close > out["sma150"]) & (close > out["sma200"])
    out["c2"] = out["sma150"] > out["sma200"]
    out["c3"] = out["sma200"] > out["sma200"].shift(config.SMA200_TREND_BARS)
    out["c4"] = (out["sma50"] > out["sma150"]) & (out["sma50"] > out["sma200"])
    out["c5"] = close > out["sma50"]
    out["c6"] = close >= out["low_52w"] * (1 + config.ABOVE_LOW_PCT / 100)
    out["c7"] = close >= out["high_52w"] * (1 - config.WITHIN_HIGH_PCT / 100)
    # Uten nok historikk til SMA200-trenden er malen ikke oppfylt, uansett.
    enough = np.arange(len(out)) >= config.MIN_BARS_TEMPLATE - 1
    for col in CRITERIA:
        out[col] = out[col] & enough
    out["score"] = out[CRITERIA].sum(axis=1).astype(int)
    return out


def _swing_highs(high: np.ndarray) -> np.ndarray:
    """Marker dager der "high" er høyest de siste PIVOT_LEFT dagene og ikke
    overgås de neste PIVOT_RIGHT dagene."""
    series = pd.Series(high)
    left_max = series.shift(1).rolling(config.PIVOT_LEFT).max()
    right_max = series[::-1].shift(1).rolling(config.PIVOT_RIGHT).max()[::-1]
    return ((series >= left_max) & (series > right_max)).to_numpy()


def detect_breakouts(frame: pd.DataFrame) -> tuple[list[Breakout], Pivot | None]:
    """Finner alle brudd over pivot og den eventuelle pivoten som fortsatt er aktiv.

    En pivot er siste bekreftede topp. Den brytes første dag sluttkursen er
    over pivotkursen, og forkastes hvis basen blir for dyp eller for gammel.
    En nyere bekreftet topp erstatter den forrige (strammere base).
    """
    high = frame["high"].to_numpy(dtype=float)
    low = frame["low"].to_numpy(dtype=float)
    close = frame["close"].to_numpy(dtype=float)
    rel_vol = frame["rel_vol"].to_numpy(dtype=float)
    dates = frame["date"].to_numpy()
    swing = _swing_highs(high)

    breakouts: list[Breakout] = []
    pivot_idx: int | None = None
    base_low = np.nan

    def depth(idx: int) -> float:
        return (high[idx] - base_low) / high[idx] * 100

    for t in range(len(frame)):
        confirmed = t - config.PIVOT_RIGHT
        if confirmed >= 0 and swing[confirmed]:
            pivot_idx = confirmed
            base_low = low[confirmed : t + 1].min()
        if pivot_idx is None:
            continue

        base_low = min(base_low, low[t])
        if (
            depth(pivot_idx) > config.MAX_BASE_DEPTH_PCT
            or t - pivot_idx > config.MAX_PIVOT_AGE_BARS
        ):
            pivot_idx = None
        elif close[t] > high[pivot_idx]:
            rv = rel_vol[t]
            breakouts.append(
                Breakout(
                    date=pd.Timestamp(dates[t]),
                    close=float(close[t]),
                    pivot_date=pd.Timestamp(dates[pivot_idx]),
                    pivot_price=float(high[pivot_idx]),
                    rel_vol=float(rv),
                    with_volume=bool(rv >= config.BREAKOUT_RVOL),
                    base_depth=float(depth(pivot_idx)),
                    base_bars=t - pivot_idx,
                )
            )
            pivot_idx = None

    active = None
    if pivot_idx is not None:
        active = Pivot(
            date=pd.Timestamp(dates[pivot_idx]),
            price=float(high[pivot_idx]),
            base_depth=float(depth(pivot_idx)),
        )
    return breakouts, active


def analyze(df: pd.DataFrame) -> Analysis:
    """Full analyse av én aksje. `df` må ha date, open, high, low, close, volume sortert på dato."""
    frame = trend_template(df)
    breakouts, active = detect_breakouts(frame)
    return Analysis(frame=frame, breakouts=breakouts, active_pivot=active)
