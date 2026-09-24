"""
@file narrative_repository.py
@description Data access layer for the AI narrative layer: claiming and
finishing the personality/rewrite job on a memoir, storing the personality
profile, and storing each memory's rewritten text. The original memory
text (body_text) is never written here.
"""

from datetime import datetime, timezone

from src.integrations.supabase_client import supabase_admin


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def claim_narrative_job(memoir_id: str, stale_before_iso: str) -> bool:
    """
    Atomically marks the memoir's narrative job as running. Succeeds when no
    job is running, or when the running job started before `stale_before_iso`
    (i.e. it died). Returns False if another live job already holds it.
    """
    now = _now()
    claim = {
        "narrative_status": "running",
        "narrative_error": None,
        "narrative_started_at": now,
        "narrative_updated_at": now,
    }
    res = supabase_admin.table("memoir") \
        .update(claim) \
        .eq("id", memoir_id) \
        .neq("narrative_status", "running") \
        .execute()
    if res.data:
        return True

    res = supabase_admin.table("memoir") \
        .update(claim) \
        .eq("id", memoir_id) \
        .eq("narrative_status", "running") \
        .lt("narrative_started_at", stale_before_iso) \
        .execute()
    return bool(res.data)


def finish_narrative_job(memoir_id: str, status_value: str, error: str | None = None):
    """Records the final state ('completed' or 'failed') of a narrative job."""
    return supabase_admin.table("memoir") \
        .update({
            "narrative_status": status_value,
            "narrative_error": error,
            "narrative_updated_at": _now(),
        }) \
        .eq("id", memoir_id) \
        .execute()


def save_personality_profile(memoir_id: str, profile: dict):
    """Stores the memoir's personality profile."""
    return supabase_admin.table("memoir") \
        .update({"personality_profile": profile}) \
        .eq("id", memoir_id) \
        .execute()


def save_rewritten_text(memory_id: str, memoir_id: str, text: str):
    """Stores the AI rewrite beside the original, scoped by memoir_id."""
    return supabase_admin.table("memory") \
        .update({"rewritten_text": text, "rewritten_at": _now()}) \
        .eq("id", memory_id) \
        .eq("memoir_id", memoir_id) \
        .is_("deleted_at", "null") \
        .execute()
