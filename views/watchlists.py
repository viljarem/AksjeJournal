"""Watchlister med siste kurs, utvikling siden åpning og kommentar per aksje."""

import pandas as pd
import streamlit as st

from core import db
from core.prices import fetch_quotes
from ui.common import nb, open_chart, pct, pct_color, require_supabase, symbol, ticker_picker, universe

st.title("Watchlister")
require_supabase()


@st.cache_data(ttl=60, show_spinner=False)
def quotes(tickers: tuple[str, ...]) -> pd.DataFrame:
    return fetch_quotes(list(tickers))


def create_list(name: str) -> None:
    try:
        created = db.create_watchlist(name)
    except db.DuplicateError:
        st.error(f"Det finnes allerede en liste som heter «{name.strip()}».")
    else:
        # Velges på neste kjøring, før listevelgeren tegnes.
        st.session_state["new_watchlist_id"] = created["id"]
        st.rerun()


lists = db.list_watchlists()

if not lists:
    st.info("Du har ingen watchlister ennå. Lag den første her.")
    with st.form("first_list"):
        name = st.text_input("Navn på lista", placeholder="F.eks. Momentum")
        if st.form_submit_button("Opprett liste", type="primary") and name.strip():
            create_list(name)
    st.stop()

ids = [w["id"] for w in lists]
names = {w["id"]: w["name"] for w in lists}
if "new_watchlist_id" in st.session_state:
    st.session_state["watchlist_id"] = st.session_state.pop("new_watchlist_id")
if st.session_state.get("watchlist_id") not in ids:
    st.session_state["watchlist_id"] = ids[0]

top = st.columns([6, 1, 1], vertical_alignment="bottom")
list_id = top[0].segmented_control(
    "Liste", ids, format_func=names.get, required=True, key="watchlist_id", label_visibility="collapsed"
)
with top[1].popover("Ny liste", icon=":material/add:", width="stretch"):
    with st.form("new_list", border=False):
        name = st.text_input("Navn på lista")
        if st.form_submit_button("Opprett", type="primary") and name.strip():
            create_list(name)
with top[2].popover("Endre", icon=":material/settings:", width="stretch"):
    with st.form("rename_list", border=False):
        new_name = st.text_input("Nytt navn", value=names[list_id])
        if st.form_submit_button("Lagre navn") and new_name.strip():
            try:
                db.rename_watchlist(list_id, new_name)
            except db.DuplicateError:
                st.error(f"Det finnes allerede en liste som heter «{new_name.strip()}».")
            else:
                st.rerun()
    st.divider()
    st.caption("Sletter lista og kommentarene i den. Kan ikke angres.")
    if st.button(f"Slett «{names[list_id]}»", type="primary"):
        db.delete_watchlist(list_id)
        st.rerun()

with st.form("add_item", clear_on_submit=True, border=True):
    cols = st.columns([3, 5, 1.4], vertical_alignment="bottom")
    with cols[0]:
        new_ticker = ticker_picker("Legg til aksje", key="watchlist_new_ticker")
    comment = cols[1].text_input("Kommentar", placeholder="Hvorfor følger du den?")
    if cols[2].form_submit_button("Legg til", type="primary", width="stretch"):
        if not new_ticker:
            st.error("Velg en aksje.")
        else:
            try:
                db.add_watchlist_item(list_id, new_ticker, comment)
            except db.DuplicateError:
                st.error(f"{symbol(new_ticker)} ligger allerede i lista.")
            else:
                st.rerun()

items = db.list_watchlist_items(list_id)
if not items:
    st.info("Lista er tom. Legg til den første aksjen over.")
    st.stop()


@st.fragment(run_every=60)
def quote_table() -> None:
    """Kurstabellen. Oppdateres av seg selv hvert minutt."""
    stocks = universe()
    tickers = tuple(item["ticker"] for item in items)
    try:
        live = quotes(tickers)
    except Exception:
        live = pd.DataFrame()
        st.warning("Fikk ikke hentet ferske kurser akkurat nå. Viser siste lagrede sluttkurs.")

    rows = []
    for item in items:
        ticker = item["ticker"]
        quote = live.loc[ticker] if ticker in live.index else None
        fallback = stocks.loc[ticker, "close"] if ticker in stocks.index else None
        rows.append(
            {
                "Ticker": symbol(ticker, stocks),
                "Navn": stocks.loc[ticker, "name"] if ticker in stocks.index else "",
                "Siste": quote["last"] if quote is not None else fallback,
                "Siden åpning": quote["chg_open"] if quote is not None else None,
                "I dag": quote["chg_day"] if quote is not None else None,
                "Kommentar": item["comment"],
            }
        )
    table = pd.DataFrame(rows)
    styler = (
        table.style.format({"Siste": nb, "Siden åpning": pct, "I dag": pct}, na_rep="–")
        .map(pct_color, subset=["Siden åpning", "I dag"])
    )
    event = st.dataframe(
        styler,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Siden åpning": st.column_config.Column(help="Siste kurs mot dagens åpningskurs."),
            "I dag": st.column_config.Column(help="Siste kurs mot forrige sluttkurs."),
            "Kommentar": st.column_config.Column(width="large"),
        },
        key=f"watchlist-table-{list_id}-{st.session_state.get('table_nonce', 0)}",
    )
    st.caption(
        f"Kurser fra Yahoo Finance, ca. 15 minutter forsinket. Sist hentet kl. "
        f"{pd.Timestamp.now(tz='Europe/Oslo'):%H:%M}. Velg en rad for å åpne, endre eller fjerne."
    )

    if not event.selection.rows:
        return
    item = items[event.selection.rows[0]]
    name = symbol(item["ticker"], stocks)
    with st.container(border=True):
        cols = st.columns([1.3, 5, 1.2, 1.2], vertical_alignment="bottom")
        if cols[0].button(f"Åpne {name}", icon=":material/candlestick_chart:", width="stretch"):
            open_chart(item["ticker"])
        edited = cols[1].text_input("Kommentar", value=item["comment"], key=f"watchlist-comment-{item['id']}")
        if cols[2].button("Lagre", type="primary", width="stretch", disabled=edited.strip() == item["comment"]):
            db.update_watchlist_comment(item["id"], edited)
            st.rerun()
        if cols[3].button("Fjern", width="stretch", help=f"Fjerner {name} fra lista."):
            db.remove_watchlist_items([item["id"]])
            st.rerun()


quote_table()
