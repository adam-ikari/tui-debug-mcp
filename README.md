# tui-debug-mcp

MCP server for debugging TUI and REPL applications.

## Features

- **Session Inspection**: View current session state, history, and context
- **Message Logging**: Log and inspect messages sent to/from LLM
- **Tool Call Tracing**: Track all tool calls with timing and results
- **State Snapshots**: Capture and compare session states
- **Interactive Debugging**: Pause execution and inspect internal state

## Installation

```bash
pip install tui-debug-mcp
```

## Usage

Add to your application configuration:

```yaml
mcp_servers:
  tui-debug:
    command: tui-debug-mcp
    args: []
```

## Tools

### `debug_get_session_info`
Get current session information including mode, language, and history count.

### `debug_get_history`
Get conversation history with optional limit.

### `debug_get_last_tool_call`
Get details of the last tool call including timing and result.

### `debug_get_tool_calls`
Get all tool calls in the current session.

### `debug_set_breakpoint`
Set a breakpoint on a specific tool name to pause execution.

### `debug_inspect_state`
Inspect internal state (loaded modules, settings, etc.).

### `debug_export_session`
Export the current session to a JSON file for analysis.

## License

MIT