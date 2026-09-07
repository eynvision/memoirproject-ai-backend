# import logging
# from typing import Optional, List
# from uuid import UUID
# from datetime import datetime, timezone
# from fastapi import BackgroundTasks
# from src.domain.memory.transcription_service import process_audio_transcription

# from src.integrations.supabase_client import (
#     get_supabase, build_storage_key, create_upload_url,
#     create_read_url, delete_object,
# )
# from src.models.memory_models import (
#     MemoryOut, MemoryCreateRequest, MemoryPatchRequest,
#     PresignRequest, PresignResponse, MediaConfirmRequest,
#     MediaAssetOut, MemoryStatus, MediaKind, MediaLinkType, TranscodeStatus
# )
# from src.domain.memory.constants import (
#     ALLOWED_AUDIO_MIME, ALLOWED_PHOTO_MIME,
#     MAX_AUDIO_SIZE_BYTES, MAX_PHOTO_SIZE_BYTES,
#     MAX_PHOTOS_PER_MEMORY,
# )

# logger = logging.getLogger(__name__)


# def _get_owner_participant(memoir_id: UUID, user_id: UUID) -> dict:
#     client = get_supabase()
#     result = (
#         client.table("memoir_participant")
#         .select("id, memoir_id, role, user_id")
#         .eq("memoir_id", str(memoir_id))
#         .eq("user_id", str(user_id))
#         .eq("role", "owner")
#         .is_("removed_at", "null")
#         .maybe_single()
#         .execute()
#     )
#     if not result.data:
#         raise PermissionError("User is not an active owner of this memoir.")
#     return result.data


# def _load_editable_memory(memory_id: UUID, memoir_id: UUID) -> dict:
#     client = get_supabase()
#     memoir = (
#         client.table("memoir")
#         .select("status")
#         .eq("id", str(memoir_id))
#         .single()
#         .execute()
#     )
#     if memoir.data and memoir.data.get("status") == "published":
#         raise PermissionError("Published memoirs and their memories are immutable.")

#     result = (
#         client.table("memory")
#         .select("*")
#         .eq("id", str(memory_id))
#         .eq("memoir_id", str(memoir_id))
#         .is_("deleted_at", "null")
#         .maybe_single()
#         .execute()
#     )
#     if not result.data:
#         raise LookupError("Memory not found or has been removed.")
#     return result.data


# def list_memories(memoir_id: UUID, user_id: UUID, include_drafts: bool = True) -> tuple[List[MemoryOut], int]:
#     _get_owner_participant(memoir_id, user_id)
#     client = get_supabase()
    
#     statuses = ["submitted", "draft"] if include_drafts else ["submitted"]
    
#     result = (
#         client.table("memory")
#         .select("*")
#         .eq("memoir_id", str(memoir_id))
#         .in_("status", statuses)
#         .is_("deleted_at", "null")
#         .order("updated_at", desc=True)
#         .execute()
#     )
    
#     if not result.data:
#         return [], 0
    
#     memory_ids = [m["id"] for m in result.data]
    
#     all_media = (
#         client.table("memory_media")
#         .select("memory_id, position, link_type, media_asset(*)")
#         .in_("memory_id", memory_ids)
#         .is_("media_asset.deleted_at", "null")
#         .order("memory_id, position")
#         .execute()
#     )
    
#     media_by_memory: dict[str, list] = {}
#     for m in all_media.data:
#         memory_id = m["memory_id"]
#         if memory_id not in media_by_memory:
#             media_by_memory[memory_id] = []
        
#         asset = m.get("media_asset")
#         if asset:
#             media_by_memory[memory_id].append(MediaAssetOut(
#                 id=asset["id"],
#                 memoir_id=asset["memoir_id"],
#                 kind=asset["kind"],
#                 storage_key=asset["storage_key"],
#                 mime_type=asset["mime_type"],
#                 byte_size=asset["byte_size"],
#                 duration_ms=asset.get("duration_ms"),
#                 width_px=asset.get("width_px"),
#                 height_px=asset.get("height_px"),
#                 caption=asset.get("caption"),
#                 playback_url=create_read_url(asset["storage_key"]),
#                 position=m["position"],
#                 link_type=m["link_type"],
#                 transcription_status=asset["transcription_status"],
#                 created_at=asset["created_at"],
#             ))
    
#     memories = []
#     for row in result.data:
#         memories.append(MemoryOut(
#             id=row["id"],
#             memoir_id=row["memoir_id"],
#             author_participant_id=row["author_participant_id"],
#             prompt_id=row.get("prompt_id"),
#             title=row.get("title"),
#             body_text=row.get("body_text"),
#             status=row["status"],
#             media=media_by_memory.get(row["id"], []),
#             created_at=row["created_at"],
#             updated_at=row["updated_at"],
#             submitted_at=row.get("submitted_at"),
#         ))
    
#     return memories, len(memories)


# def get_memory(memory_id: UUID, memoir_id: UUID, user_id: UUID) -> MemoryOut:
#     _get_owner_participant(memoir_id, user_id)
#     row = _load_editable_memory(memory_id, memoir_id)
#     return _hydrate_memory(row)


# def create_draft(memoir_id: UUID, user_id: UUID, request: MemoryCreateRequest) -> MemoryOut:
#     participant = _get_owner_participant(memoir_id, user_id)
#     client = get_supabase()
#     insert_payload = {
#         "memoir_id": str(memoir_id),
#         "author_participant_id": participant["id"],
#         "title": request.title,
#         "body_text": request.body_text,
#         "prompt_id": str(request.prompt_id) if request.prompt_id else None,
#         "status": MemoryStatus.draft.value,
#     }
#     result = client.table("memory").insert(insert_payload).execute()
#     logger.info("Created draft memory %s", result.data[0]["id"])
#     return _hydrate_memory(result.data[0])


# def patch_memory(memory_id: UUID, memoir_id: UUID, user_id: UUID, patch: MemoryPatchRequest) -> MemoryOut:
#     _get_owner_participant(memoir_id, user_id)
#     _load_editable_memory(memory_id, memoir_id)
#     updates = {k: v for k, v in patch.model_dump(exclude_unset=True).items()}
#     if not updates:
#         return get_memory(memory_id, memoir_id, user_id)
#     client = get_supabase()
#     result = client.table("memory").update(updates).eq("id", str(memory_id)).eq("memoir_id", str(memoir_id)).execute()
#     return _hydrate_memory(result.data[0])


# def submit_memory(
#     memory_id: UUID,
#     memoir_id: UUID,
#     user_id: UUID,
#     background_tasks: Optional[BackgroundTasks] = None,
# ) -> MemoryOut:
#     _get_owner_participant(memoir_id, user_id)
#     _load_editable_memory(memory_id, memoir_id)

#     client = get_supabase()
#     result = (
#         client.table("memory")
#         .update(
#             {
#                 "status": MemoryStatus.submitted.value,
#                 "submitted_at": datetime.now(timezone.utc).isoformat(),
#             }
#         )
#         .eq("id", str(memory_id))
#         .eq("memoir_id", str(memoir_id))
#         .execute()
#     )

#     # Trigger background transcription for audio assets linked to this memory
#     if background_tasks is not None:
#         media_links = (
#             client.table("memory_media")
#             .select("media_asset(id, storage_key, transcription_status, kind)")
#             .eq("memory_id", str(memory_id))
#             .execute()
#         )

#         for link in media_links.data or []:
#             asset = link.get("media_asset")
#             if asset and asset.get("kind") == "audio":
#                 status = asset.get("transcription_status")
#                 if status in ("pending", "skipped", "processing"):
#                     background_tasks.add_task(
#                         process_audio_transcription,
#                         memoir_id,
#                         UUID(asset["id"]),
#                         asset["storage_key"],
#                     )

#     return _hydrate_memory(result.data[0])

# def delete_memory(memory_id: UUID, memoir_id: UUID, user_id: UUID) -> None:
#     participant = _get_owner_participant(memoir_id, user_id)
#     _load_editable_memory(memory_id, memoir_id)
#     client = get_supabase()
#     now_iso = datetime.now(timezone.utc).isoformat()
#     client.table("memory").update({
#         "deleted_at": now_iso,
#         "deleted_by_participant_id": participant["id"],
#     }).eq("id", str(memory_id)).eq("memoir_id", str(memoir_id)).execute()


# def presign_upload(memoir_id: UUID, memory_id: UUID, user_id: UUID, request: PresignRequest) -> PresignResponse:
#     _get_owner_participant(memoir_id, user_id)
#     _load_editable_memory(memory_id, memoir_id)
#     _validate_media_request(memoir_id, memory_id, request)
#     storage_key = build_storage_key(str(memoir_id), request.kind.value, request.mime_type)
#     upload_url, expires_at = create_upload_url(storage_key)
#     return PresignResponse(upload_url=upload_url, storage_key=storage_key, expires_at=expires_at)


# def confirm_media(memoir_id: UUID, memory_id: UUID, user_id: UUID, request: MediaConfirmRequest) -> MediaAssetOut:
#     participant = _get_owner_participant(memoir_id, user_id)
#     _load_editable_memory(memory_id, memoir_id)
    
#     transcription_status = (
#         TranscodeStatus.skipped.value
#         if request.kind == MediaKind.photo
#         else TranscodeStatus.pending.value
#     )
    
#     # Strictly enforce DB constraint: (kind = 'photo') = (duration_ms IS NULL)
#     if request.kind == MediaKind.audio:
#         duration_ms = int(request.duration_ms) if request.duration_ms is not None and request.duration_ms > 0 else 1000
#     else:
#         duration_ms = None

#     clean_mime = request.mime_type.split(";")[0].strip().lower()

#     client = get_supabase()
#     asset_result = client.table("media_asset").insert({
#         "memoir_id": str(memoir_id),
#         "kind": request.kind.value,
#         "storage_key": request.storage_key,
#         "mime_type": clean_mime,
#         "byte_size": request.byte_size,
#         "checksum_sha256": request.checksum_sha256,
#         "original_filename": request.original_filename,
#         "duration_ms": duration_ms,
#         "width_px": request.width_px,
#         "height_px": request.height_px,
#         "caption": request.caption,
#         "transcription_status": transcription_status,
#         "uploaded_by_participant_id": participant["id"],
#     }).execute()
#     asset = asset_result.data[0]
    
#     position_result = client.table("memory_media").select("position").eq("memory_id", str(memory_id)).order("position", desc=True).limit(1).execute()
#     next_position = (position_result.data[0]["position"] + 1) if position_result.data else 0
    
#     client.table("memory_media").insert({
#         "memory_id": str(memory_id),
#         "media_asset_id": asset["id"],
#         "memoir_id": str(memoir_id),
#         "link_type": MediaLinkType.primary.value,
#         "position": next_position,
#         "created_by": "contributor",
#     }).execute()

#     return MediaAssetOut(
#         id=asset["id"],
#         memoir_id=asset["memoir_id"],
#         kind=asset["kind"],
#         storage_key=asset["storage_key"],
#         mime_type=asset["mime_type"],
#         byte_size=asset["byte_size"],
#         duration_ms=asset.get("duration_ms"),
#         width_px=asset.get("width_px"),
#         height_px=asset.get("height_px"),
#         caption=asset.get("caption"),
#         playback_url=create_read_url(asset["storage_key"]),
#         position=next_position,
#         link_type=MediaLinkType.primary,
#         transcription_status=asset["transcription_status"],
#         created_at=asset["created_at"],
#     )


# def remove_media(memoir_id: UUID, memory_id: UUID, media_asset_id: UUID, user_id: UUID) -> None:
#     _get_owner_participant(memoir_id, user_id)
#     _load_editable_memory(memory_id, memoir_id)
#     client = get_supabase()
#     client.table("memory_media").delete().eq("memory_id", str(memory_id)).eq("media_asset_id", str(media_asset_id)).execute()
#     now_iso = datetime.now(timezone.utc).isoformat()
#     client.table("media_asset").update({"deleted_at": now_iso}).eq("id", str(media_asset_id)).eq("memoir_id", str(memoir_id)).execute()


# def _validate_media_request(memoir_id: UUID, memory_id: UUID, request: PresignRequest) -> None:
#     base_mime = request.mime_type.split(";")[0].strip().lower()
#     if request.kind == MediaKind.audio:
#         if base_mime not in ALLOWED_AUDIO_MIME:
#             raise ValueError(f"Unsupported audio type: {request.mime_type}")
#         if request.byte_size > MAX_AUDIO_SIZE_BYTES:
#             raise ValueError("Audio file exceeds 50 MB limit.")
#     elif request.kind == MediaKind.photo:
#         if base_mime not in ALLOWED_PHOTO_MIME:
#             raise ValueError(f"Unsupported photo type: {request.mime_type}")
#         if request.byte_size > MAX_PHOTO_SIZE_BYTES:
#             raise ValueError("Photo file exceeds 10 MB limit.")
#         client = get_supabase()
#         count = client.table("memory_media").select("media_asset!inner(kind)", count="exact").eq("memory_id", str(memory_id)).eq("media_asset.kind", "photo").is_("media_asset.deleted_at", "null").execute()
#         if (count.count or 0) >= MAX_PHOTOS_PER_MEMORY:
#             raise ValueError(f"Maximum {MAX_PHOTOS_PER_MEMORY} photos per memory.")


# def _hydrate_memory(row: dict) -> MemoryOut:
#     client = get_supabase()
#     media_rows = (
#         client.table("memory_media")
#         .select("position, link_type, media_asset(*)")
#         .eq("memory_id", row["id"])
#         .is_("media_asset.deleted_at", "null")
#         .order("position")
#         .execute()
#     )
    
#     media = []
#     for m in media_rows.data:
#         asset = m.get("media_asset")
#         if not asset:
#             continue
#         media.append(MediaAssetOut(
#             id=asset["id"],
#             memoir_id=asset["memoir_id"],
#             kind=asset["kind"],
#             storage_key=asset["storage_key"],
#             mime_type=asset["mime_type"],
#             byte_size=asset["byte_size"],
#             duration_ms=asset.get("duration_ms"),
#             width_px=asset.get("width_px"),
#             height_px=asset.get("height_px"),
#             caption=asset.get("caption"),
#             playback_url=create_read_url(asset["storage_key"]),
#             position=m["position"],
#             link_type=m["link_type"],
#             transcription_status=asset["transcription_status"],
#             created_at=asset["created_at"],
#         ))
#     return MemoryOut(
#         id=row["id"],
#         memoir_id=row["memoir_id"],
#         author_participant_id=row["author_participant_id"],
#         prompt_id=row.get("prompt_id"),
#         title=row.get("title"),
#         body_text=row.get("body_text"),
#         status=row["status"],
#         media=media,
#         created_at=row["created_at"],
#         updated_at=row["updated_at"],
#         submitted_at=row.get("submitted_at"),
#     )

import logging
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone
from fastapi import BackgroundTasks
from src.domain.memory.transcription_service import process_audio_transcription

from src.integrations.supabase_client import (
    get_supabase, build_storage_key, create_upload_url,
    create_read_url, create_read_urls,
)
from src.models.memory_models import (
    MemoryOut, MemoryCreateRequest, MemoryPatchRequest,
    PresignRequest, PresignResponse, MediaConfirmRequest,
    MediaAssetOut, MemoryStatus, MediaKind, MediaLinkType, TranscodeStatus
)
from src.domain.memory.constants import (
    ALLOWED_AUDIO_MIME, ALLOWED_PHOTO_MIME,
    MAX_AUDIO_SIZE_BYTES, MAX_PHOTO_SIZE_BYTES,
    MAX_PHOTOS_PER_MEMORY,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_owner_participant(memoir_id: UUID, user_id: UUID) -> dict:
    client = get_supabase()
    result = (
        client.table("memoir_participant")
        .select("id, memoir_id, role, user_id")
        .eq("memoir_id", str(memoir_id))
        .eq("user_id", str(user_id))
        .eq("role", "owner")
        .is_("removed_at", "null")
        .maybe_single()
        .execute()
    )
    if not result or not result.data:
        raise PermissionError("User is not an active owner of this memoir.")
    return result.data


def _load_editable_memory(memory_id: UUID, memoir_id: UUID) -> dict:
    client = get_supabase()
    memoir = (
        client.table("memoir")
        .select("status")
        .eq("id", str(memoir_id))
        .single()
        .execute()
    )
    if memoir.data and memoir.data.get("status") == "published":
        raise PermissionError("Published memoirs and their memories are immutable.")

    result = (
        client.table("memory")
        .select("*")
        .eq("id", str(memory_id))
        .eq("memoir_id", str(memoir_id))
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    if not result or not result.data:
        raise LookupError("Memory not found or has been removed.")
    return result.data


def _asset_out(asset: dict, position: int, link_type: str, playback_url: str) -> MediaAssetOut:
    return MediaAssetOut(
        id=asset["id"],
        memoir_id=asset["memoir_id"],
        kind=asset["kind"],
        storage_key=asset["storage_key"],
        mime_type=asset["mime_type"],
        byte_size=asset["byte_size"],
        duration_ms=asset.get("duration_ms"),
        width_px=asset.get("width_px"),
        height_px=asset.get("height_px"),
        caption=asset.get("caption"),
        playback_url=playback_url,
        position=position,
        link_type=link_type,
        transcription_status=asset["transcription_status"],
        created_at=asset["created_at"],
    )


def _media_by_memory(memory_ids: List[str]) -> dict[str, List[MediaAssetOut]]:
    """Load all media links for many memories and sign every URL in one call."""
    if not memory_ids:
        return {}

    client = get_supabase()
    links = (
        client.table("memory_media")
        .select("memory_id, position, link_type, media_asset(*)")
        .in_("memory_id", memory_ids)
        .is_("media_asset.deleted_at", "null")
        .order("position")
        .execute()
    )

    rows = [
        row for row in (links.data or [])
        if row.get("media_asset")
    ]

    url_map = create_read_urls([row["media_asset"]["storage_key"] for row in rows])

    grouped: dict[str, List[MediaAssetOut]] = {}
    for row in rows:
        asset = row["media_asset"]
        url = url_map.get(asset["storage_key"])
        if not url:
            continue
        grouped.setdefault(row["memory_id"], []).append(
            _asset_out(asset, row["position"], row["link_type"], url)
        )

    return grouped


def _memory_out(row: dict, media: List[MediaAssetOut]) -> MemoryOut:
    return MemoryOut(
        id=row["id"],
        memoir_id=row["memoir_id"],
        author_participant_id=row["author_participant_id"],
        prompt_id=row.get("prompt_id"),
        title=row.get("title"),
        body_text=row.get("body_text"),
        status=row["status"],
        media=media,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        submitted_at=row.get("submitted_at"),
    )


def _hydrate_memory(row: dict) -> MemoryOut:
    media = _media_by_memory([row["id"]]).get(row["id"], [])
    return _memory_out(row, media)


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

def list_memories(memoir_id: UUID, user_id: UUID, include_drafts: bool = True) -> tuple[List[MemoryOut], int]:
    _get_owner_participant(memoir_id, user_id)
    client = get_supabase()

    statuses = ["submitted", "draft"] if include_drafts else ["submitted"]

    result = (
        client.table("memory")
        .select("*")
        .eq("memoir_id", str(memoir_id))
        .in_("status", statuses)
        .is_("deleted_at", "null")
        .order("updated_at", desc=True)
        .execute()
    )

    rows = result.data or []
    if not rows:
        return [], 0

    media_map = _media_by_memory([row["id"] for row in rows])
    memories = [_memory_out(row, media_map.get(row["id"], [])) for row in rows]
    return memories, len(memories)


def get_memory(memory_id: UUID, memoir_id: UUID, user_id: UUID) -> MemoryOut:
    _get_owner_participant(memoir_id, user_id)
    row = _load_editable_memory(memory_id, memoir_id)
    return _hydrate_memory(row)


def create_draft(memoir_id: UUID, user_id: UUID, request: MemoryCreateRequest) -> MemoryOut:
    participant = _get_owner_participant(memoir_id, user_id)
    client = get_supabase()
    insert_payload = {
        "memoir_id": str(memoir_id),
        "author_participant_id": participant["id"],
        "title": request.title,
        "body_text": request.body_text,
        "prompt_id": str(request.prompt_id) if request.prompt_id else None,
        "status": MemoryStatus.draft.value,
    }
    result = client.table("memory").insert(insert_payload).execute()
    logger.info("Created draft memory %s", result.data[0]["id"])
    # A brand-new draft has no media: skip the media query entirely.
    return _memory_out(result.data[0], [])


def patch_memory(memory_id: UUID, memoir_id: UUID, user_id: UUID, patch: MemoryPatchRequest) -> MemoryOut:
    _get_owner_participant(memoir_id, user_id)
    _load_editable_memory(memory_id, memoir_id)
    updates = {k: v for k, v in patch.model_dump(exclude_unset=True).items()}
    if not updates:
        return get_memory(memory_id, memoir_id, user_id)
    client = get_supabase()
    result = (
        client.table("memory")
        .update(updates)
        .eq("id", str(memory_id))
        .eq("memoir_id", str(memoir_id))
        .execute()
    )
    return _hydrate_memory(result.data[0])


def submit_memory(
    memory_id: UUID,
    memoir_id: UUID,
    user_id: UUID,
    background_tasks: Optional[BackgroundTasks] = None,
) -> MemoryOut:
    _get_owner_participant(memoir_id, user_id)
    _load_editable_memory(memory_id, memoir_id)

    client = get_supabase()
    result = (
        client.table("memory")
        .update(
            {
                "status": MemoryStatus.submitted.value,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("id", str(memory_id))
        .eq("memoir_id", str(memoir_id))
        .execute()
    )

    if background_tasks is not None:
        media_links = (
            client.table("memory_media")
            .select("media_asset(id, storage_key, transcription_status, kind)")
            .eq("memory_id", str(memory_id))
            .execute()
        )

        for link in media_links.data or []:
            asset = link.get("media_asset")
            if asset and asset.get("kind") == "audio":
                status = asset.get("transcription_status")
                if status in ("pending", "skipped", "processing"):
                    background_tasks.add_task(
                        process_audio_transcription,
                        memoir_id,
                        UUID(asset["id"]),
                        asset["storage_key"],
                    )

    return _hydrate_memory(result.data[0])


def delete_memory(memory_id: UUID, memoir_id: UUID, user_id: UUID) -> None:
    participant = _get_owner_participant(memoir_id, user_id)
    _load_editable_memory(memory_id, memoir_id)
    client = get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()
    client.table("memory").update({
        "deleted_at": now_iso,
        "deleted_by_participant_id": participant["id"],
    }).eq("id", str(memory_id)).eq("memoir_id", str(memoir_id)).execute()


def presign_upload(memoir_id: UUID, memory_id: UUID, user_id: UUID, request: PresignRequest) -> PresignResponse:
    _get_owner_participant(memoir_id, user_id)
    _load_editable_memory(memory_id, memoir_id)
    _validate_media_request(memoir_id, memory_id, request)
    storage_key = build_storage_key(str(memoir_id), request.kind.value, request.mime_type)
    upload_url, expires_at = create_upload_url(storage_key)
    return PresignResponse(upload_url=upload_url, storage_key=storage_key, expires_at=expires_at)


def confirm_media(memoir_id: UUID, memory_id: UUID, user_id: UUID, request: MediaConfirmRequest) -> MediaAssetOut:
    participant = _get_owner_participant(memoir_id, user_id)
    _load_editable_memory(memory_id, memoir_id)

    transcription_status = (
        TranscodeStatus.skipped.value
        if request.kind == MediaKind.photo
        else TranscodeStatus.pending.value
    )

    if request.kind == MediaKind.audio:
        duration_ms = int(request.duration_ms) if request.duration_ms is not None and request.duration_ms > 0 else 1000
    else:
        duration_ms = None

    clean_mime = request.mime_type.split(";")[0].strip().lower()

    client = get_supabase()
    asset_result = client.table("media_asset").insert({
        "memoir_id": str(memoir_id),
        "kind": request.kind.value,
        "storage_key": request.storage_key,
        "mime_type": clean_mime,
        "byte_size": request.byte_size,
        "checksum_sha256": request.checksum_sha256,
        "original_filename": request.original_filename,
        "duration_ms": duration_ms,
        "width_px": request.width_px,
        "height_px": request.height_px,
        "caption": request.caption,
        "transcription_status": transcription_status,
        "uploaded_by_participant_id": participant["id"],
    }).execute()
    asset = asset_result.data[0]

    position_result = (
        client.table("memory_media")
        .select("position")
        .eq("memory_id", str(memory_id))
        .order("position", desc=True)
        .limit(1)
        .execute()
    )
    next_position = (position_result.data[0]["position"] + 1) if position_result.data else 0

    client.table("memory_media").insert({
        "memory_id": str(memory_id),
        "media_asset_id": asset["id"],
        "memoir_id": str(memoir_id),
        "link_type": MediaLinkType.primary.value,
        "position": next_position,
        "created_by": "contributor",
    }).execute()

    return _asset_out(
        asset,
        next_position,
        MediaLinkType.primary.value,
        create_read_url(asset["storage_key"]),
    )


def remove_media(memoir_id: UUID, memory_id: UUID, media_asset_id: UUID, user_id: UUID) -> None:
    _get_owner_participant(memoir_id, user_id)
    _load_editable_memory(memory_id, memoir_id)
    client = get_supabase()
    client.table("memory_media").delete().eq("memory_id", str(memory_id)).eq("media_asset_id", str(media_asset_id)).execute()
    now_iso = datetime.now(timezone.utc).isoformat()
    client.table("media_asset").update({"deleted_at": now_iso}).eq("id", str(media_asset_id)).eq("memoir_id", str(memoir_id)).execute()


def _validate_media_request(memoir_id: UUID, memory_id: UUID, request: PresignRequest) -> None:
    base_mime = request.mime_type.split(";")[0].strip().lower()
    if request.kind == MediaKind.audio:
        if base_mime not in ALLOWED_AUDIO_MIME:
            raise ValueError(f"Unsupported audio type: {request.mime_type}")
        if request.byte_size > MAX_AUDIO_SIZE_BYTES:
            raise ValueError("Audio file exceeds 50 MB limit.")
    elif request.kind == MediaKind.photo:
        if base_mime not in ALLOWED_PHOTO_MIME:
            raise ValueError(f"Unsupported photo type: {request.mime_type}")
        if request.byte_size > MAX_PHOTO_SIZE_BYTES:
            raise ValueError("Photo file exceeds 10 MB limit.")
        client = get_supabase()
        count = (
            client.table("memory_media")
            .select("media_asset!inner(kind)", count="exact")
            .eq("memory_id", str(memory_id))
            .eq("media_asset.kind", "photo")
            .is_("media_asset.deleted_at", "null")
            .execute()
        )
        if (count.count or 0) >= MAX_PHOTOS_PER_MEMORY:
            raise ValueError(f"Maximum {MAX_PHOTOS_PER_MEMORY} photos per memory.")