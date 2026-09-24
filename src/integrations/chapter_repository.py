"""
@file chapter_repository.py
@description Data access layer for AI memoir organisation: reads memories for
generation, tracks generation job status, persists chapter suggestions with
their member memories, reorders members, and applies publication.
"""

from src.integrations.supabase_client import supabase_admin


def fetch_memories_for_organisation(memoir_id: str):
    """
    Fetches all active memories of a memoir, earliest first, with the fields
    needed to normalise an AI prompt. Only non-deleted records are returned.
    """
    return supabase_admin.table("memory") \
        .select(
            "id, title, body_text, occurred_start, occurred_end, occurred_precision"
        ) \
        .eq("memoir_id", memoir_id) \
        .is_("deleted_at", "null") \
        .order("occurred_start") \
        .execute()


# ---------------------------------------------------------------------------
# Generation job tracking
# ---------------------------------------------------------------------------

def insert_generation_record(record: dict):
    """Creates a new generation job row (status 'running')."""
    return supabase_admin.table("memoir_generation").insert(record).execute()


def update_generation_record(generation_id: str, updates: dict):
    """Updates a generation job row, e.g. marking it completed or failed."""
    return supabase_admin.table("memoir_generation") \
        .update(updates) \
        .eq("id", generation_id) \
        .execute()


def fetch_latest_generation(memoir_id: str):
    """Returns the most recent generation job for the memoir, if any."""
    res = supabase_admin.table("memoir_generation") \
        .select("*") \
        .eq("memoir_id", memoir_id) \
        .order("started_at", desc=True) \
        .limit(1) \
        .execute()
    return res.data[0] if res and res.data else None


# ---------------------------------------------------------------------------
# Chapter persistence
# ---------------------------------------------------------------------------

def clear_draft_chapters(memoir_id: str):
    """
    Deletes previous draft (unpublished) chapter suggestions for a memoir.
    Chapter membership rows are removed via the on-delete-cascade FK.
    """
    return supabase_admin.table("memoir_chapter") \
        .delete() \
        .eq("memoir_id", memoir_id) \
        .eq("status", "draft") \
        .execute()


def insert_chapters(chapter_records: list):
    """Inserts new chapter suggestion rows (bulk insert)."""
    return supabase_admin.table("memoir_chapter").insert(chapter_records).execute()


def insert_chapter_memories(link_records: list):
    """Links memories to chapters with sort order (bulk insert)."""
    return supabase_admin.table("chapter_memory").insert(link_records).execute()


def fetch_chapters_with_memories(memoir_id: str, status: str | None = None):
    """
    Fetches chapters for a memoir, each embedded with its ordered member
    memories. Optionally filters by chapter status ('draft' or 'published').
    """
    query = supabase_admin.table("memoir_chapter") \
        .select(
            "id, memoir_id, title, subtitle, summary, rationale, status, sort_order, confidence, "
            "chapter_memory(sort_order, memory(id, memoir_id, title, body_text, rewritten_text, occurred_start, occurred_precision, "
            "memory_media(media_asset(id, kind, storage_key, caption, deleted_at))))"
        ) \
        .eq("memoir_id", memoir_id) \
        .is_("deleted_at", "null") \
        .order("sort_order")
    if status:
        query = query.eq("status", status)
    return query.execute()


def fetch_chapter_by_id(chapter_id: str, memoir_id: str):
    """Fetches a single chapter scoped to its memoir to prevent cross-tenant access."""
    res = supabase_admin.table("memoir_chapter") \
        .select("*") \
        .eq("id", chapter_id) \
        .eq("memoir_id", memoir_id) \
        .is_("deleted_at", "null") \
        .maybe_single() \
        .execute()
    return res.data if res else None


def fetch_memories_by_ids(memoir_id: str, memory_ids: list):
    """
    Returns the IDs among memory_ids that genuinely belong to the memoir.
    Used to refuse reorders that reference foreign memories.
    """
    if not memory_ids:
        return []
    res = supabase_admin.table("memory") \
        .select("id") \
        .eq("memoir_id", memoir_id) \
        .is_("deleted_at", "null") \
        .in_("id", memory_ids) \
        .execute()
    return res.data or []


def update_chapter(chapter_id: str, memoir_id: str, updates: dict):
    """Updates chapter fields (e.g. title, subtitle, summary) scoped by memoir."""
    return supabase_admin.table("memoir_chapter") \
        .update(updates) \
        .eq("id", chapter_id) \
        .eq("memoir_id", memoir_id) \
        .execute()


def replace_chapter_memory_order(chapter_id: str, memoir_id: str, memory_ids: list):
    """
    Rebuilds the ordered membership of a chapter: removes existing links and
    re-inserts them with sort_order matching the position in memory_ids.
    """
    supabase_admin.table("chapter_memory") \
        .delete() \
        .eq("chapter_id", chapter_id) \
        .execute()

    link_records = [
        {
            "chapter_id": chapter_id,
            "memoir_id": memoir_id,
            "memory_id": memory_id,
            "sort_order": index,
        }
        for index, memory_id in enumerate(memory_ids)
    ]
    if link_records:
        return supabase_admin.table("chapter_memory").insert(link_records).execute()
    return None


# ---------------------------------------------------------------------------
# Publication
# ---------------------------------------------------------------------------

def mark_chapters_published(memoir_id: str):
    """Flips all draft chapters of a memoir to 'published'."""
    return supabase_admin.table("memoir_chapter") \
        .update({"status": "published"}) \
        .eq("memoir_id", memoir_id) \
        .eq("status", "draft") \
        .is_("deleted_at", "null") \
        .execute()


def update_memoir_status(memoir_id: str, status_value: str):
    """Updates the memoir container's own status, e.g. to 'published'."""
    return supabase_admin.table("memoir") \
        .update({"status": status_value}) \
        .eq("id", memoir_id) \
        .execute()