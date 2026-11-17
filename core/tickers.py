"""Henter tickerlister for hvert marked.

Alle funksjonene returnerer samme kolonner:
ticker (Yahoo-symbol), symbol (lokalt symbol), name, segment, sector, isin.
"""

from __future__ import annotations

import io

import pandas as pd
import requests

COLUMNS = ["ticker", "symbol", "name", "segment", "sector", "isin"]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

_EURONEXT_OSLO = (
    "https://live.euronext.com/en/pd_es/data/stocks/download"
    "?mics=XOSL%2CMERK%2CXOAS&initialLetter=&fe_type=csv"
    "&fe_decimal_separator=.&fe_date_format=d%2Fm%2FY"
)
_NASDAQ_STOCKHOLM = (
    "https://api.nasdaq.com/api/nordic/screener/shares"
    "?category=MAIN_MARKET&tableonly=false&market=STO"
)
_WIKIPEDIA_SP500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def _get(url: str) -> requests.Response:
    response = requests.get(url, headers=_HEADERS, timeout=30)
    response.raise_for_status()
    return response


def _finish(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reindex(columns=COLUMNS)
    for col in COLUMNS:
        df[col] = df[col].astype("string").str.strip()
    df = df[df["ticker"].notna() & df["symbol"].notna() & (df["symbol"] != "")]
    df = df.drop_duplicates("ticker").sort_values("symbol").reset_index(drop=True)
    if df.empty:
        raise ValueError("Tickerlista var tom")
    return df


def fetch_oslo() -> pd.DataFrame:
    """Oslo Børs, Euronext Expand og Euronext Growth fra Euronext sin CSV-eksport."""
    raw = pd.read_csv(io.BytesIO(_get(_EURONEXT_OSLO).content), sep=";", encoding="utf-8-sig")
    # Fila har noen informasjonslinjer uten ISIN rett under kolonneoverskriftene.
    raw = raw[raw["ISIN"].notna() & raw["Symbol"].notna()]
    return _finish(
        pd.DataFrame(
            {
                "ticker": raw["Symbol"].astype(str).str.strip() + ".OL",
                "symbol": raw["Symbol"],
                "name": raw["Name"],
                "segment": raw["Market"],
                "sector": None,
                "isin": raw["ISIN"],
            }
        )
    )


def fetch_stockholm() -> pd.DataFrame:
    """Hovedlista på Nasdaq Stockholm (Large, Mid og Small Cap)."""
    data = _get(_NASDAQ_STOCKHOLM).json()["data"]
    raw = pd.DataFrame(data["instrumentListing"]["rows"])
    symbol = raw["symbol"].astype(str).str.strip()
    return _finish(
        pd.DataFrame(
            {
                # Yahoo skriver aksjeklasser med bindestrek: "VOLV B" -> "VOLV-B.ST".
                "ticker": symbol.str.replace(" ", "-", regex=False) + ".ST",
                "symbol": symbol,
                "name": raw["fullName"],
                "segment": "Nasdaq Stockholm",
                "sector": raw["sector"].replace("", None),
                "isin": raw["isin"],
            }
        )
    )


def fetch_sp500() -> pd.DataFrame:
    """S&P 500-selskapene fra Wikipedia."""
    raw = pd.read_html(io.StringIO(_get(_WIKIPEDIA_SP500).text))[0]
    symbol = raw["Symbol"].astype(str).str.strip()
    return _finish(
        pd.DataFrame(
            {
                # Yahoo skriver aksjeklasser med bindestrek: "BRK.B" -> "BRK-B".
                "ticker": symbol.str.replace(".", "-", regex=False),
                "symbol": symbol,
                "name": raw["Security"],
                "segment": "S&P 500",
                "sector": raw["GICS Sector"],
                "isin": None,
            }
        )
    )


FETCHERS = {"oslo": fetch_oslo, "stockholm": fetch_stockholm, "sp500": fetch_sp500}


def fetch_tickers(market: str) -> pd.DataFrame:
    return FETCHERS[market]()
