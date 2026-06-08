"""tool-call-logger-py — structured JSONL logger for LLM tool calls and results."""

from __future__ import annotations

import functools
import inspect
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, IO


@dataclass
class ToolCallEntry:
    ts: float
    kind: str  # "call" | "result" | "error"
    tool_name: str
    args: dict
    result: Any = None
    error: str | None = None
    duration_ms: float | None = None
    metadata: dict = field(default_factory=dict)


class ToolCallLogger:
    """
    Structured JSONL logger for LLM tool calls and results.

    Wraps tool functions to automatically log calls, results, and errors.
    Outputs one JSON object per line (JSONL format).

    Example::

        logger = ToolCallLogger("~/agent-run.jsonl")

        @logger.wrap("search_web")
        def search_web(query: str) -> list[str]:
            return ["result1", "result2"]

        search_web(query="python typing")
        # Appends two entries: one "call", one "result"
    """

    def __init__(self, output: str | Path | IO | None = None) -> None:
        self._entries: list[ToolCallEntry] = []
        self._file: IO | None = None
        self._path: Path | None = None

        if output is not None:
            if isinstance(output, (str, Path)):
                self._path = Path(output).expanduser()
                self._file = open(self._path, "a", encoding="utf-8")
            else:
                self._file = output

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log_call(
        self, tool_name: str, args: dict, metadata: dict | None = None
    ) -> float:
        """Record a tool invocation. Returns the timestamp for duration tracking."""
        ts = time.time()
        entry = ToolCallEntry(
            ts=ts, kind="call", tool_name=tool_name, args=args, metadata=metadata or {}
        )
        self._write(entry)
        return ts

    def log_result(
        self,
        tool_name: str,
        args: dict,
        result: Any,
        start_ts: float,
        metadata: dict | None = None,
    ) -> None:
        duration_ms = (time.time() - start_ts) * 1000
        entry = ToolCallEntry(
            ts=time.time(),
            kind="result",
            tool_name=tool_name,
            args=args,
            result=result,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
        self._write(entry)

    def log_error(
        self,
        tool_name: str,
        args: dict,
        error: Exception,
        start_ts: float,
        metadata: dict | None = None,
    ) -> None:
        duration_ms = (time.time() - start_ts) * 1000
        entry = ToolCallEntry(
            ts=time.time(),
            kind="error",
            tool_name=tool_name,
            args=args,
            error=repr(error),
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
        self._write(entry)

    # ------------------------------------------------------------------
    # Wrapping
    # ------------------------------------------------------------------

    def wrap(self, tool_name: str, metadata: dict | None = None):
        """Decorator that wraps a tool function with automatic logging.

        Supports both positional and keyword arguments; positional arguments
        are mapped to their parameter names (best effort) for the logged
        ``args`` dict.
        """

        def decorator(fn):
            try:
                sig = inspect.signature(fn)
            except (TypeError, ValueError):
                sig = None

            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                logged_args = self._bind_args(sig, args, kwargs)
                start = self.log_call(tool_name, logged_args, metadata)
                try:
                    result = fn(*args, **kwargs)
                    self.log_result(tool_name, logged_args, result, start, metadata)
                    return result
                except Exception as exc:
                    self.log_error(tool_name, logged_args, exc, start, metadata)
                    raise

            return wrapper

        return decorator

    @staticmethod
    def _bind_args(sig, args: tuple, kwargs: dict) -> dict:
        """Build an ``args`` dict from positional/keyword call arguments.

        When the callable's signature is available, positional arguments are
        bound to their parameter names. Falls back to numeric ``arg{i}`` keys
        if binding fails.
        """
        if sig is not None:
            try:
                bound = sig.bind(*args, **kwargs)
                return dict(bound.arguments)
            except TypeError:
                pass
        logged = {f"arg{i}": value for i, value in enumerate(args)}
        logged.update(kwargs)
        return logged

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    @property
    def entries(self) -> list[ToolCallEntry]:
        return list(self._entries)

    def calls(self) -> list[ToolCallEntry]:
        return [e for e in self._entries if e.kind == "call"]

    def results(self) -> list[ToolCallEntry]:
        return [e for e in self._entries if e.kind == "result"]

    def errors(self) -> list[ToolCallEntry]:
        return [e for e in self._entries if e.kind == "error"]

    def by_tool(self, tool_name: str) -> list[ToolCallEntry]:
        return [e for e in self._entries if e.tool_name == tool_name]

    def call_count(self, tool_name: str | None = None) -> int:
        entries = self._entries if tool_name is None else self.by_tool(tool_name)
        return sum(1 for e in entries if e.kind == "call")

    def avg_duration_ms(self, tool_name: str | None = None) -> float | None:
        entries = self._entries if tool_name is None else self.by_tool(tool_name)
        durations = [e.duration_ms for e in entries if e.duration_ms is not None]
        return sum(durations) / len(durations) if durations else None

    def clear(self) -> None:
        self._entries.clear()

    def close(self) -> None:
        """Stop writing to the output.

        Files opened by this logger (constructed from a path) are closed.
        Streams passed in by the caller are left open (we do not own them),
        but writing stops in either case.
        """
        if self._file is not None and self._path is not None:
            self._file.close()
        self._file = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _write(self, entry: ToolCallEntry) -> None:
        self._entries.append(entry)
        if self._file:
            line = json.dumps(asdict(entry), default=str)
            self._file.write(line + "\n")
            self._file.flush()

    def __enter__(self) -> "ToolCallLogger":
        return self

    def __exit__(self, *_) -> None:
        self.close()


__all__ = ["ToolCallLogger", "ToolCallEntry"]
