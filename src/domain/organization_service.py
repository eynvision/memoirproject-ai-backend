import os
import json
from openai import OpenAI
from src.schemas.organization import MemoirOrganizationOutput
from src.integrations.organization_repository import (
    fetch_memories_for_ai,
    apply_ai_organization,
    fetch_archive_raw_data
)

# Note the exact base_url with "v1beta" and the trailing "/"
client = OpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

def perform_background_organization(memoir_id: str):
    """
    Background worker orchestrating memory fetching, structured LLM clustering,
    and database persistence using Gemini via the OpenAI interface.
    """
    try:
        memories = fetch_memories_for_ai(memoir_id)
        if not memories:
            print(f"No submitted memories found for memoir {memoir_id}.")
            return

        payload_for_llm = [
            {
                "memory_id": str(m["id"]),
                "title": m.get("title") or "",
                "text": m.get("body_text") or "",
                "recorded_date": m.get("occurred_start") or ""
            }
            for m in memories
        ]

        system_prompt = (
            "You are an archival biographer organizing raw memories into a published book chapter. "
            "For each chapter, write a cohesive, continuous biographical narrative ('narrative_prose') "
            "that seamlessly weaves together all the memories assigned to this chapter. "
            "It must read like a published book chapter, blending the exact details, dates, and events "
            "from those memories. CRITICAL: Do not introduce any outside information, fictional details, or facts not present in the input memories. "
            "Assign every memory to a chapter. "
            "Return a valid JSON object strictly matching this schema:\n"
            "{\n"
            '  "chapters": [\n'
            "    {\n"
            '      "title": "string",\n'
            '      "summary": "string or null",\n'
            '      "narrative_prose": "string containing the unified chapter story",\n'
            '      "sort_order": 1,\n'
            '      "memories": [\n'
            '        {"memory_id": "string", "inferred_date": "day"}\n'
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}"
        )
        
        response = client.chat.completions.create(
            model="gemini-1.5-flash",  # Changed from unstable experimental alias to stable production alias
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload_for_llm)}
            ],
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content
        
        # Validate against your Pydantic schema
        validated_output = MemoirOrganizationOutput.model_validate_json(content)
        
        apply_ai_organization(memoir_id, validated_output.model_dump())
        print(f"AI organization successfully applied for memoir {memoir_id}.")

    except Exception as e:
        print(f"AI organization job failed for memoir {memoir_id}: {str(e)}")
        
def get_archive_context_for_chat(memoir_id: str) -> str:
    """
    Optimized structural table-of-contents index for the AI co-author.
    Omits heavy raw body text to prevent token explosion and rate limits (429).
    """
    raw_data = fetch_archive_raw_data(memoir_id)
    chapters = raw_data.get("chapters", [])
    memories = raw_data.get("memories", [])

    context_str = "== MEMOIR ARCHIVE TABLE OF CONTENTS ==\n\n"
    
    for ch in chapters:
        context_str += f"Chapter {ch.get('sort_order')}: {ch.get('title')}\n"
        if ch.get('summary'):
            context_str += f"Summary: {ch.get('summary')}\n"
        
        ch_memories = [m for m in memories if m.get("chapter_id") == ch.get("id")]
        if ch_memories:
            context_str += "Contained Memories:\n"
            for m in ch_memories:
                m_title = m.get('title') or 'Untitled'
                m_date = m.get('occurred_start') or 'Undated'
                context_str += f"  - [{m_date}] {m_title}\n"
        else:
            context_str += "  - (No memories assigned yet)\n"
        context_str += "\n"
        
    unassigned = [m for m in memories if not m.get("chapter_id")]
    if unassigned:
        context_str += "Unassigned Memories:\n"
        for m in unassigned:
            context_str += f"  - Title: '{m.get('title') or 'Untitled'}'\n"
            
    return context_str