"""
@file memory_input.py
@description Shared helpers that turn raw memory rows into the normalised
MemoryInputItem shape used in AI prompts (organising, personality, rewriting).
"""

from typing import List, Optional

from src.schemas.chapter import MemoryInputItem

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def date_label(row: dict) -> Optional[str]:
    """Builds a human-friendly date label from occurred_* and precision."""
    start = row.get("occurred_start")
    if not start:
        return None

    date_str = str(start)
    year = date_str[:4]
    precision = row.get("occurred_precision") or "day"

    if precision == "year":
        return year
    if precision == "decade":
        return f"{year[:3]}0s"
    if precision == "month" and len(date_str) >= 7:
        month_index = int(date_str[5:7]) - 1
        return f"{_MONTH_NAMES[month_index]} {year}"
    return date_str


def normalize_memories(rows: List[dict]) -> List[MemoryInputItem]:
    """Transforms raw memory rows into the normalised prompt shape."""
    items = []
    for row in rows:
        items.append(
            MemoryInputItem(
                id=row["id"],
                title=row.get("title"),
                content=row.get("body_text"),
                date_label=date_label(row),
            )
        )
    return items
