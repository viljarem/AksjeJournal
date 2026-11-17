"""Kjøp og salg: åpne og lukkede posisjoner med resultat og time value score."""

from datetime import date

import pandas as pd
import streamlit as st

from core import db
from core.positions import build_positions, holding
from ui.common import nb, pct, pct_color, require_supabase, symbol, ticker_picker, universe

st.title("Handler")
require_supabase()

transactions = db.list_transactions()
stocks = universe()

# Skjemaet får nye nøkler etter hver lagret handel, slik at feltene tømmes.
# Ved valideringsfeil beholdes det som er fylt inn.
n = st.session_state.get("trade_form_nonce", 0)

with st.form(f"new_trade_{n}", border=True):
    st.subheader("Registrer kjøp eller salg")
    row = st.columns([3, 1.4, 1.6])
    with row[0]:
        ticker = ticker_picker("Aksje", key=f"trade_ticker_{n}")
    side = row[1].radio(
        "Type", ["buy", "sell"], format_func={"buy": "Kjøp", "sell": "Salg"}.get, horizontal=True, key=f"trade_side_{n}"
    )
    traded_on = row[2].date_input(
        "Dato", value=date.today(), max_value=date.today(), format="DD.MM.YYYY", key=f"trade_date_{n}"
    )
    row = st.columns(3)
    quantity = row[0].number_input("Antall", min_value=0.0, step=1.0, value=None, placeholder="0", key=f"trade_qty_{n}")
    price = row[1].number_input(
        "Kurs", min_value=0.0, step=0.01, value=None, placeholder="0,00", format="%.4f", key=f"trade_price_{n}"
    )
    fee = row[2].number_input("Kurtasje", min_value=0.0, step=1.0, value=0.0, key=f"trade_fee_{n}")
    comment = st.text_input("Kommentar", placeholder="Hvorfor tok du handelen?", key=f"trade_comment_{n}")

    if st.form_submit_button("Lagre handel", type="primary"):
        owned = holding(transactions, ticker, on=traded_on) if ticker else 0.0
        if not ticker:
            st.error("Velg en aksje.")
        elif not quantity or quantity <= 0:
            st.error("Antall må være større enn 0.")
        elif price is None:
            st.error("Fyll inn kurs.")
        elif side == "sell" and quantity > owned + 1e-9:
            st.error(
                f"Du kan ikke selge {nb(quantity, 0)} {symbol(ticker, stocks)} den {traded_on:%d.%m.%Y}. "
                f"Beholdningen den dagen var {nb(owned, 0)}."
            )
        else:
            db.add_transaction(ticker, side, quantity, price, traded_on, fee=fee, comment=comment)
            st.session_state["trade_form_nonce"] = n + 1
            st.toast("Handelen er lagret.")
            st.rerun()

if not transactions:
    st.info("Ingen handler registrert ennå.")
    st.stop()

open_positions, closed_positions = build_positions(transactions)
tab_open, tab_closed, tab_all = st.tabs(
    [f"Åpne posisjoner ({len(open_positions)})", f"Lukkede posisjoner ({len(closed_positions)})", "Alle handler"]
)

with tab_open:
    if not open_positions:
        st.info("Ingen åpne posisjoner.")
    else:
        rows = []
        for pos in open_positions:
            last = stocks.loc[pos["ticker"], "close"] if pos["ticker"] in stocks.index else None
            value = last * pos["quantity"] if last is not None else None
            rows.append(
                {
                    "Ticker": symbol(pos["ticker"], stocks),
                    "Åpnet": pos["opened_on"],
                    "Dager": pos["days"],
                    "Antall": pos["quantity"],
                    "Snittkurs": pos["avg_price"],
                    "Siste sluttkurs": last,
                    "Urealisert": value - pos["cost"] if value is not None else None,
                    "Urealisert %": (value / pos["cost"] - 1) * 100 if value is not None and pos["cost"] else None,
                    "Realisert": pos["realized"],
                    "Kommentarer": " · ".join(pos["comments"]),
                }
            )
        table = pd.DataFrame(rows)
        st.dataframe(
            table.style.format(
                {
                    "Åpnet": "{:%d.%m.%Y}", "Antall": lambda v: nb(v, 0), "Snittkurs": nb, "Siste sluttkurs": nb,
                    "Urealisert": lambda v: nb(v, 0), "Urealisert %": pct, "Realisert": lambda v: nb(v, 0),
                },
                na_rep="–",
            ).map(pct_color, subset=["Urealisert", "Urealisert %", "Realisert"]),
            hide_index=True,
            column_config={
                "Realisert": st.column_config.Column(help="Resultat av delsalg i posisjonen så langt."),
                "Kommentarer": st.column_config.Column(width="large"),
            },
        )
        st.caption("Urealisert resultat er regnet mot siste lagrede sluttkurs, inkludert kurtasje ved kjøp.")

with tab_closed:
    if not closed_positions:
        st.info("Ingen lukkede posisjoner ennå. En posisjon lukkes når hele beholdningen er solgt.")
    else:
        results = [p["result"] for p in closed_positions]
        wins = sum(r > 0 for r in results)
        metrics = st.columns(4)
        metrics[0].metric("Samlet resultat", nb(sum(results), 0))
        metrics[1].metric("Vinnere", f"{wins} av {len(results)}")
        metrics[2].metric("Snitt resultat", pct(sum(p["result_pct"] for p in closed_positions) / len(results)))
        metrics[3].metric("Snitt holdetid", f"{sum(p['days'] for p in closed_positions) / len(results):.0f} dager")

        table = pd.DataFrame(
            [
                {
                    "Ticker": symbol(p["ticker"], stocks),
                    "Åpnet": p["opened_on"],
                    "Lukket": p["closed_on"],
                    "Dager": p["days"],
                    "Kjøpt for": p["invested"],
                    "Resultat": p["result"],
                    "Resultat %": p["result_pct"],
                    "Time value score": p["time_value_score"],
                    "Kommentarer": " · ".join(p["comments"]),
                }
                for p in closed_positions
            ]
        )
        st.dataframe(
            table.style.format(
                {
                    "Åpnet": "{:%d.%m.%Y}", "Lukket": "{:%d.%m.%Y}", "Kjøpt for": lambda v: nb(v, 0),
                    "Resultat": lambda v: nb(v, 0), "Resultat %": pct, "Time value score": lambda v: nb(v, 2),
                }
            ).map(pct_color, subset=["Resultat", "Resultat %", "Time value score"]),
            hide_index=True,
            column_config={
                "Time value score": st.column_config.Column(
                    help="Resultat i prosent delt på antall dager posisjonen ble holdt. "
                    "Høyere er bedre: mer avkastning per dag kapitalen var bundet."
                ),
                "Kommentarer": st.column_config.Column(width="large"),
            },
        )

with tab_all:
    table = pd.DataFrame(
        [
            {
                "Dato": date.fromisoformat(tx["traded_on"]),
                "Ticker": symbol(tx["ticker"], stocks),
                "Type": "Kjøp" if tx["side"] == "buy" else "Salg",
                "Antall": float(tx["quantity"]),
                "Kurs": float(tx["price"]),
                "Kurtasje": float(tx["fee"]),
                "Kommentar": tx["comment"],
            }
            for tx in reversed(transactions)
        ]
    )
    event = st.dataframe(
        table.style.format(
            {"Dato": "{:%d.%m.%Y}", "Antall": lambda v: nb(v, 0), "Kurs": nb, "Kurtasje": lambda v: nb(v, 0)}
        ),
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={"Kommentar": st.column_config.Column(width="large")},
        key=f"trades-{len(transactions)}",
    )
    if event.selection.rows:
        tx = list(reversed(transactions))[event.selection.rows[0]]
        st.caption("Sletting kan ikke angres, og posisjonene regnes ut på nytt.")
        if st.button(
            f"Slett {'kjøpet' if tx['side'] == 'buy' else 'salget'} av {symbol(tx['ticker'], stocks)} "
            f"den {date.fromisoformat(tx['traded_on']):%d.%m.%Y}",
            type="primary",
        ):
            db.delete_transaction(tx["id"])
            st.rerun()
    else:
        st.caption("Velg en rad for å slette en feilregistrert handel.")
