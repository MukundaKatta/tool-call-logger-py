# tool-call-logger-py

Structured JSONL logger for LLM tool calls and results. Wraps tool functions to automatically log calls, results, and errors.

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

## License

MIT
