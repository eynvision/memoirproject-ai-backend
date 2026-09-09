import logging
from datetime import date
from uuid import UUID
from datetime import datetime, timezone

from src.integrations.supabase_client import get_supabase
from src.models.memoir_models import (
    ContributorOut,
    MemoirCreateRequest,
    MemoirOut,
)

logger = logging.getLogger(__name__)


def _safe_data(response: object):
    """Safely extract the 'data' attribute from a Supabase response object."""
    if response is None:
        return None
    return getattr(response, "data", None)


def create_memoir(user_id: UUID, request: MemoirCreateRequest) -> MemoirOut:
    client = get_supabase()

    user_acct = (
        client.table("user_account")
        .select("full_name, email")
        .eq("id", str(user_id))
        .maybe_single()
        .execute()
    )

    acct_data = _safe_data(user_acct)
    if not acct_data:
        logger.warning(f"User account not found in DB for user_id: {user_id}")
        raise PermissionError(
            "User account is not initialized. Please sign in again."
        )

    display_name = str(acct_data["full_name"]).strip()
    email = str(acct_data["email"]).strip()

    born_on = (
        date(request.birth_year, 1, 1).isoformat()
        if request.birth_year
        else None
    )
    died_on = (
        date(request.end_year, 1, 1).isoformat()
        if request.end_year and not request.is_living
        else None
    )

    memoir_res = (
        client.table("memoir")
        .insert(
            {
                "subject_name": request.subject_name.strip(),
                "subject_born_on": born_on,
                "subject_died_on": died_on,
                "subject_is_living": request.is_living,
                "created_by_user_id": str(user_id),
                "status": "draft",
            }
        )
        .execute()
    )

    memoir_data = _safe_data(memoir_res)
    if not memoir_data or not isinstance(memoir_data, list) or len(memoir_data) == 0:
        raise RuntimeError("Memoir was not created.")

    memoir = memoir_data[0]

    client.table("memoir_participant").insert(
        {
            "memoir_id": memoir["id"],
            "user_id": str(user_id),
            "role": "owner",
            "display_name": display_name,
            "email": email,
            "relationship": request.relationship.value,
        }
    ).execute()

    return MemoirOut(**memoir)


def list_memoirs(user_id: UUID | str) -> list[MemoirOut]:
    client = get_supabase()

    participants = (
        client.table("memoir_participant")
        .select("memoir_id")
        .eq("user_id", str(user_id))
        .is_("removed_at", "null")
        .execute()
    )

    p_data = _safe_data(participants) or []
    memoir_ids = {
        row["memoir_id"]
        for row in p_data
        if row.get("memoir_id")
    }

    created_memoirs = (
        client.table("memoir")
        .select("id")
        .eq("created_by_user_id", str(user_id))
        .execute()
    )

    c_data = _safe_data(created_memoirs) or []
    for row in c_data:
        if row.get("id"):
            memoir_ids.add(row["id"])

    if not memoir_ids:
        return []

    memoir_res = (
        client.table("memoir")
        .select("*")
        .in_("id", list(memoir_ids))
        .order("created_at", desc=True)
        .execute()
    )

    m_data = _safe_data(memoir_res) or []
    return [MemoirOut(**row) for row in m_data]


def get_memoir(memoir_id: UUID, user_id: UUID) -> MemoirOut:
    client = get_supabase()

    participant = (
        client.table("memoir_participant")
        .select("id")
        .eq("memoir_id", str(memoir_id))
        .eq("user_id", str(user_id))
        .is_("removed_at", "null")
        .maybe_single()
        .execute()
    )

    if not participant or not _safe_data(participant):
        raise PermissionError("Not authorized to view this memoir.")

    result = (
        client.table("memoir")
        .select("*")
        .eq("id", str(memoir_id))
        .single()
        .execute()
    )

    res_data = _safe_data(result)
    if not res_data:
        raise PermissionError("Memoir not found.")

    return MemoirOut(**res_data)


def list_contributors(
    memoir_id: UUID,
    user_id: UUID,
) -> list[ContributorOut]:
    get_memoir(memoir_id, user_id)

    client = get_supabase()
    result = (
        client.table("memoir_participant")
        .select(
            "id, email, display_name, role, invited_at, first_opened_at"
        )
        .eq("memoir_id", str(memoir_id))
        .is_("removed_at", "null")
        .order("created_at")
        .execute()
    )

    contributors: list[ContributorOut] = []
    r_data = _safe_data(result) or []

    for row in r_data:
        role = row["role"]
        is_admin = role in {"owner", "co_owner"}

        accepted = (
            is_admin
            or row.get("first_opened_at") is not None
            or row.get("invited_at") is None
        )

        contributors.append(
            ContributorOut(
                id=row["id"],
                email=row.get("email"),
                display_name=row["display_name"],
                role="Admin" if is_admin else "Contributor",
                status="Accepted" if accepted else "Pending",
            )
        )

    return contributors


def publish_memoir(memoir_id: UUID, user_id: UUID) -> MemoirOut:
    client = get_supabase()

    participant = (
        client.table("memoir_participant")
        .select("id, role")
        .eq("memoir_id", str(memoir_id))
        .eq("user_id", str(user_id))
        .is_("removed_at", "null")
        .maybe_single()
        .execute()
    )

    p_data = _safe_data(participant)
    if not p_data or p_data.get("role") not in ["owner", "co_owner"]:
        raise PermissionError("Only an owner can publish the memoir.")

    now_iso = datetime.now(timezone.utc).isoformat()

    update_res = (
        client.table("memoir")
        .update({
            "status": "published",
            "published_at": now_iso,
            "visibility": "link_public",
            "comment_policy": "anyone_who_can_view",
        })
        .eq("id", str(memoir_id))
        .execute()
    )

    u_data = _safe_data(update_res)
    if not u_data or not isinstance(u_data, list) or len(u_data) == 0:
        raise LookupError("Memoir not found.")

    existing_link = (
        client.table("memoir_link")
        .select("id")
        .eq("memoir_id", str(memoir_id))
        .eq("scope", "view")
        .is_("revoked_at", "null")
        .maybe_single()
        .execute()
    )
    
    if not _safe_data(existing_link):
        client.table("memoir_link").insert({
            "memoir_id": str(memoir_id),
            "scope": "view",
            "created_by_participant_id": p_data["id"],
        }).execute()

    return MemoirOut(**u_data[0])