#!/usr/bin/env python3
"""
fieldboard — Terminal dashboard for running local repo quality tools.

Usage:
    python fieldboard.py run                     # run all configured tools in current repo
    python fieldboard.py run --config myboard.json
    python fieldboard.py run --repo /path/to/repo
    python fieldboard.py run --tool mdguard --tool graft   # run only specific tools
    python fieldboard.py run --json               # machine-readable output
    python fieldboard.py run --no-color
    python fieldboard.py init                    # create fieldboard.json
    python fieldboard.py --version
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

VERSION = "0.1.0"

DEFAULT_CONFIG = {
    "repo": ".",
    "timeout_seconds": 120,
    "tools": [
        {
            "name": "mdguard",
            "command": "mdguard",
            "args": ["check", "."],
            "enabled": True
        },
        {
            "name": "graft",
            "command": "graft",
            "args": ["scan", "--json"],
            "enabled": True
        },
        {
            "name": "policy-runner",
            "command": "policy-runner",
            "args": ["run"],
            "enabled": True
        },
        {
            "name": "dep-health-scanner",
            "command": "dep-health-scanner",
            "args": ["scan", "--json"],
            "enabled": True
        },
        {
            "name": "config-drift",
            "command": "config-drift",
            "args": ["diff", "--configs-root", "./configs"],
            "enabled": False
        }
    ]
}

# ANSI color codes
COLORS = {
    "green": "\033[32m",
    "red": "\033[31m",
    "yellow": "\033[33m",
    "reset": "\033[0m",
    "bold": "\033[1m",
}


def print_color(text: str, color: Optional[str] = None, use_color: bool = True) -> None:
    """Print text with optional ANSI color."""
    if color and use_color:
        print(f"{COLORS.get(color, '')}{text}{COLORS['reset']}")
    else:
        print(text)


def tool_available(command: str) -> bool:
    """Check if a command is available on PATH."""
    return shutil.which(command) is not None


def load_config(config_path: Optional[str]) -> Dict[str, Any]:
    """Load configuration from file or return defaults."""
    if config_path is None:
        return DEFAULT_CONFIG.copy()

    path = Path(config_path)
    if not path.exists():
        # If user specified a config but it doesn't exist, error
        if config_path != "fieldboard.json":
            print_color(f"Error: Config file '{config_path}' not found", "red")
            sys.exit(2)
        return DEFAULT_CONFIG.copy()

    try:
        with open(path, 'r') as f:
            config = json.load(f)
        # Merge with defaults for missing keys
        merged = DEFAULT_CONFIG.copy()
        merged.update(config)
        # Ensure tools list exists
        if "tools" not in config:
            merged["tools"] = DEFAULT_CONFIG["tools"]
        return merged
    except json.JSONDecodeError as e:
        print_color(f"Error: Invalid JSON in config file: {e}", "red")
        sys.exit(2)


def run_tool(tool: Dict[str, Any], repo: str, timeout: int) -> Dict[str, Any]:
    """Run a single tool and return results."""
    command = tool["command"]

    if not tool_available(command):
        return {
            "name": tool["name"],
            "status": "skipped",
            "exit_code": None,
            "duration_ms": 0,
            "output": f"{command} not found on PATH",
            "error": None
        }

    args = [command] + tool.get("args", [])
    expected_codes = tool.get("expected_exit_codes", [0])

    start = time.monotonic()
    try:
        result = subprocess.run(
            args,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        success = result.returncode in expected_codes

        return {
            "name": tool["name"],
            "status": "pass" if success else "fail",
            "exit_code": result.returncode,
            "duration_ms": duration_ms,
            "output": result.stdout,
            "error": result.stderr
        }
    except subprocess.TimeoutExpired:
        return {
            "name": tool["name"],
            "status": "fail",
            "exit_code": None,
            "duration_ms": timeout * 1000,
            "output": "",
            "error": f"Timed out after {timeout}s"
        }


def format_terminal_output(
    results: List[Dict[str, Any]], repo: str, use_color: bool, verbose: bool
) -> None:
    """Print formatted terminal dashboard."""
    print()
    print_color(f"FIELD BOARD — {repo}", "bold", use_color)
    print()

    # Calculate column widths
    max_name = max(len("Tool"), max(len(r["name"]) for r in results) if results else 4)

    # Header
    header = f" {'Tool':<{max_name}}  {'Status':<8}  {'Duration':<10}  Details"
    print(header)
    print(" " + "─" * len(header))

    passed = failed = skipped = 0

    for r in results:
        status = r["status"].upper()
        status_color = {"pass": "green", "fail": "red", "skipped": "yellow"}.get(r["status"])

        if r["status"] == "pass":
            passed += 1
        elif r["status"] == "fail":
            failed += 1
        else:
            skipped += 1

        duration = f"{r['duration_ms']}ms" if r["duration_ms"] else "—"

        details = ""
        if r["status"] == "fail" and r["error"]:
            first_line = r["error"].split("\n")[0][:50]
            details = first_line
        elif r["status"] == "skipped":
            details = r["output"][:50] if r["output"] else ""
        elif verbose and r["output"]:
            details = r["output"].split("\n")[0][:50]

        status_str = status
        if use_color and status_color:
            status_str = f"{COLORS[status_color]}{status}{COLORS['reset']}"

        line = f" {r['name']:<{max_name}}  {status_str:<8}  {duration:<10}"
        if details:
            line += f"  {details}"
        print(line)

        if verbose and r["output"]:
            for line in r["output"].split("\n"):
                print(f"    {line}")
        if verbose and r["error"]:
            for line in r["error"].split("\n"):
                print(f"    [ERR] {line}")

    print()
    summary = f" Summary: {passed} passed, {failed} failed, {skipped} skipped"
    print_color(summary, "bold", use_color)
    print()


def format_json_output(results: List[Dict[str, Any]], repo: str) -> str:
    """Generate JSON report."""
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    skipped = sum(1 for r in results if r["status"] == "skipped")

    exit_code = 1 if failed > 0 else 0

    report = {
        "repo": os.path.abspath(repo),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "skipped": skipped
        },
        "tools": results,
        "exit_code": exit_code
    }

    return json.dumps(report, indent=2)


def create_default_config() -> None:
    """Create a default fieldboard.json file."""
    config_path = Path("fieldboard.json")
    if config_path.exists():
        print_color("fieldboard.json already exists", "yellow")
        return

    with open(config_path, 'w') as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)

    print_color("Created fieldboard.json", "green")
    print("Edit this file to customize your tool configuration.")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="fieldboard",
        description="Terminal dashboard for running local repo quality tools"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run configured tools")
    run_parser.add_argument(
        "--config", type=str, help="Path to config file (default: fieldboard.json)"
    )
    run_parser.add_argument(
        "--repo", type=str, default=".", help="Repository path (default: current directory)"
    )
    run_parser.add_argument(
        "--tool", action="append", dest="tools", help="Only run specific tool(s), repeatable"
    )
    run_parser.add_argument(
        "--json", action="store_true", dest="json_output", help="JSON output mode"
    )
    run_parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    run_parser.add_argument("--fail-fast", action="store_true", help="Stop after first failure")
    run_parser.add_argument("--timeout", type=int, default=120, help="Per-tool timeout in seconds")
    run_parser.add_argument("--verbose", action="store_true", help="Show full output for each tool")

    # Init command
    subparsers.add_parser("init", help="Create default fieldboard.json")

    args = parser.parse_args()

    if args.command == "init":
        create_default_config()
        return 0

    if args.command != "run":
        parser.print_help()
        return 2

    # Load configuration
    config = load_config(args.config)

    # Override config with CLI args
    repo = args.repo
    timeout = args.timeout

    # Get tools to run
    tools = config.get("tools", [])

    # Filter by --tool if specified
    if args.tools:
        tools = [t for t in tools if t["name"] in args.tools]
        if not tools:
            print_color(f"No tools match the specified names: {args.tools}", "red")
            return 2

    # Filter disabled tools
    tools = [t for t in tools if t.get("enabled", True)]

    if not tools:
        print_color("No tools to run", "yellow")
        return 0

    # Run tools
    results = []
    for tool in tools:
        result = run_tool(tool, repo, timeout)
        results.append(result)

        if args.fail_fast and result["status"] == "fail":
            break

    # Output results
    use_color = not args.no_color

    if args.json_output:
        print(format_json_output(results, repo))
    else:
        format_terminal_output(results, repo, use_color, args.verbose)

    # Exit code
    failed = sum(1 for r in results if r["status"] == "fail")
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
