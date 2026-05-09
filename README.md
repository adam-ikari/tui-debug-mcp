# tui-debug-mcp

MCP server for debugging TUI applications via terminal emulation.

## How It Works

This MCP simulates a terminal (PTY) that runs TUI applications. You can:
- Start a TUI app in a virtual terminal
- Read screen output frame by frame
- Send keyboard input and special keys
- Capture the current screen state

This allows Claude Code to interact with and debug TUI applications like Spark.

## Installation

```bash
pip install tui-debug-mcp
```

## Usage

Add to Claude Code MCP settings:

```json
{
  "mcpServers": {
    "tui-debug": {
      "command": "tui-debug-mcp"
    }
  }
}
```

## Tools

### `tui_start_session`
Start a new TUI session.

```json
{
  "session_id": "spark-test",
  "command": "python -m spark",
  "rows": 24,
  "cols": 80
}
```

### `tui_read_output`
Read output from the terminal.

```json
{
  "session_id": "spark-test",
  "timeout": 0.5
}
```

### `tui_send_input`
Send text input to the TUI.

```json
{
  "session_id": "spark-test",
  "text": "hello"
}
```

### `tui_send_key`
Send special keys: `enter`, `tab`, `escape`, `up`, `down`, `left`, `right`, `backspace`, `delete`, `home`, `end`, `ctrl_c`, `ctrl_d`, `ctrl_l`, `ctrl_z`, `f1`-`f4`.

```json
{
  "session_id": "spark-test",
  "key": "enter"
}
```

### `tui_capture_screen`
Capture current screen content.

### `tui_list_sessions`
List all active sessions.

### `tui_end_session`
Terminate a session.

### `tui_get_history`
Get input/output history.

### `tui_is_alive`
Check if session process is running.

## Example: Testing Spark

```
1. tui_start_session: {"session_id": "spark", "command": "python -m spark"}
2. tui_read_output: See welcome screen
3. tui_send_input: {"session_id": "spark", "text": "hello"}
4. tui_send_key: {"session_id": "spark", "key": "enter"}
5. tui_read_output: See response
6. tui_send_key: {"session_id": "spark", "key": "ctrl_c"}  # Exit
7. tui_end_session: {"session_id": "spark"}
```

## License

MIT