"""Render demo.png from the offline demo. Dev-only; needs Pillow (pip install pillow)."""
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
good, flaky = json.loads(subprocess.run([sys.executable, "demo.py", "--json"], cwd=ROOT,
                                        capture_output=True, text=True, check=True).stdout)


def font(size, bold=False):
    p = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono%s.ttf" % ("-Bold" if bold else "")
    return ImageFont.truetype(p, size) if os.path.exists(p) else ImageFont.load_default()


rows = [c for c in flaky["checks"] if c["level"] != "pass"]
W, PAD, RH = 1600, 56, 46
H = 250 + RH * len(rows) + 230
img = Image.new("RGB", (W, H), "#0d1117")
d = ImageDraw.Draw(img)
F, FB, FT, FS = font(21), font(21, True), font(44, True), font(22)
COL = {"fail": "#f85149", "warn": "#d29922", "pass": "#3fb950"}
d.text((PAD, 44), "mcp-smoke", font=FT, fill="#e6edf3")
d.text((W - PAD - 330, 56), "Applied Logic · a-l.studio", font=FS, fill="#8b949e")
d.text((PAD, 104), "Smoke-test any stdio MCP server in one command. Handshake, tools/list, tools/call.",
       font=FS, fill="#8b949e")
d.text((PAD, 160), "$ mcp-smoke --call -- python examples/flaky_server.py", font=FB, fill="#e6edf3")
x = [PAD, PAD + 100, PAD + 400, PAD + 600]
y = 205
for i, h in enumerate(["", "check", "target", "detail"]):
    d.text((x[i], y), h, font=FB, fill="#8b949e")
y += 36
d.line((PAD, y, W - PAD, y), fill="#30363d", width=2)
y += 10
for r in rows:
    d.text((x[0], y), r["level"].upper(), font=FB, fill=COL[r["level"]])
    d.text((x[1], y), r["check"], font=F, fill="#e6edf3")
    d.text((x[2], y), r["target"], font=F, fill="#c9d1d9")
    det = r["detail"] if len(r["detail"]) <= 66 else r["detail"][:63] + "..."
    d.text((x[3], y), det, font=F, fill="#c9d1d9")
    y += RH
d.line((PAD, y, W - PAD, y), fill="#30363d", width=2)
c = flaky["counts"]
d.text((PAD, y + 22), f"{c['fail']} fail · {c['warn']} warn · {c['pass']} pass   (exit code 1)", font=FB, fill="#f85149")
g = good["counts"]
d.text((PAD, y + 80), "$ mcp-smoke --call -- python examples/good_server.py", font=FB, fill="#e6edf3")
d.text((PAD, y + 122), f"{g['fail']} fail · {g['warn']} warn · {g['pass']} pass   (exit code 0)", font=FB, fill="#3fb950")
img.save(os.path.join(ROOT, "demo.png"))
print("wrote demo.png")
