import os
import time
from groq import Groq
from src.integrations.memory_repository import upsert_transcript_record
from src.integrations.supabase_client import supabase_admin

def transcribe_and_store_audio(media_asset_id: str, memoir_id: str, storage_key: str):
    """
    Downloads audio binary from Supabase storage using admin client with retries, 
    uploads raw bytes directly to Groq Whisper, and persists the resulting transcript.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("CRITICAL ERROR: GROQ_API_KEY is missing from environment variables!")
        raise ValueError("GROQ_API_KEY is missing")

    groq_client = Groq(api_key=api_key)

    try:
        bucket_name = "media-bucket"  
        audio_bytes = None
        
        # Retry loop (up to 3 attempts with a 1.5s delay) to handle browser upload race conditions
        print(f"Attempting to download storage key '{storage_key}' from bucket '{bucket_name}'...")
        for attempt in range(1, 4):
            try:
                audio_bytes = supabase_admin.storage.from_(bucket_name).download(storage_key)
                if audio_bytes:
                    print(f"Successfully downloaded audio bytes on attempt {attempt}")
                    break
            except Exception as dl_err:
                print(f"Download attempt {attempt} failed (file might still be uploading): {str(dl_err)}")
                if attempt < 3:
                    time.sleep(1.5)

        if not audio_bytes:
            raise Exception(f"Download returned empty bytes or 404 after retries for key: {storage_key}")

        print("Uploading raw audio bytes to Groq Whisper API...")
        
        # Groq requires a filename with a recognized extension to parse the format
        extension = storage_key.split('.')[-1] if '.' in storage_key else 'webm'
        
        transcript_result = groq_client.audio.transcriptions.create(
            file=(f"audio.{extension}", audio_bytes),
            model="whisper-large-v3-turbo",
            response_format="json",
            language="en" # Omit this if you want Whisper to auto-detect mixed languages
        )
        
        raw_text = transcript_result.text or ""
        print(f"Transcription successful! Text: {raw_text[:60]}...")

        transcript_payload = {
            "media_asset_id": media_asset_id,
            "memoir_id": memoir_id,
            "raw_text": raw_text,
            "engine": "groq-whisper",
            # Defaulting confidence to 1.0 since Groq's standard json response omits it
            "confidence": 1.0, 
            "language": "en"
        }
        
        response = upsert_transcript_record(transcript_payload)
        
        print("Transcript successfully saved to database!", response.data)
        return response.data

    except Exception as e:
        print(f"CRITICAL TRANSCRIPTION EXCEPTION CAUGHT: {str(e)}")
        raise e