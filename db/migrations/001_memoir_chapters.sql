-- =====================================================================
-- 001_memoir_chapters.sql
-- Adds the AI memoir-organisation schema: generation job tracking,
-- chapter suggestions, and chapter-to-memory membership with ordering.
-- Run this in the Supabase SQL Editor (or any psql client).
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Generation jobs: one row per AI organisation run for a memoir.
--    The frontend polls this via GET .../generation-status.
-- ---------------------------------------------------------------------
create table if not exists public.memoir_generation (
    id                  uuid primary key default gen_random_uuid(),
    memoir_id           uuid not null references public.memoir(id) on delete cascade,
    status              text not null default 'running'
                        check (status in ('running', 'completed', 'failed')),
    memory_count        integer,
    error_message       text,
    started_by_user_id  uuid,
    started_at          timestamptz not null default now(),
    finished_at         timestamptz
);

create index if not exists memoir_generation_memoir_idx
    on public.memoir_generation (memoir_id, started_at desc);

-- ---------------------------------------------------------------------
-- 2. Suggested chapters. status starts as 'draft' (AI suggestion) and
--    only becomes 'published' after the owner reviews and publishes.
-- ---------------------------------------------------------------------
create table if not exists public.memoir_chapter (
    id          uuid primary key default gen_random_uuid(),
    memoir_id   uuid not null references public.memoir(id) on delete cascade,
    title       text not null,
    subtitle    text,
    summary     text,
    status      text not null default 'draft'
                check (status in ('draft', 'published')),
    sort_order  integer not null default 0,
    confidence  numeric(3,2),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    deleted_at  timestamptz
);

create index if not exists memoir_chapter_memoir_idx
    on public.memoir_chapter (memoir_id, status, sort_order);

-- ---------------------------------------------------------------------
-- 3. Chapter membership. sort_order controls the order memories appear
--    inside a chapter; unique(chapter_id, memory_id) stops duplicates.
--    Cascade delete keeps junction rows tidy when a chapter is removed.
-- ---------------------------------------------------------------------
create table if not exists public.chapter_memory (
    id          uuid primary key default gen_random_uuid(),
    chapter_id  uuid not null references public.memoir_chapter(id) on delete cascade,
    memoir_id   uuid not null references public.memoir(id) on delete cascade,
    memory_id   uuid not null references public.memory(id) on delete cascade,
    sort_order  integer not null default 0,
    created_at  timestamptz not null default now(),
    unique (chapter_id, memory_id)
);

create index if not exists chapter_memory_chapter_idx
    on public.chapter_memory (chapter_id, sort_order);

create index if not exists chapter_memory_memory_idx
    on public.chapter_memory (memory_id);