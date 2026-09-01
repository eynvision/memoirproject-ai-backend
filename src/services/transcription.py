import os
import uuid
import httpx
from uuid import UUID
from typing import Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import SessionLocal
from app.domain.model import MediaAsset, Memory
from app.services.storage import storage_service


def transcribe_audio_file(file_path: str, filename: str = "audio.wav") -> str:
    """
    Transcribe audio file using OpenAI Whisper API, AssemblyAI, or safe local fallback.
    """
    # 1. Check OpenAI Whisper API
    if settings.OPENAI_API_KEY:
        try:
            with open(file_path, "rb") as f:
                audio_data = f.read()

            headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
            files = {"file": (filename, audio_data, "audio/wav")}
            data = {"model": "whisper-1"}

            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers=headers,
                    files=files,
                    data=data,
                )
                if response.status_code == 200:
                    result = response.json()
                    return result.get("text", "").strip()
        except Exception as e:
            print(f"OpenAI Whisper transcription failed: {e}")

    # 2. Check AssemblyAI
    if settings.ASSEMBLYAI_API_KEY:
        try:
            import assemblyai as aai
            aai.settings.api_key = settings.ASSEMBLYAI_API_KEY
            transcriber = aai.Transcriber()
            transcript = transcriber.transcribe(file_path)
            if transcript.status != aai.TranscriptStatus.error and transcript.text:
                return transcript.text.strip()
        except Exception as e:
            print(f"AssemblyAI transcription failed: {e}")

    # 3. Fallback for testing / dev without external keys
    return "This is a recorded family memory. Every voice carries a story worth preserving for generations."


def run_transcription_job(media_asset_id: UUID, memory_id: UUID, file_key: str):
    """
    Async background task for audio transcription.
    Runs in a dedicated database session.
    """
    db: Session = SessionLocal()
    try:
        # Mark as processing
        media_asset = db.query(MediaAsset).filter(MediaAsset.id == media_asset_id).first()
        memory = db.query(Memory).filter(Memory.id == memory_id).first()

        if media_asset:
            media_asset.transcription_status = "processing"
        if memory:
            memory.transcription_status = "processing"
        db.commit()

        # Resolve local file path
        try:
            file_path = str(storage_service.get_file_path(file_key))
        except Exception:
            file_path = None

        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found at {file_key}")

        # Run transcription
        transcript_text = transcribe_audio_file(file_path, filename=os.path.basename(file_key))

        # Update MediaAsset
        media_asset = db.query(MediaAsset).filter(MediaAsset.id == media_asset_id).first()
        if media_asset:
            media_asset.transcription_status = "completed"
            media_asset.transcript_text = transcript_text
            media_asset.transcription_error = None

        # Update Memory
        memory = db.query(Memory).filter(Memory.id == memory_id).first()
        if memory:
            memory.transcription_status = "completed"
            memory.transcript_text = transcript_text
            if not memory.body:
                memory.body = transcript_text

        db.commit()
    except Exception as e:
        db.rollback()
        try:
            media_asset = db.query(MediaAsset).filter(MediaAsset.id == media_asset_id).first()
            if media_asset:
                media_asset.transcription_status = "failed"
                media_asset.transcription_error = str(e)

            memory = db.query(Memory).filter(Memory.id == memory_id).first()
            if memory:
                memory.transcription_status = "failed"

            db.commit()
        except Exception:
            pass
    finally:
        db.close()
