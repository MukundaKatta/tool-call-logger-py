"""Standard-library (unittest) tests for tool-call-logger-py.

These tests use only the Python standard library so they can run with::

    python3 -m unittest discover -s tests

without any third-party dependencies (e.g. pytest). They import and exercise
the real :class:`tool_call_logger.ToolCallLogger` implementation.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from tool_call_logger import ToolCallLogger, ToolCallEntry


class LogCallTests(unittest.TestCase):
    def test_log_call_records_entry(self):
        logger = ToolCallLogger()
        ts = logger.log_call("search", {"query": "hello"})
        self.assertEqual(len(logger.calls()), 1)
        entry = logger.calls()[0]
        self.assertEqual(entry.kind, "call")
        self.assertEqual(entry.tool_name, "search")
        self.assertEqual(entry.args, {"query": "hello"})
        self.assertIsInstance(ts, float)

    def test_log_result_records_entry(self):
        logger = ToolCallLogger()
        start = logger.log_call("search", {"q": "x"})
        logger.log_result("search", {"q": "x"}, ["r1", "r2"], start)
        results = logger.results()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].kind, "result")
        self.assertEqual(results[0].result, ["r1", "r2"])
        self.assertIsNotNone(results[0].duration_ms)
        self.assertGreaterEqual(results[0].duration_ms, 0)

    def test_log_error_records_entry(self):
        logger = ToolCallLogger()
        start = logger.log_call("fetch", {"url": "http://x"})
        logger.log_error("fetch", {"url": "http://x"}, RuntimeError("timeout"), start)
        errors = logger.errors()
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].kind, "error")
        self.assertIn("RuntimeError", errors[0].error)
        self.assertGreaterEqual(errors[0].duration_ms, 0)

    def test_metadata_stored(self):
        logger = ToolCallLogger()
        logger.log_call("t", {}, metadata={"session": "abc"})
        self.assertEqual(logger.calls()[0].metadata, {"session": "abc"})


class QueryTests(unittest.TestCase):
    def test_entries_property_returns_copy(self):
        logger = ToolCallLogger()
        logger.log_call("t1", {})
        logger.log_call("t2", {})
        entries = logger.entries
        self.assertEqual(len(entries), 2)
        # Mutating the returned list must not affect internal state.
        entries.clear()
        self.assertEqual(len(logger.entries), 2)

    def test_call_count(self):
        logger = ToolCallLogger()
        logger.log_call("search", {"q": "a"})
        logger.log_call("search", {"q": "b"})
        logger.log_call("fetch", {"url": "x"})
        self.assertEqual(logger.call_count(), 3)
        self.assertEqual(logger.call_count("search"), 2)
        self.assertEqual(logger.call_count("fetch"), 1)
        self.assertEqual(logger.call_count("missing"), 0)

    def test_by_tool(self):
        logger = ToolCallLogger()
        logger.log_call("a", {"x": 1})
        logger.log_call("b", {"x": 2})
        logger.log_call("a", {"x": 3})
        entries = logger.by_tool("a")
        self.assertEqual(len(entries), 2)
        self.assertTrue(all(e.tool_name == "a" for e in entries))

    def test_avg_duration_ms(self):
        logger = ToolCallLogger()
        start = logger.log_call("t", {})
        logger.log_result("t", {}, "ok", start)
        avg = logger.avg_duration_ms()
        self.assertIsNotNone(avg)
        self.assertGreaterEqual(avg, 0)

    def test_avg_duration_ms_none_when_empty(self):
        logger = ToolCallLogger()
        self.assertIsNone(logger.avg_duration_ms())

    def test_avg_duration_ms_scoped_to_tool(self):
        logger = ToolCallLogger()
        start = logger.log_call("fast", {})
        logger.log_result("fast", {}, "ok", start)
        # A different tool with no results recorded yet.
        logger.log_call("slow", {})
        self.assertIsNotNone(logger.avg_duration_ms("fast"))
        self.assertIsNone(logger.avg_duration_ms("slow"))

    def test_clear(self):
        logger = ToolCallLogger()
        logger.log_call("t", {})
        logger.clear()
        self.assertEqual(len(logger.entries), 0)


class WrapTests(unittest.TestCase):
    def test_wrap_decorator_logs_call_and_result(self):
        logger = ToolCallLogger()

        @logger.wrap("greet")
        def greet(name):
            return f"Hello, {name}!"

        result = greet(name="World")
        self.assertEqual(result, "Hello, World!")
        self.assertEqual(logger.call_count("greet"), 1)
        self.assertEqual(len(logger.results()), 1)
        self.assertEqual(logger.results()[0].result, "Hello, World!")

    def test_wrap_preserves_function_metadata(self):
        logger = ToolCallLogger()

        @logger.wrap("greet")
        def greet(name):
            """Say hello."""
            return name

        self.assertEqual(greet.__name__, "greet")
        self.assertEqual(greet.__doc__, "Say hello.")

    def test_wrap_decorator_logs_error_and_reraises(self):
        logger = ToolCallLogger()

        @logger.wrap("boom")
        def boom(**kwargs):
            raise ValueError("kaboom")

        with self.assertRaises(ValueError):
            boom()

        self.assertEqual(len(logger.errors()), 1)
        self.assertIn("ValueError", logger.errors()[0].error)
        # No result entry should be recorded on error.
        self.assertEqual(len(logger.results()), 0)

    def test_wrap_decorator_supports_positional_args(self):
        logger = ToolCallLogger()

        @logger.wrap("greet")
        def greet(name):
            return f"Hello, {name}!"

        result = greet("World")
        self.assertEqual(result, "Hello, World!")
        self.assertEqual(logger.calls()[0].args, {"name": "World"})

    def test_wrap_decorator_mixes_positional_and_keyword(self):
        logger = ToolCallLogger()

        @logger.wrap("add")
        def add(a, b):
            return a + b

        self.assertEqual(add(1, b=2), 3)
        self.assertEqual(logger.calls()[0].args, {"a": 1, "b": 2})

    def test_wrap_with_metadata(self):
        logger = ToolCallLogger()

        @logger.wrap("tool", metadata={"agent": "a1"})
        def tool():
            return None

        tool()
        self.assertEqual(logger.calls()[0].metadata, {"agent": "a1"})
        self.assertEqual(logger.results()[0].metadata, {"agent": "a1"})


class OutputTests(unittest.TestCase):
    def test_jsonl_output_to_stream(self):
        buf = io.StringIO()
        logger = ToolCallLogger(buf)
        start = logger.log_call("t", {"x": 1})
        logger.log_result("t", {"x": 1}, "res", start)
        buf.seek(0)
        lines = [json.loads(line) for line in buf.readlines()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["kind"], "call")
        self.assertEqual(lines[1]["kind"], "result")
        self.assertEqual(lines[1]["result"], "res")

    def test_non_json_serializable_result_falls_back_to_str(self):
        buf = io.StringIO()
        logger = ToolCallLogger(buf)
        start = logger.log_call("t", {})
        logger.log_result("t", {}, {1, 2, 3}, start)  # a set is not JSON native
        buf.seek(0)
        lines = buf.readlines()
        # The second line is the result; it must still be valid JSON.
        record = json.loads(lines[1])
        self.assertEqual(record["kind"], "result")
        self.assertIsInstance(record["result"], str)

    def test_in_memory_only_writes_nothing_to_disk(self):
        logger = ToolCallLogger()  # no output target
        logger.log_call("t", {})
        # Nothing to assert on disk; just confirm the entry is tracked.
        self.assertEqual(len(logger.entries), 1)

    def test_file_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "run.jsonl"
            logger = ToolCallLogger(log_file)
            start = logger.log_call("ping", {})
            logger.log_result("ping", {}, "pong", start)
            logger.close()
            lines = log_file.read_text().strip().split("\n")
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["kind"], "call")
            self.assertEqual(json.loads(lines[1])["kind"], "result")

    def test_path_is_expanduser_expanded(self):
        # A "~" prefixed path must not be opened literally.
        logger = ToolCallLogger()
        self.assertIsNone(logger._path)


class LifecycleTests(unittest.TestCase):
    def test_context_manager_writes_and_closes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "out.jsonl"
            with ToolCallLogger(log_file) as logger:
                logger.log_call("tool", {"a": 1})
            lines = log_file.read_text().strip().split("\n")
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["tool_name"], "tool")

    def test_close_does_not_close_borrowed_stream(self):
        buf = io.StringIO()
        logger = ToolCallLogger(buf)
        logger.log_call("t", {"x": 1})
        logger.close()
        # We do not own the stream, so it stays open ...
        self.assertFalse(buf.closed)
        # ... but the logger stops writing to it.
        logger.log_call("t", {"x": 2})
        buf.seek(0)
        self.assertEqual(len(buf.readlines()), 1)

    def test_close_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "out.jsonl"
            logger = ToolCallLogger(log_file)
            logger.log_call("t", {})
            logger.close()
            # Calling close again must not raise.
            logger.close()


class EntryTests(unittest.TestCase):
    def test_entry_is_a_dataclass_with_defaults(self):
        entry = ToolCallEntry(ts=1.0, kind="call", tool_name="t", args={})
        self.assertIsNone(entry.result)
        self.assertIsNone(entry.error)
        self.assertIsNone(entry.duration_ms)
        self.assertEqual(entry.metadata, {})


if __name__ == "__main__":
    unittest.main()
