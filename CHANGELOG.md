# Changelog

All notable changes to this project will be documented in this file.

## [0.1.1] - 2026-08-19

### Security
- **Command injection hardening** — `command` field is validated against
  `^[A-Za-z0-9._\-/\\:]+$`; commands containing shell metacharacters
  (`;`, `|`, `&`, `` ` ``, `$`, `>`, spaces) are rejected as skipped
- **Explicit `shell=False`** — subprocess invocation is now explicit about
  never using a shell
- **Path validation** — `--repo` is resolved with `Path.resolve(strict=True)`
  and must be an existing directory
- **`--safe` mode** — new flag restricting execution to a whitelist of known
  tool binaries, for use with untrusted config files

### Added
- Security Considerations section in README
- mypy type checking in CI
- 20 new security tests (command validation, path validation, safe mode,
  injection rejection)

### Changed
- Test suite: 56 → 76 tests, coverage 97% → 98%

## [0.1.0] - 2026-08-19

### Added
- Initial release
- Zero-dependency CLI (Python 3.9+)
- Run multiple quality tools as subprocesses
- Terminal dashboard with colored output
- JSON output mode for CI
- Config file support (fieldboard.json)
- Tool availability detection (skips tools not on PATH)
- Per-tool timeout handling
- Fail-fast mode
- Exit codes: 0=pass, 1=fail, 2=config error
