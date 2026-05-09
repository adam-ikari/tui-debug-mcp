# src/tui_debug_mcp/__init__.py
"""TUI Debug MCP Server - Terminal emulation for debugging TUI apps."""

import asyncio
import json
import time
import os
import pty
import select
import struct
import fcntl
import termios
from typing import Any
from datetime import datetime

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Global state for terminal sessions
_sessions = {}


def main():
    """Run the MCP server."""
    asyncio.run(run_server())


class TerminalSession:
    """A terminal session for running TUI apps."""

    def __init__(self, session_id: str, command: str, rows: int = 24, cols: int = 80):
        self.session_id = session_id
        self.command = command
        self.rows = rows
        self.cols = cols
        self.master_fd = None
        self.pid = None
        self.buffer = ""
        self.history = []
        self.created_at = datetime.now().isoformat()

    def start(self) -> bool:
        """Start the terminal session."""
        try:
            pid, master_fd = pty.fork()

            if pid == 0:
                # Child process
                os.execvp("sh", ["sh", "-c", self.command])
            else:
                # Parent process
                self.pid = pid
                self.master_fd = master_fd

                # Set terminal size
                winsize = struct.pack('HHHH', self.rows, self.cols, 0, 0)
                fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)

                # Set non-blocking
                flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
                fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

                return True
        except Exception as e:
            return False

    def read_output(self, timeout: float = 0.1) -> str:
        """Read available output from terminal."""
        if not self.master_fd:
            return ""

        output = ""
        try:
            while True:
                ready, _, _ = select.select([self.master_fd], [], [], timeout)
                if not ready:
                    break
                data = os.read(self.master_fd, 4096)
                if data:
                    output += data.decode("utf-8", errors="replace")
                else:
                    break
        except Exception:
            pass

        if output:
            self.buffer = output
            self.history.append({
                "type": "output",
                "content": output,
                "timestamp": datetime.now().isoformat(),
            })

        return output

    def send_input(self, text: str) -> bool:
        """Send input to terminal."""
        if not self.master_fd:
            return False

        try:
            os.write(self.master_fd, text.encode())
            self.history.append({
                "type": "input",
                "content": text,
                "timestamp": datetime.now().isoformat(),
            })
            return True
        except Exception:
            return False

    def send_key(self, key: str) -> bool:
        """Send special key to terminal."""
        key_map = {
            "enter": "\r",
            "tab": "\t",
            "escape": "\x1b",
            "up": "\x1b[A",
            "down": "\x1b[B",
            "right": "\x1b[C",
            "left": "\x1b[D",
            "backspace": "\x7f",
            "delete": "\x1b[3~",
            "home": "\x1b[H",
            "end": "\x1b[F",
            "ctrl_c": "\x03",
            "ctrl_d": "\x04",
            "ctrl_l": "\x0c",
            "ctrl_z": "\x1a",
            "f1": "\x1bOP",
            "f2": "\x1bOQ",
            "f3": "\x1bOR",
            "f4": "\x1bOS",
        }

        text = key_map.get(key.lower(), key)
        return self.send_input(text)

    def capture_screen(self) -> str:
        """Capture current screen content."""
        if not self.master_fd:
            return ""

        # Request screen content using DEC special mode
        # This works with most terminals
        self.send_input("\x1b[?25h")  # Show cursor
        return self.buffer

    def is_alive(self) -> bool:
        """Check if process is alive."""
        if not self.pid:
            return False
        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            return pid == 0
        except Exception:
            return False

    def terminate(self):
        """Terminate the session."""
        if self.pid:
            try:
                os.kill(self.pid, 9)
            except Exception:
                pass
        if self.master_fd:
            try:
                os.close(self.master_fd)
            except Exception:
                pass


async def run_server():
    """Run the MCP server."""
    server = Server("tui-debug-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="tui_start_session",
                description="Start a new TUI session with a command",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Unique session identifier"},
                        "command": {"type": "string", "description": "Command to run (e.g., 'python -m spark')"},
                        "rows": {"type": "integer", "description": "Terminal rows (default 24)"},
                        "cols": {"type": "integer", "description": "Terminal columns (default 80)"},
                    },
                    "required": ["session_id", "command"],
                },
            ),
            Tool(
                name="tui_read_output",
                description="Read output from TUI session (returns screen content)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "timeout": {"type": "number", "description": "Read timeout in seconds (default 0.5)"},
                    },
                    "required": ["session_id"],
                },
            ),
            Tool(
                name="tui_send_input",
                description="Send text input to TUI session",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "text": {"type": "string", "description": "Text to send"},
                    },
                    "required": ["session_id", "text"],
                },
            ),
            Tool(
                name="tui_send_key",
                description="Send special key to TUI session (enter, tab, escape, up, down, left, right, ctrl_c, etc.)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "key": {"type": "string", "description": "Key name: enter, tab, escape, up, down, left, right, backspace, ctrl_c, ctrl_d, etc."},
                    },
                    "required": ["session_id", "key"],
                },
            ),
            Tool(
                name="tui_capture_screen",
                description="Capture current screen content as text",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                    },
                    "required": ["session_id"],
                },
            ),
            Tool(
                name="tui_list_sessions",
                description="List all active TUI sessions",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="tui_end_session",
                description="End a TUI session",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                    },
                    "required": ["session_id"],
                },
            ),
            Tool(
                name="tui_get_history",
                description="Get input/output history for a session",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "limit": {"type": "integer", "description": "Max entries to return"},
                    },
                    "required": ["session_id"],
                },
            ),
            Tool(
                name="tui_is_alive",
                description="Check if TUI session process is still running",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                    },
                    "required": ["session_id"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "tui_start_session":
            session_id = arguments["session_id"]
            command = arguments["command"]
            rows = arguments.get("rows", 24)
            cols = arguments.get("cols", 80)

            if session_id in _sessions:
                return [TextContent(type="text", text=f"Error: Session '{session_id}' already exists")]

            session = TerminalSession(session_id, command, rows, cols)
            if session.start():
                _sessions[session_id] = session
                # Wait a moment for initial output
                await asyncio.sleep(0.2)
                output = session.read_output()
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "status": "started",
                        "session_id": session_id,
                        "pid": session.pid,
                        "initial_output": output,
                    }, indent=2)
                )]
            else:
                return [TextContent(type="text", text=f"Error: Failed to start session")]

        elif name == "tui_read_output":
            session_id = arguments["session_id"]
            timeout = arguments.get("timeout", 0.5)

            session = _sessions.get(session_id)
            if not session:
                return [TextContent(type="text", text=f"Error: Session '{session_id}' not found")]

            output = session.read_output(timeout)
            return [TextContent(type="text", text=output if output else "(no output)")]

        elif name == "tui_send_input":
            session_id = arguments["session_id"]
            text = arguments["text"]

            session = _sessions.get(session_id)
            if not session:
                return [TextContent(type="text", text=f"Error: Session '{session_id}' not found")]

            if session.send_input(text):
                await asyncio.sleep(0.1)
                output = session.read_output()
                return [TextContent(type="text", text=output if output else "(input sent, no output)")]
            else:
                return [TextContent(type="text", text="Error: Failed to send input")]

        elif name == "tui_send_key":
            session_id = arguments["session_id"]
            key = arguments["key"]

            session = _sessions.get(session_id)
            if not session:
                return [TextContent(type="text", text=f"Error: Session '{session_id}' not found")]

            if session.send_key(key):
                await asyncio.sleep(0.1)
                output = session.read_output()
                return [TextContent(type="text", text=output if output else "(key sent, no output)")]
            else:
                return [TextContent(type="text", text="Error: Failed to send key")]

        elif name == "tui_capture_screen":
            session_id = arguments["session_id"]

            session = _sessions.get(session_id)
            if not session:
                return [TextContent(type="text", text=f"Error: Session '{session_id}' not found")]

            screen = session.capture_screen()
            return [TextContent(type="text", text=screen if screen else "(empty screen)")]

        elif name == "tui_list_sessions":
            sessions = []
            for sid, session in _sessions.items():
                sessions.append({
                    "session_id": sid,
                    "command": session.command,
                    "pid": session.pid,
                    "alive": session.is_alive(),
                    "created_at": session.created_at,
                })
            return [TextContent(type="text", text=json.dumps(sessions, indent=2))]

        elif name == "tui_end_session":
            session_id = arguments["session_id"]

            session = _sessions.get(session_id)
            if not session:
                return [TextContent(type="text", text=f"Error: Session '{session_id}' not found")]

            session.terminate()
            del _sessions[session_id]
            return [TextContent(type="text", text=f"Session '{session_id}' ended")]

        elif name == "tui_get_history":
            session_id = arguments["session_id"]
            limit = arguments.get("limit", 50)

            session = _sessions.get(session_id)
            if not session:
                return [TextContent(type="text", text=f"Error: Session '{session_id}' not found")]

            history = session.history[-limit:]
            return [TextContent(type="text", text=json.dumps(history, indent=2))]

        elif name == "tui_is_alive":
            session_id = arguments["session_id"]

            session = _sessions.get(session_id)
            if not session:
                return [TextContent(type="text", text=f"Error: Session '{session_id}' not found")]

            return [TextContent(
                type="text",
                text=json.dumps({"session_id": session_id, "alive": session.is_alive()})
            )]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    main()
