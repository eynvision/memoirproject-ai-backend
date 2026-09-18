from typing import Dict, Any, List
from src.integrations.supabase_client import supabase_admin
from fastapi import HTTPException, status
def fetch_memories_for_ai(memoir_id: str) -> List[Dict[str, Any]]:
    """
    Fetches active submitted memories for the memoir.
    Retrieves only textual content and timestamps to minimize token payload.
    """
    res = supabase_admin.table("memory") \
        .select("id, title, body_text, occurred_start") \
        .eq("memoir_id", memoir_id) \
        .eq("status", "draft") \
        .is_("deleted_at", "null") \
        .execute()
    return res.data or []

def apply_ai_organization(memoir_id: str, ai_output: dict):
    """
    Persists AI-proposed chapters and updates memory references according to the chapter table schema.
    """
    try:
        # 1. Clear previous AI-generated chapters that haven't been manually locked/edited by the owner
        supabase_admin.table("chapter") \
            .delete() \
            .eq("memoir_id", memoir_id) \
            .eq("edited_by_owner", False) \
            .execute()

        # 2. Insert proposed chapters matching official table schema
        for chapter_data in ai_output.get("chapters", []):
            chapter_payload = {
                "memoir_id": memoir_id,
                "title": chapter_data["title"],
                "summary": chapter_data.get("summary"),
                "narrative_prose": chapter_data.get("narrative_prose"), # Saved here
                "sort_order": chapter_data["sort_order"],
                "created_by": "ai",
                "edited_by_owner": False
            }
            
            chapter_res = supabase_admin.table("chapter") \
                .insert(chapter_payload) \
                .select("id") \
                .execute()

            if not chapter_res.data:
                continue

            new_chapter_id = chapter_res.data[0]["id"]

            # 3. Associate memories with the new chapter
            for memory_ref in chapter_data.get("memories", []):
                update_payload = {"chapter_id": new_chapter_id}
                
                # Map the AI-inferred precision to the database enum column
                if memory_ref.get("inferred_date"):
                    update_payload["occurred_precision"] = memory_ref["inferred_date"]

                supabase_admin.table("memory") \
                    .update(update_payload) \
                    .eq("id", memory_ref["memory_id"]) \
                    .eq("memoir_id", memoir_id) \
                    .execute()
                    
    except Exception as e:
        print(f"Error applying AI organization to database: {str(e)}")
        raise e
    
def update_chapter_in_db(chapter_id: str, memoir_id: str, title: str = None, summary: str = None) -> dict:
    """Updates a chapter's text and locks it from future AI deletion."""
    update_payload = {"edited_by_owner": True}
    if title is not None:
        update_payload["title"] = title
    if summary is not None:
        update_payload["summary"] = summary

    # Ensure the chapter belongs to the specified memoir_id for security
    res = supabase_admin.table("chapter") \
        .update(update_payload) \
        .eq("id", chapter_id) \
        .eq("memoir_id", memoir_id) \
        .select() \
        .execute()
        
    if not res.data:
        raise HTTPException(status_code=404, detail="Chapter not found or does not belong to this memoir.")
        
    return res.data[0]


def move_memory_in_db(memory_id: str, memoir_id: str, new_chapter_id: str) -> dict:
    """Relocates a memory to a new chapter, verifying cross-references."""
    # First, verify the new_chapter_id actually belongs to this memoir
    chapter_check = supabase_admin.table("chapter") \
        .select("id") \
        .eq("id", new_chapter_id) \
        .eq("memoir_id", memoir_id) \
        .execute()
        
    if not chapter_check.data:
         raise  HTTPException(status_code=400, detail="Invalid target chapter: Chapter does not belong to this memoir.")

    # Proceed to update the memory
    res = supabase_admin.table("memory") \
        .update({"chapter_id": new_chapter_id}) \
        .eq("id", memory_id) \
        .eq("memoir_id", memoir_id) \
        .select() \
        .execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="Memory not found or does not belong to this memoir.")
        
    return res.data[0]

def fetch_archive_raw_data(memoir_id: str) -> dict:
    """Fetches raw chapters and memories for a memoir directly from Supabase."""
    # Fetch chapters
    chapters_res = supabase_admin.table("chapter") \
        .select("id, title, summary, sort_order") \
        .eq("memoir_id", memoir_id) \
        .order("sort_order") \
        .execute()
    
    chapters = chapters_res.data or []

    # Fetch memories
    memories_res = supabase_admin.table("memory") \
        .select("id, title, body_text, occurred_start, chapter_id") \
        .eq("memoir_id", memoir_id) \
        .is_("deleted_at", "null") \
        .execute()
        
    memories = memories_res.data or []

    return {
        "chapters": chapters,
        "memories": memories
    }