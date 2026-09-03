import asyncio
import logging
from uuid import UUID

from src.integrations.assemblyai_client import transcribe_audio_url
from src.integrations.llm_client import correct_transcript
from src.integrations.supabase_client import create_read_url, get_supabase

logger = logging.getLogger(__name__)


async def process_audio_transcription(
    memoir_id: UUID, media_asset_id: UUID, storage_key: str
):
    """
    Background pipeline:
    1. Mark media_asset status as processing.
    2. Get signed URL for audio file.
    3. AssemblyAI transcribes (offloaded to thread).
    4. LLM Agent corrects misspellings.
    5. Stores final corrected text in transcript table.
    6. Updates media_asset status to ready.
    """
    client = get_supabase()

    try:
        # Step 1: Mark processing
        client.table("media_asset").update(
            {"transcription_status": "processing"}
        ).eq("id", str(media_asset_id)).execute()

        # Step 2: Get signed URL for AssemblyAI
        audio_url = create_read_url(storage_key)
        logger.info("Generated audio URL for AssemblyAI: %s", audio_url)

        # Step 3: Transcribe (Offload synchronous AssemblyAI call to thread pool)
        raw_text = await asyncio.to_thread(transcribe_audio_url, audio_url)
        logger.info("Transcription complete for media asset %s", media_asset_id)

        # Step 4: Agent corrects
        corrected_text = await correct_transcript(raw_text)
        logger.info("Agent correction complete for media asset %s", media_asset_id)

        # Step 5: Store in transcript table
        client.table("transcript").insert(
            {
                "media_asset_id": str(media_asset_id),
                "memoir_id": str(memoir_id),
                "raw_text": corrected_text or raw_text or "No speech detected.",
                "language": "en",
                "engine": "assemblyai+agent-corrected",
                "confidence": None,
            }
        ).execute()

        # Step 6: Mark ready
        client.table("media_asset").update(
            {"transcription_status": "ready"}
        ).eq("id", str(media_asset_id)).execute()

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
        client.table("media_asset").update({"transcription_status": "failed"}).eq(
            "id", str(media_asset_id)
        ).execute()