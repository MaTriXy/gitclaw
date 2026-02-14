#!/usr/bin/env python3
"""
Quest Master — Gamifies GitHub issues into RPG quests.
Run by the quest-master.yml workflow on new issue events.
"""

import json
import os
import re
import sys

from common import (
    award_xp, call_llm, gh_add_labels, gh_post_comment,
    load_state, log, read_prompt, save_state, update_stats,
)

DIFFICULTY_XP = {
    "easy": 10,
    "medium": 25,
    "hard": 50,
    "legendary": 100,
}


def classify_issue(title: str, body: str) -> dict:
    """Quick heuristic classification before LLM call."""
    text = f"{title} {body}".lower()

    if any(w in text for w in ["bug", "error", "crash", "fix", "broken"]):
        quest_type = "Bug Slaying 🐛"
        base_difficulty = "medium"
    elif any(w in text for w in ["feature", "add", "implement", "new"]):
        quest_type = "Artifact Forging ✨"
        base_difficulty = "hard"
    elif any(w in text for w in ["doc", "readme", "comment", "typo"]):
        quest_type = "Scroll Writing 📜"
        base_difficulty = "easy"
    elif any(w in text for w in ["perf", "slow", "optimize", "speed"]):
        quest_type = "Performance Enchantment ⚡"
        base_difficulty = "hard"
    elif any(w in text for w in ["refactor", "clean", "restructure"]):
        quest_type = "Refactoring Ritual 🔮"
        base_difficulty = "medium"
    else:
        quest_type = "Mystery Quest 🎲"
        base_difficulty = "medium"

    return {"quest_type": quest_type, "difficulty": base_difficulty}


def main():
    issue_number = int(os.environ.get("ISSUE_NUMBER", "0"))
    issue_title = os.environ.get("ISSUE_TITLE", "Untitled Quest")
    issue_body = os.environ.get("ISSUE_BODY", "No description provided.")

    log("Quest Master", f"New quest detected: #{issue_number} — {issue_title}")

    # Quick classification
    classification = classify_issue(issue_title, issue_body)

    # Load state for context
    state = load_state()

    # Build LLM prompt
    system_prompt = read_prompt("quest-master")
    user_message = f"""New issue opened! Transform it into a quest:

Issue #{issue_number}: {issue_title}

Description:
{issue_body}

Pre-classification hint: {classification['quest_type']} / {classification['difficulty']}

Agent XP: {state.get('xp', 0)} | Level: {state.get('level', 'Unawakened')}
Quests completed so far: {state.get('stats', {}).get('quests_completed', 0)}

Generate the Quest Posting now. At the very end, output a JSON line:
{{"difficulty": "<easy|medium|hard|legendary>", "xp": <number>}}"""

    try:
        response = call_llm(system_prompt, user_message, max_tokens=1500)
    except Exception as e:
        log("Quest Master", f"LLM call failed: {e}")
        # Fallback to template-based response
        xp = DIFFICULTY_XP[classification["difficulty"]]
        response = f"""⚔️━━━━━━━━━━━━━━━━━━⚔️

## Quest Posted: {issue_title}

**Type:** {classification["quest_type"]}
**Difficulty:** {classification["difficulty"].title()} ({xp} XP)

A new quest has appeared on the board! Brave adventurer, will you answer the call?

⚔️━━━━━━━━━━━━━━━━━━⚔️

— ⚔️ *The Quest Master has spoken. May your code compile true.*"""
        difficulty = classification["difficulty"]
        gh_post_comment(issue_number, response)
        gh_add_labels(issue_number, [f"quest:new", f"xp:{xp}"])
        update_stats("issues_triaged")
        award_xp(5)
        return

    # Parse difficulty from response
    lines = response.strip().split("\n")
    difficulty = classification["difficulty"]
    xp = DIFFICULTY_XP.get(difficulty, 25)

    # Try to extract JSON metadata from last line
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                meta = json.loads(line)
                difficulty = meta.get("difficulty", difficulty)
                xp = meta.get("xp", DIFFICULTY_XP.get(difficulty, 25))
                # Remove the JSON line from the response
                response = "\n".join(l for l in lines if l.strip() != line)
                break
            except json.JSONDecodeError:
                pass

    # Post the quest
    gh_post_comment(issue_number, response)

    # Add labels
    gh_add_labels(issue_number, [f"quest:new", f"xp:{xp}"])

    # Update stats
    update_stats("issues_triaged")
    award_xp(5)

    log("Quest Master", f"Quest posted! Difficulty: {difficulty}, XP reward: {xp}")


if __name__ == "__main__":
    main()
