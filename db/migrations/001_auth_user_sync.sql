-- =====================================================================
-- 001_auth_user_sync.sql
-- Mirrors new Supabase Auth users into public.user_account automatically.
-- The backend's memoir creation flow reads full_name from user_account,
-- and no backend code inserts into it — this trigger is that source.
--
-- Run after 000_base_schema.sql (needs the user_account table to exist).
-- =====================================================================

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.user_account (
        id,
        email,
        full_name,
        auth_provider_uid,
        last_login_at
    )
    values (
        new.id,
        new.email,
        case
            when coalesce(btrim(new.raw_user_meta_data ->> 'full_name'), '') = ''
                then 'Memoir Owner'
            else new.raw_user_meta_data ->> 'full_name'
        end,
        new.id,
        new.last_sign_in_at
    )
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();