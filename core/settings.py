"""Hemmeligheter og Supabase-klient.

Verdier leses først fra miljøvariabler (GitHub Actions) og deretter fra
Streamlit-secrets (.streamlit/secrets.toml lokalt, «Secrets» i Community Cloud).
"""

from __future__ import annotations

import os
from functools import lru_cache


def get_secret(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:  # ingen secrets-fil
        return None
    return str(value) if value else None


def supabase_configured() -> bool:
    return bool(get_secret("SUPABASE_URL") and get_secret("SUPABASE_SERVICE_KEY"))


@lru_cache(maxsize=1)
def supabase_client():
    from supabase import create_client

    return create_client(get_secret("SUPABASE_URL"), get_secret("SUPABASE_SERVICE_KEY"))
