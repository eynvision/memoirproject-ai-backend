# Domain logic for the live memoir: public book assembly, reader comments,
# one-level replies, emoji reactions and owner moderation. Readers are not
# authenticated; every name they give resolves to a memoir_participant row
# with role='reader' so comments stay attributed to a person, not a session.

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID

from src.integrations.supabase_client import create_read_urls, get_supabase
from src.models.reader_models import (
    BookOut,
    CommentCreateRequest,
    CommentNode,
    ReactionRequest,
    ReactionSummary,
    ReactionToggleOut,
    SearchHit,
    SearchOut,
)

logger = logging.getLogger(__name__)

# The fixed reaction vocabulary, chosen for a memoir rather than a social feed.
REACTION_KINDS = ("with_love", "moved", "thank_you", "brings_a_smile")

# Comment reactions reuse the reaction table: kind carries the comment id so
# the existing unique indexes give one reaction per reader per comment per emoji.
COMMENT_KIND_PREFIX = "comment:"


def _safe_data(response: object):
    if response is None:
        return None
    return getattr(response, "data", None)


def _published_memoir(memoir_id: UUID) -> dict:
    client = get_supabase()
    result = (
        client.table("memoir")
        .select("*")
        .eq("id", str(memoir_id))
        .maybe_single()
        .execute()
    )
    row = _safe_data(result)
    if not row or row.get("status") != "published":
        raise LookupError("This memoir is not published.")
    return row


def _resolve_reader_participant(
    memoir_id: UUID, name: str, create: bool = True
) -> Optional[str]:
    """Map a reader's typed name onto a participant row, creating it once."""
    trimmed = " ".join(name.split())
    if len(trimmed) < 2 or trimmed.lower() == "anonymous":
        raise ValueError("Please sign your comment with your name (not 'Anonymous').")

    client = get_supabase()
    existing = (
        client.table("memoir_participant")
        .select("id, display_name")
        .eq("memoir_id", str(memoir_id))
        .eq("role", "reader")
        .is_("removed_at", "null")
        .execute()
    )
    for row in _safe_data(existing) or []:
        if str(row["display_name"]).strip().casefold() == trimmed.casefold():
            return row["id"]

    if not create:
        return None

    inserted = (
        client.table("memoir_participant")
        .insert(
            {
                "memoir_id": str(memoir_id),
                "role": "reader",
                "display_name": trimmed,
                "relationship": "other",
            }
        )
        .execute()
    )
    return inserted.data[0]["id"]


def _owner_participant(memoir_id: UUID, user_id: UUID) -> dict:
    client = get_supabase()
    result = (
        client.table("memoir_participant")
        .select("id, role")
        .eq("memoir_id", str(memoir_id))
        .eq("user_id", str(user_id))
        .in_("role", ["owner", "co_owner"])
        .is_("removed_at", "null")
        .maybe_single()
        .execute()
    )
    row = _safe_data(result)
    if not row:
        raise PermissionError("Only the memoir owner can do this.")
    return row


def _view_link_token(memoir_id: UUID, participant_id: Optional[str] = None) -> str:
    """Return the live view-scope link token, creating it when missing."""
    client = get_supabase()
    existing = (
        client.table("memoir_link")
        .select("token")
        .eq("memoir_id", str(memoir_id))
        .eq("scope", "view")
        .is_("revoked_at", "null")
        .maybe_single()
        .execute()
    )
    row = _safe_data(existing)
    if row:
        return row["token"]
    inserted = (
        client.table("memoir_link")
        .insert(
            {
                "memoir_id": str(memoir_id),
                "scope": "view",
                "created_by_participant_id": participant_id,
            }
        )
        .execute()
    )
    return inserted.data[0]["token"]


def _summary_from_rows(rows: List[dict], reader_id: Optional[str]) -> ReactionSummary:
    counts: Dict[str, int] = {}
    mine: Set[str] = set()
    for row in rows:
        key = row["kind"]
        counts[key] = counts.get(key, 0) + 1
        if reader_id and row["participant_id"] == reader_id:
            mine.add(key)
    return ReactionSummary(counts=counts, mine=sorted(mine))


def _load_comments_and_reactions(
    memoir_id: UUID, memory_ids: List[str], reader_id: Optional[str]
) -> Tuple[
    Dict[str, List[CommentNode]], Dict[str, ReactionSummary], Dict[str, ReactionSummary]
]:
    """One pass over comment + reaction rows builds every thread and count."""
    client = get_supabase()
    by_memory: Dict[str, List[CommentNode]] = {mid: [] for mid in memory_ids}
    mem_reactions: Dict[str, ReactionSummary] = {
        mid: ReactionSummary() for mid in memory_ids
    }
    comment_reactions: Dict[str, ReactionSummary] = {}
    if not memory_ids:
        return by_memory, mem_reactions, comment_reactions

    comment_res = (
        client.table("comment")
        .select("*")
        .eq("memoir_id", str(memoir_id))
        .in_("memory_id", memory_ids)
        .is_("deleted_at", "null")
        .is_("hidden_at", "null")
        .order("created_at")
        .execute()
    )
    comments = _safe_data(comment_res) or []
    comment_ids = [c["id"] for c in comments]

    reaction_rows: List[dict] = []
    reaction_res = (
        client.table("reaction")
        .select("kind, participant_id, memory_id")
        .eq("memoir_id", str(memoir_id))
        .in_("memory_id", memory_ids)
        .execute()
    )
    reaction_rows = _safe_data(reaction_res) or []

    author_ids = {c["author_participant_id"] for c in comments}
    names: Dict[str, str] = {}
    if author_ids:
        people = (
            client.table("memoir_participant")
            .select("id, display_name")
            .in_("id", sorted(author_ids))
            .execute()
        )
        names = {p["id"]: p["display_name"] for p in _safe_data(people) or []}

    mem_reaction_rows: Dict[str, List[dict]] = {mid: [] for mid in memory_ids}
    comment_reaction_rows: Dict[str, List[dict]] = {cid: [] for cid in comment_ids}

    for row in reaction_rows:
        kind = row["kind"]
        if kind.startswith(COMMENT_KIND_PREFIX):
            parts = kind.split(":")
            if len(parts) == 3 and parts[1] in comment_reaction_rows:
                comment_reaction_rows[parts[1]].append({**row, "kind": parts[2]})
        elif row["memory_id"] in mem_reaction_rows:
            mem_reaction_rows[row["memory_id"]].append(row)

    for cid in comment_ids:
        comment_reactions[cid] = _summary_from_rows(
            comment_reaction_rows.get(cid, []), reader_id
        )
    for mid in memory_ids:
        mem_reactions[mid] = _summary_from_rows(mem_reaction_rows.get(mid, []), reader_id)

    nodes: Dict[str, CommentNode] = {}
    for row in comments:
        nodes[row["id"]] = CommentNode(
            id=row["id"],
            author_name=names.get(row["author_participant_id"], "A reader"),
            body=row["body"],
            created_at=row["created_at"],
            replies=[],
            reactions=comment_reactions.get(row["id"], ReactionSummary()),
        )

    for row in comments:
        node = nodes[row["id"]]
        parent = row.get("parent_comment_id")
        if parent and parent in nodes:
            nodes[parent].replies.append(node)
        else:
            by_memory[row["memory_id"]].append(node)

    return by_memory, mem_reactions, comment_reactions


def _flatten(nodes: List[CommentNode]) -> List[CommentNode]:
    out: List[CommentNode] = []
    for node in nodes:
        out.append(node)
        out.extend(node.replies)
    return out


def _assemble_book(
    memoir: dict, reader_id: Optional[str], share_token: Optional[str]
) -> BookOut:
    client = get_supabase()
    memoir_id = memoir["id"]

    chapter_res = (
        client.table("chapter")
        .select("*")
        .eq("memoir_id", memoir_id)
        .order("sort_order")
        .order("created_at")
        .execute()
    )
    chapters = _safe_data(chapter_res) or []

    memory_res = (
        client.table("memory")
        .select("*")
        .eq("memoir_id", memoir_id)
        .eq("status", "submitted")
        .is_("deleted_at", "null")
        .order("position_in_chapter", nullsfirst=False)
        .order("created_at")
        .execute()
    )
    memories = _safe_data(memory_res) or []
    memory_ids = [m["id"] for m in memories]

    media_by_memory: Dict[str, List[dict]] = {mid: [] for mid in memory_ids}
    assets: Dict[str, dict] = {}
    if memory_ids:
        link_res = (
            client.table("memory_media")
            .select("memory_id, position, media_asset(*)")
            .in_("memory_id", memory_ids)
            .is_("media_asset.deleted_at", "null")
            .order("position")
            .execute()
        )
        for row in _safe_data(link_res) or []:
            asset = row.get("media_asset")
            if not asset:
                continue
            assets[asset["id"]] = asset
            media_by_memory[row["memory_id"]].append(asset)

    urls = create_read_urls([a["storage_key"] for a in assets.values()]) if assets else {}

    transcripts: Dict[str, str] = {}
    playable = [a["id"] for a in assets.values() if a["kind"] != "photo"]
    if playable:
        transcript_res = (
            client.table("transcript")
            .select("media_asset_id, display_text")
            .in_("media_asset_id", playable)
            .execute()
        )
        transcripts = {
            t["media_asset_id"]: t["display_text"]
            for t in _safe_data(transcript_res) or []
        }

    comments_by_memory, mem_reactions, comment_reactions = _load_comments_and_reactions(
        UUID(memoir_id), memory_ids, reader_id
    )

    def media_out(asset: dict) -> dict:
        return {
            "id": asset["id"],
            "kind": asset["kind"],
            "playback_url": urls.get(asset["storage_key"], ""),
            "caption": asset.get("caption"),
            "duration_ms": asset.get("duration_ms"),
        }

    memory_outs: Dict[str, dict] = {}
    for row in memories:
        mid = row["id"]
        memory_media = [
            media_out(a)
            for a in media_by_memory.get(mid, [])
            if urls.get(a["storage_key"])
        ]
        transcript_text = None
        for asset in media_by_memory.get(mid, []):
            if asset["kind"] != "photo" and transcripts.get(asset["id"]):
                transcript_text = transcripts[asset["id"]]
                break
        memory_outs[mid] = {
            "id": mid,
            "title": row.get("title"),
            "body_text": row.get("body_text"),
            "transcript": transcript_text,
            "media": memory_media,
            "comments": comments_by_memory.get(mid, []),
            "reactions": mem_reactions.get(mid, ReactionSummary()),
            "comment_reactions": {
                cid: comment_reactions[cid]
                for cid in [c.id for c in _flatten(comments_by_memory.get(mid, []))]
                if cid in comment_reactions
            },
        }

    chapter_ids = {c["id"] for c in chapters}
    book_chapters = []
    for chapter in chapters:
        book_chapters.append(
            {
                "id": chapter["id"],
                "title": chapter["title"],
                "summary": chapter.get("summary"),
                "sort_order": chapter.get("sort_order", 0),
                "memories": [
                    memory_outs[m["id"]]
                    for m in memories
                    if m.get("chapter_id") == chapter["id"]
                ],
            }
        )

    # Memories nobody has filed under a chapter yet still belong in the book.
    unassigned = [
        memory_outs[m["id"]] for m in memories if m.get("chapter_id") not in chapter_ids
    ]
    if unassigned:
        fallback_title = "The Story" if not chapters else "More Memories"
        book_chapters.append(
            {
                "id": None,
                "title": fallback_title,
                "summary": None,
                "sort_order": len(book_chapters),
                "memories": unassigned,
            }
        )

    seen: Set[str] = set()
    library = []
    for mid in memory_ids:
        for item in memory_outs[mid]["media"]:
            if item["id"] not in seen:
                seen.add(item["id"])
                library.append(item)

    return BookOut(
        memoir={
            "id": memoir["id"],
            "subject_name": memoir["subject_name"],
            "subject_born_on": memoir.get("subject_born_on"),
            "subject_died_on": memoir.get("subject_died_on"),
            "subject_is_living": memoir.get("subject_is_living", False),
            "description": memoir.get("description"),
            "published_at": memoir.get("published_at"),
        },
        chapters=book_chapters,
        media_library=library,
        comments_open=memoir.get("comment_policy") == "anyone_who_can_view",
        share_token=share_token,
    )


def get_book_by_token(token: str, reader_name: Optional[str] = None) -> BookOut:
    client = get_supabase()
    link_res = (
        client.table("memoir_link")
        .select("memoir_id, expires_at")
        .eq("token", token)
        .eq("scope", "view")
        .is_("revoked_at", "null")
        .maybe_single()
        .execute()
    )
    link = _safe_data(link_res)
    if not link:
        raise LookupError("This link is not valid any more.")

    expires = link.get("expires_at")
    if expires and datetime.fromisoformat(expires) < datetime.now(timezone.utc):
        raise LookupError("This link has expired.")

    memoir = _published_memoir(UUID(link["memoir_id"]))
    reader_id = (
        _resolve_reader_participant(UUID(memoir["id"]), reader_name, create=False)
        if reader_name
        else None
    )
    return _assemble_book(memoir, reader_id, None)


# src/domain/reader/reader_service.py

def get_public_book_by_memoir(memoir_id: UUID) -> BookOut:
    """Anonymous readers opening /read/<memoirId> land here via the frontend.
    
    Only reachable while the memoir is published. A published memoir is
    immediately public - the view link is created automatically on publish.
    """
    client = get_supabase()
    
    memoir_res = (
        client.table("memoir")
        .select("*")
        .eq("id", str(memoir_id))
        .maybe_single()
        .execute()
    )
    memoir = _safe_data(memoir_res)
    
    if not memoir:
        raise LookupError("This memoir does not exist.")
    
    if memoir.get("status") != "published":
        raise LookupError("This memoir is not published yet.")
    
    link_res = (
        client.table("memoir_link")
        .select("id")
        .eq("memoir_id", str(memoir_id))
        .eq("scope", "view")
        .is_("revoked_at", "null")
        .maybe_single()
        .execute()
    )
    
    if not _safe_data(link_res):
        logger.warning("Published memoir %s missing view link, creating one", memoir_id)
        client.table("memoir_link").insert({
            "memoir_id": str(memoir_id),
            "scope": "view",
        }).execute()
    
    return _assemble_book(memoir, None, None)

def get_book_for_owner(
    memoir_id: UUID, user_id: UUID, reader_name: Optional[str] = None
) -> BookOut:
    participant = _owner_participant(memoir_id, user_id)
    client = get_supabase()
    memoir_res = (
        client.table("memoir").select("*").eq("id", str(memoir_id)).maybe_single().execute()
    )
    memoir = _safe_data(memoir_res)
    if not memoir or memoir.get("status") != "published":
        raise LookupError("This memoir is not published yet.")
    token = _view_link_token(memoir_id, participant["id"])
    reader_id = (
        _resolve_reader_participant(memoir_id, reader_name, create=False)
        if reader_name
        else None
    )
    return _assemble_book(memoir, reader_id, token)


def get_share_link(memoir_id: UUID, user_id: UUID) -> str:
    participant = _owner_participant(memoir_id, user_id)
    _published_memoir(memoir_id)
    return _view_link_token(memoir_id, participant["id"])


def create_comment(memoir_id: UUID, request: CommentCreateRequest) -> CommentNode:
    memoir = _published_memoir(memoir_id)
    if memoir.get("comment_policy") != "anyone_who_can_view":
        raise PermissionError("Comments are closed on this memoir.")

    body = request.body.strip()
    if not body:
        raise ValueError("Comment cannot be blank.")

    client = get_supabase()
    parent = None
    if request.parent_comment_id:
        parent_res = (
            client.table("comment")
            .select("id, memory_id, parent_comment_id")
            .eq("id", str(request.parent_comment_id))
            .eq("memoir_id", str(memoir_id))
            .is_("deleted_at", "null")
            .is_("hidden_at", "null")
            .maybe_single()
            .execute()
        )
        parent = _safe_data(parent_res)
        if not parent:
            raise LookupError("The comment you replied to no longer exists.")
        if parent.get("parent_comment_id"):
            raise ValueError("Replies are one level deep in this memoir.")
        memory_id = parent["memory_id"]
    else:
        memory_res = (
            client.table("memory")
            .select("id")
            .eq("id", str(request.memory_id))
            .eq("memoir_id", str(memoir_id))
            .eq("status", "submitted")
            .is_("deleted_at", "null")
            .maybe_single()
            .execute()
        )
        if not _safe_data(memory_res):
            raise LookupError("Memory not found.")
        memory_id = str(request.memory_id)

    participant_id = _resolve_reader_participant(memoir_id, request.author_name)

    inserted = (
        client.table("comment")
        .insert(
            {
                "memoir_id": str(memoir_id),
                "memory_id": memory_id,
                "parent_comment_id": str(request.parent_comment_id) if parent else None,
                "author_participant_id": participant_id,
                "body": body,
            }
        )
        .execute()
    )
    row = inserted.data[0]
    logger.info("Reader comment %s created on memory %s", row["id"], memory_id)
    return CommentNode(
        id=row["id"],
        author_name=" ".join(request.author_name.split()),
        body=row["body"],
        created_at=row["created_at"],
        replies=[],
        reactions=ReactionSummary(),
    )


def owner_hide_comment(memoir_id: UUID, comment_id: UUID, user_id: UUID) -> None:
    """Owner moderation: the comment and its replies leave the page together."""
    participant = _owner_participant(memoir_id, user_id)
    client = get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {"hidden_at": now_iso, "hidden_by_participant_id": participant["id"]}

    primary = (
        client.table("comment")
        .update(payload)
        .eq("id", str(comment_id))
        .eq("memoir_id", str(memoir_id))
        .is_("hidden_at", "null")
        .execute()
    )
    if not _safe_data(primary):
        raise LookupError("Comment not found.")

    client.table("comment").update(payload).eq("parent_comment_id", str(comment_id)).eq(
        "memoir_id", str(memoir_id)
    ).is_("hidden_at", "null").execute()


def toggle_reaction(memoir_id: UUID, request: ReactionRequest) -> ReactionToggleOut:
    _published_memoir(memoir_id)
    if request.kind not in REACTION_KINDS:
        raise ValueError("Unknown reaction.")

    client = get_supabase()
    stored_kind = request.kind
    if request.target_type == "comment":
        comment_res = (
            client.table("comment")
            .select("id, memory_id")
            .eq("id", str(request.target_id))
            .eq("memoir_id", str(memoir_id))
            .is_("deleted_at", "null")
            .is_("hidden_at", "null")
            .maybe_single()
            .execute()
        )
        comment = _safe_data(comment_res)
        if not comment:
            raise LookupError("Comment not found.")
        if not comment.get("memory_id"):
            raise ValueError("This comment cannot be reacted to.")
        memory_id = comment["memory_id"]
        stored_kind = f"{COMMENT_KIND_PREFIX}{request.target_id}:{request.kind}"
    else:
        memory_res = (
            client.table("memory")
            .select("id")
            .eq("id", str(request.target_id))
            .eq("memoir_id", str(memoir_id))
            .eq("status", "submitted")
            .is_("deleted_at", "null")
            .maybe_single()
            .execute()
        )
        if not _safe_data(memory_res):
            raise LookupError("Memory not found.")
        memory_id = str(request.target_id)

    participant_id = _resolve_reader_participant(memoir_id, request.author_name)

    existing = (
        client.table("reaction")
        .select("id")
        .eq("memory_id", memory_id)
        .eq("participant_id", participant_id)
        .eq("kind", stored_kind)
        .maybe_single()
        .execute()
    )
    if _safe_data(existing):
        client.table("reaction").delete().eq("id", existing.data["id"]).execute()
    else:
        client.table("reaction").insert(
            {
                "memoir_id": str(memoir_id),
                "memory_id": memory_id,
                "participant_id": participant_id,
                "kind": stored_kind,
            }
        ).execute()

    if request.target_type == "comment":
        rows_res = (
            client.table("reaction")
            .select("kind, participant_id")
            .eq("memory_id", memory_id)
            .like("kind", f"{COMMENT_KIND_PREFIX}{request.target_id}:%")
            .execute()
        )
        rows = [
            {**r, "kind": r["kind"].split(":")[-1]} for r in _safe_data(rows_res) or []
        ]
    else:
        rows_res = (
            client.table("reaction")
            .select("kind, participant_id")
            .eq("memory_id", memory_id)
            .not_.like("kind", f"{COMMENT_KIND_PREFIX}%")
            .execute()
        )
        rows = _safe_data(rows_res) or []

    return ReactionToggleOut(
        target_type=request.target_type,
        target_id=request.target_id,
        summary=_summary_from_rows(rows, participant_id),
    )


def _snippet(text: str, query: str) -> str:
    index = text.casefold().find(query.casefold())
    if index < 0:
        return text[:160]
    start = max(0, index - 60)
    end = min(len(text), index + len(query) + 100)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end].strip() + suffix


def search_book(memoir_id: UUID, query: str) -> SearchOut:
    q = query.strip()
    if len(q) < 2:
        return SearchOut(hits=[])
    _published_memoir(memoir_id)
    client = get_supabase()
    pattern = f"%{q}%"

    memory_res = (
        client.table("memory")
        .select("id, chapter_id, title, body_text")
        .eq("memoir_id", str(memoir_id))
        .eq("status", "submitted")
        .is_("deleted_at", "null")
        .or_(f"title.ilike.{pattern},body_text.ilike.{pattern}")
        .limit(20)
        .execute()
    )
    hits: List[SearchHit] = []
    matched_ids = set()
    for row in _safe_data(memory_res) or []:
        matched_ids.add(row["id"])
        text = row.get("body_text") or row.get("title") or ""
        hits.append(
            SearchHit(
                memory_id=row["id"],
                chapter_id=row.get("chapter_id"),
                title=row.get("title"),
                snippet=_snippet(text, q) if text else (row.get("title") or ""),
            )
        )

    transcript_res = (
        client.table("transcript")
        .select("media_asset_id, display_text, media_asset!inner(memory_media(memory_id))")
        .eq("memoir_id", str(memoir_id))
        .ilike("display_text", pattern)
        .limit(20)
        .execute()
    )
    for row in _safe_data(transcript_res) or []:
        media_asset = row.get("media_asset") or {}
        links = media_asset.get("memory_media") or []
        for link in links if isinstance(links, list) else [links]:
            mid = link.get("memory_id") if isinstance(link, dict) else None
            if not mid or mid in matched_ids:
                continue
            matched_ids.add(mid)
            memory_row = (
                client.table("memory")
                .select("id, chapter_id, title")
                .eq("id", mid)
                .maybe_single()
                .execute()
            )
            mrow = _safe_data(memory_row)
            hits.append(
                SearchHit(
                    memory_id=mid,
                    chapter_id=(mrow or {}).get("chapter_id"),
                    title=(mrow or {}).get("title"),
                    snippet=_snippet(row["display_text"], q),
                )
            )
    return SearchOut(hits=hits[:20])