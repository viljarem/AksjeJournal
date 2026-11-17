from datetime import date

import pytest

from core.positions import build_positions, holding


def tx(id, ticker, side, quantity, price, traded_on, fee=0, comment=""):
    return {
        "id": id,
        "ticker": ticker,
        "side": side,
        "quantity": quantity,
        "price": price,
        "fee": fee,
        "traded_on": traded_on,
        "comment": comment,
    }


def test_closed_trade_result_and_time_value_score():
    txs = [
        tx(1, "EQNR.OL", "buy", 100, 200, "2026-01-05"),
        tx(2, "EQNR.OL", "sell", 100, 220, "2026-01-15"),
    ]
    open_pos, closed = build_positions(txs, today=date(2026, 2, 1))
    assert open_pos == []
    (trade,) = closed
    assert trade["result"] == pytest.approx(2000)
    assert trade["result_pct"] == pytest.approx(10)
    assert trade["days"] == 10
    assert trade["time_value_score"] == pytest.approx(1.0)


def test_fees_reduce_result():
    txs = [
        tx(1, "A", "buy", 10, 100, "2026-01-01", fee=50),
        tx(2, "A", "sell", 10, 110, "2026-01-11", fee=50),
    ]
    _, (trade,) = build_positions(txs)
    assert trade["invested"] == pytest.approx(1050)
    assert trade["result"] == pytest.approx(0)


def test_average_cost_with_partial_sells():
    txs = [
        tx(1, "A", "buy", 100, 10, "2026-01-01"),
        tx(2, "A", "buy", 100, 20, "2026-01-10"),  # snittkurs 15
        tx(3, "A", "sell", 50, 30, "2026-01-20"),  # +750
    ]
    (pos,), closed = build_positions(txs, today=date(2026, 1, 31))
    assert closed == []
    assert pos["quantity"] == pytest.approx(150)
    assert pos["avg_price"] == pytest.approx(15)
    assert pos["realized"] == pytest.approx(750)
    assert pos["days"] == 30

    txs.append(tx(4, "A", "sell", 150, 10, "2026-02-01"))  # -750
    open_pos, (trade,) = build_positions(txs)
    assert open_pos == []
    assert trade["result"] == pytest.approx(0)
    assert trade["invested"] == pytest.approx(3000)


def test_reopening_after_close_starts_new_position():
    txs = [
        tx(1, "A", "buy", 10, 100, "2026-01-01"),
        tx(2, "A", "sell", 10, 90, "2026-01-03"),
        tx(3, "A", "buy", 5, 80, "2026-03-01"),
    ]
    (pos,), (trade,) = build_positions(txs, today=date(2026, 3, 11))
    assert trade["result"] == pytest.approx(-100)
    assert trade["result_pct"] == pytest.approx(-10)
    assert trade["time_value_score"] == pytest.approx(-5)
    assert pos["opened_on"] == date(2026, 3, 1)
    assert pos["quantity"] == 5


def test_same_day_trade_counts_as_one_day():
    txs = [tx(1, "A", "buy", 10, 100, "2026-01-01"), tx(2, "A", "sell", 10, 105, "2026-01-01")]
    _, (trade,) = build_positions(txs)
    assert trade["days"] == 0
    assert trade["time_value_score"] == pytest.approx(5)


def test_positions_are_separate_per_ticker_and_order_independent():
    txs = [
        tx(4, "B", "sell", 1, 50, "2026-01-09"),
        tx(1, "A", "buy", 10, 100, "2026-01-01"),
        tx(3, "B", "buy", 1, 40, "2026-01-02"),
    ]
    open_pos, closed = build_positions(txs)
    assert [p["ticker"] for p in open_pos] == ["A"]
    assert [p["ticker"] for p in closed] == ["B"]
    assert closed[0]["result"] == pytest.approx(10)


def test_sell_without_holding_is_ignored_and_oversell_is_flagged():
    assert build_positions([tx(1, "A", "sell", 10, 100, "2026-01-01")]) == ([], [])
    txs = [tx(1, "A", "buy", 10, 100, "2026-01-01"), tx(2, "A", "sell", 15, 110, "2026-01-02")]
    _, (trade,) = build_positions(txs)
    assert trade["oversold"] is True
    assert trade["result"] == pytest.approx(100)  # regnet på de 10 som faktisk var eid


def test_comments_are_collected():
    txs = [
        tx(1, "A", "buy", 10, 100, "2026-01-01", comment="Brudd over pivot"),
        tx(2, "A", "sell", 10, 110, "2026-01-05", comment="Tok gevinst"),
    ]
    _, (trade,) = build_positions(txs)
    assert trade["comments"] == ["01.01.26: Brudd over pivot", "05.01.26: Tok gevinst"]


def test_holding_now_and_on_date():
    txs = [
        tx(1, "A", "buy", 10, 100, "2026-01-01"),
        tx(2, "A", "sell", 4, 100, "2026-01-10"),
        tx(3, "B", "buy", 7, 100, "2026-01-01"),
    ]
    assert holding(txs, "A") == 6
    assert holding(txs, "A", on=date(2026, 1, 5)) == 10
    assert holding(txs, "A", on=date(2026, 1, 10)) == 6
    assert holding(txs, "C") == 0
