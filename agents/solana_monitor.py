#!/usr/bin/env python3
"""
Solana Monitor Agent — Scheduled wallet and token price monitoring.
Tracks balances and prices, detects changes, generates alerts.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from common import (
    MEMORY_DIR, award_xp, call_llm, gh_post_comment,
    log, read_prompt, today, update_stats,
)
from solana_query import (
    dex_search, get_balance, WELL_KNOWN_MINTS,
)

SNAPSHOTS_DIR = MEMORY_DIR / "solana" / "wallets"
ALERTS_DIR = MEMORY_DIR / "solana" / "alerts"


def load_previous_snapshot() -> dict:
    """Load the most recent monitoring snapshot."""
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_files = sorted(SNAPSHOTS_DIR.glob("*.json"))
    if snapshot_files:
        return json.loads(snapshot_files[-1].read_text())
    return {}


def save_snapshot(data: dict) -> Path:
    """Save current monitoring snapshot."""
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    path = SNAPSHOTS_DIR / f"snapshot-{ts}.json"
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path


def get_watched_wallets() -> list[dict]:
    """Get wallets to monitor from environment or config."""
    wallets_json = os.environ.get("SOLANA_WALLETS", "[]")
    try:
        return json.loads(wallets_json)
    except json.JSONDecodeError:
        return []


def get_watchlist_tokens() -> list[str]:
    """Get tokens to track from environment or config."""
    tokens = os.environ.get("SOLANA_WATCHLIST", "SOL")
    return [t.strip().upper() for t in tokens.split(",") if t.strip()]


def check_wallets(wallets: list[dict]) -> list[dict]:
    """Check balances for all watched wallets."""
    results = []
    for wallet in wallets:
        address = wallet.get("address", "")
        label = wallet.get("label", address[:8])
        if not address:
            continue
        try:
            balance = get_balance(address)
            results.append({
                "address": address,
                "label": label,
                "balance_sol": balance,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            log("Solana Monitor", f"Failed to check {label}: {e}")
            results.append({
                "address": address,
                "label": label,
                "balance_sol": None,
                "error": str(e),
            })
    return results


def check_prices(tokens: list[str]) -> list[dict]:
    """Check prices for all watched tokens."""
    results = []
    for token in tokens:
        try:
            data = dex_search(token)
            pairs = data.get("pairs", [])
            if pairs:
                pair = pairs[0]
                results.append({
                    "symbol": token,
                    "price_usd": pair.get("priceUsd", "N/A"),
                    "change_24h": pair.get("priceChange", {}).get("h24", "N/A"),
                    "volume_24h": pair.get("volume", {}).get("h24", "N/A"),
                    "liquidity_usd": pair.get("liquidity", {}).get("usd", "N/A"),
                    "dex": pair.get("dexId", "Unknown"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            else:
                results.append({"symbol": token, "error": "No pairs found"})
        except Exception as e:
            log("Solana Monitor", f"Failed to check {token}: {e}")
            results.append({"symbol": token, "error": str(e)})
    return results


def detect_changes(current: dict, previous: dict) -> list[str]:
    """Detect significant changes between snapshots."""
    alerts = []

    # Check wallet balance changes
    prev_wallets = {w["address"]: w for w in previous.get("wallets", [])}
    for wallet in current.get("wallets", []):
        addr = wallet["address"]
        if addr in prev_wallets and wallet.get("balance_sol") is not None:
            prev_bal = prev_wallets[addr].get("balance_sol", 0) or 0
            curr_bal = wallet["balance_sol"]
            if prev_bal > 0:
                change_pct = ((curr_bal - prev_bal) / prev_bal) * 100
                if abs(change_pct) > 5:
                    direction = "increased" if change_pct > 0 else "decreased"
                    alerts.append(
                        f"Wallet {wallet['label']}: Balance {direction} by "
                        f"{abs(change_pct):.1f}% ({prev_bal:.4f} -> {curr_bal:.4f} SOL)"
                    )

    # Check price changes
    prev_prices = {p["symbol"]: p for p in previous.get("prices", [])}
    for price in current.get("prices", []):
        sym = price["symbol"]
        if sym in prev_prices:
            try:
                curr_price = float(price.get("price_usd", 0))
                prev_price = float(prev_prices[sym].get("price_usd", 0))
                if prev_price > 0:
                    change_pct = ((curr_price - prev_price) / prev_price) * 100
                    if abs(change_pct) > 10:
                        direction = "pumped" if change_pct > 0 else "dumped"
                        alerts.append(
                            f"{sym} {direction} {abs(change_pct):.1f}% "
                            f"(${prev_price:.4f} -> ${curr_price:.4f})"
                        )
            except (ValueError, TypeError):
                pass

    return alerts


def format_report(snapshot: dict, alerts: list[str], previous: dict) -> str:
    """Format monitoring data into a readable report."""
    lines = [f"## 📡 Solana Monitor — {today()}\n"]

    # Wallet section
    wallets = snapshot.get("wallets", [])
    if wallets:
        lines.append("### Wallets\n")
        for w in wallets:
            if w.get("balance_sol") is not None:
                lines.append(f"- **{w['label']}**: {w['balance_sol']:.4f} SOL\n")
            else:
                lines.append(f"- **{w['label']}**: Error — {w.get('error', 'Unknown')}\n")

    # Price section
    prices = snapshot.get("prices", [])
    if prices:
        lines.append("\n### Token Prices\n")
        lines.append("| Token | Price | 24h | Volume | Liquidity |\n")
        lines.append("|-------|-------|-----|--------|----------|\n")
        for p in prices:
            if "error" not in p:
                lines.append(
                    f"| {p['symbol']} | ${p['price_usd']} | "
                    f"{p['change_24h']}% | ${p['volume_24h']} | "
                    f"${p['liquidity_usd']} |\n"
                )

    # Alerts section
    if alerts:
        lines.append("\n### Alerts\n")
        for alert in alerts:
            lines.append(f"- {alert}\n")
    else:
        lines.append("\n*No significant changes detected. All quiet on the chain.*\n")

    return "".join(lines)


def main():
    issue_number = int(os.environ.get("ISSUE_NUMBER", "0"))

    log("Solana Monitor", "Starting monitoring sweep...")

    wallets = get_watched_wallets()
    tokens = get_watchlist_tokens()

    # Check current state
    wallet_data = check_wallets(wallets)
    price_data = check_prices(tokens)

    current_snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "wallets": wallet_data,
        "prices": price_data,
    }

    # Compare with previous
    previous = load_previous_snapshot()
    alerts = detect_changes(current_snapshot, previous)

    # Save snapshot
    save_snapshot(current_snapshot)

    # Format report
    raw_report = format_report(current_snapshot, alerts, previous)

    # Add LLM commentary if there are alerts
    if alerts:
        try:
            system_prompt = read_prompt("solana-monitor")
            user_message = (
                f"Monitoring report:\n{raw_report}\n\n"
                f"Alerts triggered: {len(alerts)}\n"
                f"Add brief, entertaining commentary about these changes."
            )
            response = call_llm(system_prompt, user_message, max_tokens=800)
        except Exception:
            response = raw_report + "\n\n— 📡 *Solana Monitor | Always watching*"
    else:
        response = raw_report + "\n\n— 📡 *Solana Monitor | All quiet on the chain*"

    # Post to issue
    if issue_number > 0:
        gh_post_comment(issue_number, response)

    # Archive alert if any
    if alerts:
        ALERTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
        alert_file = ALERTS_DIR / f"alert-{ts}.md"
        alert_file.write_text(response + "\n")

    update_stats("solana_monitors")
    award_xp(5)

    print(response)


if __name__ == "__main__":
    main()
