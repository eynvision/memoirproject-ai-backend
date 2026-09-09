import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from src.core.auth import get_current_user_id
from src.domain.memoir import memoir_service
from src.integrations.supabase_client import get_supabase
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/memoirs/{memoir_id}/export", tags=["export"])


def _safe_data(response: object):
    if response is None:
        return None
    return getattr(response, "data", None)


@router.post("/pdf", status_code=status.HTTP_202_ACCEPTED)
async def request_pdf_export(
    memoir_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    """Request PDF generation for a published memoir."""
    try:
        memoir = memoir_service.get_memoir(memoir_id, user_id)
        if memoir.status != "published":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Only published memoirs can be exported to PDF.",
            )
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error))
    except Exception as error:
        logger.error("Failed to request PDF export: %s", error)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Could not initiate PDF export.",
        )

    client = get_supabase()
    
    participant_res = (
        client.table("memoir_participant")
        .select("id")
        .eq("memoir_id", str(memoir_id))
        .eq("user_id", str(user_id))
        .is_("removed_at", "null")
        .maybe_single()
        .execute()
    )
    participant = _safe_data(participant_res)
    if not participant:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized.")

    now_iso = datetime.now(timezone.utc).isoformat()
    export_res = (
        client.table("memoir_export")
        .insert({
            "memoir_id": str(memoir_id),
            "kind": "pdf",
            "status": "queued",
            "requested_by_participant_id": participant["id"],
            "created_at": now_iso,
        })
        .execute()
    )

    export_data = _safe_data(export_res)
    if not export_data or not isinstance(export_data, list) or len(export_data) == 0:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Could not create export record.",
        )

    return {"export_id": export_data[0]["id"], "status": "queued"}


@router.get("/pdf/{export_id}")
async def get_pdf_export_status(
    memoir_id: UUID,
    export_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    """Check PDF export status and get download URL when ready."""
    try:
        memoir_service.get_memoir(memoir_id, user_id)
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error))

    client = get_supabase()
    export_res = (
        client.table("memoir_export")
        .select("*")
        .eq("id", str(export_id))
        .eq("memoir_id", str(memoir_id))
        .maybe_single()
        .execute()
    )
    export = _safe_data(export_res)
    if not export:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Export not found.")

    response = {
        "id": export["id"],
        "status": export["status"],
        "created_at": export["created_at"],
        "completed_at": export.get("completed_at"),
        "error_message": export.get("error_message"),
    }

    if export["status"] == "ready" and export.get("storage_key"):
        from src.integrations.supabase_client import create_read_url
        response["download_url"] = create_read_url(export["storage_key"])

    return response