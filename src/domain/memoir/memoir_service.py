import logging
from datetime import date
from uuid import UUID

from src.integrations.supabase_client import get_supabase
from src.models.memoir_models import (
    ContributorOut,
    MemoirCreateRequest,
    MemoirOut,
)

logger = logging.getLogger(__name__)


def create_memoir(user_id: UUID, request: MemoirCreateRequest) -> MemoirOut:
    client = get_supabase()

    # The account is synchronized by the authentication flow before this
    # endpoint is called. Do not create placeholder accounts because email is
    # unique in user_account and placeholder identities break multi-user use.
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
    # Ensures the caller is an active participant before exposing the list.
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

        # Owners and co-owners are already accepted. An invited contributor is
        # pending until they open the link; a self-arriving participant is
        # treated as accepted because no invitation is waiting on them.
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
