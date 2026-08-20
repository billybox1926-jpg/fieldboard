#!/usr/bin/env python3
"""Tests for fieldboard v0.1.0."""

import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import fieldboard


class TestToolAvailable(unittest.TestCase):
    """Test tool availability checking."""

    def test_tool_available_found(self):
        """Test that available tool is detected."""
        with patch("shutil.which", return_value="/usr/bin/python"):
            self.assertTrue(fieldboard.tool_available("python"))

    def test_tool_available_not_found(self):
        """Test that missing tool is detected."""
        with patch("shutil.which", return_value=None):
            self.assertFalse(fieldboard.tool_available("nonexistent_tool"))


class TestLoadConfig(unittest.TestCase):
    """Test config loading."""

    def test_load_existing_config(self):
        """Test loading existing config file."""
        fd, path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({"timeout_seconds": 60}, f)
            config = fieldboard.load_config(path)
            self.assertEqual(config["timeout_seconds"], 60)
        finally:
            os.unlink(path)

    def test_load_missing_config(self):
        """Test loading missing config returns empty dict."""
        config = fieldboard.load_config("/nonexistent/path.json")
        self.assertEqual(config, {})

    def test_load_invalid_config(self):
        """Test loading invalid JSON exits with code 2."""
        fd, path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                f.write("{invalid json")
            with self.assertRaises(SystemExit) as ctx:
                fieldboard.load_config(path)
            self.assertEqual(ctx.exception.code, 2)
        finally:
            os.unlink(path)

    def test_load_config_with_explicit_path(self):
        """Test loading config with explicit path."""
        fd, path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({"custom": "value"}, f)
            config = fieldboard.load_config(path)
            self.assertEqual(config["custom"], "value")
        finally:
            os.unlink(path)


class TestGetDefaultConfig(unittest.TestCase):
    """Test default config generation."""

    def test_default_config_structure(self):
        """Test default config has expected structure."""
        config = fieldboard.get_default_config()
        self.assertIn("repo", config)
        self.assertIn("timeout_seconds", config)
        self.assertIn("tools", config)
        self.assertGreater(len(config["tools"]), 0)

    def test_default_tools_have_required_fields(self):
        """Test default tools have name, command, args, enabled."""
        config = fieldboard.get_default_config()
        for tool in config["tools"]:
            self.assertIn("name", tool)
            self.assertIn("command", tool)
            self.assertIn("args", tool)
            self.assertIn("enabled", tool)

    def test_default_config_has_5_tools(self):
        """Test default config has 5 tools."""
        config = fieldboard.get_default_config()
        self.assertEqual(len(config["tools"]), 5)

    def test_default_config_timeout(self):
        """Test default timeout is 120 seconds."""
        config = fieldboard.get_default_config()
        self.assertEqual(config["timeout_seconds"], 120)


class TestRunTool(unittest.TestCase):
    """Test tool execution."""

    def test_run_tool_success(self):
        """Test successful tool execution."""
        tool = {
            "name": "test-tool",
            "command": "python",
            "args": ["-c", "print('hello')"],
            "enabled": True,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fieldboard.run_tool(tool, tmpdir, 10)
            self.assertEqual(result["name"], "test-tool")
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["exit_code"], 0)
            self.assertIn("hello", result["output"])

    def test_run_tool_failure(self):
        """Test failed tool execution."""
        tool = {
            "name": "test-tool",
            "command": "python",
            "args": ["-c", "import sys; sys.exit(1)"],
            "enabled": True,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fieldboard.run_tool(tool, tmpdir, 10)
            self.assertEqual(result["status"], "fail")
            self.assertEqual(result["exit_code"], 1)

    def test_run_tool_disabled(self):
        """Test disabled tool is skipped."""
        tool = {
            "name": "test-tool",
            "command": "python",
            "args": [],
            "enabled": False,
        }
        result = fieldboard.run_tool(tool, ".", 10)
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["error"], "disabled in config")

    def test_run_tool_not_found(self):
        """Test missing tool is skipped."""
        tool = {
            "name": "test-tool",
            "command": "nonexistent_tool_xyz",
            "args": [],
            "enabled": True,
        }
        result = fieldboard.run_tool(tool, ".", 10)
        self.assertEqual(result["status"], "skipped")
        self.assertIn("not found", result["error"])

    def test_run_tool_timeout(self):
        """Test tool timeout handling."""
        tool = {
            "name": "test-tool",
            "command": "python",
            "args": ["-c", "import time; time.sleep(10)"],
            "enabled": True,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fieldboard.run_tool(tool, tmpdir, 1)
            self.assertEqual(result["status"], "fail")
            self.assertIn("Timed out", result["error"])

    def test_run_tool_custom_exit_code(self):
        """Test custom expected exit codes."""
        tool = {
            "name": "test-tool",
            "command": "python",
            "args": ["-c", "import sys; sys.exit(2)"],
            "enabled": True,
            "expected_exit_codes": [0, 2],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fieldboard.run_tool(tool, tmpdir, 10)
            self.assertEqual(result["status"], "pass")

    def test_run_tool_verbose(self):
        """Test verbose mode includes stderr."""
        tool = {
            "name": "test-tool",
            "command": "python",
            "args": ["-c", "import sys; sys.stderr.write('error msg')"],
            "enabled": True,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fieldboard.run_tool(tool, tmpdir, 10, verbose=True)
            self.assertIn("error msg", result["output"])

    def test_run_tool_oserror(self):
        """Test OSError handling."""
        tool = {
            "name": "test-tool",
            "command": "python",
            "args": [],
            "enabled": True,
        }
        with patch("subprocess.run", side_effect=OSError("permission denied")):
            result = fieldboard.run_tool(tool, ".", 10)
            self.assertEqual(result["status"], "fail")
            self.assertIn("permission denied", result["error"])

    def test_run_tool_duration_tracked(self):
        """Test that duration is tracked."""
        tool = {
            "name": "test-tool",
            "command": "python",
            "args": ["-c", "pass"],
            "enabled": True,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fieldboard.run_tool(tool, tmpdir, 10)
            self.assertGreaterEqual(result["duration_ms"], 0)

    def test_run_tool_stderr_captured(self):
        """Test that stderr is captured on failure."""
        tool = {
            "name": "test-tool",
            "command": "python",
            "args": ["-c", "import sys; sys.stderr.write('err'); sys.exit(1)"],
            "enabled": True,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fieldboard.run_tool(tool, tmpdir, 10)
            self.assertIn("err", result["error"])


class TestFormatTerminal(unittest.TestCase):
    """Test terminal output formatting."""

    def test_format_terminal_basic(self):
        """Test basic terminal formatting."""
        results = [
            {
                "name": "tool1",
                "status": "pass",
                "duration_ms": 100,
                "output": "",
                "error": "",
            },
            {
                "name": "tool2",
                "status": "fail",
                "duration_ms": 200,
                "output": "",
                "error": "some error",
            },
        ]
        output = fieldboard.format_terminal(results, "/repo", no_color=True)
        self.assertIn("FIELD BOARD", output)
        self.assertIn("tool1", output)
        self.assertIn("tool2", output)
        self.assertIn("PASS", output)
        self.assertIn("FAIL", output)
        self.assertIn("1 passed, 1 failed", output)

    def test_format_terminal_with_skipped(self):
        """Test terminal formatting with skipped tools."""
        results = [
            {
                "name": "tool1",
                "status": "pass",
                "duration_ms": 100,
                "output": "",
                "error": "",
            },
            {
                "name": "tool2",
                "status": "skipped",
                "duration_ms": 0,
                "output": "",
                "error": "not found",
            },
        ]
        output = fieldboard.format_terminal(results, "/repo", no_color=True)
        self.assertIn("SKIP", output)
        self.assertIn("1 passed, 0 failed, 1 skipped", output)

    def test_format_terminal_no_color(self):
        """Test no-color mode strips ANSI codes."""
        results = [
            {
                "name": "tool1",
                "status": "pass",
                "duration_ms": 100,
                "output": "",
                "error": "",
            },
        ]
        output = fieldboard.format_terminal(results, "/repo", no_color=True)
        self.assertNotIn("\033[", output)

    def test_format_terminal_verbose(self):
        """Test verbose mode shows output."""
        results = [
            {
                "name": "tool1",
                "status": "pass",
                "duration_ms": 100,
                "output": "some output",
                "error": "",
            },
        ]
        output = fieldboard.format_terminal(
            results, "/repo", no_color=True, verbose=True
        )
        self.assertIn("some output", output)

    def test_format_terminal_with_color(self):
        """Test color mode includes ANSI codes."""
        results = [
            {
                "name": "tool1",
                "status": "pass",
                "duration_ms": 100,
                "output": "",
                "error": "",
            },
        ]
        output = fieldboard.format_terminal(results, "/repo", no_color=False)
        self.assertIn("\033[", output)

    def test_format_terminal_all_pass(self):
        """Test terminal output when all tools pass."""
        results = [
            {
                "name": "t1",
                "status": "pass",
                "duration_ms": 100,
                "output": "",
                "error": "",
            },
            {
                "name": "t2",
                "status": "pass",
                "duration_ms": 200,
                "output": "",
                "error": "",
            },
        ]
        output = fieldboard.format_terminal(results, "/repo", no_color=True)
        self.assertIn("2 passed, 0 failed, 0 skipped", output)

    def test_format_terminal_all_fail(self):
        """Test terminal output when all tools fail."""
        results = [
            {
                "name": "t1",
                "status": "fail",
                "duration_ms": 100,
                "output": "",
                "error": "err1",
            },
            {
                "name": "t2",
                "status": "fail",
                "duration_ms": 200,
                "output": "",
                "error": "err2",
            },
        ]
        output = fieldboard.format_terminal(results, "/repo", no_color=True)
        self.assertIn("0 passed, 2 failed, 0 skipped", output)

    def test_format_terminal_empty_results(self):
        """Test terminal output with no results."""
        output = fieldboard.format_terminal([], "/repo", no_color=True)
        self.assertIn("FIELD BOARD", output)
        self.assertIn("0 passed, 0 failed, 0 skipped", output)

    def test_format_terminal_shows_error_detail(self):
        """Test that error detail is shown for failed tools."""
        results = [
            {
                "name": "tool1",
                "status": "fail",
                "duration_ms": 100,
                "output": "",
                "error": "something went wrong",
            },
        ]
        output = fieldboard.format_terminal(results, "/repo", no_color=True)
        self.assertIn("something went wrong", output)

    def test_format_terminal_skipped_detail(self):
        """Test that skipped reason is shown."""
        results = [
            {
                "name": "tool1",
                "status": "skipped",
                "duration_ms": 0,
                "output": "",
                "error": "not found on PATH",
            },
        ]
        output = fieldboard.format_terminal(results, "/repo", no_color=True)
        self.assertIn("not found on PATH", output)

    def test_format_terminal_duration_dash_for_zero(self):
        """Test that zero duration shows as dash."""
        results = [
            {
                "name": "tool1",
                "status": "skipped",
                "duration_ms": 0,
                "output": "",
                "error": "",
            },
        ]
        output = fieldboard.format_terminal(results, "/repo", no_color=True)
        self.assertIn("─", output)


class TestFormatJson(unittest.TestCase):
    """Test JSON output formatting."""

    def test_format_json_basic(self):
        """Test basic JSON formatting."""
        results = [
            {
                "name": "tool1",
                "status": "pass",
                "exit_code": 0,
                "duration_ms": 100,
                "output": "",
                "error": "",
            },
            {
                "name": "tool2",
                "status": "fail",
                "exit_code": 1,
                "duration_ms": 200,
                "output": "",
                "error": "err",
            },
        ]
        output = fieldboard.format_json(results, "/repo", 1)
        parsed = json.loads(output)
        self.assertEqual(parsed["repo"], str(Path("/repo").resolve()))
        self.assertEqual(parsed["summary"]["total"], 2)
        self.assertEqual(parsed["summary"]["passed"], 1)
        self.assertEqual(parsed["summary"]["failed"], 1)
        self.assertEqual(parsed["exit_code"], 1)
        self.assertIn("tools", parsed)
        self.assertIn("timestamp", parsed)

    def test_format_json_empty(self):
        """Test JSON formatting with no results."""
        output = fieldboard.format_json([], "/repo", 0)
        parsed = json.loads(output)
        self.assertEqual(parsed["summary"]["total"], 0)

    def test_format_json_all_pass(self):
        """Test JSON output when all tools pass."""
        results = [
            {
                "name": "t1",
                "status": "pass",
                "exit_code": 0,
                "duration_ms": 100,
                "output": "",
                "error": "",
            },
        ]
        output = fieldboard.format_json(results, "/repo", 0)
        parsed = json.loads(output)
        self.assertEqual(parsed["summary"]["passed"], 1)
        self.assertEqual(parsed["summary"]["failed"], 0)
        self.assertEqual(parsed["exit_code"], 0)

    def test_format_json_includes_all_tools(self):
        """Test JSON output includes all tool results."""
        results = [
            {
                "name": "t1",
                "status": "pass",
                "exit_code": 0,
                "duration_ms": 100,
                "output": "out",
                "error": "err",
            },
            {
                "name": "t2",
                "status": "fail",
                "exit_code": 1,
                "duration_ms": 200,
                "output": "",
                "error": "fail err",
            },
        ]
        output = fieldboard.format_json(results, "/repo", 1)
        parsed = json.loads(output)
        self.assertEqual(len(parsed["tools"]), 2)
        self.assertEqual(parsed["tools"][0]["name"], "t1")
        self.assertEqual(parsed["tools"][1]["name"], "t2")


class TestRunCommand(unittest.TestCase):
    """Test run command."""

    def test_run_command_with_defaults(self):
        """Test run command with default config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake tool using Python
            tool_path = Path(tmpdir) / "fake_tool.py"
            tool_path.write_text("#!/usr/bin/env python\nprint('ok')\n")

            config = {
                "repo": tmpdir,
                "timeout_seconds": 10,
                "tools": [
                    {
                        "name": "fake",
                        "command": "python",
                        "args": [str(tool_path)],
                        "enabled": True,
                    }
                ],
            }
            config_path = Path(tmpdir) / "fieldboard.json"
            config_path.write_text(json.dumps(config))

            args = argparse.Namespace(
                config=str(config_path),
                repo=tmpdir,
                tool=None,
                json=False,
                no_color=True,
                fail_fast=False,
                timeout=10,
                verbose=False,
            )
            exit_code = fieldboard.run_command(args)
            self.assertEqual(exit_code, 0)

    def test_run_command_with_tool_filter(self):
        """Test run command with tool filter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create fake tools using Python
            tool1_path = Path(tmpdir) / "tool1.py"
            tool1_path.write_text("#!/usr/bin/env python\nprint('ok')\n")

            tool2_path = Path(tmpdir) / "tool2.py"
            tool2_path.write_text("#!/usr/bin/env python\nprint('ok')\n")

            config = {
                "repo": tmpdir,
                "timeout_seconds": 10,
                "tools": [
                    {
                        "name": "tool1",
                        "command": "python",
                        "args": [str(tool1_path)],
                        "enabled": True,
                    },
                    {
                        "name": "tool2",
                        "command": "python",
                        "args": [str(tool2_path)],
                        "enabled": True,
                    },
                ],
            }
            config_path = Path(tmpdir) / "fieldboard.json"
            config_path.write_text(json.dumps(config))

            args = argparse.Namespace(
                config=str(config_path),
                repo=tmpdir,
                tool=["tool1"],
                json=True,
                no_color=True,
                fail_fast=False,
                timeout=10,
                verbose=False,
            )
            exit_code = fieldboard.run_command(args)
            self.assertEqual(exit_code, 0)

    def test_run_command_invalid_repo(self):
        """Test run command with invalid repo path."""
        args = argparse.Namespace(
            config=None,
            repo="/nonexistent/path",
            tool=None,
            json=False,
            no_color=True,
            fail_fast=False,
            timeout=10,
            verbose=False,
        )
        exit_code = fieldboard.run_command(args)
        self.assertEqual(exit_code, 2)

    def test_run_command_fail_fast(self):
        """Test fail-fast stops after first failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create failing tool
            fail_path = Path(tmpdir) / "fail_tool"
            fail_path.write_text("#!/bin/sh\nexit 1\n")
            fail_path.chmod(0o755)

            # Create passing tool
            pass_path = Path(tmpdir) / "pass_tool"
            pass_path.write_text("#!/bin/sh\necho 'ok'\n")
            pass_path.chmod(0o755)

            config = {
                "repo": tmpdir,
                "timeout_seconds": 10,
                "tools": [
                    {
                        "name": "fail",
                        "command": str(fail_path),
                        "args": [],
                        "enabled": True,
                    },
                    {
                        "name": "pass",
                        "command": str(pass_path),
                        "args": [],
                        "enabled": True,
                    },
                ],
            }
            config_path = Path(tmpdir) / "fieldboard.json"
            config_path.write_text(json.dumps(config))

            args = argparse.Namespace(
                config=str(config_path),
                repo=tmpdir,
                tool=None,
                json=True,
                no_color=True,
                fail_fast=True,
                timeout=10,
                verbose=False,
            )
            exit_code = fieldboard.run_command(args)
            self.assertEqual(exit_code, 1)

    def test_run_command_json_output(self):
        """Test run command with JSON output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool_path = Path(tmpdir) / "tool.py"
            tool_path.write_text("#!/usr/bin/env python\nprint('ok')\n")

            config = {
                "repo": tmpdir,
                "timeout_seconds": 10,
                "tools": [
                    {
                        "name": "tool1",
                        "command": "python",
                        "args": [str(tool_path)],
                        "enabled": True,
                    }
                ],
            }
            config_path = Path(tmpdir) / "fieldboard.json"
            config_path.write_text(json.dumps(config))

            args = argparse.Namespace(
                config=str(config_path),
                repo=tmpdir,
                tool=None,
                json=True,
                no_color=True,
                fail_fast=False,
                timeout=10,
                verbose=False,
            )
            exit_code = fieldboard.run_command(args)
            self.assertEqual(exit_code, 0)

    def test_run_command_no_tools(self):
        """Test run command with no tools to run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "repo": tmpdir,
                "timeout_seconds": 10,
                "tools": [],
            }
            config_path = Path(tmpdir) / "fieldboard.json"
            config_path.write_text(json.dumps(config))

            args = argparse.Namespace(
                config=str(config_path),
                repo=tmpdir,
                tool=None,
                json=False,
                no_color=True,
                fail_fast=False,
                timeout=10,
                verbose=False,
            )
            exit_code = fieldboard.run_command(args)
            self.assertEqual(exit_code, 2)

    def test_run_command_uses_default_config(self):
        """Test run command uses default config when no config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            args = argparse.Namespace(
                config=None,
                repo=tmpdir,
                tool=None,
                json=False,
                no_color=True,
                fail_fast=False,
                timeout=10,
                verbose=False,
            )
            # Should use default config (which has tools that aren't on PATH)
            exit_code = fieldboard.run_command(args)
            # All tools will be skipped since they're not on PATH
            self.assertEqual(exit_code, 0)

    def test_run_command_with_timeout_override(self):
        """Test run command with timeout override."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool_path = Path(tmpdir) / "tool.py"
            tool_path.write_text("#!/usr/bin/env python\nprint('ok')\n")

            config = {
                "repo": tmpdir,
                "timeout_seconds": 10,
                "tools": [
                    {
                        "name": "tool1",
                        "command": "python",
                        "args": [str(tool_path)],
                        "enabled": True,
                    }
                ],
            }
            config_path = Path(tmpdir) / "fieldboard.json"
            config_path.write_text(json.dumps(config))

            args = argparse.Namespace(
                config=str(config_path),
                repo=tmpdir,
                tool=None,
                json=False,
                no_color=True,
                fail_fast=False,
                timeout=30,
                verbose=False,
            )
            exit_code = fieldboard.run_command(args)
            self.assertEqual(exit_code, 0)

    def test_run_command_all_skipped(self):
        """Test run command when all tools are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "repo": tmpdir,
                "timeout_seconds": 10,
                "tools": [
                    {
                        "name": "missing",
                        "command": "nonexistent_tool",
                        "args": [],
                        "enabled": True,
                    }
                ],
            }
            config_path = Path(tmpdir) / "fieldboard.json"
            config_path.write_text(json.dumps(config))

            args = argparse.Namespace(
                config=str(config_path),
                repo=tmpdir,
                tool=None,
                json=False,
                no_color=True,
                fail_fast=False,
                timeout=10,
                verbose=False,
            )
            exit_code = fieldboard.run_command(args)
            self.assertEqual(exit_code, 0)


class TestInitCommand(unittest.TestCase):
    """Test init command."""

    def test_init_creates_config(self):
        """Test that init creates a config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            try:
                os.chdir(tmpdir)
                args = argparse.Namespace(config=None)
                fieldboard.init_command(args)
                self.assertTrue(os.path.exists("fieldboard.json"))
                with open("fieldboard.json") as f:
                    config = json.load(f)
                self.assertIn("tools", config)
            finally:
                os.chdir(original_dir)

    def test_init_overwrite_prompt(self):
        """Test that init prompts before overwriting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            try:
                os.chdir(tmpdir)
                # Create existing config
                with open("fieldboard.json", "w") as f:
                    json.dump({"test": True}, f)

                args = argparse.Namespace(config=None)
                with patch("builtins.input", return_value="n"):
                    fieldboard.init_command(args)

                # Config should not be overwritten
                with open("fieldboard.json") as f:
                    config = json.load(f)
                self.assertIn("test", config)
            finally:
                os.chdir(original_dir)

    def test_init_overwrite_with_yes(self):
        """Test that init overwrites when user says yes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            try:
                os.chdir(tmpdir)
                # Create existing config
                with open("fieldboard.json", "w") as f:
                    json.dump({"test": True}, f)

                args = argparse.Namespace(config=None)
                with patch("builtins.input", return_value="y"):
                    fieldboard.init_command(args)

                # Config should be overwritten with default
                with open("fieldboard.json") as f:
                    config = json.load(f)
                self.assertIn("tools", config)
                self.assertNotIn("test", config)
            finally:
                os.chdir(original_dir)

    def test_init_custom_config_path(self):
        """Test init with custom config path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            try:
                os.chdir(tmpdir)
                custom_path = "custom_board.json"
                args = argparse.Namespace(config=custom_path)
                fieldboard.init_command(args)
                self.assertTrue(os.path.exists(custom_path))
            finally:
                os.chdir(original_dir)


class TestMain(unittest.TestCase):
    """Test main function."""

    def test_main_run_command(self):
        """Test main with run command."""
        with patch("argparse.ArgumentParser.parse_args") as mock_args:
            mock_args.return_value = argparse.Namespace(
                command="run",
                config=None,
                repo=None,
                tool=None,
                json=False,
                no_color=True,
                fail_fast=False,
                timeout=None,
                verbose=False,
            )
            with self.assertRaises(SystemExit) as ctx:
                fieldboard.main()
            # Should exit with code from run_command
            self.assertIn(ctx.exception.code, [0, 1, 2])

    def test_main_init_command(self):
        """Test main with init command."""
        with patch("argparse.ArgumentParser.parse_args") as mock_args:
            mock_args.return_value = argparse.Namespace(
                command="init",
                config=None,
            )
            with tempfile.TemporaryDirectory() as tmpdir:
                original_dir = os.getcwd()
                try:
                    os.chdir(tmpdir)
                    with self.assertRaises(SystemExit) as ctx:
                        fieldboard.main()
                    self.assertEqual(ctx.exception.code, 0)
                finally:
                    os.chdir(original_dir)

    def test_main_no_command(self):
        """Test main with no command prints help."""
        with patch("argparse.ArgumentParser.parse_args") as mock_args:
            mock_args.return_value = argparse.Namespace(
                command=None,
            )
            with self.assertRaises(SystemExit) as ctx:
                fieldboard.main()
            self.assertEqual(ctx.exception.code, 1)

    def test_main_version_flag(self):
        """Test main with --version flag."""
        with self.assertRaises(SystemExit) as ctx:
            with patch("sys.argv", ["fieldboard", "--version"]):
                fieldboard.main()
            self.assertEqual(ctx.exception.code, 0)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases."""

    def test_run_tool_with_no_args(self):
        """Test run tool with no args."""
        tool = {
            "name": "test",
            "command": "python",
            "args": [],
            "enabled": True,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fieldboard.run_tool(tool, tmpdir, 10)
            self.assertEqual(result["status"], "pass")

    def test_run_tool_with_multiple_args(self):
        """Test run tool with multiple args."""
        tool = {
            "name": "test",
            "command": "python",
            "args": ["-c", "import sys; print(sys.argv[1])", "arg1"],
            "enabled": True,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fieldboard.run_tool(tool, tmpdir, 10)
            self.assertIn("arg1", result["output"])

    def test_format_terminal_long_tool_name(self):
        """Test terminal formatting with long tool name."""
        results = [
            {
                "name": "very-long-tool-name-that-is-long",
                "status": "pass",
                "duration_ms": 100,
                "output": "",
                "error": "",
            },
        ]
        output = fieldboard.format_terminal(results, "/repo", no_color=True)
        self.assertIn("very-long-tool-name-that-is-long", output)

    def test_format_terminal_multiline_error(self):
        """Test terminal formatting with multiline error."""
        results = [
            {
                "name": "tool1",
                "status": "fail",
                "duration_ms": 100,
                "output": "",
                "error": "line1\nline2\nline3",
            },
        ]
        output = fieldboard.format_terminal(results, "/repo", no_color=True)
        self.assertIn("line1", output)
        # Should only show first line
        self.assertNotIn("line2", output)


if __name__ == "__main__":
    unittest.main()
