-- AksjeJournal – databaseskjema for Supabase.
-- Kjør hele fila én gang i Supabase: SQL Editor → New query → Run.
-- Fila kan trygt kjøres på nytt; eksisterende tabeller og data røres ikke.

-- Watchlister ----------------------------------------------------------------
create table if not exists public.watchlists (
    id         bigint generated always as identity primary key,
    name       text        not null unique check (length(btrim(name)) > 0),
    created_at timestamptz not null default now()
);

create table if not exists public.watchlist_items (
    id           bigint generated always as identity primary key,
    watchlist_id bigint      not null references public.watchlists (id) on delete cascade,
    ticker       text        not null,
    comment      text        not null default '',
    added_at     timestamptz not null default now(),
    unique (watchlist_id, ticker)
);

create index if not exists watchlist_items_ticker_idx on public.watchlist_items (ticker);

-- Journal ----------------------------------------------------------------------
create table if not exists public.journal_entries (
    id         bigint generated always as identity primary key,
    ticker     text        not null,
    body       text        not null check (length(btrim(body)) > 0),
    created_at timestamptz not null default now()
);

create index if not exists journal_entries_created_idx on public.journal_entries (created_at desc);
create index if not exists journal_entries_ticker_idx on public.journal_entries (ticker, created_at desc);

-- Kjøp og salg -----------------------------------------------------------------
create table if not exists public.transactions (
    id         bigint generated always as identity primary key,
    ticker     text        not null,
    side       text        not null check (side in ('buy', 'sell')),
    quantity   numeric     not null check (quantity > 0),
    price      numeric     not null check (price >= 0),
    fee        numeric     not null default 0 check (fee >= 0),
    traded_on  date        not null,
    comment    text        not null default '',
    created_at timestamptz not null default now()
);

create index if not exists transactions_ticker_idx on public.transactions (ticker, traded_on);

-- Tegninger i chart (én rad per aksje) -----------------------------------------
create table if not exists public.chart_drawings (
    ticker      text primary key,
    annotations jsonb       not null default '[]'::jsonb,
    updated_at  timestamptz not null default now()
);

-- Tilgang ----------------------------------------------------------------------
-- Row Level Security uten regler: den offentlige (anon) nøkkelen får ikke lese
-- eller skrive noe. Appen og GitHub Actions bruker service-nøkkelen.
alter table public.watchlists      enable row level security;
alter table public.watchlist_items enable row level security;
alter table public.journal_entries enable row level security;
alter table public.transactions    enable row level security;
alter table public.chart_drawings  enable row level security;

grant select, insert, update, delete on
    public.watchlists,
    public.watchlist_items,
    public.journal_entries,
    public.transactions,
    public.chart_drawings
to service_role;

-- Privat lagringsbøtte for kurshistorikk og screening (Parquet-filer) ------------
insert into storage.buckets (id, name, public)
values ('market-data', 'market-data', false)
on conflict (id) do nothing;
