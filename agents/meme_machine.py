#!/usr/bin/env python3
"""
Meme Machine — Content generation powerhouse.
Triggered via workflow_dispatch.
"""

import os
from datetime import datetime, timezone

from common import (
    MEMORY_DIR, award_xp, call_llm, log, read_prompt, today, update_stats,
)


def main():
    content_type = os.environ.get("CONTENT_TYPE", "tweet_thread")
    topic = os.environ.get("TOPIC", "programming")
    tone = os.environ.get("TONE", "funny")
    platform = os.environ.get("PLATFORM", "twitter")

    log("Meme Machine", f"Generating {content_type} about {topic}")

    system_prompt = read_prompt("meme-machine")

    user_message = f"""Generate content:
- Type: {content_type}
- Topic: {topic}
- Tone: {tone}
- Platform: {platform}

Create genuinely good content that someone would actually want to post.
Make it punchy, engaging, and optimized for the target platform."""

    try:
        response = call_llm(system_prompt, user_message, max_tokens=2000)
    except Exception as e:
        log("Meme Machine", f"LLM call failed: {e}")
        response = f"""## 🎨 Content Generation Failed

The Meme Machine encountered an error: {e}

**Topic:** {topic}
**Type:** {content_type}

Try again — the machine needs a reboot.

— 🎨 *The Meme Machine will return.*"""

    # Save content
    slug = topic.lower().replace(" ", "-")[:50]
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")

    content_dir = MEMORY_DIR / "content"
    content_dir.mkdir(parents=True, exist_ok=True)
    content_file = content_dir / f"{timestamp}-{slug}.md"

    content_file.write_text(
        f"# 🎨 Content: {topic}\n"
        f"_Generated on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_\n"
        f"_Type: {content_type} | Tone: {tone} | Platform: {platform}_\n\n"
        f"---\n\n{response}\n"
    )

    update_stats("comments_posted")
    award_xp(15)

    print(response)


if __name__ == "__main__":
    main()
