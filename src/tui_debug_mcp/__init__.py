# src/tui_debug_mcp/__init__.py
"""TUI Debug MCP - Real TUI debugging tool.

First principles:
1. Start TUI process
2. Capture screen output (ANSI terminal content)
3. Send keyboard input
4. Observe response
5. Record and replay sessions
"""

import asyncio
import json
import os
import pty
import select
import signal
import sys
import termios
import fcntl
import struct
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


# Recording storage directory
RECORDINGS_DIR = Path.home() / ".tui-debug-mcp" / "recordings"
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)


class TUIProcess:
    """真正的 TUI 进程管理器。"""

    def __init__(self, session_id: str, command: str, rows: int = 24, cols: int = 80):
        self.session_id = session_id
        self.command = command
        self.rows = rows
        self.cols = cols
        self.pid = None
        self.master_fd = None
        self.screen_buffer = ""  # 当前屏幕内容
        self.history = []  # 输出历史
        self.created_at = datetime.now().isoformat()

    def start(self) -> bool:
        """启动 TUI 进程。"""
        try:
            # 创建伪终端
            self.pid, self.master_fd = pty.fork()

            if self.pid == 0:
                # 子进程：执行命令
                try:
                    os.setsid()
                except OSError:
                    pass  # Ignore setsid failure in sandboxed environments
                os.execvp("sh", ["sh", "-c", self.command])
            else:
                # 父进程：设置终端大小
                self._set_terminal_size(self.rows, self.cols)
                # 设置非阻塞
                flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
                fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                return True
        except Exception as e:
            return False

    def _set_terminal_size(self, rows: int, cols: int):
        """设置终端大小。"""
        if self.master_fd:
            winsize = struct.pack('HHHH', rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)

    def read_screen(self, timeout: float = 0.5) -> str:
        """读取屏幕输出。"""
        if not self.master_fd:
            return ""

        output = b""
        start_time = asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0

        while True:
            try:
                ready, _, _ = select.select([self.master_fd], [], [], timeout)
                if not ready:
                    break
                data = os.read(self.master_fd, 65536)
                if data:
                    output += data
                else:
                    break
            except (OSError, IOError):
                break

        if output:
            text = output.decode("utf-8", errors="replace")
            self.screen_buffer = text
            self.history.append({
                "type": "output",
                "content": text,
                "timestamp": datetime.now().isoformat(),
            })
            return text

        return self.screen_buffer

    def send_input(self, text: str) -> bool:
        """发送文本输入。"""
        if not self.master_fd:
            return False
        try:
            os.write(self.master_fd, text.encode())
            self.history.append({
                "type": "input",
                "content": repr(text),
                "timestamp": datetime.now().isoformat(),
            })
            return True
        except Exception:
            return False

    def send_key(self, key: str) -> bool:
        """发送特殊按键。"""
        key_map = {
            "enter": "\r",
            "tab": "\t",
            "escape": "\x1b",
            "esc": "\x1b",
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
            "ctrl_a": "\x01",
            "ctrl_e": "\x05",
            "ctrl_k": "\x0b",
            "ctrl_u": "\x15",
            "ctrl_w": "\x17",
            "f1": "\x1bOP",
            "f2": "\x1bOQ",
            "f3": "\x1bOR",
            "f4": "\x1bOS",
            "f5": "\x1b[15~",
            "f6": "\x1b[17~",
            "f7": "\x1b[18~",
            "f8": "\x1b[19~",
            "f9": "\x1b[20~",
            "f10": "\x1b[21~",
            "page_up": "\x1b[5~",
            "page_down": "\x1b[6~",
        }

        text = key_map.get(key.lower(), key)
        return self.send_input(text)

    def is_alive(self) -> bool:
        """检查进程是否存活。"""
        if not self.pid:
            return False
        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            return pid == 0
        except Exception:
            return False

    def terminate(self):
        """终止进程。"""
        if self.pid:
            try:
                os.kill(self.pid, signal.SIGTERM)
                os.waitpid(self.pid, 0)
            except Exception:
                pass
        if self.master_fd:
            try:
                os.close(self.master_fd)
            except Exception:
                pass
        self.pid = None
        self.master_fd = None


# 全局会话管理
_sessions: dict[str, TUIProcess] = {}


def main():
    """运行 MCP 服务器。"""
    asyncio.run(run_server())


async def run_server():
    """运行 MCP 服务器。"""
    server = Server("tui-debug-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            # 会话管理
            Tool(
                name="tui_start",
                description="启动 TUI 应用。返回初始屏幕内容。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "会话 ID"},
                        "command": {"type": "string", "description": "启动命令，如 'python -m spark'"},
                        "rows": {"type": "integer", "description": "终端行数（默认 24）"},
                        "cols": {"type": "integer", "description": "终端列数（默认 80）"},
                    },
                    "required": ["session_id", "command"],
                },
            ),
            Tool(
                name="tui_stop",
                description="停止 TUI 会话。",
                inputSchema={
                    "type": "object",
                    "properties": {"session_id": {"type": "string"}},
                    "required": ["session_id"],
                },
            ),
            Tool(
                name="tui_list",
                description="列出所有 TUI 会话。",
                inputSchema={"type": "object", "properties": {}},
            ),

            # 屏幕操作
            Tool(
                name="tui_read",
                description="读取当前屏幕内容。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "wait": {"type": "number", "description": "等待时间（秒，默认 0.5）"},
                    },
                    "required": ["session_id"],
                },
            ),
            Tool(
                name="tui_screenshot",
                description="获取屏幕快照（清理 ANSI 转义序列后的纯文本）。",
                inputSchema={
                    "type": "object",
                    "properties": {"session_id": {"type": "string"}},
                    "required": ["session_id"],
                },
            ),

            # 输入操作
            Tool(
                name="tui_type",
                description="输入文本。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "text": {"type": "string", "description": "要输入的文本"},
                    },
                    "required": ["session_id", "text"],
                },
            ),
            Tool(
                name="tui_key",
                description="发送特殊按键：enter, tab, escape, up, down, left, right, backspace, delete, home, end, ctrl_c, ctrl_d, ctrl_l, ctrl_z, f1-f10, page_up, page_down。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "key": {"type": "string", "description": "按键名称"},
                    },
                    "required": ["session_id", "key"],
                },
            ),

            # 状态
            Tool(
                name="tui_alive",
                description="检查 TUI 进程是否存活。",
                inputSchema={
                    "type": "object",
                    "properties": {"session_id": {"type": "string"}},
                    "required": ["session_id"],
                },
            ),
            Tool(
                name="tui_history",
                description="获取输入/输出历史。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "limit": {"type": "integer", "description": "限制条数"},
                    },
                    "required": ["session_id"],
                },
            ),

            # Recording
            Tool(
                name="tui_record_save",
                description="Save session recording to file.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "name": {"type": "string", "description": "Recording name (optional, defaults to session_id)"},
                    },
                    "required": ["session_id"],
                },
            ),
            Tool(
                name="tui_record_load",
                description="Load a saved recording.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Recording name"},
                    },
                    "required": ["name"],
                },
            ),
            Tool(
                name="tui_record_list",
                description="List all saved recordings.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="tui_record_delete",
                description="Delete a saved recording.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Recording name"},
                    },
                    "required": ["name"],
                },
            ),
            Tool(
                name="tui_record_playback",
                description="Playback a recording step by step (returns each input/output pair).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Recording name"},
                        "step": {"type": "integer", "description": "Step number (0-indexed)"},
                    },
                    "required": ["name", "step"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "tui_start":
            session_id = arguments["session_id"]
            command = arguments["command"]
            rows = arguments.get("rows", 24)
            cols = arguments.get("cols", 80)

            if session_id in _sessions:
                return [TextContent(type="text", text=f"Error: Session '{session_id}' 已存在")]

            proc = TUIProcess(session_id, command, rows, cols)
            if not proc.start():
                return [TextContent(type="text", text=f"Error: Cannot start command '{command}'")]

            _sessions[session_id] = proc

            # 等待初始输出
            await asyncio.sleep(0.5)
            screen = proc.read_screen(0.2)

            return [TextContent(type="text", text=f"已启动: {command}\nPID: {proc.pid}\n\n初始屏幕:\n{screen}")]

        elif name == "tui_stop":
            session_id = arguments["session_id"]
            if session_id not in _sessions:
                return [TextContent(type="text", text=f"Error: Session '{session_id}' 不存在")]

            proc = _sessions.pop(session_id)
            proc.terminate()
            return [TextContent(type="text", text=f"已停止会话 '{session_id}'")]

        elif name == "tui_list":
            sessions = []
            for sid, proc in _sessions.items():
                sessions.append({
                    "session_id": sid,
                    "command": proc.command,
                    "pid": proc.pid,
                    "alive": proc.is_alive(),
                    "created_at": proc.created_at,
                })
            return [TextContent(type="text", text=json.dumps(sessions, indent=2, ensure_ascii=False))]

        elif name == "tui_read":
            session_id = arguments["session_id"]
            wait = arguments.get("wait", 0.5)

            if session_id not in _sessions:
                return [TextContent(type="text", text=f"Error: Session '{session_id}' 不存在")]

            proc = _sessions[session_id]
            await asyncio.sleep(wait)
            screen = proc.read_screen(wait)
            return [TextContent(type="text", text=screen if screen else "(无输出)")]

        elif name == "tui_screenshot":
            session_id = arguments["session_id"]

            if session_id not in _sessions:
                return [TextContent(type="text", text=f"Error: Session '{session_id}' 不存在")]

            proc = _sessions[session_id]
            # 清理 ANSI 转义序列
            import re
            clean = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', proc.screen_buffer)
            clean = re.sub(r'\x1b\].*?\x07', '', clean)
            clean = re.sub(r'\r\n', '\n', clean)
            return [TextContent(type="text", text=clean if clean else "(空)")]

        elif name == "tui_type":
            session_id = arguments["session_id"]
            text = arguments["text"]

            if session_id not in _sessions:
                return [TextContent(type="text", text=f"Error: Session '{session_id}' 不存在")]

            proc = _sessions[session_id]
            if not proc.send_input(text):
                return [TextContent(type="text", text="Error: Send failed")]

            await asyncio.sleep(0.1)
            screen = proc.read_screen(0.3)
            return [TextContent(type="text", text=screen if screen else "(已发送，无输出)")]

        elif name == "tui_key":
            session_id = arguments["session_id"]
            key = arguments["key"]

            if session_id not in _sessions:
                return [TextContent(type="text", text=f"Error: Session '{session_id}' 不存在")]

            proc = _sessions[session_id]
            if not proc.send_key(key):
                return [TextContent(type="text", text="Error: Send failed")]

            await asyncio.sleep(0.1)
            screen = proc.read_screen(0.3)
            return [TextContent(type="text", text=screen if screen else "(已发送，无输出)")]

        elif name == "tui_alive":
            session_id = arguments["session_id"]

            if session_id not in _sessions:
                return [TextContent(type="text", text=f"Error: Session '{session_id}' 不存在")]

            proc = _sessions[session_id]
            return [TextContent(type="text", text=json.dumps({"alive": proc.is_alive()}))]

        elif name == "tui_history":
            session_id = arguments["session_id"]
            limit = arguments.get("limit", 50)

            if session_id not in _sessions:
                return [TextContent(type="text", text=f"Error: Session '{session_id}' not found")]

            proc = _sessions[session_id]
            history = proc.history[-limit:]
            return [TextContent(type="text", text=json.dumps(history, indent=2, ensure_ascii=False))]

        # Recording tools
        elif name == "tui_record_save":
            session_id = arguments["session_id"]
            rec_name = arguments.get("name", session_id)

            if session_id not in _sessions:
                return [TextContent(type="text", text=f"Error: Session '{session_id}' not found")]

            proc = _sessions[session_id]
            recording = {
                "session_id": session_id,
                "command": proc.command,
                "rows": proc.rows,
                "cols": proc.cols,
                "created_at": proc.created_at,
                "history": proc.history,
            }

            rec_file = RECORDINGS_DIR / f"{rec_name}.json"
            rec_file.write_text(json.dumps(recording, indent=2, ensure_ascii=False))

            return [TextContent(type="text", text=f"Recording saved: {rec_name}\nSteps: {len(proc.history)}")]

        elif name == "tui_record_load":
            rec_name = arguments["name"]
            rec_file = RECORDINGS_DIR / f"{rec_name}.json"

            if not rec_file.exists():
                return [TextContent(type="text", text=f"Error: Recording '{rec_name}' not found")]

            recording = json.loads(rec_file.read_text())
            return [TextContent(type="text", text=json.dumps(recording, indent=2, ensure_ascii=False))]

        elif name == "tui_record_list":
            recordings = []
            for rec_file in RECORDINGS_DIR.glob("*.json"):
                try:
                    data = json.loads(rec_file.read_text())
                    recordings.append({
                        "name": rec_file.stem,
                        "command": data.get("command", "unknown"),
                        "steps": len(data.get("history", [])),
                        "created_at": data.get("created_at", "unknown"),
                    })
                except Exception:
                    pass
            return [TextContent(type="text", text=json.dumps(recordings, indent=2, ensure_ascii=False))]

        elif name == "tui_record_delete":
            rec_name = arguments["name"]
            rec_file = RECORDINGS_DIR / f"{rec_name}.json"

            if not rec_file.exists():
                return [TextContent(type="text", text=f"Error: Recording '{rec_name}' not found")]

            rec_file.unlink()
            return [TextContent(type="text", text=f"Recording deleted: {rec_name}")]

        elif name == "tui_record_playback":
            rec_name = arguments["name"]
            step = arguments["step"]

            rec_file = RECORDINGS_DIR / f"{rec_name}.json"

            if not rec_file.exists():
                return [TextContent(type="text", text=f"Error: Recording '{rec_name}' not found")]

            recording = json.loads(rec_file.read_text())
            history = recording.get("history", [])

            if step < 0 or step >= len(history):
                return [TextContent(type="text", text=f"Error: Step {step} out of range (0-{len(history)-1})")]

            entry = history[step]
            return [TextContent(type="text", text=json.dumps({
                "step": step,
                "total_steps": len(history),
                "type": entry.get("type"),
                "content": entry.get("content"),
                "timestamp": entry.get("timestamp"),
            }, indent=2, ensure_ascii=False))]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    main()
