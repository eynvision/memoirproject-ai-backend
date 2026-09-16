-- =====================================================================
-- 000_base_schema.sql
-- Creates the ten application tables the backend references. This is the
-- missing foundation: the Supabase project only had Auth enabled, so every
-- table-based query was failing with PGRST205.
--
-- Columns were reconstructed from the repository/service code so the names
-- and types match exactly what the app sends and reads.
--
-- Run order: 000_base_schema.sql  ->  001_auth_user_sync.sql  ->  001_memoir_chapters.sql
--
-- NOTE: Row Level Security is intentionally disabled for local/dev testing;
-- the backend mix of anon and service-role clients expects open tables today.
-- Enable RLS + policies before production.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. user_account — profile row mirrored from supabase.auth.users.
--    Mirrors the SQLAlchemy model in src/integrations/user.py.
--    Populated automatically by the auth sync trigger (001_auth_user_sync).
-- ---------------------------------------------------------------------
create table if not exists public.user_account (
    id                 uuid primary key,
    email              text not null,
    full_name          text not null check (btrim(full_name) <> ''),
    auth_provider_uid  text,
    last_login_at      timestamptz,
    created_at         timestamptz not null default now(),
    deleted_at         timestamptz
);

-- Emulate CITEXT uniqueness (case-insensitive) without requiring the extension
create unique index if not exists user_account_email_unique_idx
    on public.user_account (lower(email));

create unique index if not exists user_account_auth_provider_uid_unique_idx
    on public.user_account (auth_provider_uid)
    where auth_provider_uid is not null;

-- ---------------------------------------------------------------------
-- 2. memoir — the root memoir container for a subject.
-- ---------------------------------------------------------------------
create table if not exists public.memoir (
    id                 uuid primary key default gen_random_uuid(),
    subject_name       text not null,
    subject_born_on    date,
    subject_died_on    date,
    subject_is_living  boolean not null default false,
    description        text,
    visibility         text not null default 'invited_only',
    comment_policy     text not null default 'invited_only',
    created_by_user_id uuid references auth.users(id) on delete set null,
    status             text not null default 'draft'
                       check (status in ('draft', 'published')),
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now(),
    deleted_at         timestamptz
);

create index if not exists memoir_creator_idx
    on public.memoir (created_by_user_id);

-- ---------------------------------------------------------------------
-- 3. memoir_participant — who belongs to a memoir and with what role.
-- ---------------------------------------------------------------------
create table if not exists public.memoir_participant (
    id            uuid primary key default gen_random_uuid(),
    memoir_id     uuid not null references public.memoir(id) on delete cascade,
    user_id       uuid not null references auth.users(id) on delete cascade,
    role          text not null default 'contributor'
                  check (role in ('owner', 'admin', 'contributor', 'reader')),
    display_name  text,
    email         text,
    relationship  text,
    removed_at    timestamptz,
    created_at    timestamptz not null default now(),
    unique (memoir_id, user_id)
);

create index if not exists memoir_participant_user_idx
    on public.memoir_participant (user_id);

-- ---------------------------------------------------------------------
-- 4. memory — the core story record (text, dates, source, status).
-- ---------------------------------------------------------------------
create table if not exists public.memory (
    id                     uuid primary key default gen_random_uuid(),
    memoir_id              uuid not null references public.memoir(id) on delete cascade,
    author_participant_id  uuid references public.memoir_participant(id) on delete set null,
    title                  text,
    body_text              text,
    status                 text not null default 'draft'
                           check (status in ('draft', 'saved')),
    occurred_start         date,
    occurred_end           date,
    occurred_precision     text not null default 'day'
                           check (occurred_precision in ('day', 'month', 'year', 'decade')),
    date_source            text not null default 'owner'
                           check (date_source in ('owner', 'contributor', 'ai')),
    created_at             timestamptz not null default now(),
    updated_at             timestamptz not null default now(),
    deleted_at             timestamptz
);

create index if not exists memory_memoir_active_idx
    on public.memory (memoir_id, deleted_at);

create index if not exists memory_occurred_start_idx
    on public.memory (occurred_start);

-- ---------------------------------------------------------------------
-- 5. media_asset — metadata for photos/audio/video uploads.
-- ---------------------------------------------------------------------
create table if not exists public.media_asset (
    id                        uuid primary key default gen_random_uuid(),
    memoir_id                 uuid not null references public.memoir(id) on delete cascade,
    uploaded_by_participant_id uuid references public.memoir_participant(id) on delete set null,
    storage_key               text not null,
    kind                      text not null check (kind in ('photo', 'audio', 'video')),
    mime_type                 text,
    byte_size                 bigint,
    original_filename         text,
    duration_ms               integer,
    width_px                  integer,
    height_px                 integer,
    caption                   text,
    checksum_sha256           text,
    storage_tier              text not null default 'hot',
    transcription_status      text not null default 'pending'
                              check (transcription_status in ('pending', 'completed', 'failed', 'skipped')),
    created_at                timestamptz not null default now(),
    updated_at                timestamptz not null default now(),
    deleted_at                timestamptz
);

create index if not exists media_asset_memoir_idx
    on public.media_asset (memoir_id, deleted_at);

create unique index if not exists media_asset_checksum_idx
    on public.media_asset (memoir_id, checksum_sha256)
    where checksum_sha256 is not null;

-- ---------------------------------------------------------------------
-- 6. transcript — AssemblyAI transcription results for audio assets.
-- ---------------------------------------------------------------------
create table if not exists public.transcript (
    id              uuid primary key default gen_random_uuid(),
    media_asset_id  uuid not null references public.media_asset(id) on delete cascade,
    memoir_id       uuid not null references public.memoir(id) on delete cascade,
    raw_text        text,
    display_text    text,
    engine          text,
    confidence      numeric,
    language        text,
    created_at      timestamptz not null default now(),
    unique (media_asset_id, memoir_id)
);

create index if not exists transcript_memoir_idx
    on public.transcript (memoir_id);

-- ---------------------------------------------------------------------
-- 7. memory_media — junction linking memories to media assets.
-- ---------------------------------------------------------------------
create table if not exists public.memory_media (
    id             uuid primary key default gen_random_uuid(),
    memory_id      uuid not null references public.memory(id) on delete cascade,
    media_asset_id uuid not null references public.media_asset(id) on delete cascade,
    memoir_id      uuid not null references public.memoir(id) on delete cascade,
    created_at     timestamptz not null default now(),
    unique (memory_id, media_asset_id)
);

create index if not exists memory_media_asset_idx
    on public.memory_media (media_asset_id);

-- ---------------------------------------------------------------------
-- 8. comment — replies/notes attached to memories or media.
-- ---------------------------------------------------------------------
create table if not exists public.comment (
    id                     uuid primary key default gen_random_uuid(),
    memoir_id              uuid not null references public.memoir(id) on delete cascade,
    memory_id              uuid references public.memory(id) on delete cascade,
    media_asset_id         uuid references public.media_asset(id) on delete cascade,
    parent_comment_id      uuid references public.comment(id) on delete cascade,
    author_participant_id  uuid not null references public.memoir_participant(id) on delete cascade,
    body                   text not null,
    created_at             timestamptz not null default now(),
    updated_at             timestamptz not null default now(),
    deleted_at             timestamptz,
    hidden_at              timestamptz
);

create index if not exists comment_memory_idx
    on public.comment (memory_id, created_at);

create index if not exists comment_memoir_idx
    on public.comment (memoir_id);

-- ---------------------------------------------------------------------
-- 9. memoir_export — PDF export job tracking.
-- ---------------------------------------------------------------------
create table if not exists public.memoir_export (
    id                            uuid primary key default gen_random_uuid(),
    memoir_id                     uuid not null references public.memoir(id) on delete cascade,
    requested_by_participant_id   uuid references public.memoir_participant(id) on delete set null,
    kind                          text not null default 'pdf',
    status                        text not null default 'queued'
                                  check (status in ('queued', 'processing', 'ready', 'failed')),
    storage_key                   text,
    byte_size                     bigint,
    error_message                 text,
    created_at                    timestamptz not null default now(),
    updated_at                    timestamptz not null default now(),
    completed_at                  timestamptz
);

create index if not exists memoir_export_memoir_idx
    on public.memoir_export (memoir_id, created_at desc);

-- ---------------------------------------------------------------------
-- 10. memoir_link — share links with one active link per scope.
-- ---------------------------------------------------------------------
create table if not exists public.memoir_link (
    id                         uuid primary key default gen_random_uuid(),
    memoir_id                  uuid not null references public.memoir(id) on delete cascade,
    scope                      text not null,
    token                      text not null unique default gen_random_uuid()::text,
    created_by_participant_id  uuid references public.memoir_participant(id) on delete set null,
    open_count                 integer not null default 0,
    expires_at                 timestamptz,
    revoked_at                 timestamptz,
    created_at                 timestamptz not null default now(),
    updated_at                 timestamptz not null default now()
);

-- One live link per scope per memoir (matches share_repository.get_active_link)
create unique index if not exists memoir_link_active_scope_idx
    on public.memoir_link (memoir_id, scope)
    where revoked_at is null;

-- ---------------------------------------------------------------------
-- 11. search_memoirs_fts RPC — used by GET /api/search (see search_repository).
--     Simple full-text search across memory titles and bodies.
-- ---------------------------------------------------------------------
create or replace function public.search_memoirs_fts(
    target_memoir_id uuid,
    search_query text
)
returns table (
    memory_id uuid,
    title text,
    snippet text
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    q tsquery;
begin
    q := plainto_tsquery('english', search_query);
    return query
        select m.id,
               m.title,
               left(m.body_text, 200)
        from public.memory m
        where m.memoir_id = target_memoir_id
          and m.deleted_at is null
          and to_tsvector('english', coalesce(m.title, '') || ' ' || coalesce(m.body_text, '')) @@ q
        order by ts_rank(
            to_tsvector('english', coalesce(m.title, '') || ' ' || coalesce(m.body_text, '')),
            q
        ) desc;
end;
$$;