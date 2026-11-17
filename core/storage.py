"""Lagring av Parquet-filer.

Med Supabase konfigurert er Storage-bøtta fasit, og `data/` brukes bare som
lokal mellomlagring. Uten Supabase leses og skrives filene kun i `data/`.
"""

from __future__ import annotations

import io

import pandas as pd

from core.config import BUCKET, DATA_DIR
from core.settings import supabase_client, supabase_configured


def _is_not_found(error: Exception) -> bool:
    status = str(getattr(error, "status", ""))
    return status == "404" or "not found" in str(error).lower()


def save_frame(name: str, df: pd.DataFrame) -> None:
    """Skriver tabellen lokalt og laster den opp til Supabase Storage hvis konfigurert."""
    path = DATA_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, compression="zstd")
    payload = buffer.getvalue()
    path.write_bytes(payload)

    if supabase_configured():
        supabase_client().storage.from_(BUCKET).upload(
            name,
            payload,
            {"content-type": "application/octet-stream", "upsert": "true"},
        )


def load_frame(name: str) -> pd.DataFrame | None:
    """Leser en tabell. Returnerer None hvis den ikke finnes ennå."""
    path = DATA_DIR / name
    if supabase_configured():
        try:
            payload = supabase_client().storage.from_(BUCKET).download(name)
        except Exception as error:
            if _is_not_found(error):
                return None
            raise
        return pd.read_parquet(io.BytesIO(payload))
    if path.exists():
        return pd.read_parquet(path)
    return None
