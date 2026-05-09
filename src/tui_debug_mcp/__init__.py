# src/tui_debug_mcp/__init__.py
"""TUI Debug MCP Server."""

import asyncio
import json
import time
from typing import Any
from datetime import datetime

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Global debug state
_debug_state = {
    "sessions": {},
    "tool_calls": [],
    "breakpoints": set(),
    "current_session": None,
    "message_log": [],
}


def main():
    """Run the MCP server."""
    asyncio.run(run_server())


async def run_server():
    """Run the MCP server."""
    server = Server("tui-debug-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="debug_get_session_info",
                description="Get current session information",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="debug_get_history",
                description="Get conversation history",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Max number of messages to return",
                        }
                    },
                },
            ),
            Tool(
                name="debug_log_message",
                description="Log a message for debugging",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "role": {"type": "string", "description": "Message role (user/assistant/system)"},
                        "content": {"type": "string", "description": "Message content"},
                    },
                    "required": ["role", "content"],
                },
            ),
            Tool(
                name="debug_log_tool_call",
                description="Log a tool call for debugging",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tool_name": {"type": "string"},
                        "arguments": {"type": "object"},
                        "result": {"type": "string"},
                        "success": {"type": "boolean"},
                    },
                    "required": ["tool_name", "arguments", "success"],
                },
            ),
            Tool(
                name="debug_get_tool_calls",
                description="Get all logged tool calls",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max number of calls to return"},
                    },
                },
            ),
            Tool(
                name="debug_set_breakpoint",
                description="Set a breakpoint on a tool name",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tool_name": {"type": "string", "description": "Tool name to break on"},
                        "enabled": {"type": "boolean", "description": "Enable or disable breakpoint"},
                    },
                    "required": ["tool_name", "enabled"],
                },
            ),
            Tool(
                name="debug_check_breakpoint",
                description="Check if a breakpoint is set for a tool",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tool_name": {"type": "string"},
                    },
                    "required": ["tool_name"],
                },
            ),
            Tool(
                name="debug_clear_state",
                description="Clear all debug state",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="debug_export_session",
                description="Export current debug state as JSON",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="debug_set_session_info",
                description="Set session information for tracking",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string"},
                        "language": {"type": "string"},
                        "model": {"type": "string"},
                    },
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "debug_get_session_info":
            return [TextContent(
                type="text",
                text=json.dumps(_debug_state["current_session"] or {"status": "no session"}, indent=2)
            )]

        elif name == "debug_get_history":
            limit = arguments.get("limit", 10)
            messages = _debug_state["message_log"][-limit:]
            return [TextContent(type="text", text=json.dumps(messages, indent=2))]

        elif name == "debug_log_message":
            _debug_state["message_log"].append({
                "role": arguments["role"],
                "content": arguments["content"],
                "timestamp": datetime.now().isoformat(),
            })
            return [TextContent(type="text", text="Message logged")]

        elif name == "debug_log_tool_call":
            call_record = {
                "tool_name": arguments["tool_name"],
                "arguments": arguments["arguments"],
                "result": arguments.get("result", ""),
                "success": arguments["success"],
                "timestamp": datetime.now().isoformat(),
                "time": time.time(),
            }
            _debug_state["tool_calls"].append(call_record)
            return [TextContent(type="text", text="Tool call logged")]

        elif name == "debug_get_tool_calls":
            limit = arguments.get("limit", 10)
            calls = _debug_state["tool_calls"][-limit:]
            return [TextContent(type="text", text=json.dumps(calls, indent=2))]

        elif name == "debug_set_breakpoint":
            tool_name = arguments["tool_name"]
            enabled = arguments["enabled"]
            if enabled:
                _debug_state["breakpoints"].add(tool_name)
            else:
                _debug_state["breakpoints"].discard(tool_name)
            return [TextContent(
                type="text",
                text=f"Breakpoint {'set' if enabled else 'removed'} for {tool_name}"
            )]

        elif name == "debug_check_breakpoint":
            tool_name = arguments["tool_name"]
            has_breakpoint = tool_name in _debug_state["breakpoints"]
            return [TextContent(
                type="text",
                text=json.dumps({"tool": tool_name, "breakpoint": has_breakpoint})
            )]

        elif name == "debug_clear_state":
            _debug_state["tool_calls"].clear()
            _debug_state["message_log"].clear()
            _debug_state["breakpoints"].clear()
            return [TextContent(type="text", text="Debug state cleared")]

        elif name == "debug_export_session":
            export = {
                "session": _debug_state["current_session"],
                "tool_calls": _debug_state["tool_calls"],
                "messages": _debug_state["message_log"],
                "breakpoints": list(_debug_state["breakpoints"]),
                "exported_at": datetime.now().isoformat(),
            }
            return [TextContent(type="text", text=json.dumps(export, indent=2))]

        elif name == "debug_set_session_info":
            _debug_state["current_session"] = {
                "mode": arguments.get("mode", "ask"),
                "language": arguments.get("language", "en"),
                "model": arguments.get("model", "unknown"),
                "updated_at": datetime.now().isoformat(),
            }
            return [TextContent(type="text", text="Session info updated")]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    main()
