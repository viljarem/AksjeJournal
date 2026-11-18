"""Aksjeside: chart med tegneverktøy, pivoter og 7/7-perioder, pluss notater og watchlister."""

import pandas as pd
import streamlit as st

from core import db
from core.indicators import CRITERIA, CRITERIA_TEXT, analyze
from core.prices import with_quote
from core.screener import apply_quotes
from core.settings import supabase_configured
from ui.chart import indicator_editor, sma_editor, stock_chart
from ui.common import history, live_quotes, load_screen, nb, pct, ticker_picker, universe
from ui.journal import entry_form, render_entries

stocks = universe()
if stocks.empty:
    st.title("Aksje og chart")
    st.info("Det finnes ingen kursdata ennå. Trykk **Oppdater kurser nå** i menyen til venstre.")
    st.stop()

# Aksje valgt fra en tabell, eller den som sist ble vist.
state = st.session_state
pending = state.pop("pending_ticker", None)
if pending is None and "aksje_picker" not in state:
    pending = state.get("ticker")
if pending in stocks.index:
    state["aksje_picker"] = pending

ticker = ticker_picker("Aksje", key="aksje_picker", label_visibility="collapsed")
if not ticker:
    st.title("Aksje og chart")
    st.info("Velg en aksje over for å se chart, signaler og notater.")
    st.stop()
state["ticker"] = ticker

prices = history(ticker)
if prices is None:
    st.warning("Fant ingen kurshistorikk for denne aksjen.")
    st.stop()

info = stocks.loc[ticker]
screen = load_screen(info["market"])
row_frame = screen[screen["ticker"] == ticker]
quotes = live_quotes([ticker])
if quotes is not None and ticker in quotes.index:
    # Dagens uferdige candle legges til, og nøkkeltallene over chartet bruker fersk kurs.
    row_frame = apply_quotes(row_frame, quotes)
    prices = with_quote(prices, quotes.loc[ticker])
row = row_frame.iloc[0]
analysis = analyze(prices)

st.title(f"{info['symbol']} · {info['name']}")
metrics = st.columns(6)
metrics[0].metric("Siste kurs", nb(row["close"]), pct(row["chg_1d"]) if pd.notna(row["chg_1d"]) else None)
metrics[1].metric("Trend template", f"{row['score']}/7")
metrics[2].metric("Rel. volum", "–" if pd.isna(row["rel_vol"]) else f"{nb(row['rel_vol'])}x")
metrics[3].metric("Fra 52u topp", pct(row["from_high"]))
metrics[4].metric("RS", "–" if pd.isna(row["rs"]) else f"{row['rs']:.0f}")
if pd.notna(row["pivot_price"]):
    metrics[5].metric("Aktiv pivot", nb(row["pivot_price"]), f"{nb(row['to_pivot'], 1)} % opp", delta_color="off")
else:
    metrics[5].metric("Aktiv pivot", "Ingen")

signal = f"**{row['status']}** · " if row["status"] else ""
st.caption(f"{signal}Kurser til og med {row['date']:%d.%m.%Y}.")

with st.expander(f"Trend template: {row['score']} av 7 kriterier oppfylt"):
    for name in CRITERIA:
        icon = ":green[:material/check_circle:]" if row[name] else ":red[:material/cancel:]"
        st.markdown(f"{icon} {CRITERIA_TEXT[name]}")

drawings = db.get_drawings(ticker) if supabase_configured() else []
trades = db.ticker_transactions(ticker) if supabase_configured() else []
menus = st.columns([1, 1, 4])
with menus[0]:
    smas = sma_editor()
with menus[1]:
    indicators = indicator_editor()
stock_chart(ticker, f"{info['symbol']}", analysis, drawings, trades, smas, indicators)
st.caption(
    "Tegn med verktøyene til venstre i chartet. Dra i datoaksen for å strekke eller presse sammen stolpene, "
    "dra i kursaksen til høyre for å flytte kursen opp/ned (dobbeltklikk der for automatisk skala), "
    "dra i selve chartet for å panorere (også forbi siste kurs), rull for å zoome. "
    "Klikk på navnene under chartet for å vise eller skjule linjer, pivoter, brudd (B) og 7/7-perioder (grønt felt)."
)

if not supabase_configured():
    st.info("Notater og watchlister krever at Supabase er koblet til.")
    st.stop()

left, right = st.columns([3, 2], gap="large")

with left:
    st.subheader("Notater")
    entry_form(f"aksje_note_{ticker}", ticker=ticker)
    entries, total = db.list_journal(ticker=ticker, limit=50)
    if not entries:
        st.caption("Ingen notater på denne aksjen ennå.")
    else:
        render_entries(entries, key="aksje", link_ticker=False)
        if total > len(entries):
            st.caption(f"Viser de {len(entries)} nyeste av {total}. Resten finner du i dagboken.")

with right:
    st.subheader("Watchlister")
    memberships = db.watchlist_comments(ticker)
    if not memberships:
        st.caption("Aksjen ligger ikke i noen watchlist.")
    for membership in memberships:
        with st.container(border=True):
            st.markdown(f"**{membership['watchlist']}**")
            st.text(membership["comment"] or "Ingen kommentar.")

    lists = [w for w in db.list_watchlists() if w["name"] not in {m["watchlist"] for m in memberships}]
    if lists:
        with st.form(f"add_to_list_{ticker}", clear_on_submit=True):
            target = st.selectbox("Legg til i watchlist", lists, format_func=lambda w: w["name"])
            comment = st.text_input("Kommentar", placeholder="Hvorfor følger du den?")
            if st.form_submit_button("Legg til"):
                db.add_watchlist_item(target["id"], ticker, comment)
                st.rerun()
