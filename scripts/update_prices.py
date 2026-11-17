"""Kjøres av GitHub Actions etter børsslutt: python -m scripts.update_prices --market oslo"""

from __future__ import annotations

import argparse
import sys

from core.config import MARKETS
from core.pipeline import update_market
from core.settings import supabase_configured


def main() -> int:
    parser = argparse.ArgumentParser(description="Oppdaterer kurser og screening for et marked.")
    parser.add_argument("--market", required=True, choices=[*MARKETS, "all"])
    parser.add_argument(
        "--require-supabase",
        action="store_true",
        help="Avbryt hvis Supabase ikke er konfigurert (brukes i GitHub Actions).",
    )
    args = parser.parse_args()

    if not supabase_configured():
        if args.require_supabase:
            print("SUPABASE_URL og SUPABASE_SERVICE_KEY må være satt.", file=sys.stderr)
            return 2
        print("Supabase er ikke konfigurert – lagrer kun lokalt i data/.")

    markets = list(MARKETS) if args.market == "all" else [args.market]
    failed = False
    for market in markets:
        try:
            update_market(market)
        except Exception as error:
            failed = True
            print(f"FEIL for {market}: {error}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
