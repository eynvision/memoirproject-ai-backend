import os
import logging
import assemblyai as aai

logger = logging.getLogger(__name__)


def transcribe_audio_url(audio_url: str) -> str:
    """
    Send a Supabase signed audio URL to AssemblyAI (batch/file mode).
    Returns the raw transcript text.
    """
    api_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not api_key:
        raise RuntimeError("ASSEMBLYAI_API_KEY is not configured.")

    aai.settings.api_key = api_key
    transcriber = aai.Transcriber()

    # Use the new speech_models parameter (plural list) instead of the deprecated speech_model
    config = aai.TranscriptionConfig(
        speech_models=["universal-2"]  # or ["universal-3-5-pro"] for best accuracy
    )

    transcript = transcriber.transcribe(audio_url, config=config)

    if transcript.status == aai.TranscriptStatus.error:
        logger.error("AssemblyAI error: %s", transcript.error)
        raise RuntimeError(f"Transcription failed: {transcript.error}")

    return transcript.text or ""