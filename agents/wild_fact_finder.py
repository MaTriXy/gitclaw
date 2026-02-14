#!/usr/bin/env python3
"""
Wild Fact Finder — Research agent with entertaining tangents.
Triggered by /research command.
"""

import os
from datetime import datetime, timezone

from common import (
    MEMORY_DIR, append_memory, award_xp, call_llm,
    gh_post_comment, log, read_prompt, today, update_stats,
)


def main():
    topic = os.environ.get("RESEARCH_TOPIC", "the meaning of life")
    issue_number = int(os.environ.get("ISSUE_NUMBER", "0"))
    requester = os.environ.get("REQUESTER", "anonymous")

    log("Wild Fact Finder", f"Researching: {topic}")

    system_prompt = read_prompt("wild-fact-finder")

    user_message = f"""Research topic: {topic}

Requested by: @{requester}
Date: {today()}

Provide a thorough, entertaining research brief. Include:
1. Key findings with confidence levels
2. A wild card / plot twist fact
3. A fun tangent / rabbit hole
4. A tech/programming connection
5. A TL;DR that's both informative and funny"""

    try:
        response = call_llm(system_prompt, user_message, max_tokens=1500)
    except Exception as e:
        log("Wild Fact Finder", f"LLM call failed: {e}")
        response = f"""## 🔍 Research: {topic}

My research library is temporarily offline (API error), but here's what I know:

This topic deserves a deep dive. Try again in a bit, and I'll have a full brief ready.

**TL;DR:** The truth is out there. Just not right now.

— 🔍 *The Wild Fact Finder will return.*"""

    # Post to issue if provided
    if issue_number > 0:
        gh_post_comment(issue_number, response)

    # Archive
    slug = topic.lower().replace(" ", "-")[:50]
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    archive_path = MEMORY_DIR / "research" / f"{today()}-{slug}.md"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(
        f"# Research: {topic}\n"
        f"_Researched on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_\n"
        f"_Requested by: @{requester}_\n\n"
        f"{response}\n"
    )

    update_stats("researches_completed")
    award_xp(15)

    print(response)


if __name__ == "__main__":
    main()
