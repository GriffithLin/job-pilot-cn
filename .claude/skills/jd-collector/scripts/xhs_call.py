# -*- coding: utf-8 -*-
"""小红书 MCP 调用工具（绕过 Windows curl 的 ANSI 代码页乱码问题）。

用法：
  python xhs_call.py <tool_name> [args.json]
  - tool_name: MCP 工具名（ASCII，如 search_feeds / get_feed_detail）
  - args.json: 参数 JSON 文件的路径；文件内容为 UTF-8 编码的 JSON 对象。
              省略时传 {}。
结果以 UTF-8 打印到 stdout。
"""
import json
import os
import sys
import urllib.request

MCP_URL = os.environ.get("MCP_URL", "http://localhost:18060/mcp")


def post(url, payload, session_id=None, timeout=150):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return body, resp.headers.get("Mcp-Session-Id")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    tool_name = sys.argv[1]
    args = {}
    if len(sys.argv) > 2:
        with open(sys.argv[2], encoding="utf-8") as f:
            args = json.load(f)

    # 1. initialize 拿 Session ID
    init = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "xhs-py", "version": "1.0"},
        },
    }
    _, session_id = post(MCP_URL, init)
    if not session_id:
        print("错误: 无法获取 MCP Session ID", file=sys.stderr)
        sys.exit(1)

    # 2. initialized 通知
    post(MCP_URL, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id)

    # 3. 调用工具
    call = {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": tool_name, "arguments": args},
    }
    body, _ = post(MCP_URL, call, session_id)
    sys.stdout.buffer.write(body.encode("utf-8"))


if __name__ == "__main__":
    main()
