"""
@file narrative_service.py
@description Business logic for the AI narrative layer: builds the memoir's
personality profile from all its memories, rewrites each chapter's memories
as warm memoir prose in that voice, and stores the result beside (never over)
the user's original memory text. The AI output is validated before saving.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import HTTPException, status

from src.core.config import NARRATIVE_STALE_MINUTES, REWRITE_MAX_CHARS
from src.domain.authorization import verify_active_participant
from src.domain.memory_input import normalize_memories
from src.integrations import (
    chapter_repository,
    memoir_repository,
    memory_repository,
    narrative_repository,
)
from src.integrations.memory_rewrite_chain import ChapterRewriteResult, MemoryRewriteChain
from src.integrations.personality_chain import PersonalityProfileChain
from src.schemas.narrative import NarrativeStatusData

logger = logging.getLogger(__name__)


def _has_text(item) -> bool:
    return bool(item.content and item.content.strip())


class NarrativeService:
    """Coordinates personality analysis and memory rewriting for a memoir."""

    # ------------------------------------------------------------------
    # Job state helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _stale_cutoff_iso() -> str:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=NARRATIVE_STALE_MINUTES)
        return cutoff.isoformat()

    @staticmethod
    def is_running(memoir: dict) -> bool:
        """True if a narrative job is running and has not gone stale."""
        if memoir.get("narrative_status") != "running":
            return False
        started = memoir.get("narrative_started_at")
        if not started:
            return True
        try:
            started_at = datetime.fromisoformat(started)
        except ValueError:
            return True
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=NARRATIVE_STALE_MINUTES)
        return started_at >= cutoff

    @classmethod
    def claim_job(cls, memoir_id: str) -> bool:
        """
        Claims the narrative job without raising HTTP errors. Used right after
        chapter generation. Returns False if the memoir is missing, already
        published, or another live job holds the claim.
        """
        memoir = memoir_repository.get_memoir_by_id(memoir_id)
        if not memoir or memoir.get("status") == "published":
            return False
        return narrative_repository.claim_narrative_job(memoir_id, cls._stale_cutoff_iso())

    @classmethod
    def start_regeneration(cls, memoir_id: str, user_id: str) -> None:
        """Validates the request and claims the job; the caller schedules run_narrative_job."""
        verify_active_participant(memoir_id, user_id, required_roles=["owner", "admin"])

        memoir = memoir_repository.get_memoir_by_id(memoir_id)
        if not memoir:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memoir not found.")
        if memoir.get("status") == "published":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This memoir has been published and can no longer be changed.",
            )

        res = chapter_repository.fetch_chapters_with_memories(memoir_id, "draft")
        if not (res and res.data):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No draft chapters found. Generate chapters first.",
            )

        if not narrative_repository.claim_narrative_job(memoir_id, cls._stale_cutoff_iso()):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A narrative rewrite is already running for this memoir.",
            )

    @classmethod
    def get_status(cls, memoir_id: str, user_id: str) -> NarrativeStatusData:
        verify_active_participant(memoir_id, user_id)
        memoir = memoir_repository.get_memoir_by_id(memoir_id)
        if not memoir:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memoir not found.")
        return NarrativeStatusData(
            memoir_id=memoir_id,
            status=memoir.get("narrative_status") or "idle",
            error=memoir.get("narrative_error"),
            updated_at=memoir.get("narrative_updated_at"),
            personality_profile=memoir.get("personality_profile"),
        )

    # ------------------------------------------------------------------
    # The job (runs in a background task; never raises)
    # ------------------------------------------------------------------
    @classmethod
    def run_narrative_job(cls, memoir_id: str) -> None:
        """
        Builds the personality profile then rewrites every chapter's memories.
        The caller must already have claimed the job. Any failure is recorded
        on the memoir as narrative_status='failed'; chapters are unaffected.
        """
        try:
            cls._execute(memoir_id)
        except Exception as e:
            logger.exception("Narrative job failed for memoir %s", memoir_id)
            try:
                narrative_repository.finish_narrative_job(memoir_id, "failed", str(e))
            except Exception:
                logger.exception("Could not record narrative failure for memoir %s", memoir_id)

    @classmethod
    def _execute(cls, memoir_id: str) -> None:
        memoir = memoir_repository.get_memoir_by_id(memoir_id)
        if not memoir:
            raise ValueError("Memoir not found.")

        res = chapter_repository.fetch_memories_for_organisation(memoir_id)
        all_memories = [m for m in normalize_memories(res.data or []) if _has_text(m)]
        if not all_memories:
            narrative_repository.finish_narrative_job(memoir_id, "completed")
            return

        profile = PersonalityProfileChain().analyse(memoir["subject_name"], all_memories).model_dump()
        narrative_repository.save_personality_profile(memoir_id, profile)

        rewriter = MemoryRewriteChain()
        attempted = 0
        failed = 0
        for chapter in cls._load_draft_chapters(memoir_id):
            items = [m for m in normalize_memories(chapter["memories"]) if _has_text(m)]
            if not items:
                continue
            attempted += 1
            try:
                result = rewriter.rewrite(profile, chapter["title"], items)
                cls._validate_rewrites(result, {str(item.id) for item in items})
                for rewritten in result.memories:
                    narrative_repository.save_rewritten_text(
                        rewritten.memory_id, memoir_id, rewritten.text.strip()
                    )
            except Exception:
                failed += 1
                logger.exception(
                    "Rewrite failed for chapter '%s' of memoir %s", chapter.get("title"), memoir_id
                )

        if failed:
            narrative_repository.finish_narrative_job(
                memoir_id, "failed", f"{failed} of {attempted} chapters could not be rewritten."
            )
        else:
            narrative_repository.finish_narrative_job(memoir_id, "completed")

    @staticmethod
    def _load_draft_chapters(memoir_id: str) -> List[dict]:
        """Draft chapters, each with its ordered member memories under 'memories'."""
        res = chapter_repository.fetch_chapters_with_memories(memoir_id, "draft")
        chapters = []
        for row in (res.data if res and res.data else []):
            links = [link for link in row.pop("chapter_memory", []) if link and link.get("memory")]
            links.sort(key=lambda link: link.get("sort_order", 0))
            row["memories"] = [link["memory"] for link in links]
            chapters.append(row)
        return chapters

    # ------------------------------------------------------------------
    # Validation (never trust the AI blindly)
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_rewrites(result: ChapterRewriteResult, expected_ids: set) -> None:
        """
        Rejects rewrites that reference memories we never sent, repeat or skip
        a memory, or contain empty / oversized text.
        """
        returned = [m.memory_id for m in result.memories]
        if len(returned) != len(set(returned)):
            raise ValueError("The model returned the same memory more than once.")

        unknown = set(returned) - expected_ids
        if unknown:
            raise ValueError(f"The model returned memory ids that were never provided: {sorted(unknown)}")

        missing = expected_ids - set(returned)
        if missing:
            raise ValueError(f"The model skipped {len(missing)} provided memories.")

        for rewritten in result.memories:
            if not rewritten.text or not rewritten.text.strip():
                raise ValueError(f"Memory '{rewritten.memory_id}' came back with empty text.")
            if len(rewritten.text) > REWRITE_MAX_CHARS:
                raise ValueError(
                    f"Memory '{rewritten.memory_id}' rewrite exceeds {REWRITE_MAX_CHARS} characters."
                )

    # ------------------------------------------------------------------
    # Manual rewrite (used when the user confirms a chat proposal)
    # ------------------------------------------------------------------
    @staticmethod
    def apply_manual_rewrite(memoir_id: str, memory_id: str, text: str) -> dict:
        """
        Stores a user-approved rewrite for one memory. The caller must already
        have verified the user's role. Only rewritten_text is written; the
        original body_text is never touched.
        """
        memoir = memoir_repository.get_memoir_by_id(memoir_id)
        if not memoir:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memoir not found.")
        if memoir.get("status") == "published":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This memoir has been published and can no longer be changed.",
            )

        cleaned = (text or "").strip()
        if not cleaned:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rewrite text cannot be empty.")
        if len(cleaned) > REWRITE_MAX_CHARS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Rewrite text cannot exceed {REWRITE_MAX_CHARS} characters.",
            )

        mem_res = memory_repository.fetch_memory_by_id(memory_id, memoir_id)
        if not mem_res.data or mem_res.data[0].get("deleted_at"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found in this memoir.")

        narrative_repository.save_rewritten_text(memory_id, memoir_id, cleaned)
        return {"memory_id": memory_id, "rewritten_text": cleaned}
