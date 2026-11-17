"""All lesing og skriving mot Supabase-tabellene (watchlister, journal, handler, tegninger)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from core.settings import supabase_client

_UNIQUE_VIOLATION = "23505"


class DuplicateError(Exception):
    """Raden finnes fra før (brudd på unik-regel)."""


def _table(name: str):
    return supabase_client().table(name)


def _insert(table: str, row: dict) -> dict:
    try:
        return _table(table).insert(row).execute().data[0]
    except Exception as error:
        if getattr(error, "code", None) == _UNIQUE_VIOLATION:
            raise DuplicateError(str(error)) from error
        raise


# --- Watchlister --------------------------------------------------------------
def list_watchlists() -> list[dict]:
    return _table("watchlists").select("id, name").order("created_at").execute().data


def create_watchlist(name: str) -> dict:
    return _insert("watchlists", {"name": name.strip()})


def rename_watchlist(watchlist_id: int, name: str) -> None:
    try:
        _table("watchlists").update({"name": name.strip()}).eq("id", watchlist_id).execute()
    except Exception as error:
        if getattr(error, "code", None) == _UNIQUE_VIOLATION:
            raise DuplicateError(str(error)) from error
        raise


def delete_watchlist(watchlist_id: int) -> None:
    _table("watchlists").delete().eq("id", watchlist_id).execute()


def list_watchlist_items(watchlist_id: int) -> list[dict]:
    return (
        _table("watchlist_items")
        .select("id, ticker, comment, added_at")
        .eq("watchlist_id", watchlist_id)
        .order("added_at")
        .execute()
        .data
    )


def add_watchlist_item(watchlist_id: int, ticker: str, comment: str = "") -> dict:
    return _insert(
        "watchlist_items",
        {"watchlist_id": watchlist_id, "ticker": ticker, "comment": comment.strip()},
    )


def update_watchlist_comment(item_id: int, comment: str) -> None:
    _table("watchlist_items").update({"comment": comment.strip()}).eq("id", item_id).execute()


def remove_watchlist_items(item_ids: list[int]) -> None:
    if item_ids:
        _table("watchlist_items").delete().in_("id", item_ids).execute()


def watchlist_comments(ticker: str) -> list[dict]:
    """Watchlistene en aksje ligger i, med kommentar: [{"watchlist": navn, "comment": tekst}]."""
    rows = (
        _table("watchlist_items")
        .select("comment, added_at, watchlists(name)")
        .eq("ticker", ticker)
        .order("added_at")
        .execute()
        .data
    )
    return [{"watchlist": row["watchlists"]["name"], "comment": row["comment"]} for row in rows]


# --- Journal ------------------------------------------------------------------
def add_journal_entry(ticker: str, body: str) -> dict:
    return _insert("journal_entries", {"ticker": ticker, "body": body.strip()})


def list_journal(
    ticker: str | None = None, search: str | None = None, limit: int = 30
) -> tuple[list[dict], int]:
    """Nyeste notater først. Returnerer (notater, totalt antall treff)."""
    query = _table("journal_entries").select("id, ticker, body, created_at", count="exact")
    if ticker:
        query = query.eq("ticker", ticker)
    if search and search.strip():
        escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.ilike("body", f"%{escaped}%")
    response = query.order("created_at", desc=True).limit(limit).execute()
    return response.data, response.count or 0


def delete_journal_entry(entry_id: int) -> None:
    _table("journal_entries").delete().eq("id", entry_id).execute()


# --- Kjøp og salg -------------------------------------------------------------
def list_transactions() -> list[dict]:
    return _table("transactions").select("*").order("traded_on").order("id").execute().data


def add_transaction(
    ticker: str,
    side: str,
    quantity: float,
    price: float,
    traded_on: date,
    fee: float = 0.0,
    comment: str = "",
) -> dict:
    return _insert(
        "transactions",
        {
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "price": price,
            "fee": fee,
            "traded_on": traded_on.isoformat(),
            "comment": comment.strip(),
        },
    )


def delete_transaction(transaction_id: int) -> None:
    _table("transactions").delete().eq("id", transaction_id).execute()


# --- Tegninger i chart --------------------------------------------------------
def get_drawings(ticker: str) -> list:
    rows = _table("chart_drawings").select("annotations").eq("ticker", ticker).execute().data
    return rows[0]["annotations"] if rows else []


def save_drawings(ticker: str, annotations: list) -> None:
    _table("chart_drawings").upsert(
        {
            "ticker": ticker,
            "annotations": annotations,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    ).execute()
