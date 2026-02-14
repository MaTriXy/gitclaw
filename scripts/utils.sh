#!/usr/bin/env bash
# ============================================================================
# utils.sh — GitClaw's shared utility belt
# Logging, date helpers, and common functions used across all scripts.
# ============================================================================

# Colors (disabled in CI if NO_COLOR is set)
if [[ -z "${NO_COLOR:-}" ]]; then
  RED='\033[0;31m'
  GREEN='\033[0;32m'
  YELLOW='\033[0;33m'
  BLUE='\033[0;34m'
  PURPLE='\033[0;35m'
  CYAN='\033[0;36m'
  NC='\033[0m'
else
  RED='' GREEN='' YELLOW='' BLUE='' PURPLE='' CYAN='' NC=''
fi

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_info()  { echo -e "${GREEN}[GitClaw]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[GitClaw ⚠]${NC} $*"; }
log_error() { echo -e "${RED}[GitClaw ✗]${NC} $*" >&2; }
log_debug() { [[ "${GITCLAW_DEBUG:-0}" == "1" ]] && echo -e "${CYAN}[GitClaw 🔍]${NC} $*"; }
log_agent() { echo -e "${PURPLE}[🤖 $1]${NC} ${*:2}"; }

# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------
today()     { date -u +"%Y-%m-%d"; }
now_utc()   { date -u +"%Y-%m-%d %H:%M:%S UTC"; }
timestamp() { date -u +"%Y%m%d_%H%M%S"; }

# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------
# Safe jq that returns empty string instead of null
jq_safe() { jq -r "$1 // empty" "${@:2}"; }

# Read a key from state.json
read_state() {
  local key="${1:?Usage: read_state <key>}"
  local state_file="${REPO_ROOT:-$(git rev-parse --show-toplevel)}/memory/state.json"
  if [[ -f "$state_file" ]]; then
    jq -r ".$key // empty" "$state_file"
  fi
}

# ---------------------------------------------------------------------------
# String helpers
# ---------------------------------------------------------------------------
# Truncate string to max length, adding ... if truncated
truncate() {
  local str="$1" max="${2:-500}"
  if [[ ${#str} -gt $max ]]; then
    echo "${str:0:$((max-3))}..."
  else
    echo "$str"
  fi
}

# Escape string for JSON embedding
json_escape() {
  python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))" <<< "$1"
}

# ---------------------------------------------------------------------------
# XP and leveling system
# ---------------------------------------------------------------------------
XP_LEVELS=(
  "0:Unawakened"
  "50:Novice"
  "150:Apprentice"
  "300:Journeyman"
  "500:Adept"
  "800:Expert"
  "1200:Master"
  "1800:Grandmaster"
  "2500:Legend"
  "5000:Mythic"
  "10000:Transcendent"
)

# Get level name for a given XP amount
get_level() {
  local xp="${1:-0}"
  local level="Unawakened"
  for entry in "${XP_LEVELS[@]}"; do
    local threshold="${entry%%:*}"
    local name="${entry#*:}"
    if [[ $xp -ge $threshold ]]; then
      level="$name"
    fi
  done
  echo "$level"
}

# Get XP needed for next level
xp_to_next_level() {
  local xp="${1:-0}"
  for entry in "${XP_LEVELS[@]}"; do
    local threshold="${entry%%:*}"
    if [[ $threshold -gt $xp ]]; then
      echo "$((threshold - xp))"
      return
    fi
  done
  echo "0" # Already max level
}

# Format XP bar (visual progress indicator)
xp_bar() {
  local xp="${1:-0}"
  local current_threshold=0
  local next_threshold=50

  for entry in "${XP_LEVELS[@]}"; do
    local threshold="${entry%%:*}"
    if [[ $threshold -le $xp ]]; then
      current_threshold=$threshold
    else
      next_threshold=$threshold
      break
    fi
  done

  local range=$((next_threshold - current_threshold))
  local progress=$((xp - current_threshold))
  local pct=0
  if [[ $range -gt 0 ]]; then
    pct=$((progress * 10 / range))
  fi

  local bar=""
  for i in $(seq 1 10); do
    if [[ $i -le $pct ]]; then
      bar="${bar}█"
    else
      bar="${bar}░"
    fi
  done

  echo "$bar $xp XP"
}

# ---------------------------------------------------------------------------
# Personality helpers
# ---------------------------------------------------------------------------
# Pick a random item from a list
random_pick() {
  local items=("$@")
  local count=${#items[@]}
  echo "${items[$((RANDOM % count))]}"
}

# Generate a fun greeting based on time of day
time_greeting() {
  local hour
  hour=$(date -u +"%H")
  if [[ $hour -lt 6 ]]; then
    random_pick "🦉 Burning the midnight oil?" "🌙 The code never sleeps..." "👻 Who's coding at this hour?"
  elif [[ $hour -lt 12 ]]; then
    random_pick "☕ Good morning, code warrior!" "🌅 Rise and debug!" "🍳 Fresh commits for breakfast?"
  elif [[ $hour -lt 18 ]]; then
    random_pick "☀️ Afternoon hacking session!" "🏗️ Building empires, one commit at a time" "💪 Peak productivity hours!"
  else
    random_pick "🌆 Evening code review vibes" "🍕 Late-night pizza-driven development" "🎯 One more feature before bed?"
  fi
}
