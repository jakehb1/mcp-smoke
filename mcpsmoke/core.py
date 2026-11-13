"""Spawn a stdio MCP server, run the handshake, list tools, optionally call them, and report problems.

Standard library only. MCP stdio transport is newline-delimited JSON-RPC 2.0 on stdin/stdout.
"""
import json
import queue
import shlex
import subprocess
import threading
import time

PROTOCOL_VERSION = "2025-06-18"


class Report:
    def __init__(self, command):
        self.command = command
        self.checks = []      # dicts: level, check, target, detail
        self.server = {}
        self.tools = []       # dicts: name, ms, status
        self.stdout_noise = []
        self.stderr_tail = []

    def add(self, level, check, target, detail):
        self.checks.append({"level": level, "check": check, "target": target, "detail": detail})

    def counts(self):
        c = {"fail": 0, "warn": 0, "pass": 0}
        for x in self.checks:
            c[x["level"]] += 1
        return c

    def ok(self):
        return self.counts()["fail"] == 0

    def to_dict(self):
        return {"command": self.command, "server": self.server, "tools": self.tools,
                "checks": self.checks, "counts": self.counts(), "ok": self.ok(),
                "stdout_noise": self.stdout_noise, "stderr_tail": self.stderr_tail}


class Session:
    def __init__(self, argv, report, timeout):
        self.report = report
        self.timeout = timeout
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, bufsize=1)
        self.msgs = queue.Queue()
        self.next_id = 1
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self):
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                if not isinstance(msg, dict):
                    raise ValueError
            except ValueError:
                self.report.stdout_noise.append(line[:200])
                continue
            self.msgs.put(msg)
        self.msgs.put(None)

    def _read_stderr(self):
        for line in self.proc.stderr:
            self.report.stderr_tail = (self.report.stderr_tail + [line.rstrip()[:200]])[-10:]

    def send(self, obj):
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def notify(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self.send(msg)

    def request(self, method, params=None, timeout=None):
        """Returns (response_or_None, elapsed_ms). None means timeout or server exit."""
        rid = self.next_id
        self.next_id += 1
        msg = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        t0 = time.monotonic()
        try:
            self.send(msg)
        except (BrokenPipeError, OSError):
            return None, 0
        deadline = t0 + (timeout or self.timeout)
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return None, int((time.monotonic() - t0) * 1000)
            try:
                m = self.msgs.get(timeout=left)
            except queue.Empty:
                continue
            if m is None:
                return None, int((time.monotonic() - t0) * 1000)
            if m.get("id") == rid and ("result" in m or "error" in m):
                return m, int((time.monotonic() - t0) * 1000)
            if "method" in m and "id" in m:  # server->client request (e.g. ping); answer politely
                self.send({"jsonrpc": "2.0", "id": m["id"], "result": {}})

    def close(self):
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        for f in (self.proc.stdout, self.proc.stderr):
            try:
                f.close()
            except (OSError, ValueError):
                pass


def sample_value(schema, depth=0):
    """Build a plausible argument value from a JSON Schema fragment."""
    if not isinstance(schema, dict) or depth > 4:
        return "test"
    if "default" in schema:
        return schema["default"]
    if "const" in schema:
        return schema["const"]
    if schema.get("enum"):
        return schema["enum"][0]
    if schema.get("examples"):
        return schema["examples"][0]
    for key in ("anyOf", "oneOf"):
        if schema.get(key):
            return sample_value(schema[key][0], depth + 1)
    t = schema.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), "string")
    if t == "integer":
        return max(1, int(schema.get("minimum", 1)))
    if t == "number":
        return float(schema.get("minimum", 1.0))
    if t == "boolean":
        return True
    if t == "array":
        n = schema.get("minItems", 0)
        return [sample_value(schema.get("items", {}), depth + 1) for _ in range(n)]
    if t == "object" or "properties" in schema:
        return sample_args(schema, depth + 1)
    if schema.get("format") == "uri":
        return "https://example.com"
    s = "test"
    if schema.get("minLength", 0) > len(s):
        s = s * schema["minLength"]
    return s


def sample_args(schema, depth=0):
    props = (schema or {}).get("properties", {}) or {}
    req = (schema or {}).get("required", []) or []
    return {k: sample_value(props.get(k, {}), depth) for k in req}


def check_tool_def(report, tool):
    name = tool.get("name")
    if not isinstance(name, str) or not name:
        report.add("fail", "tool.name", "?", "tool has no name")
        return False
    if not tool.get("description"):
        report.add("warn", "tool.description", name, "no description; the model has to guess what it does")
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        report.add("fail", "tool.inputSchema", name, "missing inputSchema (spec requires an object schema)")
        return True
    if schema.get("type") != "object":
        report.add("fail", "tool.inputSchema", name, f"inputSchema.type is {schema.get('type')!r}, expected 'object'")
    props = schema.get("properties", {}) or {}
    for r in schema.get("required", []) or []:
        if r not in props:
            report.add("fail", "tool.inputSchema", name, f"required field {r!r} is not in properties")
    return True


def run(command, call=False, timeout=10.0, slow_ms=1000, only=None):
    argv = shlex.split(command) if isinstance(command, str) else list(command)
    report = Report(" ".join(argv))
    try:
        s = Session(argv, report, timeout)
    except OSError as e:
        report.add("fail", "spawn", argv[0], f"could not start server: {e}")
        return report
    try:
        _run(s, report, call, slow_ms, only)
    finally:
        s.close()
        time.sleep(0.05)
    if report.stdout_noise:
        report.add("fail", "stdout.clean", "server",
                   f"{len(report.stdout_noise)} non-JSON line(s) on stdout (log to stderr instead): "
                   f"{report.stdout_noise[0][:60]!r}")
    else:
        report.add("pass", "stdout.clean", "server", "stdout carried only JSON-RPC")
    return report


def _run(s, report, call, slow_ms, only):
    resp, ms = s.request("initialize", {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "mcp-smoke", "version": "0.1.0"},
    })
    if resp is None:
        report.add("fail", "initialize", "server", f"no response after {ms} ms (crashed or hung)")
        return
    if "error" in resp:
        report.add("fail", "initialize", "server", f"error: {resp['error'].get('message')}")
        return
    res = resp.get("result", {}) or {}
    info = res.get("serverInfo", {}) or {}
    report.server = {"name": info.get("name"), "version": info.get("version"),
                     "protocolVersion": res.get("protocolVersion"), "init_ms": ms}
    report.add("pass", "initialize", "server", f"{info.get('name')} {info.get('version')} in {ms} ms")
    if not res.get("protocolVersion"):
        report.add("fail", "initialize.protocolVersion", "server", "no protocolVersion in result")
    if not info.get("name"):
        report.add("warn", "initialize.serverInfo", "server", "no serverInfo.name")
    caps = res.get("capabilities", {}) or {}
    s.notify("notifications/initialized")

    if "tools" not in caps:
        report.add("warn", "capabilities.tools", "server", "server does not advertise tools")
        return

    tools, cursor, pages = [], None, 0
    while True:
        params = {"cursor": cursor} if cursor else {}
        resp, ms = s.request("tools/list", params)
        pages += 1
        if resp is None or "error" in resp:
            why = "no response" if resp is None else resp["error"].get("message")
            report.add("fail", "tools/list", "server", why)
            return
        r = resp.get("result", {}) or {}
        tools.extend(r.get("tools", []) or [])
        cursor = r.get("nextCursor")
        if not cursor or pages >= 50:
            break
    report.add("pass", "tools/list", "server", f"{len(tools)} tool(s) across {pages} page(s)")

    seen = set()
    for t in tools:
        if not check_tool_def(report, t):
            continue
        if t["name"] in seen:
            report.add("fail", "tool.name.unique", t["name"], "duplicate tool name")
        seen.add(t["name"])

    called = set()
    for t in tools:
        name = t.get("name")
        if not name or name in called:
            continue
        called.add(name)
        row = {"name": name, "ms": None, "status": "listed"}
        report.tools.append(row)
        if not call or (only and name not in only):
            continue
        args = sample_args(t.get("inputSchema") or {})
        resp, ms = s.request("tools/call", {"name": name, "arguments": args})
        row["ms"] = ms
        if resp is None:
            row["status"] = "timeout"
            report.add("fail", "tools/call", name, f"no response after {ms} ms")
            if s.proc.poll() is not None:
                report.add("fail", "server.alive", "server", f"server exited (code {s.proc.returncode})")
                return
            continue
        if "error" in resp:
            row["status"] = "rpc-error"
            report.add("fail", "tools/call", name,
                       f"JSON-RPC error {resp['error'].get('code')}: {resp['error'].get('message')} "
                       "(tool failures should return isError, not crash the call)")
            continue
        r = resp.get("result", {}) or {}
        if not isinstance(r.get("content"), list):
            row["status"] = "bad-result"
            report.add("fail", "tools/call.content", name, "result has no content array")
            continue
        if r.get("isError"):
            row["status"] = "isError"
            report.add("warn", "tools/call", name, "returned isError with sample args")
        else:
            row["status"] = "ok"
        if ms > slow_ms:
            report.add("warn", "tools/call.latency", name, f"{ms} ms (slower than {slow_ms} ms)")
        elif row["status"] == "ok":
            report.add("pass", "tools/call", name, f"ok in {ms} ms")
