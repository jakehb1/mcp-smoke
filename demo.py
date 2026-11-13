"""Offline demo: smoke-test the bundled good and flaky MCP servers. No API keys, no network."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcpsmoke.cli import main  # noqa: E402
from mcpsmoke.core import run  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
servers = [os.path.join(HERE, "examples", f) for f in ("good_server.py", "flaky_server.py")]

if "--json" in sys.argv:
    print(json.dumps([run([sys.executable, s], call=True).to_dict() for s in servers]))
else:
    for s in servers:
        main(["--call", "--", sys.executable, os.path.relpath(s, HERE)])
        print()
