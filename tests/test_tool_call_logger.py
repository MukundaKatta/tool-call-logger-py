"""Tests for tool-call-logger-py."""
import io
import json
import pytest
from tool_call_logger import ToolCallLogger, ToolCallEntry


def test_log_call_records_entry():
    logger = ToolCallLogger()
    ts = logger.log_call("search", {"query": "hello"})
    assert len(logger.calls()) == 1
    entry = logger.calls()[0]
    assert entry.kind == "call"
    assert entry.tool_name == "search"
    assert entry.args == {"query": "hello"}
    assert isinstance(ts, float)


def test_log_result_records_entry():
    logger = ToolCallLogger()
    start = logger.log_call("search", {"q": "x"})
    logger.log_result("search", {"q": "x"}, ["r1", "r2"], start)
    results = logger.results()
    assert len(results) == 1
    assert results[0].kind == "result"
    assert results[0].result == ["r1", "r2"]
    assert results[0].duration_ms is not None
    assert results[0].duration_ms >= 0


def test_log_error_records_entry():
    logger = ToolCallLogger()
    start = logger.log_call("fetch", {"url": "http://x"})
    logger.log_error("fetch", {"url": "http://x"}, RuntimeError("timeout"), start)
    errors = logger.errors()
    assert len(errors) == 1
    assert errors[0].kind == "error"
    assert "RuntimeError" in errors[0].error
    assert errors[0].duration_ms >= 0


def test_entries_property():
    logger = ToolCallLogger()
    logger.log_call("t1", {})
    logger.log_call("t2", {})
    assert len(logger.entries) == 2


def test_call_count():
    logger = ToolCallLogger()
    logger.log_call("search", {"q": "a"})
    logger.log_call("search", {"q": "b"})
    logger.log_call("fetch", {"url": "x"})
    assert logger.call_count() == 3
    assert logger.call_count("search") == 2
    assert logger.call_count("fetch") == 1


def test_by_tool():
    logger = ToolCallLogger()
    logger.log_call("a", {"x": 1})
    logger.log_call("b", {"x": 2})
    logger.log_call("a", {"x": 3})
    entries = logger.by_tool("a")
    assert len(entries) == 2
    assert all(e.tool_name == "a" for e in entries)


def test_avg_duration_ms():
    logger = ToolCallLogger()
    start = logger.log_call("t", {})
    logger.log_result("t", {}, "ok", start)
    avg = logger.avg_duration_ms()
    assert avg is not None
    assert avg >= 0


def test_avg_duration_ms_none_when_empty():
    logger = ToolCallLogger()
    assert logger.avg_duration_ms() is None


def test_clear():
    logger = ToolCallLogger()
    logger.log_call("t", {})
    logger.clear()
    assert len(logger.entries) == 0


def test_wrap_decorator_logs_call_and_result():
    logger = ToolCallLogger()

    @logger.wrap("greet")
    def greet(name):
        return f"Hello, {name}!"

    result = greet(name="World")
    assert result == "Hello, World!"
    assert logger.call_count("greet") == 1
    assert len(logger.results()) == 1
    assert logger.results()[0].result == "Hello, World!"


def test_wrap_decorator_logs_error():
    logger = ToolCallLogger()

    @logger.wrap("boom")
    def boom(**kwargs):
        raise ValueError("kaboom")

    with pytest.raises(ValueError):
        boom()

    assert len(logger.errors()) == 1
    assert "ValueError" in logger.errors()[0].error


def test_jsonl_output_to_stream():
    buf = io.StringIO()
    logger = ToolCallLogger(buf)
    start = logger.log_call("t", {"x": 1})
    logger.log_result("t", {"x": 1}, "res", start)
    buf.seek(0)
    lines = [json.loads(l) for l in buf.readlines()]
    assert len(lines) == 2
    assert lines[0]["kind"] == "call"
    assert lines[1]["kind"] == "result"
    assert lines[1]["result"] == "res"


def test_context_manager(tmp_path):
    log_file = tmp_path / "out.jsonl"
    with ToolCallLogger(log_file) as logger:
        logger.log_call("tool", {"a": 1})
    lines = log_file.read_text().strip().split("\n")
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["tool_name"] == "tool"


def test_metadata_stored():
    logger = ToolCallLogger()
    logger.log_call("t", {}, metadata={"session": "abc"})
    assert logger.calls()[0].metadata == {"session": "abc"}


def test_file_output(tmp_path):
    log_file = tmp_path / "run.jsonl"
    logger = ToolCallLogger(log_file)
    start = logger.log_call("ping", {})
    logger.log_result("ping", {}, "pong", start)
    logger.close()
    lines = log_file.read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["kind"] == "call"
    assert json.loads(lines[1])["kind"] == "result"
