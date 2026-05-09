# src/tui_debug_mcp/__init__.py
"""TUI Debug MCP Server - Debug TUI apps via direct API calls."""

import asyncio
import json
import sys
import os
from typing import Any
from datetime import datetime

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Global debug state
_debug_state = {
    "sessions": {},
    "current_session": None,
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
                name="debug_start_session",
                description="Start a debug session",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "app_name": {"type": "string"},
                    },
                    "required": ["session_id", "app_name"],
                },
            ),
            Tool(
                name="debug_end_session",
                description="End a debug session",
                inputSchema={
                    "type": "object",
                    "properties": {"session_id": {"type": "string"}},
                    "required": ["session_id"],
                },
            ),
            Tool(
                name="debug_log_message",
                description="Log a message",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "role": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["session_id", "role", "content"],
                },
            ),
            Tool(
                name="debug_log_tool_call",
                description="Log a tool call",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "tool_name": {"type": "string"},
                        "arguments": {"type": "object"},
                        "success": {"type": "boolean"},
                        "result": {"type": "string"},
                    },
                    "required": ["session_id", "tool_name", "arguments", "success"],
                },
            ),
            Tool(
                name="debug_get_session",
                description="Get session data",
                inputSchema={
                    "type": "object",
                    "properties": {"session_id": {"type": "string"}},
                    "required": ["session_id"],
                },
            ),
            Tool(
                name="spark_test_command",
                description="Test a shell command via Spark",
                inputSchema={
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            ),
            Tool(
                name="spark_test_llm",
                description="Test Spark LLM",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "use_tools": {"type": "boolean"},
                    },
                    "required": ["prompt"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "debug_start_session":
            session_id = arguments["session_id"]
            _debug_state["sessions"][session_id] = {
                "app_name": arguments["app_name"],
                "messages": [],
                "tool_calls": [],
                "created_at": datetime.now().isoformat(),
            }
            _debug_state["current_session"] = session_id
            return [TextContent(type="text", text=f"Session {session_id} started")]

        elif name == "debug_end_session":
            session_id = arguments["session_id"]
            if session_id in _debug_state["sessions"]:
                del _debug_state["sessions"][session_id]
            return [TextContent(type="text", text=f"Session {session_id} ended")]

        elif name == "debug_log_message":
            session_id = arguments["session_id"]
            if session_id not in _debug_state["sessions"]:
                return [TextContent(type="text", text=f"Error: Session not found")]
            _debug_state["sessions"][session_id]["messages"].append({
                "role": arguments["role"],
                "content": arguments["content"],
                "timestamp": datetime.now().isoformat(),
            })
            return [TextContent(type="text", text="Message logged")]

        elif name == "debug_log_tool_call":
            session_id = arguments["session_id"]
            if session_id not in _debug_state["sessions"]:
                return [TextContent(type="text", text=f"Error: Session not found")]
            _debug_state["sessions"][session_id]["tool_calls"].append({
                "tool_name": arguments["tool_name"],
                "arguments": arguments["arguments"],
                "success": arguments["success"],
                "result": arguments.get("result", ""),
                "timestamp": datetime.now().isoformat(),
            })
            return [TextContent(type="text", text="Tool call logged")]

        elif name == "debug_get_session":
            session_id = arguments["session_id"]
            if session_id not in _debug_state["sessions"]:
                return [TextContent(type="text", text=f"Error: Session not found")]
            data = _debug_state["sessions"][session_id].copy()
            data["session_id"] = session_id
            return [TextContent(type="text", text=json.dumps(data, indent=2))]

        elif name == "spark_test_command":
            try:
                sys.path.insert(0, os.path.expanduser("~/zero-agent/src"))
                from spark.builtin.shell import execute
                result = execute(arguments["command"])
                return [TextContent(type="text", text=json.dumps(result, indent=2))]
            except Exception as e:
                return [TextContent(type="text", text=f"Error: {e}")]

        elif name == "spark_test_llm":
            try:
                sys.path.insert(0, os.path.expanduser("~/zero-agent/src"))
                from spark.config import load_config
                from spark.llm import OllamaAdapter
                from spark.builtin.shell import get_tool_definition

                cfg = load_config()
                llm = OllamaAdapter(cfg.llm)
                tools = [get_tool_definition()] if arguments.get("use_tools") else None
                response = llm.chat([{"role": "user", "content": arguments["prompt"]}], tools=tools)
                return [TextContent(type="text", text=json.dumps({
                    "content": response.content,
                    "tool_calls": response.tool_calls,
                }, indent=2))]
            except Exception as e:
                return [TextContent(type="text", text=f"Error: {e}")]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    main()
