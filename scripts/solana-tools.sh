#!/usr/bin/env bash
# ============================================================================
# solana-tools.sh — GitClaw's Solana plugin toolkit
# Wraps Dexscreener, Jupiter v6, and Solana RPC into reusable functions.
# This is a MODULAR PLUGIN — only loaded when Solana features are enabled.
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/utils.sh"

# ── Configuration ────────────────────────────────────────────────────────────

SOLANA_NETWORK="${SOLANA_NETWORK:-mainnet-beta}"

# RPC endpoints
SOLANA_RPC_MAINNET="https://api.mainnet-beta.solana.com"
SOLANA_RPC_DEVNET="https://api.devnet.solana.com"

# Pick RPC based on network setting
if [[ "$SOLANA_NETWORK" == "devnet" ]]; then
  SOLANA_RPC="$SOLANA_RPC_DEVNET"
else
  SOLANA_RPC="$SOLANA_RPC_MAINNET"
fi

# Use custom RPC if provided (e.g., Helius, Alchemy)
SOLANA_RPC="${SOLANA_RPC_URL:-$SOLANA_RPC}"

# API endpoints
DEXSCREENER_API="https://api.dexscreener.com"
JUPITER_API="https://quote-api.jup.ag/v6"

# ── Dexscreener API ─────────────────────────────────────────────────────────

# dex_get_pair <chain_id> <pair_address>
# Returns pair data: price, volume, liquidity, etc.
dex_get_pair() {
  local chain_id="${1:-solana}"
  local pair_address="${2:?Usage: dex_get_pair <chain_id> <pair_address>}"

  curl -sS --fail-with-body \
    "$DEXSCREENER_API/latest/dex/pairs/$chain_id/$pair_address" \
    2>/dev/null || echo '{"error": "Dexscreener API call failed"}'
}

# dex_search <query>
# Search for tokens/pairs by name, symbol, or address.
dex_search() {
  local query="${1:?Usage: dex_search <query>}"

  curl -sS --fail-with-body \
    "$DEXSCREENER_API/latest/dex/search?q=$(jq -rn --arg q "$query" '$q | @uri')" \
    2>/dev/null || echo '{"error": "Dexscreener search failed"}'
}

# dex_get_token_pairs <chain_id> <token_address>
# Returns all pairs for a given token.
dex_get_token_pairs() {
  local chain_id="${1:-solana}"
  local token_address="${2:?Usage: dex_get_token_pairs <chain_id> <token_address>}"

  curl -sS --fail-with-body \
    "$DEXSCREENER_API/token-pairs/v1/$chain_id/$token_address" \
    2>/dev/null || echo '{"error": "Dexscreener token pairs call failed"}'
}

# dex_format_pair <pair_json>
# Formats raw pair JSON into a readable summary.
dex_format_pair() {
  local pair_json="$1"

  echo "$pair_json" | jq -r '
    .pair // .pairs[0] // . |
    "Token: \(.baseToken.name // "Unknown") (\(.baseToken.symbol // "???"))\n" +
    "Price: $\(.priceUsd // "N/A")\n" +
    "24h Change: \(.priceChange.h24 // "N/A")%\n" +
    "24h Volume: $\(.volume.h24 // "N/A")\n" +
    "Liquidity: $\(.liquidity.usd // "N/A")\n" +
    "DEX: \(.dexId // "Unknown")\n" +
    "Pair: \(.pairAddress // "N/A")"
  ' 2>/dev/null || echo "Failed to parse pair data"
}

# ── Jupiter Aggregator v6 ───────────────────────────────────────────────────

# jupiter_quote <input_mint> <output_mint> <amount_lamports> [slippage_bps]
# Gets a swap quote from Jupiter.
jupiter_quote() {
  local input_mint="${1:?Usage: jupiter_quote <input_mint> <output_mint> <amount> [slippage_bps]}"
  local output_mint="${2:?}"
  local amount="${3:?}"
  local slippage="${4:-50}"  # Default 0.5% slippage

  curl -sS --fail-with-body \
    "$JUPITER_API/quote?inputMint=$input_mint&outputMint=$output_mint&amount=$amount&slippageBps=$slippage" \
    2>/dev/null || echo '{"error": "Jupiter quote failed"}'
}

# jupiter_format_quote <quote_json>
# Formats a Jupiter quote into readable output.
jupiter_format_quote() {
  local quote_json="$1"

  echo "$quote_json" | jq -r '
    "Input: \(.inputMint // "?")\n" +
    "Output: \(.outputMint // "?")\n" +
    "In Amount: \(.inAmount // "?")\n" +
    "Out Amount: \(.outAmount // "?")\n" +
    "Price Impact: \(.priceImpactPct // "?")%\n" +
    "Route: \((.routePlan // []) | length) hops\n" +
    "Slippage: \(.slippageBps // "?") bps"
  ' 2>/dev/null || echo "Failed to parse quote"
}

# ── Solana RPC ──────────────────────────────────────────────────────────────

# Internal helper: make a JSON-RPC call
_solana_rpc() {
  local method="$1"
  local params="$2"

  local payload
  payload=$(jq -n \
    --arg method "$method" \
    --argjson params "$params" \
    '{jsonrpc: "2.0", id: 1, method: $method, params: $params}')

  curl -sS --fail-with-body \
    -X POST \
    -H "Content-Type: application/json" \
    "$SOLANA_RPC" \
    -d "$payload" 2>/dev/null || echo '{"error": "Solana RPC call failed"}'
}

# rpc_get_balance <pubkey>
# Returns SOL balance for a wallet address.
rpc_get_balance() {
  local pubkey="${1:?Usage: rpc_get_balance <pubkey>}"

  local result
  result=$(_solana_rpc "getBalance" "[\"$pubkey\"]")

  local lamports
  lamports=$(echo "$result" | jq -r '.result.value // 0')

  # Convert lamports to SOL (1 SOL = 1,000,000,000 lamports)
  local sol
  sol=$(echo "scale=9; $lamports / 1000000000" | bc 2>/dev/null || echo "0")

  echo "$sol"
}

# rpc_get_balance_formatted <pubkey>
# Returns formatted balance string.
rpc_get_balance_formatted() {
  local pubkey="${1:?}"
  local sol
  sol=$(rpc_get_balance "$pubkey")
  echo "${sol} SOL"
}

# rpc_get_latest_blockhash
# Returns the latest blockhash (for transaction preparation).
rpc_get_latest_blockhash() {
  local result
  result=$(_solana_rpc "getLatestBlockhash" '[]')
  echo "$result" | jq -r '.result.value.blockhash // empty'
}

# rpc_get_performance
# Returns recent performance samples (TPS, slot info).
rpc_get_performance() {
  local limit="${1:-5}"
  _solana_rpc "getRecentPerformanceSamples" "[$limit]"
}

# rpc_format_performance <performance_json>
# Formats performance data into readable output.
rpc_format_performance() {
  local perf_json="$1"

  echo "$perf_json" | jq -r '
    .result[:3] // [] | map(
      "Slot: \(.slot) | TPS: \((.numTransactions // 0) / (.samplePeriodSecs // 1) | floor) | Transactions: \(.numTransactions // 0)"
    ) | join("\n")
  ' 2>/dev/null || echo "Failed to parse performance data"
}

# rpc_get_slot
# Returns the current slot number.
rpc_get_slot() {
  local result
  result=$(_solana_rpc "getSlot" '[]')
  echo "$result" | jq -r '.result // empty'
}

# ── Well-known Token Addresses ──────────────────────────────────────────────

# Common Solana token mint addresses for convenience
SOL_MINT="So11111111111111111111111111111111111111112"
USDC_MINT="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT="Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
BONK_MINT="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
JUP_MINT="JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"
RAY_MINT="4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"

# sol_price_check <token_symbol_or_mint>
# Quick price check via Dexscreener search.
sol_price_check() {
  local query="${1:?Usage: sol_price_check <token_symbol_or_mint>}"
  local result
  result=$(dex_search "$query")

  echo "$result" | jq -r '
    .pairs[:3] // [] | map(
      "\(.baseToken.symbol // "?")/\(.quoteToken.symbol // "?") @ $\(.priceUsd // "N/A") (24h: \(.priceChange.h24 // "?")%) on \(.dexId // "?")"
    ) | join("\n")
  ' 2>/dev/null || echo "No results found for: $query"
}

# ── Solana Feature Gate ─────────────────────────────────────────────────────

# check_solana_enabled
# Returns 0 if Solana features are enabled, 1 otherwise.
# Checks agent.md and config/solana.yml for enablement.
check_solana_enabled() {
  local repo_root
  repo_root="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"

  # Check agent.md for solana enablement
  if [[ -f "$repo_root/agent.md" ]]; then
    if grep -qi "solana" "$repo_root/agent.md" 2>/dev/null; then
      return 0
    fi
  fi

  # Check solana config
  if [[ -f "$repo_root/config/solana.yml" ]]; then
    local enabled
    enabled=$(grep -oP 'enabled:\s*\K\w+' "$repo_root/config/solana.yml" 2>/dev/null || echo "false")
    if [[ "$enabled" == "true" ]]; then
      return 0
    fi
  fi

  # Check settings.yml feature flag
  if [[ -f "$repo_root/config/settings.yml" ]]; then
    local flag
    flag=$(grep -A1 'solana:' "$repo_root/config/settings.yml" 2>/dev/null | grep -oP 'enabled:\s*\K\w+' || echo "false")
    if [[ "$flag" == "true" ]]; then
      return 0
    fi
  fi

  return 1
}

# Allow sourcing or direct execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  "${1:?Usage: solana-tools.sh <function_name> [args...]}" "${@:2}"
fi
