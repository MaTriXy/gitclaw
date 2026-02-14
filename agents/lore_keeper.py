#!/usr/bin/env python3
"""
Lore Keeper — Chronicles repo knowledge with dramatic narrative.
Triggered by /lore command.
"""

import os
from pathlib import Path

from common import (
    MEMORY_DIR, award_xp, call_llm, gh_post_comment,
    log, read_prompt, today, update_stats,
)


def gather_existing_lore() -> str:
    """Read existing lore entries for narrative continuity."""
    lore_dir = MEMORY_DIR / "lore"
    if not lore_dir.exists():
        return "(The chronicles are empty. This shall be the first entry.)"

    entries = []
    for f in sorted(lore_dir.glob("*.md"))[-5:]:
        first_line = f.read_text().split("\n")[0].lstrip("# ").strip()
        entries.append(f"- {first_line} ({f.name})")

    if not entries:
        return "(The chronicles are empty. This shall be the first entry.)"

    return "\n".join(entries)


def main():
    topic = os.environ.get("LORE_TOPIC", "the beginning")
    issue_number = int(os.environ.get("ISSUE_NUMBER", "0"))

    log("Lore Keeper", f"Chronicling: {topic}")

    existing_lore = gather_existing_lore()
    system_prompt = read_prompt("lore-keeper")

    user_message = f"""Chronicle this topic: {topic}

Existing lore entries for continuity:
{existing_lore}

Date of inscription: {today()}

Create a lore entry worthy of the chronicles. Write it as if documenting
an epic saga — dramatic, but grounded in real technical/project knowledge."""

    try:
        response = call_llm(system_prompt, user_message, max_tokens=1500)
    except Exception as e:
        log("Lore Keeper", f"LLM call failed: {e}")
        response = f"""## 📜 The Chronicles — {topic}

*The Lore Keeper's quill has run dry (API error).*

The tale of "{topic}" shall be told another day. The scrolls await.

— 📜 *The Lore Keeper watches eternal.*"""

    # Post to issue
    if issue_number > 0:
        gh_post_comment(issue_number, response)

    # Archive as lore file
    slug = topic.lower().replace(" ", "-")[:50]
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    lore_file = MEMORY_DIR / "lore" / f"{today()}-{slug}.md"
    lore_file.parent.mkdir(parents=True, exist_ok=True)
    lore_file.write_text(response + "\n")

    update_stats("lore_entries")
    award_xp(10)

    print(response)


if __name__ == "__main__":
    main()
