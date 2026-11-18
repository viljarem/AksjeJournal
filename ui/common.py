"""Felles byggeklosser for sidene: innlogging, datalasting, aksjevelger og formatering."""

from __future__ import annotations

import hmac
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from core import config, storage
from core.prices import fetch_quotes
from core.screener import apply_quotes
from core.settings import get_secret, supabase_configured

CHART_PAGE = "views/aksje.py"
OSLO = ZoneInfo("Europe/Oslo")
GREEN, RED, AMBER, BLUE = "#16a34a", "#dc2626", "#d97706", "#2563eb"


# --- Innlogging ---------------------------------------------------------------
def is_locked() -> bool:
    """Sant når APP_PASSWORD er satt og brukeren ikke har logget inn."""
    return bool(get_secret("APP_PASSWORD")) and not st.session_state.get("authenticated")


def require_login() -> None:
    """Ber om passord hvis APP_PASSWORD er satt i secrets."""
    if not is_locked():
        return
    password = get_secret("APP_PASSWORD")
    st.title("AksjeJournal")
    with st.form("login"):
        entered = st.text_input("Passord", type="password")
        if st.form_submit_button("Logg inn", type="primary"):
            if hmac.compare_digest(entered.encode(), password.encode()):
                st.session_state["authenticated"] = True
                st.rerun()
            st.error("Feil passord.")
    st.stop()


def require_supabase() -> None:
    """Stopper siden med en forklaring hvis Supabase ikke er koblet til."""
    if supabase_configured():
        return
    st.info(
        "Denne siden lagrer data i Supabase, som ikke er koblet til ennå. "
        "Legg inn `SUPABASE_URL` og `SUPABASE_SERVICE_KEY` i secrets."
    )
    st.stop()


# --- Data ---------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner="Henter screening …")
def _screen(market: str) -> pd.DataFrame | None:
    return storage.load_frame(config.screen_file(market))


@st.cache_resource(ttl=600, show_spinner="Henter kurshistorikk …")
def _prices(market: str) -> pd.DataFrame | None:
    return storage.load_frame(config.prices_file(market))


@st.cache_data(ttl=60, show_spinner="Henter ferske kurser …")
def _quotes(tickers: tuple[str, ...]) -> tuple[pd.DataFrame, str]:
    return fetch_quotes(list(tickers)), pd.Timestamp.now(tz=OSLO).strftime("%H:%M")


def live_quotes(tickers) -> pd.DataFrame | None:
    """Ferske kurser fra Yahoo (mellomlagres ett minutt), eller None hvis hentingen feilet."""
    try:
        quotes, fetched = _quotes(tuple(str(t) for t in tickers))
    except Exception:
        quotes, fetched = None, None
    if quotes is None or quotes.empty:
        st.session_state["live_time"] = None
        return None
    st.session_state["live_time"] = fetched
    return quotes


def clear_data_cache() -> None:
    _screen.clear()
    _prices.clear()


def load_screen(market: str) -> pd.DataFrame | None:
    """Screeningtabellen for et marked, eller None hvis kurser aldri er hentet."""
    try:
        return _screen(market)
    except Exception as error:
        st.error(f"Kunne ikke lese data for {config.MARKETS[market].name}: {error}")
        st.stop()


def current_market() -> str:
    return st.session_state.get("market", "oslo")


def require_screen() -> tuple[str, pd.DataFrame]:
    """Valgt marked og screeningtabellen. Stopper siden hvis markedet mangler data."""
    market = current_market()
    screen = load_screen(market)
    if screen is None:
        st.info(
            f"Det finnes ingen kursdata for {config.MARKETS[market].name} ennå. "
            "Trykk **Oppdater kurser nå** i menyen til venstre."
        )
        st.stop()
    return market, apply_quotes(screen, live_quotes(screen["ticker"]))


def universe() -> pd.DataFrame:
    """Alle aksjer med kursdata på tvers av markeder, indeksert på ticker."""
    frames = []
    for market in config.MARKETS:
        screen = load_screen(market)
        if screen is not None:
            frames.append(screen[["ticker", "symbol", "name", "close", "date"]].assign(market=market))
    if not frames:
        return pd.DataFrame(columns=["symbol", "name", "close", "date", "market"])
    return pd.concat(frames, ignore_index=True).drop_duplicates("ticker").set_index("ticker")


def history(ticker: str) -> pd.DataFrame | None:
    """Kurshistorikk for én aksje, sortert på dato."""
    stocks = universe()
    if ticker not in stocks.index:
        return None
    try:
        prices = _prices(stocks.loc[ticker, "market"])
    except Exception as error:
        st.error(f"Kunne ikke lese kurshistorikk: {error}")
        st.stop()
    if prices is None:
        return None
    rows = prices[prices["ticker"] == ticker]
    if rows.empty:
        return None
    return rows.drop(columns="ticker").sort_values("date").reset_index(drop=True)


# --- Aksjevelger og navigering --------------------------------------------------
def symbol(ticker: str, stocks: pd.DataFrame | None = None) -> str:
    stocks = universe() if stocks is None else stocks
    return str(stocks.loc[ticker, "symbol"]) if ticker in stocks.index else ticker


def ticker_picker(label: str, key: str, label_visibility: str = "visible") -> str | None:
    stocks = universe().sort_values("symbol")
    return st.selectbox(
        label,
        stocks.index.tolist(),
        index=None,
        format_func=lambda t: f"{stocks.loc[t, 'symbol']} · {stocks.loc[t, 'name']}",
        placeholder="Søk på ticker eller navn",
        key=key,
        label_visibility=label_visibility,
    )


def open_chart(ticker: str) -> None:
    """Går til aksjesiden for tickeren."""
    st.session_state["pending_ticker"] = ticker
    # Ny nøkkel på tabellene, slik at raden ikke fortsatt er valgt når man kommer tilbake.
    st.session_state["table_nonce"] = st.session_state.get("table_nonce", 0) + 1
    st.switch_page(CHART_PAGE)


# --- Formatering --------------------------------------------------------------
def nb(value, decimals: int = 2) -> str:
    """Tall med norsk formatering: 1 234,50."""
    if value is None or pd.isna(value):
        return "–"
    return f"{value:,.{decimals}f}".replace(",", "\u00a0").replace(".", ",")


def pct(value, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return "–"
    return f"{'+' if value > 0 else ''}{nb(value, decimals)} %"


def local_time(value: str) -> str:
    """ISO-tidspunkt fra databasen som norsk dato og klokkeslett."""
    return pd.Timestamp(value).tz_convert(OSLO).strftime("%d.%m.%Y kl. %H:%M")


def pct_color(value) -> str:
    if value is None or pd.isna(value) or value == 0:
        return ""
    return f"color: {GREEN}" if value > 0 else f"color: {RED}"
