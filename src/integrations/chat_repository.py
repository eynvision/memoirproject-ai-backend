"""
@file chat_repository.py
@description Data access layer for the memoir chat agent: persisted chat
messages (one row per LangChain message) and the changes the agent proposes,
which stay 'pending' until the user confirms or rejects them. Every query is
scoped by memoir_id (and user_id for a user's own conversation).
"""

from datetime import datetime, timezone

from src.integrations.supabase_client import supabase_admin


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def insert_messages(rows: list):
    """Persists new chat messages in order (bulk insert)."""
    return supabase_admin.table("memoir_chat_message").insert(rows).execute()


def fetch_recent_messages(memoir_id: str, user_id: str, limit: int) -> list:
    """The user's most recent `limit` messages for this memoir, oldest first."""
    res = supabase_admin.table("memoir_chat_message") \
        .select("id, role, message, created_at, seq") \
        .eq("memoir_id", memoir_id) \
        .eq("user_id", user_id) \
        .order("seq", desc=True) \
        .limit(limit) \
        .execute()
    return list(reversed(res.data or []))


# ---------------------------------------------------------------------------
# Proposed actions
# ---------------------------------------------------------------------------

def insert_action(record: dict) -> dict:
    """Creates a pending action and returns the stored row."""
    res = supabase_admin.table("memoir_chat_action").insert(record).execute()
    return res.data[0]


def fetch_action(action_id: str, memoir_id: str):
    """Fetches one action scoped to its memoir."""
    res = supabase_admin.table("memoir_chat_action") \
        .select("*") \
        .eq("id", action_id) \
        .eq("memoir_id", memoir_id) \
        .maybe_single() \
        .execute()
    return res.data if res else None


def fetch_actions(memoir_id: str, user_id: str, status_value: str | None = None, limit: int = 20) -> list:
    """The user's actions for this memoir, newest first, optionally by status."""
    query = supabase_admin.table("memoir_chat_action") \
        .select("*") \
        .eq("memoir_id", memoir_id) \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .limit(limit)
    if status_value:
        query = query.eq("status", status_value)
    return query.execute().data or []


def transition_action(action_id: str, memoir_id: str, user_id: str, from_status: str, to_status: str):
    """
    Atomically moves an action from one status to another. Returns the updated
    row, or None if the action was not in `from_status` (already handled).
    """
    updates = {"status": to_status}
    if to_status in ("rejected", "applied", "failed"):
        updates["resolved_at"] = _now()
    res = supabase_admin.table("memoir_chat_action") \
        .update(updates) \
        .eq("id", action_id) \
        .eq("memoir_id", memoir_id) \
        .eq("user_id", user_id) \
        .eq("status", from_status) \
        .execute()
    return res.data[0] if res.data else None


def resolve_action(action_id: str, status_value: str, error: str | None = None):
    """Records the final outcome ('applied' or 'failed') of a claimed action."""
    return supabase_admin.table("memoir_chat_action") \
        .update({"status": status_value, "error": error, "resolved_at": _now()}) \
        .eq("id", action_id) \
        .execute()
