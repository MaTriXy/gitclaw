#!/usr/bin/env python3
"""
Code Jester — PR review with theatrical commentary.
Run by the code-jester.yml workflow on pull_request events.
"""

import json
import os
import subprocess

from common import (
    award_xp, call_llm, log, read_prompt, update_stats,
)


def get_pr_diff(pr_number: int) -> str:
    """Get PR diff, truncated for token limits."""
    try:
        result = subprocess.run(
            ["gh", "pr", "diff", str(pr_number)],
            capture_output=True, text=True, check=True,
        )
        diff = result.stdout
        # Truncate to ~3000 chars to stay within token budget
        if len(diff) > 3000:
            diff = diff[:3000] + "\n\n... [diff truncated for brevity] ..."
        return diff
    except subprocess.CalledProcessError:
        return "(Could not fetch diff)"


def get_pr_files(pr_number: int) -> list[str]:
    """Get list of changed files."""
    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr_number),
             "--json", "files", "--jq", ".files[].path"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip().split("\n")[:20]
    except subprocess.CalledProcessError:
        return []


def analyze_diff_stats(diff: str) -> dict:
    """Quick heuristic analysis of the diff."""
    additions = diff.count("\n+") - diff.count("\n+++")
    deletions = diff.count("\n-") - diff.count("\n---")

    stats = {
        "additions": max(additions, 0),
        "deletions": max(deletions, 0),
        "net": max(additions, 0) - max(deletions, 0),
        "size": "small",
    }

    total = stats["additions"] + stats["deletions"]
    if total > 500:
        stats["size"] = "massive"
    elif total > 200:
        stats["size"] = "large"
    elif total > 50:
        stats["size"] = "medium"

    return stats


def main():
    pr_number = int(os.environ.get("PR_NUMBER", "0"))
    pr_title = os.environ.get("PR_TITLE", "Untitled PR")
    pr_body = os.environ.get("PR_BODY", "")

    log("Code Jester", f"Reviewing PR #{pr_number}: {pr_title}")

    diff = get_pr_diff(pr_number)
    files = get_pr_files(pr_number)
    stats = analyze_diff_stats(diff)

    system_prompt = read_prompt("code-jester")

    user_message = f"""Review this PR:

PR #{pr_number}: {pr_title}

Description:
{pr_body or "(No description provided — a bold move.)"}

Changed files ({len(files)}):
{chr(10).join(f"  - {f}" for f in files)}

Diff stats: +{stats['additions']} / -{stats['deletions']} (net: {stats['net']:+d}, size: {stats['size']})

Diff:
{diff}

Deliver your Jester's Review now."""

    try:
        response = call_llm(system_prompt, user_message, max_tokens=2000)
    except Exception as e:
        log("Code Jester", f"LLM call failed: {e}")
        response = f"""## 🃏 The Jester's Quick Take

*adjusts monocle*

I tried to review this PR but my crystal ball is cloudy today (API error).

What I can see:
- **{len(files)} files** changed
- **+{stats['additions']} / -{stats['deletions']}** lines
- Size: **{stats['size']}**

I shall return with a proper review when the stars align.

— 🃏 *The Jester rests. Temporarily.*"""

    update_stats("prs_reviewed")
    award_xp(25)

    print(response)


if __name__ == "__main__":
    main()
