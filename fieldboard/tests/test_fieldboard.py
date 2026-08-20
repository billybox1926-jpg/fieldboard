import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Import the module under test
sys.path.insert(0, str(Path(__file__).parent.parent))
import fieldboard


class TestToolAvailability:
    """Test tool availability detection."""

    def test_tool_available_existing_command(self):
        """Test that existing commands are detected."""
        # python should always exist
        assert fieldboard.tool_available("python") is True

    def test_tool_available_nonexistent_command(self):
        """Test that non-existent commands are detected."""
        assert fieldboard.tool_available("nonexistent-command-xyz123") is False


class TestConfigLoading:
    """Test configuration loading."""

    def test_default_config(self):
        """Test default config is returned when no path specified."""
        config = fieldboard.load_config(None)
        assert "tools" in config
        assert len(config["tools"]) > 0

    def test_custom_config(self, tmp_path):
        """Test loading custom config file."""
        config_file = tmp_path / "test_config.json"
        custom_config = {
            "timeout_seconds": 60,
            "tools": [
                {
                    "name": "test-tool",
                    "command": "echo",
                    "args": ["hello"],
                    "enabled": True
                }
            ]
        }
        config_file.write_text(json.dumps(custom_config))

        config = fieldboard.load_config(str(config_file))
        assert config["timeout_seconds"] == 60
        assert len(config["tools"]) == 1
        assert config["tools"][0]["name"] == "test-tool"

    def test_invalid_json_config(self, tmp_path, capsys):
        """Test error handling for invalid JSON."""
        config_file = tmp_path / "invalid.json"
        config_file.write_text("{ invalid json }")

        with pytest.raises(SystemExit) as exc_info:
            fieldboard.load_config(str(config_file))

        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert "Invalid JSON" in captured.out


class TestRunTool:
    """Test tool execution."""

    def test_run_successful_tool(self, tmp_path):
        """Test running a tool that succeeds."""
        # Create a simple script that exits 0
        script = tmp_path / "success.sh"
        script.write_text("#!/bin/bash\necho 'success'\nexit 0\n")
        script.chmod(0o755)

        tool = {
            "name": "test-tool",
            "command": str(script),
            "args": [],
            "enabled": True
        }

        result = fieldboard.run_tool(tool, str(tmp_path), timeout=10)

        assert result["name"] == "test-tool"
        assert result["status"] == "pass"
        assert result["exit_code"] == 0
        assert result["duration_ms"] >= 0

    def test_run_failing_tool(self, tmp_path):
        """Test running a tool that fails."""
        script = tmp_path / "fail.sh"
        script.write_text("#!/bin/bash\necho 'error' >&2\nexit 1\n")
        script.chmod(0o755)

        tool = {
            "name": "test-tool",
            "command": str(script),
            "args": [],
            "enabled": True
        }

        result = fieldboard.run_tool(tool, str(tmp_path), timeout=10)

        assert result["status"] == "fail"
        assert result["exit_code"] == 1

    def test_run_missing_tool(self):
        """Test running a tool that doesn't exist."""
        tool = {
            "name": "missing-tool",
            "command": "nonexistent-command-xyz",
            "args": [],
            "enabled": True
        }

        result = fieldboard.run_tool(tool, ".", timeout=10)

        assert result["status"] == "skipped"
        assert result["exit_code"] is None
        assert "not found on PATH" in result["output"]

    def test_run_timeout(self, tmp_path):
        """Test tool timeout handling."""
        script = tmp_path / "slow.sh"
        script.write_text("#!/bin/bash\nsleep 10\n")
        script.chmod(0o755)

        tool = {
            "name": "slow-tool",
            "command": str(script),
            "args": [],
            "enabled": True
        }

        result = fieldboard.run_tool(tool, str(tmp_path), timeout=1)

        assert result["status"] == "fail"
        assert result["exit_code"] is None
        assert "Timed out" in result["error"]

    def test_run_expected_exit_codes(self, tmp_path):
        """Test custom expected exit codes."""
        script = tmp_path / "special.sh"
        script.write_text("#!/bin/bash\nexit 42\n")
        script.chmod(0o755)

        tool = {
            "name": "special-tool",
            "command": str(script),
            "args": [],
            "enabled": True,
            "expected_exit_codes": [0, 42]
        }

        result = fieldboard.run_tool(tool, str(tmp_path), timeout=10)

        assert result["status"] == "pass"
        assert result["exit_code"] == 42


class TestOutputFormatting:
    """Test output formatting functions."""

    def test_terminal_output_pass(self, capsys):
        """Test terminal output for passing tool."""
        results = [{
            "name": "test-tool",
            "status": "pass",
            "exit_code": 0,
            "duration_ms": 100,
            "output": "",
            "error": None
        }]

        fieldboard.format_terminal_output(results, "/test/repo", use_color=False, verbose=False)

        captured = capsys.readouterr()
        assert "FIELD BOARD" in captured.out
        assert "test-tool" in captured.out
        assert "PASS" in captured.out
        assert "100ms" in captured.out

    def test_terminal_output_fail(self, capsys):
        """Test terminal output for failing tool."""
        results = [{
            "name": "failing-tool",
            "status": "fail",
            "exit_code": 1,
            "duration_ms": 200,
            "output": "",
            "error": "Error: something went wrong"
        }]

        fieldboard.format_terminal_output(results, "/test/repo", use_color=False, verbose=False)

        captured = capsys.readouterr()
        assert "FAIL" in captured.out
        assert "something went wrong" in captured.out

    def test_terminal_output_skip(self, capsys):
        """Test terminal output for skipped tool."""
        results = [{
            "name": "missing-tool",
            "status": "skipped",
            "exit_code": None,
            "duration_ms": 0,
            "output": "command not found on PATH",
            "error": None
        }]

        fieldboard.format_terminal_output(results, "/test/repo", use_color=False, verbose=False)

        captured = capsys.readouterr()
        assert "SKIP" in captured.out

    def test_terminal_output_no_color(self, capsys):
        """Test that --no-color strips ANSI codes."""
        results = [{
            "name": "test-tool",
            "status": "pass",
            "exit_code": 0,
            "duration_ms": 100,
            "output": "",
            "error": None
        }]

        fieldboard.format_terminal_output(results, "/test/repo", use_color=False, verbose=False)

        captured = capsys.readouterr()
        # Check no ANSI escape codes
        assert "\033[" not in captured.out

    def test_json_output(self, capsys):
        """Test JSON output format."""
        results = [
            {
                "name": "tool1",
                "status": "pass",
                "exit_code": 0,
                "duration_ms": 100,
                "output": "",
                "error": None
            },
            {
                "name": "tool2",
                "status": "fail",
                "exit_code": 1,
                "duration_ms": 200,
                "output": "",
                "error": "failed"
            },
            {
                "name": "tool3",
                "status": "skipped",
                "exit_code": None,
                "duration_ms": 0,
                "output": "not found",
                "error": None
            }
        ]

        json_output = fieldboard.format_json_output(results, "/test/repo")
        report = json.loads(json_output)

        assert report["repo"] == os.path.abspath("/test/repo")
        assert "timestamp" in report
        assert report["summary"]["total"] == 3
        assert report["summary"]["passed"] == 1
        assert report["summary"]["failed"] == 1
        assert report["summary"]["skipped"] == 1
        assert report["exit_code"] == 1

    def test_json_output_all_pass(self):
        """Test JSON output when all tools pass."""
        results = [{
            "name": "tool1",
            "status": "pass",
            "exit_code": 0,
            "duration_ms": 100,
            "output": "",
            "error": None
        }]

        json_output = fieldboard.format_json_output(results, "/test/repo")
        report = json.loads(json_output)

        assert report["exit_code"] == 0


class TestCLI:
    """Test CLI functionality."""

    def test_version_flag(self, capsys):
        """Test --version flag."""
        with pytest.raises(SystemExit) as exc_info:
            fieldboard.main()

        # This will fail because we didn't pass any args
        # Let's test it properly
        sys.argv = ["fieldboard", "--version"]
        try:
            fieldboard.main()
        except SystemExit as e:
            assert e.code == 0

        captured = capsys.readouterr()
        assert fieldboard.VERSION in captured.out

    def test_init_command(self, tmp_path, capsys):
        """Test init command creates config file."""
        os.chdir(tmp_path)

        sys.argv = ["fieldboard", "init"]
        result = fieldboard.main()

        assert result == 0
        assert (tmp_path / "fieldboard.json").exists()

    def test_run_with_no_tools(self, capsys):
        """Test run with empty tools list."""
        sys.argv = ["fieldboard", "run", "--config", "nonexistent.json"]
        # This should use defaults since nonexistent.json doesn't exist but
        # we fall back to defaults for fieldboard.json specifically
        # Let's create an empty config instead
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"tools": []}, f)
            config_path = f.name

        try:
            sys.argv = ["fieldboard", "run", "--config", config_path]
            result = fieldboard.main()
            assert result == 0
        finally:
            os.unlink(config_path)

    def test_run_with_tool_filter(self, tmp_path, capsys):
        """Test --tool filter."""
        # Create two scripts
        script1 = tmp_path / "tool1.sh"
        script1.write_text("#!/bin/bash\necho tool1\n")
        script1.chmod(0o755)

        script2 = tmp_path / "tool2.sh"
        script2.write_text("#!/bin/bash\necho tool2\n")
        script2.chmod(0o755)

        config = {
            "tools": [
                {"name": "tool1", "command": str(script1), "args": [], "enabled": True},
                {"name": "tool2", "command": str(script2), "args": [], "enabled": True}
            ]
        }

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config))

        sys.argv = ["fieldboard", "run", "--config", str(config_file), "--tool", "tool1"]
        result = fieldboard.main()

        captured = capsys.readouterr()
        assert "tool1" in captured.out
        assert "tool2" not in captured.out


class TestIntegration:
    """Integration tests with fake tools."""

    def test_full_run_with_fake_tools(self, tmp_path, capsys):
        """Test complete run with fake tools."""
        # Create fake tools
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()

        pass_tool = tools_dir / "pass-tool"
        pass_tool.write_text("#!/bin/bash\necho 'PASS'\nexit 0\n")
        pass_tool.chmod(0o755)

        fail_tool = tools_dir / "fail-tool"
        fail_tool.write_text("#!/bin/bash\necho 'FAIL' >&2\nexit 1\n")
        fail_tool.chmod(0o755)

        # Create config
        config = {
            "tools": [
                {"name": "passing", "command": str(pass_tool), "args": [], "enabled": True},
                {"name": "failing", "command": str(fail_tool), "args": [], "enabled": True}
            ]
        }

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config))

        # Run fieldboard
        sys.argv = ["fieldboard", "run", "--config", str(config_file)]
        result = fieldboard.main()

        captured = capsys.readouterr()

        assert result == 1  # One tool failed
        assert "PASS" in captured.out
        assert "FAIL" in captured.out
        assert "1 passed, 1 failed" in captured.out

    def test_fail_fast(self, tmp_path, capsys):
        """Test --fail-fast stops after first failure."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()

        fail_tool = tools_dir / "fail-tool"
        fail_tool.write_text("#!/bin/bash\nexit 1\n")
        fail_tool.chmod(0o755)

        pass_tool = tools_dir / "pass-tool"
        pass_tool.write_text("#!/bin/bash\necho 'should not reach here'\n")
        pass_tool.chmod(0o755)

        config = {
            "tools": [
                {"name": "first", "command": str(fail_tool), "args": [], "enabled": True},
                {"name": "second", "command": str(pass_tool), "args": [], "enabled": True}
            ]
        }

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config))

        sys.argv = ["fieldboard", "run", "--config", str(config_file), "--fail-fast"]
        result = fieldboard.main()

        captured = capsys.readouterr()

        # Should only show first tool (the failing one)
        assert "first" in captured.out
        assert "second" not in captured.out

    def test_json_mode(self, tmp_path, capsys):
        """Test --json output mode."""
        script = tmp_path / "tool.sh"
        script.write_text("#!/bin/bash\necho ok\n")
        script.chmod(0o755)

        config = {
            "tools": [
                {"name": "test", "command": str(script), "args": [], "enabled": True}
            ]
        }

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config))

        sys.argv = ["fieldboard", "run", "--config", str(config_file), "--json"]
        result = fieldboard.main()

        captured = capsys.readouterr()
        report = json.loads(captured.out)

        assert "summary" in report
        assert "tools" in report
        assert result == 0

    def test_repo_directory(self, tmp_path, capsys):
        """Test --repo runs tools in correct directory."""
        # Create a tool that prints current directory
        script = tmp_path / "pwd-tool"
        script.write_text("#!/bin/bash\npwd\n")
        script.chmod(0o755)

        target_dir = tmp_path / "target"
        target_dir.mkdir()

        config = {
            "tools": [
                {"name": "pwd", "command": str(script), "args": [], "enabled": True}
            ]
        }

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config))

        sys.argv = [
            "fieldboard", "run", "--config", str(config_file),
            "--repo", str(target_dir), "--verbose"
        ]
        fieldboard.main()

        captured = capsys.readouterr()

        assert str(target_dir) in captured.out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
