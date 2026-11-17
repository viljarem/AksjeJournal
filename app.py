"""AksjeJournal – startfil. Kjør lokalt med: streamlit run app.py"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core import config
from core.pipeline import update_market
from ui.common import OSLO, clear_data_cache, is_locked, load_screen, require_login

st.set_page_config(page_title="AksjeJournal", page_icon="📈", layout="wide")

# Navigasjonen settes opp før innlogging, slik at man havner på siden man åpnet.
page = st.navigation(
    {
        "Journal": [
            st.Page("views/watchlists.py", title="Watchlister", icon=":material/visibility:", default=True),
            st.Page("views/journal.py", title="Dagbok", icon=":material/edit_note:"),
            st.Page("views/trades.py", title="Handler", icon=":material/swap_horiz:"),
        ],
        "Analyse": [
            st.Page("views/minervini.py", title="Minervini", icon=":material/trending_up:"),
            st.Page("views/screener.py", title="Screener", icon=":material/filter_alt:"),
            st.Page("views/ipo.py", title="Nye noteringer", icon=":material/fiber_new:"),
            st.Page("views/aksje.py", title="Aksje og chart", icon=":material/candlestick_chart:"),
        ],
    },
    position="hidden" if is_locked() else "sidebar",
)
require_login()

with st.sidebar:
    market = st.selectbox(
        "Børs",
        list(config.MARKETS),
        format_func=lambda key: config.MARKETS[key].name,
        key="market",
        help="Gjelder Minervini, Screener og Nye noteringer.",
    )
    screen = load_screen(market)
    if screen is None:
        st.caption("Ingen kursdata hentet ennå.")
    else:
        updated = pd.Timestamp(screen["updated_at"].max()).tz_localize("UTC").tz_convert(OSLO)
        st.caption(
            f"Kurser til og med {screen['date'].max():%d.%m.%Y}. "
            f"Hentet {updated:%d.%m. kl. %H:%M}."
        )
    if st.button("Oppdater kurser nå", width="stretch", help="Tar vanligvis under ett minutt."):
        try:
            with st.spinner(f"Henter kurser for {config.MARKETS[market].name} …"):
                update_market(market, log=lambda message: None)
        except Exception as error:
            st.error(f"Oppdateringen feilet: {error}")
        else:
            clear_data_cache()
            st.rerun()

page.run()
