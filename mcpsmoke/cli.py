import argparse
import json
import sys

from . import __version__
from .core import run

C = {"fail": "\033[31m", "warn": "\033[33m", "pass": "\033[32m", "dim": "\033[2m", "end": "\033[0m"}


def main(argv=None):
    p = argparse.ArgumentParser(prog="mcp-smoke",
                                description="Smoke-test a stdio MCP server: handshake, tools/list, optional tools/call.")
    p.add_argument("command", nargs=argparse.REMAINDER,
                   help="server command, e.g. -- python server.py (put it after --)")
    p.add_argument("--call", action="store_true",
                   help="also call every tool with sample args built from its schema (tools may have side effects!)")
    p.add_argument("--only", action="append", help="only call this tool (repeatable)")
    p.add_argument("--timeout", type=float, default=10.0, help="seconds to wait per request (default 10)")
    p.add_argument("--slow-ms", type=int, default=1000, help="warn when a call is slower than this (default 1000)")
    p.add_argument("--json", action="store_true", help="print the report as JSON")
    p.add_argument("--quiet", action="store_true", help="hide passing checks")
    p.add_argument("--version", action="version", version=__version__)
    a = p.parse_args(argv)
    cmd = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not cmd:
        p.error("give the server command after --, e.g. mcp-smoke -- python server.py")

    rep = run(cmd, call=a.call, timeout=a.timeout, slow_ms=a.slow_ms, only=a.only)
    if a.json:
        print(json.dumps(rep.to_dict(), indent=2))
        return 0 if rep.ok() else 1

    color = sys.stdout.isatty()
    c = (lambda k: C[k]) if color else (lambda k: "")
    print(f"mcp-smoke {c('dim')}{rep.command}{c('end')}")
    for x in rep.checks:
        if a.quiet and x["level"] == "pass":
            continue
        print(f"  {c(x['level'])}{x['level'].upper():<4}{c('end')}  {x['check']:<26} {x['target']:<14} {x['detail']}")
    n = rep.counts()
    print(f"\n{n['fail']} fail, {n['warn']} warn, {n['pass']} pass")
    if rep.stderr_tail and not rep.ok():
        print(f"{c('dim')}last stderr: {rep.stderr_tail[-1]}{c('end')}")
    return 0 if rep.ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
