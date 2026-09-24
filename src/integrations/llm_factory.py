"""
@file llm_factory.py
@description Builds the Gemini chat model used by the AI narrative and chat
features, failing fast with a clear message when the API key is missing.
"""

from langchain_google_genai import ChatGoogleGenerativeAI

from src.core.config import settings


def build_chat_model(temperature: float) -> ChatGoogleGenerativeAI:
    """Returns a configured Gemini chat model, or raises if no API key is set."""
    if not settings.google_api_key:
        raise ValueError(
            "GOOGLE_API_KEY is missing from environment variables. "
            "AI features cannot run without it."
        )
    return ChatGoogleGenerativeAI(
        model=settings.google_model,
        google_api_key=settings.google_api_key,
        temperature=temperature,
        # Gemini intermittently returns 503 "high demand"; retry with backoff.
        max_retries=5,
    )
