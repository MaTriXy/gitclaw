#!/usr/bin/env python3
"""
Solana Builder Agent — Verifiable Solana program builds in GitHub Actions.
Handles cargo-build-sbf and Anchor builds, outputs artifacts and hashes.
"""

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from common import (
    MEMORY_DIR, award_xp, call_llm, gh_post_comment,
    log, read_prompt, today, update_stats,
)

BUILDS_DIR = MEMORY_DIR / "solana" / "builds"


def find_program_dirs(root: Path) -> list[Path]:
    """Find Solana program directories (contain Cargo.toml with solana deps)."""
    programs = []
    for cargo_toml in root.rglob("Cargo.toml"):
        try:
            content = cargo_toml.read_text()
            if "solana-program" in content or "anchor-lang" in content:
                programs.append(cargo_toml.parent)
        except Exception:
            pass
    return programs


def detect_framework(program_dir: Path) -> str:
    """Detect if a program uses Anchor or native Solana SDK."""
    cargo_toml = program_dir / "Cargo.toml"
    if cargo_toml.exists():
        content = cargo_toml.read_text()
        if "anchor-lang" in content:
            return "anchor"
    # Check for Anchor.toml in parent dirs
    check = program_dir
    for _ in range(5):
        if (check / "Anchor.toml").exists():
            return "anchor"
        check = check.parent
    return "native"


def build_native(program_dir: Path) -> dict:
    """Build a native Solana program using cargo-build-sbf."""
    log("Solana Builder", f"Building native program: {program_dir}")

    result = {
        "program": program_dir.name,
        "framework": "native",
        "status": "unknown",
        "artifacts": [],
        "warnings": [],
        "errors": [],
    }

    try:
        proc = subprocess.run(
            ["cargo", "build-sbf"],
            cwd=str(program_dir),
            capture_output=True, text=True,
            timeout=600,  # 10 minute timeout
        )

        result["build_output"] = proc.stdout + proc.stderr

        if proc.returncode == 0:
            result["status"] = "success"
            # Find .so artifacts
            target_dir = program_dir / "target" / "deploy"
            if target_dir.exists():
                for so_file in target_dir.glob("*.so"):
                    file_hash = hashlib.sha256(so_file.read_bytes()).hexdigest()
                    result["artifacts"].append({
                        "name": so_file.name,
                        "size_bytes": so_file.stat().st_size,
                        "sha256": file_hash,
                    })
        else:
            result["status"] = "failed"
            result["errors"] = [
                line for line in proc.stderr.split("\n")
                if "error" in line.lower()
            ][:10]

        # Extract warnings
        result["warnings"] = [
            line for line in proc.stderr.split("\n")
            if "warning" in line.lower()
        ][:5]

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["errors"] = ["Build timed out after 10 minutes"]
    except FileNotFoundError:
        result["status"] = "failed"
        result["errors"] = ["cargo-build-sbf not found. Install solana-cli."]
    except Exception as e:
        result["status"] = "failed"
        result["errors"] = [str(e)]

    return result


def build_anchor(program_dir: Path) -> dict:
    """Build an Anchor program."""
    log("Solana Builder", f"Building Anchor program: {program_dir}")

    # Find Anchor.toml root
    anchor_root = program_dir
    for _ in range(5):
        if (anchor_root / "Anchor.toml").exists():
            break
        anchor_root = anchor_root.parent

    result = {
        "program": program_dir.name,
        "framework": "anchor",
        "status": "unknown",
        "artifacts": [],
        "warnings": [],
        "errors": [],
    }

    try:
        proc = subprocess.run(
            ["anchor", "build"],
            cwd=str(anchor_root),
            capture_output=True, text=True,
            timeout=600,
        )

        result["build_output"] = proc.stdout + proc.stderr

        if proc.returncode == 0:
            result["status"] = "success"
            target_dir = anchor_root / "target" / "deploy"
            if target_dir.exists():
                for so_file in target_dir.glob("*.so"):
                    file_hash = hashlib.sha256(so_file.read_bytes()).hexdigest()
                    result["artifacts"].append({
                        "name": so_file.name,
                        "size_bytes": so_file.stat().st_size,
                        "sha256": file_hash,
                    })
                # Also check for IDL
                for idl_file in (anchor_root / "target" / "idl").glob("*.json"):
                    result["artifacts"].append({
                        "name": idl_file.name,
                        "size_bytes": idl_file.stat().st_size,
                        "type": "idl",
                    })
        else:
            result["status"] = "failed"
            result["errors"] = [
                line for line in proc.stderr.split("\n")
                if "error" in line.lower()
            ][:10]

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["errors"] = ["Build timed out after 10 minutes"]
    except FileNotFoundError:
        result["status"] = "failed"
        result["errors"] = ["Anchor CLI not found. Install anchor-cli."]
    except Exception as e:
        result["status"] = "failed"
        result["errors"] = [str(e)]

    return result


def format_build_report(result: dict) -> str:
    """Format build result into a readable report."""
    status_emoji = {
        "success": "✅",
        "failed": "❌",
        "timeout": "⏰",
    }.get(result["status"], "❓")

    lines = [
        f"## 🔨 Solana Build Report\n",
        f"**Program:** {result['program']}\n",
        f"**Framework:** {result['framework'].title()}\n",
        f"**Status:** {status_emoji} {result['status'].title()}\n",
    ]

    if result["artifacts"]:
        lines.append("\n### Artifacts\n")
        for artifact in result["artifacts"]:
            size_kb = artifact.get("size_bytes", 0) / 1024
            lines.append(f"- `{artifact['name']}` ({size_kb:.1f} KB)\n")
            if "sha256" in artifact:
                lines.append(f"  SHA256: `{artifact['sha256'][:16]}...`\n")

    if result["warnings"]:
        lines.append("\n### Warnings\n")
        for w in result["warnings"][:3]:
            lines.append(f"- {w.strip()}\n")

    if result["errors"]:
        lines.append("\n### Errors\n")
        for e in result["errors"][:5]:
            lines.append(f"- {e.strip()}\n")

    return "".join(lines)


def main():
    program_path = os.environ.get("PROGRAM_PATH", ".")
    issue_number = int(os.environ.get("ISSUE_NUMBER", "0"))

    log("Solana Builder", f"Build requested for: {program_path}")

    program_dir = Path(program_path).resolve()
    if not program_dir.exists():
        # Search for programs in repo
        repo_root = Path(os.environ.get("GITHUB_WORKSPACE", "."))
        programs = find_program_dirs(repo_root)
        if programs:
            program_dir = programs[0]
            log("Solana Builder", f"Auto-detected program: {program_dir}")
        else:
            response = (
                "## 🔨 Solana Builder\n\n"
                "No Solana programs found in the repository.\n"
                "Make sure your program has `solana-program` or `anchor-lang` "
                "in its Cargo.toml.\n\n"
                "— 🔨 *Solana Builder*"
            )
            if issue_number > 0:
                gh_post_comment(issue_number, response)
            print(response)
            return

    # Detect framework and build
    framework = detect_framework(program_dir)
    if framework == "anchor":
        result = build_anchor(program_dir)
    else:
        result = build_native(program_dir)

    # Format report
    raw_report = format_build_report(result)

    # Add LLM commentary
    try:
        system_prompt = read_prompt("solana-builder")
        user_message = (
            f"Build report:\n{raw_report}\n\n"
            f"Build output (truncated):\n"
            f"{result.get('build_output', '')[:1000]}\n\n"
            f"Add entertaining commentary about this build result."
        )
        response = call_llm(system_prompt, user_message, max_tokens=1500)
    except Exception:
        response = raw_report + "\n\n— 🔨 *Solana Builder | Verified builds, verified vibes*"

    # Post and archive
    if issue_number > 0:
        gh_post_comment(issue_number, response)

    BUILDS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    build_file = BUILDS_DIR / f"build-{ts}.json"
    result.pop("build_output", None)  # Don't persist full output
    build_file.write_text(json.dumps(result, indent=2) + "\n")

    update_stats("solana_builds")
    award_xp(20)

    print(response)


if __name__ == "__main__":
    main()
