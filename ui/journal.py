"""Visning og registrering av journalnotater, brukt både i dagboken og på aksjesiden."""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from core import db, storage
from ui.common import local_time, open_chart, symbol, ticker_picker, universe


def pending_image_key(ticker: str) -> str:
    """Session-nøkkel for et chartbilde som venter på å bli lagt ved neste notat."""
    return f"chart_image_{ticker}"


def _save_entry(key: str, fixed_ticker: str | None) -> None:
    """Kjøres når skjemaet sendes. Teksten tømmes bare når notatet faktisk ble lagret."""
    state = st.session_state
    ticker = fixed_ticker or state.get(f"{key}_ticker")
    body = state.get(f"{key}_body", "")
    image = state.get(pending_image_key(ticker)) if ticker else None
    attach = bool(image) and state.get(f"{key}_attach", True)
    if not ticker:
        state[f"{key}_message"] = ("error", "Velg en aksje.")
    elif not body.strip():
        state[f"{key}_message"] = ("error", "Skriv et notat først.")
    else:
        try:
            image_path = None
            if attach:
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                image_path = f"journal/{ticker}/{stamp}.png"
            db.add_journal_entry(ticker, body, image_path)
            if attach:
                storage.save_image(image_path, image)
        except Exception as error:
            state[f"{key}_message"] = ("error", f"Notatet ble ikke lagret: {error}")
        else:
            state[f"{key}_body"] = ""
            if attach:
                state.pop(pending_image_key(ticker), None)
            state[f"{key}_message"] = ("ok", "Notatet er lagret.")


def entry_form(key: str, ticker: str | None = None) -> None:
    """Skjema for nytt notat. Med `ticker` satt gjelder notatet den aksjen."""
    image = st.session_state.get(pending_image_key(ticker)) if ticker else None
    if image:
        with st.container(border=True):
            st.image(image, caption="Chartbilde – legges ved neste notat", width="stretch")
            cols = st.columns([2, 2, 4])
            cols[0].download_button(
                "Last ned PNG", image, file_name=f"{ticker}_{datetime.now():%Y-%m-%d}.png",
                mime="image/png", key=f"{key}_download", icon=":material/download:",
            )
            if cols[1].button("Forkast bildet", key=f"{key}_discard", icon=":material/delete:"):
                st.session_state.pop(pending_image_key(ticker), None)
                st.rerun()
    with st.form(f"{key}_form", border=ticker is None):
        if ticker is None:
            ticker_picker("Aksje", key=f"{key}_ticker")
        st.text_area(
            "Nytt notat",
            height=110,
            placeholder="Hva ser du, og hva er planen?",
            key=f"{key}_body",
        )
        if image:
            st.checkbox("Legg ved chartbildet", value=True, key=f"{key}_attach")
        st.form_submit_button("Lagre notat", type="primary", on_click=_save_entry, args=(key, ticker))
    kind, text = st.session_state.pop(f"{key}_message", (None, None))
    if kind == "error":
        st.error(text)
    elif kind == "ok":
        st.toast(text)


@st.cache_data(show_spinner=False, ttl=3600)
def _image(path: str) -> bytes | None:
    return storage.load_image(path)


def render_entries(entries: list[dict], key: str, link_ticker: bool = True) -> None:
    stocks = universe()
    for entry in entries:
        with st.container(border=True):
            head = st.columns([6, 1], vertical_alignment="center")
            name = symbol(entry["ticker"], stocks)
            if link_ticker:
                head[0].markdown(f"**{name}** · {local_time(entry['created_at'])}")
            else:
                head[0].caption(local_time(entry["created_at"]))
            with head[1].popover("", icon=":material/more_horiz:"):
                if link_ticker and st.button("Åpne aksjen", key=f"{key}-open-{entry['id']}"):
                    open_chart(entry["ticker"])
                if st.button("Slett notatet", key=f"{key}-delete-{entry['id']}", type="primary"):
                    db.delete_journal_entry(entry["id"])
                    st.rerun()
            st.text(entry["body"])
            if entry.get("image_path"):
                image = _image(entry["image_path"])
                if image:
                    st.image(image, width="stretch")
                else:
                    st.caption("Bildet ble ikke funnet.")
