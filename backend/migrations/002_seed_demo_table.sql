-- 002_seed_demo_table.sql
-- Purpose: Seed public.demo_table with representative demo rows.
-- Idempotency: Inserts only when the table is currently empty.

with seed(title, category, price, status) as (
  values
    ('Widget Pro',        'Electronics', 49.99,  'active'),
    ('Widget Mini',       'Electronics', 19.99,  'active'),
    ('Widget Max',        'Electronics', 89.99,  'active'),
    ('Leather Case',      'Accessories', 29.50,  'active'),
    ('Screen Protector',  'Accessories', 12.00,  'active'),
    ('USB-C Cable',       'Accessories', 9.99,   'active'),
    ('Ergo Keyboard',     'Peripherals', 79.00,  'active'),
    ('Gaming Mouse',      'Peripherals', 59.00,  'active'),
    ('4K Monitor',        'Peripherals', 299.00, 'active'),
    ('Desk Lamp',         'Home',        24.99,  'active'),
    ('Standing Desk',     'Home',        499.00, 'active'),
    ('Office Chair',      'Home',        229.00, 'active'),
    ('Notebook',          'Stationery',  4.99,   'active'),
    ('Pen Set',           'Stationery',  7.49,   'active'),
    ('Noise Cancelling',  'Audio',       149.00, 'active'),
    ('Bluetooth Speaker', 'Audio',       39.99,  'active'),
    ('Refurb Widget',     'Electronics', 34.99,  'archived'),
    ('Discontinued Case', 'Accessories', 14.50,  'archived'),
    ('Prototype Board',   'Electronics', 65.00,  'draft'),
    ('Sample Pack',       'Stationery',  2.99,   'draft')
)
insert into public.demo_table (title, category, price, status)
select s.title, s.category, s.price, s.status
from seed s
where not exists (select 1 from public.demo_table limit 1);

-- Optional: quick sanity query
-- select count(*) as seeded_rows from public.demo_table;