import pandas as pd

from core.pipeline import merge_prices


def rows(ticker, start, closes, volume=1000.0):
    dates = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame(
        {
            "ticker": ticker,
            "date": dates,
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": volume,
        }
    )


def closes(frame, ticker):
    part = frame[frame["ticker"] == ticker].sort_values("date")
    return part["close"].tolist()


def test_new_day_is_appended_and_old_days_untouched():
    stored = rows("A", "2026-01-05", [10.0, 11.0, 12.0])
    fresh = rows("A", "2026-01-06", [11.0, 12.0, 13.0])
    merged, refetch = merge_prices(stored, fresh)
    assert refetch == []
    assert closes(merged, "A") == [10.0, 11.0, 12.0, 13.0]


def test_partial_last_day_is_replaced():
    # Siste lagrede dag ble hentet midt i børsdagen (12,0); endelig sluttkurs er 12,8.
    stored = rows("A", "2026-01-05", [10.0, 11.0, 12.0])
    fresh = rows("A", "2026-01-06", [11.0, 12.8])
    merged, refetch = merge_prices(stored, fresh)
    assert refetch == []
    assert closes(merged, "A") == [10.0, 11.0, 12.8]


def test_split_triggers_full_refetch_and_keeps_stored_rows():
    stored = rows("A", "2026-01-05", [100.0, 102.0, 104.0])
    fresh = rows("A", "2026-01-05", [10.0, 10.2, 10.4, 10.5])  # 10:1-splitt
    merged, refetch = merge_prices(stored, fresh)
    assert refetch == ["A"]
    assert closes(merged, "A") == [100.0, 102.0, 104.0]  # urørt til full historikk er hentet


def test_gap_or_new_ticker_triggers_refetch():
    stored = rows("A", "2026-01-05", [10.0, 11.0])
    fresh = pd.concat(
        [
            rows("A", "2026-02-02", [12.0, 13.0]),  # ingen overlapp: hull i historikken
            rows("NY", "2026-02-02", [5.0, 6.0]),  # ny aksje
        ]
    )
    merged, refetch = merge_prices(stored, fresh)
    assert refetch == ["A", "NY"]
    assert set(merged["ticker"]) == {"A"}


def test_ticker_without_fresh_data_keeps_history():
    stored = pd.concat([rows("A", "2026-01-05", [10.0, 11.0]), rows("B", "2026-01-05", [1.0, 2.0])])
    fresh = rows("A", "2026-01-06", [11.0, 12.0])
    merged, refetch = merge_prices(stored, fresh)
    assert refetch == []
    assert closes(merged, "B") == [1.0, 2.0]


def test_category_and_date_units_from_parquet_are_handled():
    stored = rows("A", "2026-01-05", [10.0, 11.0])
    stored["ticker"] = stored["ticker"].astype("category")
    stored["date"] = stored["date"].astype("datetime64[ms]")
    fresh = rows("A", "2026-01-06", [11.0, 12.0])
    fresh["date"] = fresh["date"].astype("datetime64[s]")
    merged, refetch = merge_prices(stored, fresh)
    assert refetch == []
    assert closes(merged, "A") == [10.0, 11.0, 12.0]
