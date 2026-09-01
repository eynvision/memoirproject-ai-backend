import os
import tempfile
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/speech", tags=["Speech To Text"])


class TranscriptionResponse(BaseModel):
    text: str


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(file: UploadFile = File(...)):
    assemblyai_key = settings.ASSEMBLYAI_API_KEY or os.getenv("ASSEMBLYAI_API_KEY")
    if not assemblyai_key:
        raise HTTPException(
            status_code=500,
            detail="ASSEMBLYAI_API_KEY is not configured on the server."
        )

    try:
        import assemblyai as aai
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="assemblyai package is not installed on the server."
        )

    # Read uploaded file content
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded audio file is empty.")

    # Save to a temporary file for AssemblyAI SDK processing
    file_suffix = os.path.splitext(file.filename or "")[1] or ".wav"
    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_suffix) as temp_file:
            temp_file.write(contents)
            temp_file_path = temp_file.name

        aai.settings.api_key = assemblyai_key
        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(temp_file_path)

        if transcript.status == aai.TranscriptStatus.error:
            raise HTTPException(
                status_code=500,
                detail=f"Transcription failed: {transcript.error}"
            )

        return TranscriptionResponse(text=transcript.text or "")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Speech-to-text processing failed: {str(e)}")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception:
                pass
