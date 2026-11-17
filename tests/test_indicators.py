import numpy as np
import pandas as pd
import pytest

from core import config
from core.indicators import analyze, trend_template
from core.screener import STATUS_NEAR, STATUS_NO_VOLUME, STATUS_VOLUME, build_screen, summarize


def make_prices(closes, volumes=None, highs=None, lows=None):
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2022-01-03", periods=n),
            "open": closes,
            "high": closes if highs is None else np.asarray(highs, dtype=float),
            "low": closes if lows is None else np.asarray(lows, dtype=float),
            "close": closes,
            "volume": np.full(n, 1000.0) if volumes is None else np.asarray(volumes, dtype=float),
        }
    )


def base_then(tail, flat=60):
    """Flat kurs på 100, en topp på 110, og deretter `tail`."""
    return [100.0] * flat + [110.0] + list(tail)


# --- Trend template -----------------------------------------------------------
def test_steady_uptrend_meets_all_seven_criteria():
    frame = trend_template(make_prices(np.linspace(50, 150, 300)))
    last = frame.iloc[-1]
    assert last["score"] == 7
    assert last["sma50"] == pytest.approx(frame["close"].tail(50).mean())
    assert last["sma200"] == pytest.approx(frame["close"].tail(200).mean())


def test_steady_downtrend_meets_none():
    frame = trend_template(make_prices(np.linspace(150, 50, 300)))
    assert frame.iloc[-1]["score"] == 0


def test_template_requires_enough_history():
    frame = trend_template(make_prices(np.linspace(50, 150, 300)))
    first_possible = config.MIN_BARS_TEMPLATE - 1
    assert (frame["score"].iloc[:first_possible] == 0).all()
    assert frame["score"].iloc[first_possible] == 7


def test_52_week_criteria_use_thresholds():
    # Flat på 100, deretter fall til 74: mer enn 25 % under 52-ukers topp.
    frame = trend_template(make_prices([100.0] * 299 + [74.0]))
    assert not frame.iloc[-1]["c7"]
    frame = trend_template(make_prices([100.0] * 299 + [76.0]))
    assert frame.iloc[-1]["c7"]
    assert not frame.iloc[-1]["c6"]  # 76 er ikke 30 % over bunnen (76)


def test_relative_volume_is_volume_over_sma50():
    volumes = [1000.0] * 99 + [3000.0]
    frame = trend_template(make_prices([100.0] * 100, volumes=volumes))
    assert frame.iloc[-1]["rel_vol"] == pytest.approx(3000 / ((49 * 1000 + 3000) / 50))
    assert np.isnan(frame.iloc[10]["rel_vol"])  # for lite historikk


def test_template_periods_start_and_end():
    closes = list(np.linspace(50, 150, 260)) + [60.0] * 5
    analysis = analyze(make_prices(closes))
    dates = analysis.frame["date"]
    (period,) = analysis.template_periods()
    assert period == (dates.iloc[config.MIN_BARS_TEMPLATE - 1], dates.iloc[260])

    (ongoing,) = analyze(make_prices(np.linspace(50, 150, 260))).template_periods()
    assert ongoing[1] is None


# --- Pivoter og brudd ---------------------------------------------------------
def test_breakout_above_pivot_with_volume():
    closes = base_then([105.0] * 10 + [112.0])
    volumes = [1000.0] * (len(closes) - 1) + [3000.0]
    df = make_prices(closes, volumes=volumes)
    analysis = analyze(df)
    (breakout,) = analysis.breakouts
    assert breakout.pivot_price == 110
    assert breakout.pivot_date == df["date"].iloc[60]
    assert breakout.date == df["date"].iloc[-1]
    assert breakout.with_volume
    assert breakout.base_bars == 11
    assert breakout.base_depth == pytest.approx((110 - 105) / 110 * 100)
    assert analysis.active_pivot is None


def test_breakout_without_volume():
    analysis = analyze(make_prices(base_then([105.0] * 10 + [112.0])))
    (breakout,) = analysis.breakouts
    assert not breakout.with_volume
    assert breakout.rel_vol == pytest.approx(1.0)


def test_unbroken_pivot_stays_active():
    analysis = analyze(make_prices(base_then([105.0] * 10 + [109.0])))
    assert analysis.breakouts == []
    assert analysis.active_pivot.price == 110
    assert analysis.active_pivot.base_depth == pytest.approx((110 - 105) / 110 * 100)


def test_pivot_needs_confirmation_bars():
    # Bare 3 dager etter toppen: for tidlig til å kalle den en pivot.
    analysis = analyze(make_prices(base_then([105.0] * 3)))
    assert analysis.active_pivot is None
    analysis = analyze(make_prices(base_then([105.0] * config.PIVOT_RIGHT)))
    assert analysis.active_pivot.price == 110


def test_close_at_pivot_is_not_a_breakout():
    analysis = analyze(make_prices(base_then([105.0] * 10 + [110.0])))
    assert analysis.breakouts == []
    assert analysis.active_pivot.price == 110


def test_intraday_high_above_pivot_without_close_is_not_a_breakout():
    closes = base_then([105.0] * 10 + [108.0])
    highs = closes[:-1] + [115.0]
    analysis = analyze(make_prices(closes, highs=highs))
    assert analysis.breakouts == []


def test_deep_base_invalidates_pivot():
    # Fall på 40 % fra pivoten: basen er for dyp, bruddet teller ikke.
    analysis = analyze(make_prices(base_then([66.0] * 10 + [112.0])))
    assert analysis.breakouts == []


def test_old_pivot_expires():
    tail = [105.0] * (config.MAX_PIVOT_AGE_BARS + 1) + [112.0]
    analysis = analyze(make_prices(base_then(tail)))
    assert analysis.breakouts == []
    assert analysis.active_pivot is None


def test_newer_lower_high_replaces_pivot():
    closes = base_then([104.0] * 12 + [107.0] + [103.0] * 7 + [108.0])
    analysis = analyze(make_prices(closes))
    (breakout,) = analysis.breakouts
    assert breakout.pivot_price == 107


def test_high_too_close_to_previous_top_is_not_a_new_pivot():
    # 107 ligger innenfor 10 dager etter toppen på 110 og er derfor ingen egen pivot.
    closes = base_then([104.0] * 8 + [107.0] + [103.0] * 7 + [108.0])
    analysis = analyze(make_prices(closes))
    assert analysis.breakouts == []
    assert analysis.active_pivot.price == 110


# --- Screeningtabell ----------------------------------------------------------
def test_summarize_status_and_distances():
    closes = base_then([105.0] * 10 + [112.0])
    volumes = [1000.0] * (len(closes) - 1) + [3000.0]
    row = summarize("A", make_prices(closes, volumes=volumes))
    assert row["status"] == STATUS_VOLUME
    assert row["breakout_bars_ago"] == 0
    assert row["breakout_gain"] == pytest.approx((112 / 110 - 1) * 100)
    assert row["from_high"] == pytest.approx(0)

    row = summarize("A", make_prices(base_then([105.0] * 10 + [112.0])))
    assert row["status"] == STATUS_NO_VOLUME

    row = summarize("A", make_prices(base_then([105.0] * 10 + [109.0])))
    assert row["status"] == STATUS_NEAR
    assert row["to_pivot"] == pytest.approx((110 / 109 - 1) * 100)

    row = summarize("A", make_prices(base_then([100.0] * 10)))
    assert row["status"] == ""  # 10 % under pivot


def test_breakout_status_expires_after_recent_window():
    tail = [105.0] * 10 + [112.0] + [113.0] * config.RECENT_BREAKOUT_BARS
    row = summarize("A", make_prices(base_then(tail)))
    assert row["breakout_bars_ago"] == config.RECENT_BREAKOUT_BARS
    assert row["status"] == ""


def test_summarize_performance_and_short_history():
    row = summarize("A", make_prices(np.linspace(100, 200, 300)))
    closes = np.linspace(100, 200, 300)
    assert row["perf_3m"] == pytest.approx((closes[-1] / closes[-64] - 1) * 100)
    assert row["perf_12m"] == pytest.approx((closes[-1] / closes[-253] - 1) * 100)
    assert row["score"] == 7
    assert row["template_since"] == make_prices(closes)["date"].iloc[config.MIN_BARS_TEMPLATE - 1]

    row = summarize("NY", make_prices([10.0, 11.0, 12.0]))
    assert row["n_bars"] == 3
    assert row["score"] == 0
    assert np.isnan(row["perf_3m"])
    assert row["since_first"] == pytest.approx(20)
    assert row["chg_1d"] == pytest.approx((12 / 11 - 1) * 100)

    row = summarize("EN", make_prices([10.0]))
    assert np.isnan(row["chg_1d"])


def test_build_screen_ranks_and_clears_stale_status():
    strong = make_prices(np.linspace(50, 150, 300)).assign(ticker="STRONG")
    weak = make_prices(np.linspace(150, 50, 300)).assign(ticker="WEAK")
    # Suspendert aksje: siste kurs er et brudd, men flere uker gammelt.
    closes = base_then([105.0] * 10 + [112.0], flat=200)
    stale = make_prices(closes).assign(ticker="STALE")
    prices = pd.concat([strong, weak, stale], ignore_index=True)
    tickers = pd.DataFrame(
        {
            "ticker": ["STRONG", "WEAK"],
            "symbol": ["STR", "WK"],
            "name": ["Sterk", "Svak"],
            "segment": ["x", "x"],
            "sector": [None, None],
        }
    )
    screen = build_screen(prices, tickers).set_index("ticker")
    assert screen.loc["STRONG", "rs"] > screen.loc["WEAK", "rs"]
    assert screen.loc["STRONG", "name"] == "Sterk"
    assert screen.loc["STALE", "name"] == "STALE"  # mangler i tickerlista: faller tilbake på ticker
    assert screen.loc["STALE", "status"] == ""
