"""A stdio MCP server with the bugs people actually ship. Used for the offline demo and tests.

- prints a startup log line to stdout (corrupts the JSON-RPC stream in strict clients)
- one tool has no inputSchema, one requires a field it never defines
- a duplicate tool name
- one tool raises a JSON-RPC error instead of returning isError
- one tool is slow
"""
import json
import sys
import time

print("flaky-server starting on stdio...")  # the classic bug: logging to stdout
sys.stdout.flush()

TOOLS = [
    {"name": "search_docs", "description": "Search the docs.",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "fetch_page"},
    {"name": "create_ticket", "description": "Open a ticket.",
     "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title", "priority"]}},
    {"name": "summarize", "description": "",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "search_docs", "description": "Search the docs again.",
     "inputSchema": {"type": "object", "properties": {}}},
]


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    msg = json.loads(line)
    m, mid = msg.get("method"), msg.get("id")
    if mid is None:
        continue
    if m == "initialize":
        send({"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
            "serverInfo": {"name": "flaky-server", "version": "0.0.3"}}})
    elif m == "tools/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
    elif m == "tools/call":
        n = msg["params"]["name"]
        if n == "create_ticket":
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": "KeyError: 'priority'"}})
        elif n == "summarize":
            time.sleep(1.6)
            send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": "ok"}]}})
        elif n == "fetch_page":
            send({"jsonrpc": "2.0", "id": mid, "result": {"text": "no content array here"}})
        else:
            send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": "3 hits"}]}})
