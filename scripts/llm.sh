#!/usr/bin/env bash
# ============================================================================
# llm.sh — GitClaw's brain interface
# Wraps LLM API calls (Anthropic Claude / OpenAI) into a single function.
# All agents funnel through here. No direct curl calls elsewhere.
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/utils.sh"

# ---------------------------------------------------------------------------
# call_llm <provider> <model> <system_prompt> <user_message> [max_tokens]
#
#   provider:      "anthropic" | "openai"
#   model:         e.g. "claude-haiku-4-5-20251001" or "gpt-4o"
#   system_prompt: system-level instructions (can be a file path or string)
#   user_message:  the actual prompt
#   max_tokens:    optional, default 2048
#
# Requires secrets: ANTHROPIC_API_KEY or OPENAI_API_KEY
# Returns: raw text content from the model
# ---------------------------------------------------------------------------
call_llm() {
  local provider="${1:?Usage: call_llm <provider> <model> <system_prompt> <user_message> [max_tokens]}"
  local model="${2:?}"
  local system_prompt="${3:?}"
  local user_message="${4:?}"
  local max_tokens="${5:-2048}"

  # If system_prompt is a file path, read it
  if [[ -f "$system_prompt" ]]; then
    system_prompt="$(cat "$system_prompt")"
  fi

  case "$provider" in
    anthropic)
      _call_anthropic "$model" "$system_prompt" "$user_message" "$max_tokens"
      ;;
    openai)
      _call_openai "$model" "$system_prompt" "$user_message" "$max_tokens"
      ;;
    *)
      log_error "Unknown provider: $provider"
      exit 1
      ;;
  esac
}

# ---------------------------------------------------------------------------
# Anthropic Claude API
# ---------------------------------------------------------------------------
_call_anthropic() {
  local model="$1" system="$2" message="$3" max_tokens="$4"

  if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    log_error "ANTHROPIC_API_KEY not set. Add it to your repo secrets."
    exit 1
  fi

  local payload
  payload=$(jq -n \
    --arg model "$model" \
    --arg system "$system" \
    --arg message "$message" \
    --argjson max_tokens "$max_tokens" \
    '{
      model: $model,
      max_tokens: $max_tokens,
      system: $system,
      messages: [{ role: "user", content: $message }]
    }')

  local response
  response=$(curl -sS --fail-with-body \
    https://api.anthropic.com/v1/messages \
    -H "Content-Type: application/json" \
    -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H "anthropic-version: 2023-06-01" \
    -d "$payload" 2>&1) || {
      log_error "Anthropic API call failed: $response"
      exit 1
    }

  # Extract text content from response
  echo "$response" | jq -r '.content[0].text // empty'
}

# ---------------------------------------------------------------------------
# OpenAI API
# ---------------------------------------------------------------------------
_call_openai() {
  local model="$1" system="$2" message="$3" max_tokens="$4"

  if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    log_error "OPENAI_API_KEY not set. Add it to your repo secrets."
    exit 1
  fi

  local payload
  payload=$(jq -n \
    --arg model "$model" \
    --arg system "$system" \
    --arg message "$message" \
    --argjson max_tokens "$max_tokens" \
    '{
      model: $model,
      max_tokens: $max_tokens,
      messages: [
        { role: "system", content: $system },
        { role: "user", content: $message }
      ]
    }')

  local response
  response=$(curl -sS --fail-with-body \
    https://api.openai.com/v1/chat/completions \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $OPENAI_API_KEY" \
    -d "$payload" 2>&1) || {
      log_error "OpenAI API call failed: $response"
      exit 1
    }

  echo "$response" | jq -r '.choices[0].message.content // empty'
}

# ---------------------------------------------------------------------------
# call_llm_with_context <provider> <model> <prompt_file> <context_json>
#
# Higher-level wrapper: reads a prompt template, injects context variables,
# and calls the LLM. Context is a JSON object whose keys become {{KEY}}
# replacements in the prompt template.
# ---------------------------------------------------------------------------
call_llm_with_context() {
  local provider="$1" model="$2" prompt_file="$3" context_json="$4"
  local max_tokens="${5:-2048}"

  if [[ ! -f "$prompt_file" ]]; then
    log_error "Prompt file not found: $prompt_file"
    exit 1
  fi

  local system_prompt
  system_prompt="$(cat "$prompt_file")"

  # Replace {{KEY}} placeholders with values from context JSON
  local keys
  keys=$(echo "$context_json" | jq -r 'keys[]')
  for key in $keys; do
    local value
    value=$(echo "$context_json" | jq -r --arg k "$key" '.[$k] // ""')
    system_prompt="${system_prompt//\{\{$key\}\}/$value}"
  done

  # The context itself becomes the user message
  local user_message
  user_message=$(echo "$context_json" | jq -r '.user_message // "Execute your task."')

  call_llm "$provider" "$model" "$system_prompt" "$user_message" "$max_tokens"
}

# Allow sourcing or direct execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  call_llm "$@"
fi
