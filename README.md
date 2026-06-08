# tool-call-logger-py

[![CI](https://github.com/MukundaKatta/tool-call-logger-py/actions/workflows/ci.yml/badge.svg)](https://github.com/MukundaKatta/tool-call-logger-py/actions/workflows/ci.yml)

Structured JSONL logger for LLM tool calls and results. Wraps tool functions to automatically log calls, results, and errors.

Zero runtime dependencies — it uses only the Python standard library and ships
with inline type hints (PEP 561 `py.typed`).

## Install

```bash
pip install tool-call-logger-py
```

## Usage

```python
from tool_call_logger import ToolCallLogger

# Log to file
logger = ToolCallLogger("~/agent-run.jsonl")

@logger.wrap("search_web")
def search_web(query: str) -> list[str]:
    return ["result1", "result2"]

search_web(query="python typing")
# Appends one "call" entry and one "result" entry

# Log to stream / in-memory only
logger = ToolCallLogger()  # in-memory only

# Manual logging
start = logger.log_call("fetch", {"url": "https://example.com"})
result = fetch("https://example.com")
logger.log_result("fetch", {"url": "https://example.com"}, result, start)

# Context manager (auto-close)
with ToolCallLogger("run.jsonl") as logger:
    start = logger.log_call("tool", {"x": 1})
    logger.log_result("tool", {"x": 1}, "ok", start)

# Query
logger.calls()              # list of call entries
logger.results()            # list of result entries
logger.errors()             # list of error entries
logger.by_tool("search")    # all entries for a tool
logger.call_count()         # total calls
logger.call_count("search") # calls for specific tool
logger.avg_duration_ms()    # average result duration
```

## Output Format (JSONL)

Each line is a JSON object:
```json
{"ts": 1716000000.0, "kind": "call", "tool_name": "search_web", "args": {"query": "python"}, ...}
{"ts": 1716000000.1, "kind": "result", "tool_name": "search_web", "result": [...], "duration_ms": 120.5, ...}
```

Every entry shares the same shape (see `ToolCallEntry`):

| Field         | Type             | Present on        | Description                                      |
| ------------- | ---------------- | ----------------- | ------------------------------------------------ |
| `ts`          | `float`          | all               | Unix timestamp (seconds) when the entry was made |
| `kind`        | `str`            | all               | One of `"call"`, `"result"`, `"error"`           |
| `tool_name`   | `str`            | all               | Name passed to the logger / decorator            |
| `args`        | `dict`           | all               | The tool's arguments (positional args are bound to names) |
| `result`      | `Any`            | `result`          | The tool's return value                          |
| `error`       | `str` \| `null`  | `error`           | `repr()` of the raised exception                 |
| `duration_ms` | `float` \| `null`| `result`, `error` | Wall-clock duration since the matching call      |
| `metadata`    | `dict`           | all               | Caller-supplied metadata (e.g. session id)       |

Values that are not natively JSON-serializable are stringified via `str()`, so a
log line is always valid JSON.

## API

`ToolCallLogger(output=None)` — create a logger.
- `output` may be a file path (`str`/`Path`, opened in append mode and
  `~`-expanded), an already-open writable stream, or `None` for in-memory only.

Logging:
- `wrap(tool_name, metadata=None)` — decorator that wraps a callable; logs a
  `call` plus a `result` (or `error`, re-raising) on every invocation.
- `log_call(tool_name, args, metadata=None) -> float` — record a call; returns a
  start timestamp to pass to `log_result`/`log_error`.
- `log_result(tool_name, args, result, start_ts, metadata=None)` — record a result.
- `log_error(tool_name, args, error, start_ts, metadata=None)` — record an error.

Querying (all return in-memory `ToolCallEntry` objects):
- `entries` — a copy of every entry recorded so far.
- `calls()`, `results()`, `errors()` — entries filtered by kind.
- `by_tool(tool_name)` — every entry for one tool.
- `call_count(tool_name=None)` — number of `call` entries (optionally per tool).
- `avg_duration_ms(tool_name=None)` — mean duration, or `None` if no durations.

Lifecycle:
- `clear()` — drop the in-memory entries (does not touch the file).
- `close()` — stop writing; closes files the logger opened, leaves borrowed
  streams open. Also usable as a context manager (`with ToolCallLogger(...) as l:`).

## Development

The package uses a `src/` layout, so install it (editable) before running the
test suite:

```bash
pip install -e .
python -m unittest discover -s tests -v
```

The tests rely only on the standard library `unittest` module — no third-party
test runner is required.

## License

MIT
