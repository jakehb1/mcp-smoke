import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from mcpsmoke.core import run, sample_args  # noqa: E402

GOOD = [sys.executable, os.path.join(ROOT, "examples", "good_server.py")]
FLAKY = [sys.executable, os.path.join(ROOT, "examples", "flaky_server.py")]


def checks(rep, level):
    return {(c["check"], c["target"]) for c in rep.checks if c["level"] == level}


class TestGood(unittest.TestCase):
    def test_good_server_passes(self):
        rep = run(GOOD, call=True)
        self.assertTrue(rep.ok(), rep.checks)
        self.assertEqual(rep.server["name"], "good-server")
        self.assertEqual([t["status"] for t in rep.tools], ["ok", "ok", "ok"])

    def test_list_only_does_not_call(self):
        rep = run(GOOD, call=False)
        self.assertTrue(all(t["status"] == "listed" for t in rep.tools))


class TestFlaky(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rep = run(FLAKY, call=True, slow_ms=1000)

    def test_fails(self):
        self.assertFalse(self.rep.ok())

    def test_stdout_noise(self):
        self.assertIn(("stdout.clean", "server"), checks(self.rep, "fail"))

    def test_schema_problems(self):
        f = checks(self.rep, "fail")
        self.assertIn(("tool.inputSchema", "fetch_page"), f)
        self.assertIn(("tool.inputSchema", "create_ticket"), f)
        self.assertIn(("tool.name.unique", "search_docs"), f)

    def test_call_problems(self):
        self.assertIn(("tools/call", "create_ticket"), checks(self.rep, "fail"))
        self.assertIn(("tools/call.content", "fetch_page"), checks(self.rep, "fail"))
        self.assertIn(("tools/call.latency", "summarize"), checks(self.rep, "warn"))
        self.assertIn(("tool.description", "summarize"), checks(self.rep, "warn"))


class TestMisc(unittest.TestCase):
    def test_missing_binary(self):
        rep = run(["definitely-not-a-real-binary-xyz"])
        self.assertIn(("spawn", "definitely-not-a-real-binary-xyz"), checks(rep, "fail"))

    def test_hung_server_times_out(self):
        rep = run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5)
        self.assertIn(("initialize", "server"), checks(rep, "fail"))

    def test_sample_args(self):
        s = {"type": "object", "required": ["a", "b", "c", "d", "e"], "properties": {
            "a": {"type": "integer", "minimum": 5}, "b": {"enum": ["x", "y"]}, "c": {"type": "boolean"},
            "d": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "e": {"type": "object", "properties": {"z": {"type": "number"}}, "required": ["z"]}}}
        self.assertEqual(sample_args(s), {"a": 5, "b": "x", "c": True, "d": ["test"], "e": {"z": 1.0}})


if __name__ == "__main__":
    unittest.main()
