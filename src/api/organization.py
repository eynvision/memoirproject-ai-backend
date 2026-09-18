import os
from openai import OpenAI
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from src.core.auth import get_current_user
from src.integrations.share_repository import ShareRepository
from src.integrations.organization_repository import fetch_archive_raw_data
from src.domain.organization_service import perform_background_organization ,get_archive_context_for_chat
from src.schemas.organization import (
    OrganizeResponseEnvelope,
    ChapterUpdateRequest,
    MemoryMoveRequest,
    ChatRequest, 
    ChatResponse
)
from src.integrations.organization_repository import (
    update_chapter_in_db,
    move_memory_in_db
)

organization_router = APIRouter(prefix="/api/memoirs", tags=["AI Organization & Editing"])
client = OpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)
@organization_router.post(
    "/{memoir_id}/organize",
    response_model=OrganizeResponseEnvelope,
    status_code=status.HTTP_202_ACCEPTED
)
async def trigger_ai_organization(
    memoir_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Triggers automated AI chapter clustering and timeline generation in the background."""
    user_id = str(current_user.get("user_id") or current_user.get("id") or current_user.get("sub"))

    participant = await ShareRepository.get_participant(memoir_id, user_id)
    if not participant or participant.get("role") != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the memoir owner can trigger AI organization."
        )

    memoir = await ShareRepository.get_memoir_by_id(memoir_id)
    if not memoir:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memoir not found."
        )

    if memoir.get("status") == "published":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot organize a published, immutable memoir."
        )

    background_tasks.add_task(perform_background_organization, memoir_id)

    return OrganizeResponseEnvelope(
        success=True,
        message="Organization started in the background.",
        job_status="processing"
    )


@organization_router.put(
    "/{memoir_id}/chapters/{chapter_id}",
    status_code=status.HTTP_200_OK
)
async def manual_update_chapter(
    memoir_id: str,
    chapter_id: str,
    payload: ChapterUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Allows the memoir owner to manually rename or summarize a chapter.
    Automatically locks the chapter by setting edited_by_owner to True.
    """
    user_id = str(current_user.get("user_id") or current_user.get("id") or current_user.get("sub"))

    participant = await ShareRepository.get_participant(memoir_id, user_id)
    if not participant or participant.get("role") != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner can edit chapters."
        )

    if not payload.title and not payload.summary:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide title or summary to update."
        )

    updated_chapter = update_chapter_in_db(
        chapter_id=chapter_id,
        memoir_id=memoir_id,
        title=payload.title,
        summary=payload.summary
    )
    
    return {
        "success": True,
        "message": "Chapter manually edited and locked against automated AI overwrites.",
        "data": updated_chapter
    }


@organization_router.put(
    "/{memoir_id}/memories/{memory_id}/move",
    status_code=status.HTTP_200_OK
)
async def manual_move_memory(
    memoir_id: str,
    memory_id: str,
    payload: MemoryMoveRequest,
    current_user: dict = Depends(get_current_user)
):
    """Allows the memoir owner to reassign a memory to a different chapter."""
    user_id = str(current_user.get("user_id") or current_user.get("id") or current_user.get("sub"))

    participant = await ShareRepository.get_participant(memoir_id, user_id)
    if not participant or participant.get("role") != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner can move memories."
        )

    updated_memory = move_memory_in_db(
        memory_id=memory_id,
        memoir_id=memoir_id,
        new_chapter_id=payload.new_chapter_id
    )
    
    return {
        "success": True,
        "message": "Memory successfully relocated to the target chapter.",
        "data": updated_memory
    }
    

@organization_router.post(
    "/{memoir_id}/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK
)
async def chat_with_archive(
    memoir_id: str,
    payload: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Allows the user to converse with an AI co-author that has full contextual 
    awareness and conversational history support.
    """
    user_id = str(current_user.get("user_id") or current_user.get("id") or current_user.get("sub"))

    # Security: Verify participant access
    participant = await ShareRepository.get_participant(memoir_id, user_id)
    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this memoir."
        )

    # 1. Gather optimized archive table-of-contents context
    archive_context = get_archive_context_for_chat(memoir_id)

    # 2. Build system instructions incorporating the archive context
    system_prompt = (
        "You are an empathetic, insightful archival co-author assisting a user with their family memoir. "
        "You have direct access to the structured table of contents of their archive below. "
        "Use this context to answer their questions, suggest chapter improvements, or help them brainstorm ideas. "
        "Keep your tone warm, encouraging, and focused on storytelling.\n\n"
        f"{archive_context}"
    )

    try:
        messages = [{"role": "system", "content": system_prompt}]
        
        if payload.history:
            for hist_item in payload.history:
                messages.append({"role": hist_item.role, "content": hist_item.content})
                
        messages.append({"role": "user", "content": payload.message})

        response = client.chat.completions.create(
            model="gemini-3.8-flash",
            messages=messages
        )

        reply_text = response.choices[0].message.content

        return ChatResponse(
            success=True,
            reply=reply_text
        )

    except Exception as e:
        error_str = str(e)
        # Explicitly intercept Google AI Studio rate limits and quotas
        if "429" in error_str or "ResourceExhausted" in error_str or "Too Many Requests" in error_str:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="You are sending messages too quickly or have exceeded your quota. Please wait 30 seconds."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI chat service failed: {error_str}"
        )
        
@organization_router.get("/{memoir_id}/chapters", status_code=status.HTTP_200_OK)
async def get_memoir_chapters(
    memoir_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Fetches all structured chapters for a specific memoir."""
    user_id = str(current_user.get("user_id") or current_user.get("id") or current_user.get("sub"))

    participant = await ShareRepository.get_participant(memoir_id, user_id)
    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this memoir."
        )

    try:
        raw_data = fetch_archive_raw_data(memoir_id)
        chapters = raw_data.get("chapters", [])
    except Exception:
        chapters = []

    return {
        "success": True,
        "message": "Chapters fetched successfully.",
        "data": chapters
    }