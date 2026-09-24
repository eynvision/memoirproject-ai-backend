"""
@file chat_tools.py
@description The tools the memoir chat agent can call. Read tools answer
questions immediately. Write tools NEVER change anything: they validate the
request and record a 'pending' action for the user to confirm. The memoir and
user ids are bound here by closure, so the model can never choose them.
"""

import functools
import json
import logging
from typing import List

from fastapi import HTTPException
from langchain_core.tools import tool

from src.core.config import REWRITE_MAX_CHARS
from src.domain.chapter_service import ChapterService
from src.integrations import chat_repository, memoir_repository, memory_repository

logger = logging.getLogger(__name__)

_PREVIEW_CHARS = 80


def _guard(fn):
    """Turns unexpected errors (e.g. a malformed id from the model) into a tool result the model can read."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except HTTPException as e:
            return f"Error: {e.detail}"
        except Exception:
            logger.exception("Chat tool '%s' failed", fn.__name__)
            return "Error: that request could not be completed. Check that the ids are exactly as listed."
    return wrapper


def build_chat_tools(memoir_id: str, user_id: str):
    """
    Returns (tools, proposed). `proposed` fills up with the action rows the
    agent creates during the turn so the API can return them to the user.
    """
    proposed: list = []

    def _memoir() -> dict | None:
        return memoir_repository.get_memoir_by_id(memoir_id)

    def _locked_reason() -> str | None:
        memoir = _memoir()
        if not memoir:
            return "Memoir not found."
        if memoir.get("status") == "published":
            return "This memoir is published and can no longer be changed."
        return None

    def _draft_chapters() -> List[dict]:
        return ChapterService.get_chapters(memoir_id, user_id, "draft")

    def _find_draft_chapter(chapter_id: str) -> dict | None:
        return next((c for c in _draft_chapters() if str(c["id"]) == chapter_id), None)

    def _propose(action_type: str, payload: dict, summary: str) -> str:
        row = chat_repository.insert_action({
            "memoir_id": memoir_id,
            "user_id": user_id,
            "action_type": action_type,
            "payload": payload,
            "summary": summary,
        })
        proposed.append(row)
        return (
            "Proposed and waiting for the user to confirm; NOTHING has changed yet. "
            f"Proposal: {summary}"
        )

    # ------------------------------------------------------------------
    # Read tools (run immediately)
    # ------------------------------------------------------------------
    @tool
    @_guard
    def list_chapters() -> str:
        """List the memoir's chapters: id, title, subtitle, summary, the reason the AI grouped them (rationale), and each memory's id, title and a short preview of its original text. Use it to look up ids or to explain why memories were grouped together."""
        memoir = _memoir()
        chapter_status = "published" if memoir and memoir.get("status") == "published" else "draft"
        chapters = ChapterService.get_chapters(memoir_id, user_id, chapter_status)
        return json.dumps([
            {
                "id": c["id"],
                "title": c["title"],
                "subtitle": c.get("subtitle"),
                "summary": c.get("summary"),
                "rationale": c.get("rationale"),
                "memories": [
                    {
                        "id": m["id"],
                        "title": m.get("title"),
                        "preview": (m.get("body_text") or "")[:_PREVIEW_CHARS],
                    }
                    for m in c["memories"]
                ],
            }
            for c in chapters
        ])

    @tool
    @_guard
    def get_memory(memory_id: str) -> str:
        """Get one memory in full: its title, the ORIGINAL text as the family wrote it, and the AI-rewritten version if one exists."""
        res = memory_repository.fetch_memory_by_id(memory_id, memoir_id)
        if not res.data or res.data[0].get("deleted_at"):
            return "Error: memory not found in this memoir."
        m = res.data[0]
        return json.dumps({
            "id": m["id"],
            "title": m.get("title"),
            "original_text": m.get("body_text"),
            "rewritten_text": m.get("rewritten_text"),
        })

    @tool
    @_guard
    def get_personality_profile() -> str:
        """Get the personality profile ('vibe') of the person the memoir is about, if it has been built."""
        memoir = _memoir()
        profile = memoir.get("personality_profile") if memoir else None
        return json.dumps(profile) if profile else "The personality profile has not been built yet."

    # ------------------------------------------------------------------
    # Write tools (only PROPOSE; the user must confirm)
    # ------------------------------------------------------------------
    @tool
    @_guard
    def propose_chapter_edit(chapter_id: str, title: str = "", subtitle: str = "", summary: str = "") -> str:
        """Propose new text for a draft chapter. Pass only the fields to change; leave the others as empty strings. The user must confirm before anything changes."""
        locked = _locked_reason()
        if locked:
            return f"Error: {locked}"
        fields = {k: v.strip() for k, v in
                  {"title": title, "subtitle": subtitle, "summary": summary}.items() if v and v.strip()}
        if not fields:
            return "Error: provide at least one of title, subtitle or summary."
        chapter = _find_draft_chapter(chapter_id)
        if not chapter:
            return "Error: no draft chapter with that id."
        changes = ", ".join(f"{k} -> '{v}'" for k, v in fields.items())
        return _propose(
            "update_chapter",
            {"chapter_id": chapter_id, **fields},
            f"Edit chapter '{chapter['title']}': {changes}",
        )

    @tool
    @_guard
    def propose_reorder(chapter_id: str, memory_ids: List[str]) -> str:
        """Propose a new order for the memories inside one draft chapter. memory_ids must contain exactly the chapter's current memories (no additions or removals), in the new order. The user must confirm before anything changes."""
        locked = _locked_reason()
        if locked:
            return f"Error: {locked}"
        chapter = _find_draft_chapter(chapter_id)
        if not chapter:
            return "Error: no draft chapter with that id."
        current = [str(m["id"]) for m in chapter["memories"]]
        if sorted(memory_ids) != sorted(current):
            return "Error: memory_ids must contain exactly this chapter's current memories: " + json.dumps(current)
        return _propose(
            "reorder_chapter_memories",
            {"chapter_id": chapter_id, "memory_ids": memory_ids},
            f"Reorder the {len(memory_ids)} memories in chapter '{chapter['title']}'",
        )

    @tool
    @_guard
    def propose_memory_rewrite(memory_id: str, new_text: str) -> str:
        """Propose a new AI-rewritten version of one memory (for example a shorter or differently toned version). You write new_text yourself. It replaces only the rewritten version; the original text is never changed. The user must confirm before anything changes."""
        locked = _locked_reason()
        if locked:
            return f"Error: {locked}"
        text = (new_text or "").strip()
        if not text:
            return "Error: new_text cannot be empty."
        if len(text) > REWRITE_MAX_CHARS:
            return f"Error: new_text cannot exceed {REWRITE_MAX_CHARS} characters."
        res = memory_repository.fetch_memory_by_id(memory_id, memoir_id)
        if not res.data or res.data[0].get("deleted_at"):
            return "Error: memory not found in this memoir."
        label = res.data[0].get("title") or memory_id
        return _propose(
            "rewrite_memory",
            {"memory_id": memory_id, "text": text},
            f"Replace the rewritten version of memory '{label}' (the original text stays unchanged)",
        )

    @tool
    @_guard
    def propose_regenerate_chapters() -> str:
        """Propose re-organising all memories into new chapters from scratch. This REPLACES every current draft chapter, including any manual edits, then rewrites the memories again. The user must confirm before anything changes."""
        locked = _locked_reason()
        if locked:
            return f"Error: {locked}"
        return _propose(
            "regenerate_chapters",
            {},
            "Re-organise all memories into new chapters. This replaces every current draft chapter "
            "(including manual edits) and then rewrites the memories again.",
        )

    @tool
    @_guard
    def propose_regenerate_narrative() -> str:
        """Propose re-running the personality profile and re-writing every memory in the memoir's voice. This overwrites all current rewritten versions, including any the user approved earlier. The user must confirm before anything changes."""
        locked = _locked_reason()
        if locked:
            return f"Error: {locked}"
        return _propose(
            "regenerate_narrative",
            {},
            "Rebuild the personality profile and rewrite every memory again. "
            "This overwrites all current rewritten versions.",
        )

    tools = [
        list_chapters,
        get_memory,
        get_personality_profile,
        propose_chapter_edit,
        propose_reorder,
        propose_memory_rewrite,
        propose_regenerate_chapters,
        propose_regenerate_narrative,
    ]
    return tools, proposed
