import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from src.integrations.assemblyai_client import transcribe_audio_url
from src.integrations.llm_client import correct_transcript
from src.integrations.supabase_client import create_read_url, get_supabase

logger = logging.getLogger(__name__)


def _update_asset_status(media_asset_id: UUID, status: str) -> None:
    client = get_supabase()
    client.table("media_asset").update(
        {"transcription_status": status}
    ).eq("id", str(media_asset_id)).execute()


def _insert_transcript(
    memoir_id: UUID,
    media_asset_id: UUID,
    raw_text: str,
    edited_text: str | None,
) -> None:
    """Store the true ASR output in raw_text; agent corrections go to edited_text.

    The schema's attribution CHECK requires edited_at whenever edited_text is
    set, so both are written together. edited_by_participant_id stays NULL
    because the editor is the pipeline, not a human.
    """
    client = get_supabase()
    final_raw = raw_text or "No speech detected."
    payload = {
        "media_asset_id": str(media_asset_id),
        "memoir_id": str(memoir_id),
        "raw_text": final_raw,
        "language": "en",
        "engine": "assemblyai+agent-corrected",
        "confidence": None,
    }
    if edited_text and edited_text.strip() and edited_text != final_raw:
        payload["edited_text"] = edited_text
        payload["edited_at"] = datetime.now(timezone.utc).isoformat()
    client.table("transcript").insert(payload).execute()


async def process_audio_transcription(
    memoir_id: UUID, media_asset_id: UUID, storage_key: str
):
    """
    Background pipeline:
    1. Mark media_asset status as processing.
    2. Get signed URL for audio file.
    3. AssemblyAI transcribes (offloaded to thread).
    4. LLM Agent corrects misspellings.
    5. Stores raw and corrected text in the transcript table.
    6. Updates media_asset status to ready.
    """
    try:
        await asyncio.to_thread(_update_asset_status, media_asset_id, "processing")

        audio_url = await asyncio.to_thread(create_read_url, storage_key)
        logger.info("Generated audio URL for AssemblyAI: %s", audio_url)

        raw_text = await asyncio.to_thread(transcribe_audio_url, audio_url)
        logger.info("Transcription complete for media asset %s", media_asset_id)

        corrected_text = await correct_transcript(raw_text)
        logger.info("Agent correction complete for media asset %s", media_asset_id)

        await asyncio.to_thread(
            _insert_transcript, memoir_id, media_asset_id, raw_text, corrected_text
        )

        await asyncio.to_thread(_update_asset_status, media_asset_id, "ready")

        logger.info(
            "Transcription pipeline finished successfully for media asset %s",
            media_asset_id,
        )

    except Exception as error:
        logger.error(
            "Transcription pipeline failed for media asset %s: %s",
            media_asset_id,
            error,
            exc_info=True,
        )
        await asyncio.to_thread(_update_asset_status, media_asset_id, "failed")