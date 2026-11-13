"""A small, well-behaved stdio MCP server (stdlib only) used for the offline demo and tests."""
import json
import sys

TOOLS = [
    {"name": "add", "description": "Add two integers.",
     "inputSchema": {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                     "required": ["a", "b"]}},
    {"name": "echo", "description": "Echo a message back.",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "weather", "description": "Fake weather for a city (offline).",
     "inputSchema": {"type": "object", "properties": {
         "city": {"type": "string"}, "units": {"type": "string", "enum": ["c", "f"]}}, "required": ["city", "units"]}},
]


def reply(mid, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}) + "\n")
    sys.stdout.flush()


def text(s):
    return {"content": [{"type": "text", "text": s}]}


for line in sys.stdin:
    msg = json.loads(line)
    m, mid = msg.get("method"), msg.get("id")
    if mid is None:
        continue
    if m == "initialize":
        reply(mid, {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                    "serverInfo": {"name": "good-server", "version": "1.0.0"}})
    elif m == "tools/list":
        reply(mid, {"tools": TOOLS})
    elif m == "tools/call":
        n, a = msg["params"]["name"], msg["params"].get("arguments", {})
        if n == "add":
            reply(mid, text(str(a["a"] + a["b"])))
        elif n == "echo":
            reply(mid, text(a["text"]))
        elif n == "weather":
            reply(mid, text(f"{a['city']}: 21{a['units'].upper()}, clear"))
        else:
            reply(mid, {"content": [{"type": "text", "text": "unknown tool"}], "isError": True})
    else:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid,
                                     "error": {"code": -32601, "message": "method not found"}}) + "\n")
        sys.stdout.flush()
