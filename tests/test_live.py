import numpy as np
import pandas as pd
import pytest

from core.prices import fresh_quote, with_quote
from core.screener import apply_quotes


def history():
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-11-13", "2026-11-16"]).astype("datetime64[ms]"),
            "open": [10.0, 11.0],
            "high": [11.0, 12.0],
            "low": [9.0, 10.0],
            "close": [10.5, 11.5],
            "volume": [1000.0, 2000.0],
        }
    )


def quote(day, last=12.5, volume=500.0):
    return pd.Series(
        {"last": last, "open": 12.0, "high": 13.0, "low": 11.8, "volume": volume, "date": pd.Timestamp(day)}
    )


def test_with_quote_appends_new_day():
    out = with_quote(history(), quote("2026-11-17"))
    assert out["close"].tolist() == [10.5, 11.5, 12.5]
    assert out.iloc[-1][["open", "high", "low", "volume"]].tolist() == [12.0, 13.0, 11.8, 500.0]
    assert out["date"].is_monotonic_increasing


def test_with_quote_replaces_same_day_and_ignores_older_or_missing():
    out = with_quote(history(), quote("2026-11-16"))
    assert out["close"].tolist() == [10.5, 12.5]
    assert with_quote(history(), quote("2026-11-13"))["close"].tolist() == [10.5, 11.5]
    assert with_quote(history(), None)["close"].tolist() == [10.5, 11.5]
    assert with_quote(history(), quote("2026-11-17", last=np.nan))["close"].tolist() == [10.5, 11.5]


def test_fresh_quote_rejects_quotes_older_than_stored_history():
    quotes = pd.DataFrame(
        {"last": [6.0, np.nan], "date": pd.to_datetime(["2026-11-16", "2026-11-17"])}, index=["PSE.OL", "X"]
    )
    assert fresh_quote(quotes, "PSE.OL", pd.Timestamp("2026-11-17")) is None  # lagret er nyere
    assert fresh_quote(quotes, "PSE.OL", pd.Timestamp("2026-11-16"))["last"] == 6.0
    assert fresh_quote(quotes, "PSE.OL", None)["last"] == 6.0  # ukjent aksje: bruk kursen
    assert fresh_quote(quotes, "X", None) is None  # uten kurs
    assert fresh_quote(quotes, "FINNESIKKE", None) is None
    assert fresh_quote(None, "PSE.OL", None) is None


def screen():
    return pd.DataFrame(
        {
            "ticker": ["A", "B", "C"],
            "date": pd.to_datetime(["2026-11-16"] * 3).astype("datetime64[ms]"),
            "close": [100.0, 50.0, 20.0],
            "chg_1d": [1.0, 1.0, 1.0],
            "volume": [1000.0, 1000.0, 1000.0],
            "vol_sma50": [1000.0, 0.0, 1000.0],
            "rel_vol": [1.0, np.nan, 1.0],
            "high_52w": [110.0, 60.0, 25.0],
            "low_52w": [80.0, 40.0, 15.0],
            "from_high": [-9.09, -16.67, -20.0],
            "above_low": [25.0, 25.0, 33.3],
            "pivot_price": [105.0, np.nan, 22.0],
            "to_pivot": [5.0, np.nan, 10.0],
            "breakout_bars_ago": [2.0, np.nan, 4.0],
            "score": [7, 3, 1],
        }
    )


def test_apply_quotes_updates_price_volume_and_distances():
    quotes = pd.DataFrame(
        {
            "last": [112.0, 55.0],
            "open": [101.0, 50.0],
            "high": [113.0, 56.0],
            "low": [100.0, 49.0],
            "volume": [2500.0, 300.0],
            "chg_day": [12.0, 10.0],
            "date": pd.to_datetime(["2026-11-17", "2026-11-17"]),
        },
        index=["A", "B"],
    )
    out = apply_quotes(screen(), quotes).set_index("ticker")
    a = out.loc["A"]
    assert a["close"] == 112 and a["chg_1d"] == 12 and a["rel_vol"] == pytest.approx(2.5)
    assert a["high_52w"] == 113 and a["from_high"] == pytest.approx((112 / 113 - 1) * 100)
    assert a["above_low"] == pytest.approx(40) and a["to_pivot"] == pytest.approx((105 / 112 - 1) * 100)
    assert a["date"] == pd.Timestamp("2026-11-17") and a["score"] == 7
    assert a["breakout_bars_ago"] == 3  # ny børsdag teller med
    assert np.isnan(out.loc["B", "breakout_bars_ago"]) and out.loc["C", "breakout_bars_ago"] == 4
    assert out.loc["B", "close"] == 55 and np.isnan(out.loc["B", "rel_vol"])  # uten snittvolum
    assert np.isnan(out.loc["B", "to_pivot"])
    c = out.loc["C"]  # ingen fersk kurs: uendret
    assert c["close"] == 20 and c["rel_vol"] == 1 and c["date"] == pd.Timestamp("2026-11-16")


def test_apply_quotes_ignores_stale_or_missing_quotes():
    stale = pd.DataFrame(
        {"last": [1.0], "open": [1.0], "high": [1.0], "low": [1.0], "volume": [1.0], "chg_day": [0.0],
         "date": pd.to_datetime(["2026-11-10"])},
        index=["A"],
    )
    assert apply_quotes(screen(), stale)["close"].tolist() == [100.0, 50.0, 20.0]
    assert apply_quotes(screen(), None)["close"].tolist() == [100.0, 50.0, 20.0]
    assert apply_quotes(screen(), stale.iloc[0:0])["close"].tolist() == [100.0, 50.0, 20.0]
