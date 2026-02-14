#!/usr/bin/env python3
"""
Fortune Cookie — Daily coding wisdom and motivational nonsense.
Run by fortune-cookie.yml on schedule.
"""

import os
from datetime import datetime, timezone

from common import (
    MEMORY_DIR, award_xp, call_llm, load_state,
    log, read_prompt, today, update_stats, xp_bar,
)


def get_recent_fortunes() -> str:
    """Get recent fortunes to avoid repetition."""
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    fortune_file = MEMORY_DIR / "fortunes" / f"{month}.md"

    if not fortune_file.exists():
        return "(No fortunes yet this month. A blank slate.)"

    lines = fortune_file.read_text().split("\n")
    # Return last 20 lines
    recent = "\n".join(lines[-20:])
    return recent or "(No recent fortunes.)"


def main():
    log("Fortune Cookie", "Cracking open today's cookie...")

    state = load_state()
    recent = get_recent_fortunes()
    system_prompt = read_prompt("fortune-cookie")

    now = datetime.now(timezone.utc)

    user_message = f"""Date: {now.strftime('%B %d, %Y')}
Day of week: {now.strftime('%A')}

Agent XP: {xp_bar(state.get('xp', 0))}
Level: {state.get('level', 'Unawakened')}
Streak: {state.get('streak', {}).get('current', 0)} days

Recent fortunes (avoid repeating themes):
{recent}

Generate today's fortune cookie. Make it original and memorable."""

    try:
        response = call_llm(
            system_prompt, user_message,
            model="claude-haiku-4-5-20251001",  # Fortunes use cheaper model
            max_tokens=800,
        )
    except Exception as e:
        log("Fortune Cookie", f"LLM call failed: {e}")
        # Fallback fortunes
        import random
        fallbacks = [
            "Today's fortune: The semicolon you forgot is in the last place you'll look.",
            "Today's fortune: A refactor saved is a refactor earned.",
            "Today's fortune: Trust the compiler. But verify.",
            "Today's fortune: The best time to write tests was yesterday. The second best time is now.",
        ]
        response = random.choice(fallbacks) + "\n\n— 🔮 *Your fortune has been sealed.*"

    # Archive fortune
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    fortune_dir = MEMORY_DIR / "fortunes"
    fortune_dir.mkdir(parents=True, exist_ok=True)
    fortune_file = fortune_dir / f"{month}.md"

    with open(fortune_file, "a") as f:
        f.write(f"\n---\n### {today()}\n\n{response}\n")

    update_stats("fortunes_dispensed")
    award_xp(2)

    print(response)


if __name__ == "__main__":
    main()
