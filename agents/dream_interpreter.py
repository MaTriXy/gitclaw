#!/usr/bin/env python3
"""
Dream Interpreter — Personal journaling with mystical interpretations.
Triggered by /dream command.
"""

import os

from common import (
    MEMORY_DIR, award_xp, call_llm, gh_post_comment,
    log, read_prompt, today, update_stats,
)


def get_dream_history() -> str:
    """Read recent dream entries for pattern tracking."""
    dreams_dir = MEMORY_DIR / "dreams"
    if not dreams_dir.exists():
        return "(No previous dreams recorded. This is the first entry in the dream journal.)"

    entries = []
    for f in sorted(dreams_dir.glob("*.md"))[-3:]:
        first_line = f.read_text().split("\n")[0].lstrip("# ").strip()
        entries.append(f"- {first_line} ({f.name})")

    if not entries:
        return "(No previous dreams recorded.)"

    return "\n".join(entries)


def main():
    description = os.environ.get("DREAM_DESCRIPTION", "I had a dream about code.")
    issue_number = int(os.environ.get("ISSUE_NUMBER", "0"))
    dreamer = os.environ.get("DREAMER", "anonymous")

    log("Dream Interpreter", f"Interpreting dream from @{dreamer}")

    history = get_dream_history()
    system_prompt = read_prompt("dream-interpreter")

    user_message = f"""Dream to interpret:
{description}

Dreamer: @{dreamer}
Date: {today()}

Previous dreams for pattern tracking:
{history}

Interpret this dream now. Be creative, warm, and insightful."""

    try:
        response = call_llm(system_prompt, user_message, max_tokens=1200)
    except Exception as e:
        log("Dream Interpreter", f"LLM call failed: {e}")
        response = f"""## 🌙 Dream Log

*The Dream Interpreter's crystal ball is foggy tonight (API error).*

Your dream has been noted. The interpretation will come when the stars align.

> {description[:200]}...

— 🌙 *The Dream Interpreter fades into the mist.*"""

    # Post to issue
    if issue_number > 0:
        gh_post_comment(issue_number, response)

    # Archive dream
    dream_file = MEMORY_DIR / "dreams" / f"{today()}.md"
    dream_file.parent.mkdir(parents=True, exist_ok=True)

    # Append if multiple dreams in one day
    with open(dream_file, "a") as f:
        f.write(f"\n---\n\n**Dreamer:** @{dreamer}\n\n{response}\n")

    update_stats("dreams_interpreted")
    award_xp(5)

    print(response)


if __name__ == "__main__":
    main()
