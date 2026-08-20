#!/usr/bin/env python3
"""fieldboard - Terminal dashboard for running local repo quality tools.

Runs multiple quality tools as subprocesses, captures results, and displays
a clean terminal dashboard or JSON report.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__version__ = "0.1.0"

DEFAULT_TIMEOUT = 120


def tool_available(command: str) -> bool:
    """Check if a tool is available on PATH."""
    return shutil.which(command) is not None


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """Load fieldboard.json config file."""
    if config_path:
        path = Path(config_path)
    else:
        path = Path("fieldboard.json")

    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error: invalid config file {path}: {e}", file=sys.stderr)
        sys.exit(2)


def get_default_config() -> dict[str, Any]:
    """Get default configuration."""
    return {
        "repo": ".",
        "timeout_seconds": DEFAULT_TIMEOUT,
        "tools": [
            {
                "name": "mdguard",
                "command": "mdguard",
                "args": ["check", "."],
                "enabled": True,
            },
            {
                "name": "graft",
                "command": "graft",
                "args": ["scan", "--json"],
                "enabled": True,
            },
            {
                "name": "policy-runner",
                "command": "policy-runner",
                "args": ["run"],
                "enabled": True,
            },
            {
                "name": "dep-health-scanner",
                "command": "dep-health-scanner",
                "args": ["scan", "--json"],
                "enabled": True,
            },
            {
                "name": "config-drift",
                "command": "config-drift",
                "args": ["diff", "--configs-root", "./configs"],
                "enabled": False,
            },
        ],
    }


def run_tool(
    tool: dict[str, Any],
    repo: str,
    timeout: int,
    verbose: bool = False,
) -> dict[str, Any]:
    """Run a single tool and return results."""
    name = tool["name"]
    command = tool["command"]

    if not tool.get("enabled", True):
        return {
            "name": name,
            "status": "skipped",
            "exit_code": None,
            "duration_ms": 0,
            "output": "",
            "error": "disabled in config",
        }

    if not tool_available(command):
        return {
            "name": name,
            "status": "skipped",
            "exit_code": None,
            "duration_ms": 0,
            "output": "",
            "error": f"{command} not found on PATH",
        }

    cmd_args = [command] + tool.get("args", [])
    start = time.monotonic()

    try:
        result = subprocess.run(
            cmd_args,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        expected = tool.get("expected_exit_codes", [0])
        success = result.returncode in expected

        output = result.stdout
        if verbose and result.stderr:
            output = f"{output}\n{result.stderr}" if output else result.stderr

        return {
            "name": name,
            "status": "pass" if success else "fail",
            "exit_code": result.returncode,
            "duration_ms": duration_ms,
            "output": output,
            "error": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {
            "name": name,
            "status": "fail",
            "exit_code": None,
            "duration_ms": timeout * 1000,
            "output": "",
            "error": f"Timed out after {timeout}s",
        }
    except OSError as e:
        return {
            "name": name,
            "status": "fail",
            "exit_code": None,
            "duration_ms": int((time.monotonic() - start) * 1000),
            "output": "",
            "error": str(e),
        }


def format_terminal(
    results: list[dict[str, Any]],
    repo: str,
    no_color: bool = False,
    verbose: bool = False,
) -> str:
    """Format results as terminal dashboard."""
    lines = []

    # Header
    if no_color:
        lines.append(f"FIELD BOARD — {repo}")
    else:
        lines.append(f"\033[1mFIELD BOARD\033[0m — {repo}")
    lines.append("")

    # Column headers
    lines.append(f" {'Tool':<22} {'Status':<10} {'Duration':<12} Details")
    lines.append(" " + "─" * 60)

    # Tool results
    for r in results:
        name = r["name"]
        status = r["status"]
        duration = f"{r['duration_ms']}ms" if r["duration_ms"] > 0 else "─"

        if no_color:
            status_str = status.upper()
        else:
            if status == "pass":
                status_str = "\033[32mPASS\033[0m"
            elif status == "fail":
                status_str = "\033[31mFAIL\033[0m"
            else:
                status_str = "\033[33mSKIP\033[0m"

        detail = ""
        if status == "fail":
            detail = r.get("error", "").split("\n")[0][:40]
        elif status == "skipped":
            detail = r.get("error", "")[:40]

        lines.append(f" {name:<22} {status_str:<20} {duration:<12} {detail}")

        if verbose and r.get("output"):
            for out_line in r["output"].split("\n")[:3]:
                lines.append(f"   {out_line[:70]}")

    # Summary
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    skipped = sum(1 for r in results if r["status"] == "skipped")

    lines.append("")
    lines.append(f" Summary: {passed} passed, {failed} failed, {skipped} skipped")

    return "\n".join(lines)


def format_json(
    results: list[dict[str, Any]],
    repo: str,
    exit_code: int,
) -> str:
    """Format results as JSON."""
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    skipped = sum(1 for r in results if r["status"] == "skipped")

    output = {
        "repo": str(Path(repo).resolve()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
        },
        "tools": results,
        "exit_code": exit_code,
    }

    return json.dumps(output, indent=2)


def run_command(args: argparse.Namespace) -> int:
    """Run the fieldboard command."""
    # Load config
    config = load_config(args.config)
    if not config:
        config = get_default_config()

    repo = args.repo or config.get("repo", ".")
    timeout = args.timeout or config.get("timeout_seconds", DEFAULT_TIMEOUT)

    if not Path(repo).is_dir():
        print(f"Error: {repo} is not a directory", file=sys.stderr)
        return 2

    # Get tools list
    tools = config.get("tools", [])

    # Filter tools if --tool specified
    if args.tool:
        tools = [t for t in tools if t["name"] in args.tool]

    if not tools:
        print("No tools to run.", file=sys.stderr)
        return 2

    # Run tools
    results = []
    for tool in tools:
        result = run_tool(tool, repo, timeout, args.verbose)
        results.append(result)

        # Fail fast
        if args.fail_fast and result["status"] == "fail":
            break

    # Calculate exit code
    failed = sum(1 for r in results if r["status"] == "fail")
    exit_code = 1 if failed > 0 else 0

    # Output
    if args.json:
        print(format_json(results, repo, exit_code))
    else:
        print(format_terminal(results, repo, args.no_color, args.verbose))

    return exit_code


def init_command(args: argparse.Namespace) -> int:
    """Run the init command."""
    config = get_default_config()
    config_path = Path(args.config or "fieldboard.json")

    if config_path.exists():
        print(f"{config_path} already exists. Overwrite? [y/N]")
        response = input().strip().lower()
        if response != "y":
            print("Aborted.")
            return 0

    with config_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    print(f"Created {config_path}")
    return 0


def main() -> None:
    desc = "fieldboard - Terminal dashboard for running local repo quality tools"
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "--version", action="version", version=f"fieldboard {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="command to execute")

    run_parser = subparsers.add_parser("run", help="run quality tools")
    run_parser.add_argument(
        "--config",
        default=None,
        help="config file (default: fieldboard.json)",
    )
    run_parser.add_argument(
        "--repo",
        default=None,
        help="repo to run tools in (default: current directory)",
    )
    run_parser.add_argument(
        "--tool",
        action="append",
        help="only run specific tool(s), repeatable",
    )
    run_parser.add_argument(
        "--json",
        action="store_true",
        help="JSON output instead of terminal dashboard",
    )
    run_parser.add_argument(
        "--no-color",
        action="store_true",
        help="disable ANSI colors",
    )
    run_parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="stop after first failing tool",
    )
    run_parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="per-tool timeout in seconds (default: 120)",
    )
    run_parser.add_argument(
        "--verbose",
        action="store_true",
        help="show full stdout/stderr for each tool",
    )

    init_parser = subparsers.add_parser("init", help="create fieldboard.json config")
    init_parser.add_argument(
        "--config",
        default=None,
        help="config file path (default: fieldboard.json)",
    )

    args = parser.parse_args()

    if args.command == "run":
        sys.exit(run_command(args))
    elif args.command == "init":
        sys.exit(init_command(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
