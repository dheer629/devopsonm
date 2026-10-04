#!/usr/bin/env bash
# DevOpsSentinel Web -- seed the demo PostgreSQL with a realistic schema.
#
# The Database page is only interesting with real tables and rows, so the demo
# fixtures include a small order/event schema. Everything runs through the
# postgres pod's own `psql`, so no client tooling is required on the workstation.
#
#   scripts/seed-demo-data.sh [NAMESPACE]
#
# Read-only note: the *application* only ever issues read-only statements. This
# script is dev-setup tooling and is the only place that writes to the database.
set -euo pipefail

NS="${1:-default}"

command -v kubectl >/dev/null 2>&1 || { printf 'kubectl is required on PATH\n' >&2; exit 3; }

POD=$(kubectl -n "$NS" get pods -l app=demo-postgres \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [[ -z "$POD" ]]; then
    printf 'no demo-postgres pod found in namespace %s\n' "$NS" >&2
    exit 4
fi

printf '[seed-demo-data] seeding schema into %s/%s\n' "$NS" "$POD"

kubectl -n "$NS" exec -i "$POD" -- psql -U demo -d demo -v ON_ERROR_STOP=1 -q <<'SQL'
drop view if exists public.v_customer_value;
drop table if exists public.demo_events;
drop table if exists public.demo_orders;
drop table if exists public.demo_customers;

create table public.demo_customers (
    id        serial primary key,
    name      text not null,
    tier      text not null default 'standard',
    country   text not null,
    joined_at timestamptz not null default now()
);

create table public.demo_orders (
    id          serial primary key,
    customer_id integer not null references public.demo_customers(id),
    sku         text not null,
    quantity    integer not null check (quantity > 0),
    amount      numeric(10,2) not null,
    status      text not null,
    created_at  timestamptz not null default now()
);

create table public.demo_events (
    id         bigserial primary key,
    order_id   integer references public.demo_orders(id),
    event_type text not null,
    payload    jsonb not null default '{}'::jsonb,
    at         timestamptz not null default now()
);

create index demo_orders_customer_idx on public.demo_orders (customer_id);
create index demo_orders_status_idx   on public.demo_orders (status);

create view public.v_customer_value as
    select c.name, c.tier, c.country,
           count(o.id) as orders,
           coalesce(sum(o.amount), 0)::numeric(12,2) as revenue
    from public.demo_customers c
    left join public.demo_orders o on o.customer_id = c.id
    group by c.name, c.tier, c.country;

insert into public.demo_customers (name, tier, country) values
    ('Ada Lovelace',      'gold',     'GB'),
    ('Grace Hopper',      'gold',     'US'),
    ('Alan Turing',       'gold',     'GB'),
    ('Katherine Johnson', 'silver',   'US'),
    ('Margaret Hamilton', 'silver',   'US'),
    ('Barbara Liskov',    'silver',   'US'),
    ('Radia Perlman',     'standard', 'US'),
    ('Shafi Goldwasser',  'standard', 'IL'),
    ('Anita Borg',        'standard', 'US'),
    ('Frances Allen',     'standard', 'US');

insert into public.demo_orders (customer_id, sku, quantity, amount, status, created_at)
select 1 + (g * 7) % 10,
       (array['SKU-KAFKA-01','SKU-POSTGRES-02','SKU-PVC-03','SKU-TLS-04','SKU-ETDP-05'])[1 + g % 5],
       1 + g % 5,
       round((9.99 + ((g * 137) % 88900) / 100.0)::numeric, 2),
       (array['pending','paid','shipped','delivered','refunded','failed'])[1 + g % 6],
       now() - (g * interval '3 hours')
from generate_series(0, 59) as g;

insert into public.demo_events (order_id, event_type, payload, at)
select o.id,
       (array['order.created','payment.authorized','shipment.dispatched','order.delivered'])[1 + o.id % 4],
       jsonb_build_object('orderId', o.id, 'source', 'demo-seed'),
       o.created_at
from public.demo_orders o;

select 'customers' as table, count(*) from public.demo_customers
union all select 'orders', count(*) from public.demo_orders
union all select 'events', count(*) from public.demo_events;
SQL

printf '[seed-demo-data] done\n'
