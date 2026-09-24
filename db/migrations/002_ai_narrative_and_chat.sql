-- =====================================================================
-- 002_ai_narrative_and_chat.sql
-- Adds the AI narrative layer (personality profile + emotional rewrite of
-- memories) and the chat agent (message history + pending actions).
-- The user's original memory text (memory.body_text) is never modified.
-- Run this in the Supabase SQL Editor (or any psql client), after
-- 000_base_schema.sql and 001_memoir_chapters.sql.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Memoir-level narrative state: the personality profile ("vibe") and
--    the status of the profile + rewrite job (polled by the frontend).
-- ---------------------------------------------------------------------
alter table public.memoir
    add column if not exists personality_profile jsonb,
    add column if not exists narrative_status text not null default 'idle'
        check (narrative_status in ('idle', 'running', 'completed', 'failed')),
    add column if not exists narrative_error text,
    add column if not exists narrative_started_at timestamptz,
    add column if not exists narrative_updated_at timestamptz;

-- ---------------------------------------------------------------------
-- 2. AI-rewritten version of a memory, stored beside the original.
-- ---------------------------------------------------------------------
alter table public.memory
    add column if not exists rewritten_text text,
    add column if not exists rewritten_at timestamptz;

-- ---------------------------------------------------------------------
-- 3. Why the AI grouped a chapter's memories together (lets the chat
--    agent answer "why did you group these?").
-- ---------------------------------------------------------------------
alter table public.memoir_chapter
    add column if not exists rationale text;

-- ---------------------------------------------------------------------
-- 4. Chat history. One row per LangChain message; `message` holds the
--    full message_to_dict payload so tool calls replay correctly.
--    Conversations are scoped to (memoir_id, user_id).
-- ---------------------------------------------------------------------
create table if not exists public.memoir_chat_message (
    id          uuid primary key default gen_random_uuid(),
    memoir_id   uuid not null references public.memoir(id) on delete cascade,
    user_id     uuid not null references auth.users(id) on delete cascade,
    seq         bigint generated always as identity,
    role        text not null check (role in ('human', 'ai', 'tool')),
    message     jsonb not null,
    created_at  timestamptz not null default now()
);

create index if not exists memoir_chat_message_thread_idx
    on public.memoir_chat_message (memoir_id, user_id, seq);

-- ---------------------------------------------------------------------
-- 5. Changes the chat agent proposes. Nothing is applied until the user
--    confirms: pending -> processing -> applied | failed, or rejected.
-- ---------------------------------------------------------------------
create table if not exists public.memoir_chat_action (
    id           uuid primary key default gen_random_uuid(),
    memoir_id    uuid not null references public.memoir(id) on delete cascade,
    user_id      uuid not null references auth.users(id) on delete cascade,
    action_type  text not null
                 check (action_type in (
                     'update_chapter', 'reorder_chapter_memories',
                     'rewrite_memory', 'regenerate_chapters',
                     'regenerate_narrative')),
    payload      jsonb not null default '{}'::jsonb,
    summary      text not null,
    status       text not null default 'pending'
                 check (status in ('pending', 'processing', 'applied', 'rejected', 'failed')),
    error        text,
    created_at   timestamptz not null default now(),
    resolved_at  timestamptz
);

create index if not exists memoir_chat_action_memoir_idx
    on public.memoir_chat_action (memoir_id, user_id, created_at desc);
