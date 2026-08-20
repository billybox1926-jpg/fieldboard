# fieldboard

**Terminal dashboard for running local repo quality tools**

fieldboard runs all your BillyBox local tools in one pass and shows green/red status per repo.

## Features

- ✅ Run a configurable list of external commands
- ✅ Support multiple repos (scan current repo by default, or `--repo PATH`)
- ✅ Detect tool availability (`command -v` / `which`)
- ✅ Capture and display:
  - Tool name
  - Pass / Fail / Skipped status
  - Exit code
  - Duration
  - First line of output on failure
- ✅ Colorized terminal output (green/red/yellow)
- ✅ JSON output mode for CI/automation
- ✅ Optional config file (`fieldboard.json`)
- ✅ Zero Python dependencies — stdlib only
- ✅ Single-file CLI

## Installation

```bash
pip install .
```

Or use directly:

```bash
python fieldboard.py run
```

## Quick Start

```bash
# Create default config
fieldboard init

# Run all configured tools in current repo
fieldboard run

# Run with JSON output for CI
fieldboard run --json

# Run specific tools only
fieldboard run --tool mdguard --tool graft

# Run in a different repo
fieldboard run --repo /path/to/repo

# Stop after first failure
fieldboard run --fail-fast

# Show full output for each tool
fieldboard run --verbose
```

## Example Output

```
FIELD BOARD — /home/user/myproject

 Tool                  Status    Duration    Details
 ─────────────────────────────────────────────────────────
 mdguard               PASS       210ms
 graft                 PASS       380ms
 policy-runner         FAIL      1500ms    denied: rm -rf /
 dep-health-scanner    SKIP        —        not found on PATH
 config-drift          PASS       900ms

 Summary: 4 passed, 1 failed, 1 skipped
```

## Configuration

Create a `fieldboard.json` file:

```bash
fieldboard init
```

Example configuration:

```json
{
  "repo": ".",
  "timeout_seconds": 120,
  "tools": [
    {
      "name": "mdguard",
      "command": "mdguard",
      "args": ["check", "."],
      "enabled": true
    },
    {
      "name": "graft",
      "command": "graft",
      "args": ["scan", "--json"],
      "enabled": true
    },
    {
      "name": "policy-runner",
      "command": "policy-runner",
      "args": ["run"],
      "enabled": true
    },
    {
      "name": "dep-health-scanner",
      "command": "dep-health-scanner",
      "args": ["scan", "--json"],
      "enabled": true
    },
    {
      "name": "config-drift",
      "command": "config-drift",
      "args": ["diff", "--configs-root", "./configs"],
      "enabled": false
    }
  ]
}
```

### Tool Configuration Options

| Field | Type | Description | Default |
|-------|------|-------------|---------|
| `name` | string | Display name | required |
| `command` | string | Executable name (must be on PATH) | required |
| `args` | array | List of arguments | `[]` |
| `enabled` | boolean | Whether to run this tool | `true` |
| `expected_exit_codes` | array | Exit codes considered success | `[0]` |

## CLI Reference

### Commands

| Command | Description |
|---------|-------------|
| `run` | Run configured tools |
| `init` | Create default fieldboard.json |

### Flags

| Flag | Description | Default |
|------|-------------|---------|
| `--config PATH` | Config file path | `fieldboard.json` |
| `--repo PATH` | Repository path | `.` (current dir) |
| `--tool NAME` | Only run specific tool(s), repeatable | all enabled tools |
| `--json` | JSON output mode | terminal dashboard |
| `--no-color` | Disable ANSI colors | colors enabled |
| `--fail-fast` | Stop after first failure | run all tools |
| `--timeout SEC` | Per-tool timeout | `120` |
| `--verbose` | Show full stdout/stderr | summary only |

## Exit Codes

- **0**: All tools passed (or all skipped)
- **1**: One or more tools failed
- **2**: Configuration error or invalid flags

Useful for CI:

```bash
fieldboard run --repo . || echo "Quality gates failed"
```

## JSON Output

With `--json`, emit a machine-readable report:

```json
{
  "repo": "/home/user/myproject",
  "timestamp": "2026-08-19T10:00:00Z",
  "summary": {
    "total": 5,
    "passed": 4,
    "failed": 1,
    "skipped": 1
  },
  "tools": [
    {
      "name": "mdguard",
      "status": "pass",
      "exit_code": 0,
      "duration_ms": 210,
      "output": "...",
      "error": ""
    }
  ],
  "exit_code": 1
}
```

## Testing

```bash
pip install pytest
pytest tests/test_fieldboard.py -v
```

## Development

Lint with ruff:

```bash
ruff check fieldboard.py
```

Fix issues automatically:

```bash
ruff check fieldboard.py --fix
```

## License

MIT License — see LICENSE file.
