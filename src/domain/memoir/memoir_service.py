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


def create_memoir(user_id: UUID, request: MemoirCreateRequest) -> MemoirOut:
    client = get_supabase()

    user_acct = (
        client.table("user_account")
        .select("full_name, email")
        .eq("id", str(user_id))
        .maybe_single()
        .execute()
    )

    if not user_acct.data:
        raise PermissionError(
            "User account is not initialized. Please sign in again."
        )

    display_name = str(user_acct.data["full_name"]).strip()
    email = str(user_acct.data["email"]).strip()

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

    if not memoir_res.data:
        raise RuntimeError("Memoir was not created.")

    memoir = memoir_res.data[0]

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

    # 1. Fetch participant rows
    participants = (
        client.table("memoir_participant")
        .select("memoir_id")
        .eq("user_id", str(user_id))
        .is_("removed_at", "null")
        .execute()
    )

    memoir_ids = {
        row["memoir_id"]
        for row in (participants.data or [])
        if row.get("memoir_id")
    }

    # 2. Also fetch memoirs directly created by this user
    created_memoirs = (
        client.table("memoir")
        .select("id")
        .eq("created_by_user_id", str(user_id))
        .execute()
    )

    for row in (created_memoirs.data or []):
        if row.get("id"):
            memoir_ids.add(row["id"])

    if not memoir_ids:
        return []

    # 3. Fetch full memoir details
    memoir_res = (
        client.table("memoir")
        .select("*")
        .in_("id", list(memoir_ids))
        .order("created_at", desc=True)
        .execute()
    )

    return [MemoirOut(**row) for row in (memoir_res.data or [])]


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

    if not participant or not participant.data:
        raise PermissionError("Not authorized to view this memoir.")

    result = (
        client.table("memoir")
        .select("*")
        .eq("id", str(memoir_id))
        .single()
        .execute()
    )

    return MemoirOut(**result.data)


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

    for row in result.data or []:
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

    # Verify that the user has admin/owner rights to this memoir
    participant = (
        client.table("memoir_participant")
        .select("role")
        .eq("memoir_id", str(memoir_id))
        .eq("user_id", str(user_id))
        .is_("removed_at", "null")
        .maybe_single()
        .execute()
    )

    if not participant.data or participant.data["role"] not in ["owner", "co_owner"]:
        raise PermissionError("Only an owner can publish the memoir.")

    now_iso = datetime.now(timezone.utc).isoformat()
    
    update_res = (
        client.table("memoir")
        .update({
            "status": "published",
            "published_at": now_iso
        })
        .eq("id", str(memoir_id))
        .execute()
    )

    if not update_res.data:
        raise LookupError("Memoir not found.")

    return MemoirOut(**update_res.data[0])