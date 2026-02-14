#!/usr/bin/env python3
"""
Morning Roast — Daily briefing with coffee-fueled sarcasm.
Run by the morning-roast.yml workflow on schedule.
"""

import json
import os
import subprocess
from datetime import datetime, timezone

from common import (
    award_xp, call_llm, gh_post_comment, load_state,
    log, read_prompt, today, update_stats, xp_bar,
)


def get_open_issues() -> list[dict]:
    """Fetch open issues via gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--state", "open",
             "--json", "number,title,labels,createdAt", "--limit", "20"],
            capture_output=True, text=True, check=True,
        )
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return []


def get_open_prs() -> list[dict]:
    """Fetch open PRs via gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--state", "open",
             "--json", "number,title,createdAt", "--limit", "10"],
            capture_output=True, text=True, check=True,
        )
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return []


def build_context() -> str:
    """Build the context string for the morning roast."""
    state = load_state()
    issues = get_open_issues()
    prs = get_open_prs()

    now = datetime.now(timezone.utc)
    day_of_week = now.strftime("%A")
    date_str = now.strftime("%B %d, %Y")

    xp = state.get("xp", 0)
    level = state.get("level", "Unawakened")
    streak = state.get("streak", {}).get("current", 0)
    stats = state.get("stats", {})

    context = f"""Date: {date_str} ({day_of_week})

Open Issues ({len(issues)}):
"""
    for issue in issues[:10]:
        labels = ", ".join(l.get("name", "") for l in issue.get("labels", []))
        context += f"  - #{issue['number']}: {issue['title']}"
        if labels:
            context += f" [{labels}]"
        context += "\n"

    if not issues:
        context += "  (None — a suspiciously clean board)\n"

    context += f"""
Open PRs ({len(prs)}):
"""
    for pr in prs[:5]:
        context += f"  - PR #{pr['number']}: {pr['title']}\n"

    if not prs:
        context += "  (None — the PR queue is empty. Suspicious.)\n"

    context += f"""
Agent Status:
  XP: {xp_bar(xp)}
  Level: {level}
  Streak: {streak} days
  Issues triaged: {stats.get('issues_triaged', 0)}
  PRs reviewed: {stats.get('prs_reviewed', 0)}
  Roasts delivered: {stats.get('roasts_delivered', 0)}

Generate the Morning Roast briefing now. Make it punchy and caffeinated."""

    return context


def main():
    log("Morning Roast", "Brewing today's roast...")

    system_prompt = read_prompt("morning-roast")
    context = build_context()

    try:
        response = call_llm(system_prompt, context, max_tokens=1500)
    except Exception as e:
        log("Morning Roast", f"LLM call failed: {e}")
        response = f"""## ☕ Morning Roast — {today()}

The coffee machine is broken today (LLM API error), but here's what I can tell you:

**Open Issues:** Check your issue tracker.
**Vibe:** Uncertain, like a Monday.

*The roast will return tomorrow, stronger and more caffeinated.*

— ☕ *Your Morning Roast, served lukewarm by GitClaw*"""

    # Update stats
    update_stats("comments_posted")
    award_xp(5)

    # Output the response for the workflow to use
    print(response)


if __name__ == "__main__":
    main()
