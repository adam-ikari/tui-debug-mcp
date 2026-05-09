# tui-debug-mcp

真正的 TUI 调试工具 - 通过伪终端（PTY）调试 TUI 应用。

## 第一性原理

调试 TUI 需要：
1. **看到屏幕内容** - 捕获终端输出
2. **发送输入** - 文本和特殊按键
3. **观察响应** - 看到变化

## 工具列表

### 会话管理

| 工具 | 描述 |
|------|------|
| `tui_start` | 启动 TUI 应用，返回初始屏幕 |
| `tui_stop` | 停止会话 |
| `tui_list` | 列出所有会话 |

### 屏幕操作

| 工具 | 描述 |
|------|------|
| `tui_read` | 读取当前屏幕（包含 ANSI 转义） |
| `tui_screenshot` | 获取清理后的纯文本快照 |

### 输入操作

| 工具 | 描述 |
|------|------|
| `tui_type` | 输入文本 |
| `tui_key` | 发送特殊按键 |

### 状态

| 工具 | 描述 |
|------|------|
| `tui_alive` | 检查进程是否存活 |
| `tui_history` | 获取输入/输出历史 |

## 支持的按键

`enter`, `tab`, `escape`, `up`, `down`, `left`, `right`, `backspace`, `delete`, `home`, `end`, `ctrl_c`, `ctrl_d`, `ctrl_l`, `ctrl_z`, `ctrl_a`, `ctrl_e`, `ctrl_k`, `ctrl_u`, `ctrl_w`, `f1`-`f10`, `page_up`, `page_down`

## 使用示例

```
1. tui_start: {"session_id": "spark", "command": "cd ~/zero-agent && PYTHONPATH=src python -m spark"}
   → 看到欢迎屏幕

2. tui_type: {"session_id": "spark", "text": "hello"}
   → 输入文本

3. tui_key: {"session_id": "spark", "key": "enter"}
   → 发送回车，看到响应

4. tui_screenshot: {"session_id": "spark"}
   → 获取清理后的屏幕内容

5. tui_key: {"session_id": "spark", "key": "ctrl_c"}
   → 退出

6. tui_stop: {"session_id": "spark"}
   → 结束会话
```

## 安装

```bash
pip install tui-debug-mcp
```

## 配置

添加到 Claude Code MCP 设置：

```json
{
  "mcpServers": {
    "tui-debug": {
      "command": "tui-debug-mcp"
    }
  }
}
```

## License

MIT