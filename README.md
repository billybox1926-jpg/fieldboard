# fieldboard

**Terminal dashboard for running local repo quality tools.**

Run multiple quality tools as subprocesses, capture results, and display a clean terminal dashboard or JSON report.

## The Problem

> Manually running `mdguard`, `graft`, `policy-runner`, `dep-health-scanner`, and `config-drift` one at a time is tedious.

## Quick Start

```bash
# Clone and run
git clone https://github.com/billybox1926-jpg/fieldboard.git
cd fieldboard

# Initialize config
python fieldboard.py init

# Run all configured tools in current repo
python fieldboard.py run

# Run specific tools only
python fieldboard.py run --tool mdguard --tool config-drift

# JSON output for CI
python fieldboard.py run --json
```

## Features

- **Zero dependencies** — Python 3.9+ stdlib only
- **Multiple tools** — Run any CLI tool as a subprocess
- **Configurable** — JSON config file for tool definitions
- **Flexible output** — Terminal dashboard or JSON
- **Smart detection** — Skips tools not on PATH
- **Fail-fast mode** — Stop after first failure
- **Timeout handling** — Per-tool timeout with graceful failure
- **CI-friendly** — Exit codes: 0=pass, 1=fail, 2=config error

## CLI Usage

```
python fieldboard.py run [--config PATH] [--repo PATH] [--tool NAME]
                          [--json] [--no-color] [--fail-fast] [--timeout SEC]
                          [--verbose]

python fieldboard.py init [--config PATH]
```

## Configuration

Create `fieldboard.json`:

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
      "name": "config-drift",
      "command": "config-drift",
      "args": ["diff", "--configs-root", "./configs"],
      "enabled": false
    }
  ]
}
```

Each tool supports:

| Field | Description |
|-------|-------------|
| `name` | Display name |
| `command` | Executable name (must be on PATH) |
| `args` | List of arguments |
| `enabled` | Boolean, default true |
| `expected_exit_codes` | Optional list, default `[0]` |

## Terminal Output

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

## JSON Output

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
  "tools": [...],
  "exit_code": 1
}
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All tools passed |
| 1 | At least one tool failed |
| 2 | Configuration error |

## License

MIT
