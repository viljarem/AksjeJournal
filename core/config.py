"""Felles konfigurasjon: markeder, filnavn og terskler for screening."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

# Supabase Storage-bøtte for Parquet-filene.
BUCKET = "market-data"

# Antall år med historikk som lagres per aksje.
HISTORY_YEARS = 5


@dataclass(frozen=True)
class Market:
    key: str
    name: str
    currency: str


MARKETS: dict[str, Market] = {
    "oslo": Market("oslo", "Oslo Børs", "NOK"),
    "stockholm": Market("stockholm", "Nasdaq Stockholm", "SEK"),
    "sp500": Market("sp500", "S&P 500", "USD"),
}

# --- Minervini trend template -------------------------------------------------
SMA200_TREND_BARS = 21  # SMA200 må være høyere enn for ca. én måned siden
MIN_BARS_TEMPLATE = 200 + SMA200_TREND_BARS  # færre børsdager enn dette = "ny notering"
BARS_52W = 252
ABOVE_LOW_PCT = 30.0  # minst 30 % over 52-ukers bunn
WITHIN_HIGH_PCT = 25.0  # høyst 25 % under 52-ukers topp

# --- Pivot og brudd -----------------------------------------------------------
PIVOT_LEFT = 10  # pivot-toppen må være høyeste "high" de 10 foregående dagene
PIVOT_RIGHT = 5  # ... og ikke overgått de 5 neste dagene (da er pivoten bekreftet)
MAX_BASE_DEPTH_PCT = 35.0  # faller kursen mer enn dette under pivoten, forkastes den
MAX_PIVOT_AGE_BARS = 252  # en pivot som ikke er brutt på ett år forkastes
BREAKOUT_RVOL = 1.5  # brudd "med volum" = volum minst 1,5 x SMA50 av volum
RECENT_BREAKOUT_BARS = 5  # "nylig brudd" = innen de siste 5 børsdagene
NEAR_PIVOT_PCT = 5.0  # "nær brudd" = høyst 5 % under aktiv pivot


def prices_file(market: str) -> str:
    return f"prices/{market}.parquet"


def screen_file(market: str) -> str:
    return f"screens/{market}.parquet"


def tickers_file(market: str) -> str:
    return f"tickers/{market}.parquet"
