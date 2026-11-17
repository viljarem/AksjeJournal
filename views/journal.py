"""Dagbok: notater per aksje med dato og tid, søk og filtrering."""

import streamlit as st

from core import db
from ui.common import require_supabase, ticker_picker
from ui.journal import entry_form, render_entries

st.title("Dagbok")
require_supabase()

PAGE_SIZE = 30

entry_form("journal_new")

filters = st.columns([3, 2])
search = filters[0].text_input("Søk i notater", placeholder="Søk i teksten", key="journal_search")
with filters[1]:
    only_ticker = ticker_picker("Vis bare aksje", key="journal_filter_ticker")

# Nytt søk starter på første side igjen.
signature = (search, only_ticker)
if st.session_state.get("journal_signature") != signature:
    st.session_state["journal_signature"] = signature
    st.session_state["journal_limit"] = PAGE_SIZE
limit = st.session_state["journal_limit"]

entries, total = db.list_journal(ticker=only_ticker, search=search, limit=limit)

if total == 0:
    st.info("Ingen notater passer søket." if (search.strip() or only_ticker) else "Ingen notater ennå.")
else:
    st.caption(f"Viser {len(entries)} av {total} notater, nyeste først.")
    with st.container(height=640, border=False):
        render_entries(entries, key="journal")
        if total > len(entries) and st.button("Vis flere"):
            st.session_state["journal_limit"] = limit + PAGE_SIZE
            st.rerun()
