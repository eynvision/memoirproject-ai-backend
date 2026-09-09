import os
import logging
from groq import AsyncGroq

logger = logging.getLogger(__name__)

async def correct_transcript(raw_text: str) -> str:
    """
    AI Agent (using Groq): Fixes misspellings, punctuation, and grammar 
    errors from the automated transcription without changing meaning.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("GROQ_API_KEY missing. Returning raw transcript uncorrected.")
        return raw_text

    client = AsyncGroq(api_key=api_key)

    system_prompt = (
        "You are a silent editing agent. Fix obvious spelling mistakes, "
        "grammar errors, and punctuation from this speech-to-text transcript. "
        "Do not add comments. Do not summarize. Return only the corrected text."
    )

    model_name = "llama-3.1-8b-instant"

    try:
        response = await client.chat.completions.create(
            model=model_name, 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_text},
            ],
            temperature=0.2,
        )
        corrected = response.choices[0].message.content.strip()
        return corrected
    except Exception as e:
        logger.warning("Groq Agent correction failed with model %s: %s", model_name, e)
        return raw_text