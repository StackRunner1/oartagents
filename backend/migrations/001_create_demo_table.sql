-- 001_create_demo_table.sql
-- Purpose: Create a public.demo_table without RLS for the Supabase tool demo.
-- Safe to run multiple times if IF NOT EXISTS is supported. Otherwise guard in CI.

-- Schema
create table if not exists public.demo_table (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  category text,
  price numeric,
  status text,
  created_at timestamptz not null default now()
);

-- Useful indexes for query patterns (filters on equality and sorting by created_at)
create index if not exists demo_table_category_idx on public.demo_table (category);
create index if not exists demo_table_status_idx on public.demo_table (status);
create index if not exists demo_table_created_at_idx on public.demo_table (created_at desc);

-- Ensure RLS is disabled for this demo table
alter table public.demo_table disable row level security;

-- Note: In Supabase, gen_random_uuid() requires the pgcrypto extension.
-- If needed, enable it once per database:
-- create extension if not exists pgcrypto;