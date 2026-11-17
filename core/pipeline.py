"""Daglig oppdatering av et marked: tickerliste, kurshistorikk og screeningtabell."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from core import config, storage
from core.prices import download_history
from core.screener import build_screen
from core.tickers import fetch_tickers

# Under denne andelen tickere med kursdata avbrytes oppdateringen uten å lagre.
MIN_COVERAGE = 0.5


def _load_tickers(market: str, log: Callable[[str], None]) -> pd.DataFrame:
    try:
        return fetch_tickers(market)
    except Exception as error:
        stored = storage.load_frame(config.tickers_file(market))
        if stored is None:
            raise
        log(f"  kunne ikke hente ny tickerliste ({error}); bruker den lagrede")
        return stored


def _window(last_date: pd.Timestamp) -> str:
    """Hvor langt tilbake vi må hente for å overlappe med lagret historikk."""
    gap = (pd.Timestamp.now().normalize() - last_date).days
    if gap <= 20:
        return "1mo"
    if gap <= 75:
        return "3mo"
    return f"{config.HISTORY_YEARS}y"


def _normalize(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.assign(
        ticker=prices["ticker"].astype(str), date=prices["date"].astype("datetime64[ns]")
    )


def merge_prices(
    stored: pd.DataFrame, fresh: pd.DataFrame, tolerance: float = 0.01
) -> tuple[pd.DataFrame, list[str]]:
    """Legger nye kursdager til lagret historikk.

    Lagrede dager beholdes urørt; dager som finnes i begge erstattes av de ferske
    (siste lagrede dag kan være hentet midt i børsdagen). Returnerer også tickere
    som må hentes helt på nytt: nye aksjer, aksjer med hull mellom lagret og fersk
    historikk, og aksjer der gamle sluttkurser er endret (splitt).
    """
    stored, fresh = _normalize(stored), _normalize(fresh)
    last_stored = stored.groupby("ticker")["date"].max()
    overlap = fresh.merge(
        stored[["ticker", "date", "close"]], on=["ticker", "date"], suffixes=("", "_old")
    )
    refetch = set(fresh["ticker"]) - set(overlap["ticker"])
    # Siste lagrede dag kan være ufullstendig og brukes ikke til kontroll.
    verify = overlap[overlap["date"] < overlap["ticker"].map(last_stored)]
    changed = (verify["close"] / verify["close_old"] - 1).abs() > tolerance
    refetch |= set(verify.loc[changed, "ticker"])

    merged = pd.concat([stored, fresh[~fresh["ticker"].isin(refetch)]], ignore_index=True)
    merged = merged.drop_duplicates(["ticker", "date"], keep="last")
    return merged, sorted(refetch)


def update_market(market: str, log: Callable[[str], None] = print) -> dict:
    """Henter nye kursdager, legger dem til lagret historikk og beregner screening."""
    name = config.MARKETS[market].name
    log(f"{name}: henter tickerliste")
    tickers = _load_tickers(market, log)
    wanted = tickers["ticker"].tolist()

    stored = storage.load_frame(config.prices_file(market))
    full_period = f"{config.HISTORY_YEARS}y"
    period = full_period if stored is None or stored.empty else _window(stored["date"].max())

    log(f"{name}: henter kurser ({period}) for {len(wanted)} tickere")
    fresh, missing = download_history(wanted, period=period, log=log)

    coverage = 1 - len(missing) / len(wanted)
    if coverage < MIN_COVERAGE:
        raise RuntimeError(
            f"{name}: fikk bare kurser for {coverage:.0%} av tickerne. "
            "Ingenting er lagret, forrige datasett beholdes."
        )

    refetched: list[str] = []
    if stored is None or stored.empty:
        prices = _normalize(fresh)
        rows_before = 0
    else:
        rows_before = len(stored)
        prices, refetch = merge_prices(stored, fresh)
        if refetch and period != full_period:
            log(f"  henter full historikk for {len(refetch)} nye eller endrede aksjer")
            full, _ = download_history(refetch, period=full_period, log=log)
            full = _normalize(full)
            refetched = sorted(full["ticker"].unique())
            prices = pd.concat([prices[~prices["ticker"].isin(refetched)], full], ignore_index=True)
        elif refetch:
            # Full historikk er allerede hentet: bruk den for disse aksjene.
            full = _normalize(fresh)
            full = full[full["ticker"].isin(refetch)]
            refetched = refetch
            prices = pd.concat([prices[~prices["ticker"].isin(refetch)], full], ignore_index=True)

    have = set(prices["ticker"])
    kept = sorted(t for t in missing if t in have)
    prices["ticker"] = prices["ticker"].astype("category")
    prices = prices.sort_values(["ticker", "date"]).reset_index(drop=True)

    log(f"{name}: beregner screening")
    # Historikk for aksjer som er tatt av børs beholdes i fila, men screenes ikke.
    screen = build_screen(prices[prices["ticker"].isin(wanted)], tickers)

    storage.save_frame(config.tickers_file(market), tickers)
    storage.save_frame(config.prices_file(market), prices)
    storage.save_frame(config.screen_file(market), screen)

    without_data = sorted(set(missing) - set(kept))
    summary = {
        "market": market,
        "tickers": len(tickers),
        "with_data": int(prices["ticker"].nunique()),
        "kept_from_previous": kept,
        "refetched": refetched,
        "without_data": without_data,
        "rows": len(prices),
        "new_rows": len(prices) - rows_before,
        "last_date": prices["date"].max(),
    }
    log(
        f"{name}: ferdig. {summary['with_data']} aksjer, {summary['rows']} kursrader "
        f"({summary['new_rows']:+d}), siste dato {summary['last_date']:%Y-%m-%d}"
    )
    if refetched:
        log(f"  full historikk hentet på nytt for {len(refetched)}: {', '.join(refetched)}")
    if kept:
        log(f"  ingen nye kurser, lagret historikk beholdt for {len(kept)}: {', '.join(kept)}")
    if without_data:
        log(f"  uten kursdata hos Yahoo ({len(without_data)}): {', '.join(without_data)}")
    return summary
