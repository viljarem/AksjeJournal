"""Regner om kjøp og salg til åpne og lukkede posisjoner.

En posisjon åpnes ved første kjøp og lukkes når beholdningen er solgt ned
til null. Resultat beregnes mot gjennomsnittlig kjøpskurs, inkludert kurtasje.
"""

from __future__ import annotations

from datetime import date

_EPS = 1e-9


def _as_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def holding(transactions: list[dict], ticker: str, on: date | None = None) -> float:
    """Beholdning i en aksje, eventuelt slik den var ved utgangen av datoen `on`."""
    total = 0.0
    for tx in transactions:
        if tx["ticker"] != ticker or (on is not None and _as_date(tx["traded_on"]) > on):
            continue
        total += float(tx["quantity"]) if tx["side"] == "buy" else -float(tx["quantity"])
    return total


def build_positions(transactions: list[dict], today: date | None = None) -> tuple[list[dict], list[dict]]:
    """Returnerer (åpne posisjoner, lukkede posisjoner).

    Lukkede posisjoner har `result`, `result_pct` (resultat i prosent av samlet
    kjøpsbeløp), `days` og `time_value_score` (prosent resultat per dag holdt).
    """
    today = today or date.today()
    ordered = sorted(transactions, key=lambda tx: (tx["ticker"], _as_date(tx["traded_on"]), tx["id"]))
    open_positions: list[dict] = []
    closed_positions: list[dict] = []
    current: dict | None = None

    def new_position(ticker: str, opened: date) -> dict:
        return {
            "ticker": ticker,
            "opened_on": opened,
            "quantity": 0.0,
            "cost": 0.0,  # kostpris for gjenværende beholdning
            "invested": 0.0,  # samlet kjøpsbeløp i posisjonens levetid
            "realized": 0.0,
            "comments": [],
            "oversold": False,
        }

    def close_out() -> None:
        nonlocal current
        if current is not None and current["quantity"] > _EPS:
            current["days"] = (today - current["opened_on"]).days
            current["avg_price"] = current["cost"] / current["quantity"]
            open_positions.append(current)
        current = None

    for tx in ordered:
        if current is not None and current["ticker"] != tx["ticker"]:
            close_out()
        when = _as_date(tx["traded_on"])
        qty = float(tx["quantity"])
        price = float(tx["price"])
        fee = float(tx.get("fee") or 0)

        if tx["side"] == "buy":
            if current is None:
                current = new_position(tx["ticker"], when)
            current["quantity"] += qty
            current["cost"] += qty * price + fee
            current["invested"] += qty * price + fee
        else:
            if current is None:
                continue  # salg uten beholdning: ingenting å regne resultat mot
            if qty > current["quantity"] + _EPS:
                current["oversold"] = True
                qty = current["quantity"]
            avg = current["cost"] / current["quantity"]
            current["realized"] += qty * (price - avg) - fee
            current["cost"] -= qty * avg
            current["quantity"] -= qty

        if tx.get("comment"):
            current["comments"].append(f"{when:%d.%m.%y}: {tx['comment']}")

        if current["quantity"] <= _EPS:
            days = (when - current["opened_on"]).days
            result_pct = current["realized"] / current["invested"] * 100 if current["invested"] else 0.0
            closed_positions.append(
                {
                    "ticker": current["ticker"],
                    "opened_on": current["opened_on"],
                    "closed_on": when,
                    "days": days,
                    "invested": current["invested"],
                    "result": current["realized"],
                    "result_pct": result_pct,
                    # Samme dag teller som én dag, så scoren alltid er definert.
                    "time_value_score": result_pct / max(days, 1),
                    "comments": current["comments"],
                    "oversold": current["oversold"],
                }
            )
            current = None

    close_out()
    closed_positions.sort(key=lambda p: p["closed_on"], reverse=True)
    open_positions.sort(key=lambda p: p["opened_on"], reverse=True)
    return open_positions, closed_positions
