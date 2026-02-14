#!/usr/bin/env python3
"""
Solana Query Agent — On-chain data fetcher and interpreter.
Handles /sol price, /sol balance, /sol quote, /sol network commands.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

from common import (
    MEMORY_DIR, award_xp, call_llm, gh_post_comment,
    log, read_prompt, today, update_stats,
)

# ── Solana Constants ─────────────────────────────────────────────────────────

WELL_KNOWN_MINTS = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "RAY": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
    "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
}

DEXSCREENER_API = "https://api.dexscreener.com"
JUPITER_API = "https://quote-api.jup.ag/v6"
LAMPORTS_PER_SOL = 1_000_000_000


def get_solana_rpc() -> str:
    """Get the configured Solana RPC endpoint."""
    custom_rpc = os.environ.get("SOLANA_RPC_URL", "")
    if custom_rpc:
        return custom_rpc
    network = os.environ.get("SOLANA_NETWORK", "mainnet-beta")
    if network == "devnet":
        return "https://api.devnet.solana.com"
    return "https://api.mainnet-beta.solana.com"


# ── API Callers ──────────────────────────────────────────────────────────────

def fetch_json(url: str, method: str = "GET", data: bytes | None = None,
               headers: dict | None = None) -> dict:
    """Generic JSON fetch helper."""
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def dex_search(query: str) -> dict:
    """Search Dexscreener for a token/pair."""
    encoded = urllib.request.quote(query)
    return fetch_json(f"{DEXSCREENER_API}/latest/dex/search?q={encoded}")


def dex_get_pair(chain_id: str, pair_address: str) -> dict:
    """Get specific pair data from Dexscreener."""
    return fetch_json(f"{DEXSCREENER_API}/latest/dex/pairs/{chain_id}/{pair_address}")


def dex_get_token_pairs(chain_id: str, token_address: str) -> dict:
    """Get all pairs for a token."""
    return fetch_json(f"{DEXSCREENER_API}/token-pairs/v1/{chain_id}/{token_address}")


def jupiter_quote(input_mint: str, output_mint: str, amount: int,
                  slippage_bps: int = 50) -> dict:
    """Get a swap quote from Jupiter v6."""
    url = (f"{JUPITER_API}/quote?inputMint={input_mint}"
           f"&outputMint={output_mint}&amount={amount}"
           f"&slippageBps={slippage_bps}")
    return fetch_json(url)


def rpc_call(method: str, params: list) -> dict:
    """Make a Solana JSON-RPC call."""
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1,
        "method": method, "params": params,
    }).encode()
    return fetch_json(get_solana_rpc(), method="POST", data=payload)


def get_balance(pubkey: str) -> float:
    """Get SOL balance for a wallet address."""
    result = rpc_call("getBalance", [pubkey])
    lamports = result.get("result", {}).get("value", 0)
    return lamports / LAMPORTS_PER_SOL


def get_latest_blockhash() -> str:
    """Get the latest blockhash."""
    result = rpc_call("getLatestBlockhash", [])
    return result.get("result", {}).get("value", {}).get("blockhash", "")


def get_network_performance(limit: int = 5) -> list:
    """Get recent performance samples."""
    result = rpc_call("getRecentPerformanceSamples", [limit])
    return result.get("result", [])


def get_slot() -> int:
    """Get current slot number."""
    result = rpc_call("getSlot", [])
    return result.get("result", 0)


# ── Query Handlers ───────────────────────────────────────────────────────────

def handle_price(args: str) -> str:
    """Handle /sol price <token> queries."""
    token = args.strip().upper() if args.strip() else "SOL"
    log("Solana Query", f"Price check: {token}")

    # Try mint address first, then search
    if token in WELL_KNOWN_MINTS:
        data = dex_get_token_pairs("solana", WELL_KNOWN_MINTS[token])
    else:
        data = dex_search(args.strip())

    if "error" in data:
        return f"Failed to fetch price data: {data['error']}"

    # Extract top pairs
    pairs = data.get("pairs", data.get("pair", []))
    if isinstance(pairs, dict):
        pairs = [pairs]
    if not pairs:
        return f"No trading pairs found for: {token}"

    # Format top 3 pairs
    lines = [f"## 🌐 Price Check: {token}\n"]
    for pair in pairs[:3]:
        base = pair.get("baseToken", {})
        quote = pair.get("quoteToken", {})
        price = pair.get("priceUsd", "N/A")
        change_24h = pair.get("priceChange", {}).get("h24", "N/A")
        volume_24h = pair.get("volume", {}).get("h24", "N/A")
        liquidity = pair.get("liquidity", {}).get("usd", "N/A")
        dex = pair.get("dexId", "Unknown")

        lines.append(
            f"**{base.get('symbol', '?')}/{quote.get('symbol', '?')}** on {dex}\n"
            f"- Price: **${price}**\n"
            f"- 24h Change: {change_24h}%\n"
            f"- 24h Volume: ${volume_24h}\n"
            f"- Liquidity: ${liquidity}\n"
        )

    return "\n".join(lines)


def handle_balance(args: str) -> str:
    """Handle /sol balance <address> queries."""
    address = args.strip()
    if not address or len(address) < 32:
        return "Please provide a valid Solana wallet address."

    log("Solana Query", f"Balance check: {address[:8]}...")

    balance = get_balance(address)

    # Try to get SOL price for USD estimate
    sol_data = dex_search("SOL")
    sol_price = 0.0
    pairs = sol_data.get("pairs", [])
    for p in pairs:
        if p.get("baseToken", {}).get("symbol") == "SOL":
            try:
                sol_price = float(p.get("priceUsd", 0))
            except (ValueError, TypeError):
                pass
            break

    usd_value = balance * sol_price if sol_price > 0 else None

    lines = [
        f"## 🌐 Wallet Balance\n",
        f"**Address:** `{address[:8]}...{address[-4:]}`\n",
        f"**Balance:** {balance:.4f} SOL\n",
    ]
    if usd_value is not None:
        lines.append(f"**USD Value:** ~${usd_value:,.2f} (@ ${sol_price:,.2f}/SOL)\n")
    lines.append(f"**Network:** {os.environ.get('SOLANA_NETWORK', 'mainnet-beta')}\n")

    return "\n".join(lines)


def handle_quote(args: str) -> str:
    """Handle /sol quote <from> <to> <amount> queries."""
    parts = args.strip().split()
    if len(parts) < 3:
        return "Usage: `/sol quote <from_token> <to_token> <amount>`\nExample: `/sol quote SOL USDC 1`"

    from_token = parts[0].upper()
    to_token = parts[1].upper()
    try:
        amount = float(parts[2])
    except ValueError:
        return f"Invalid amount: {parts[2]}"

    # Resolve mint addresses
    from_mint = WELL_KNOWN_MINTS.get(from_token, from_token)
    to_mint = WELL_KNOWN_MINTS.get(to_token, to_token)

    # Convert to lamports/smallest unit (assume SOL-like 9 decimals)
    amount_raw = int(amount * LAMPORTS_PER_SOL)

    log("Solana Query", f"Quote: {amount} {from_token} -> {to_token}")

    data = jupiter_quote(from_mint, to_mint, amount_raw)

    if "error" in data:
        return f"Jupiter quote failed: {data['error']}"

    out_amount = int(data.get("outAmount", 0))
    # Assume 6 decimals for USDC/USDT, 9 for SOL
    if to_token in ("USDC", "USDT"):
        out_human = out_amount / 1_000_000
    else:
        out_human = out_amount / LAMPORTS_PER_SOL

    price_impact = data.get("priceImpactPct", "0")
    slippage = data.get("slippageBps", 50)
    route_len = len(data.get("routePlan", []))

    lines = [
        f"## 🌐 Jupiter Swap Quote\n",
        f"**{amount} {from_token}** → **{out_human:.6f} {to_token}**\n",
        f"- Price Impact: {price_impact}%\n",
        f"- Slippage Tolerance: {slippage} bps ({int(slippage)/100}%)\n",
        f"- Route: {route_len} hop{'s' if route_len != 1 else ''}\n",
        f"\n*This is a quote only — no swap executed. NFA.*\n",
    ]

    return "\n".join(lines)


def handle_network(_args: str) -> str:
    """Handle /sol network status queries."""
    log("Solana Query", "Network status check")

    slot = get_slot()
    blockhash = get_latest_blockhash()
    perf = get_network_performance(3)

    lines = [
        f"## 🌐 Solana Network Status\n",
        f"**Current Slot:** {slot:,}\n",
        f"**Latest Blockhash:** `{blockhash[:16]}...`\n",
        f"**Network:** {os.environ.get('SOLANA_NETWORK', 'mainnet-beta')}\n",
    ]

    if perf:
        lines.append("\n**Recent Performance:**\n")
        for sample in perf[:3]:
            txs = sample.get("numTransactions", 0)
            period = sample.get("samplePeriodSecs", 1)
            tps = txs // period if period > 0 else 0
            lines.append(f"- Slot {sample.get('slot', '?')}: {tps} TPS ({txs:,} txs)\n")

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────

HANDLERS = {
    "price": handle_price,
    "balance": handle_balance,
    "quote": handle_quote,
    "network": handle_network,
}


def main():
    raw_args = os.environ.get("QUERY_ARGS", "").strip()
    issue_number = int(os.environ.get("ISSUE_NUMBER", "0"))
    solana_style = os.environ.get("SOLANA_STYLE", "degen")

    # Parse subcommand: "price SOL" -> command="price", args="SOL"
    parts = raw_args.split(None, 1)
    command = parts[0].lower() if parts else "price"
    args = parts[1] if len(parts) > 1 else ""

    handler = HANDLERS.get(command)
    if not handler:
        response = (
            f"Unknown Solana query: `{command}`\n\n"
            f"Available commands:\n"
            f"- `/sol price <token>` — Check token price\n"
            f"- `/sol balance <address>` — Check wallet balance\n"
            f"- `/sol quote <from> <to> <amount>` — Get swap quote\n"
            f"- `/sol network` — Network status\n"
        )
        if issue_number > 0:
            gh_post_comment(issue_number, response)
        print(response)
        return

    # Get raw data
    raw_data = handler(args)

    # Pass through LLM for entertaining commentary
    try:
        system_prompt = read_prompt("solana-query")
        user_message = (
            f"Query type: {command}\n"
            f"Query args: {args}\n"
            f"Style: {solana_style}\n\n"
            f"Raw data:\n{raw_data}\n\n"
            f"Add entertaining commentary to this data. Keep the actual numbers "
            f"accurate — embellish the narrative, not the data."
        )
        response = call_llm(system_prompt, user_message, max_tokens=1200)
    except Exception as e:
        log("Solana Query", f"LLM commentary failed: {e}, using raw data")
        response = raw_data + "\n\n— 🌐 *Solana Query Agent | NFA*"

    # Post and archive
    if issue_number > 0:
        gh_post_comment(issue_number, response)

    archive_dir = MEMORY_DIR / "solana" / "prices"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_file = archive_dir / f"{today()}-{command}.md"
    with open(archive_file, "a") as f:
        ts = datetime.now(timezone.utc).strftime("%H:%M UTC")
        f.write(f"\n---\n### {ts} — {command} {args}\n\n{raw_data}\n")

    update_stats("solana_queries")
    award_xp(10)

    print(response)


if __name__ == "__main__":
    main()
