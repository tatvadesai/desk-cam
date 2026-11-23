import http.server
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

import desk_cam


class DeskCamTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="desk_cam_test_")
        self.orig = (
            desk_cam.OUT_DIR,
            desk_cam.OUT_FILE,
            desk_cam.PORT,
            desk_cam.PROVIDER,
            desk_cam.MODEL,
            desk_cam.FRONTMATTER,
        )
        desk_cam.OUT_DIR = self.tmpdir
        desk_cam.OUT_FILE = "work.md"
        desk_cam.FRONTMATTER = False
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), desk_cam.Handler)
        self.port = self.server.server_address[1]
        desk_cam.PORT = self.port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        (
            desk_cam.OUT_DIR,
            desk_cam.OUT_FILE,
            desk_cam.PORT,
            desk_cam.PROVIDER,
            desk_cam.MODEL,
            desk_cam.FRONTMATTER,
        ) = self.orig
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_health_and_html_js_syntax(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health") as r:
            health = json.loads(r.read())
        self.assertTrue(health["ok"])
        self.assertEqual(health["outDir"], self.tmpdir)

        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/") as r:
            html = r.read().decode("utf-8")
        m = re.search(r"<script>(.*)</script>", html, re.S)
        self.assertIsNotNone(m)
        if shutil.which("node"):
            p = os.path.join(self.tmpdir, "check.js")
            with open(p, "w", encoding="utf-8") as f:
                f.write(m.group(1))
            res = subprocess.run(["node", "--check", p], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stderr)

    def test_confirm_plain_and_frontmatter(self):
        snap = os.path.join(self.tmpdir, "snap-20260101-000000.jpg")
        with open(snap, "wb") as f:
            f.write(b"\xff\xd8test")

        with mock.patch.object(desk_cam, "_copy_clipboard", return_value=True):
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/confirm",
                data=json.dumps({"markdown": "$x^2 + 1$", "photoName": "snap-20260101-000000.jpg"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as r:
                res = json.loads(r.read())
        self.assertTrue(res["ok"])
        self.assertFalse(os.path.exists(snap))
        with open(os.path.join(self.tmpdir, "work.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "$x^2 + 1$\n")

        desk_cam.FRONTMATTER = True
        with mock.patch.object(desk_cam, "_copy_clipboard", return_value=True):
            req2 = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/confirm",
                data=json.dumps({"markdown": "$y = 2x$"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req2) as r:
                res2 = json.loads(r.read())
        self.assertTrue(res2["overwrote"])
        with open(os.path.join(self.tmpdir, "work.md"), encoding="utf-8") as f:
            body = f.read()
        self.assertIn("verified_by_learner: true", body)
        self.assertTrue(body.endswith("$y = 2x$\n"))

    def test_csrf_rejects_foreign_origin(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/confirm",
            data=b"{}",
            headers={"Origin": "https://evil.example", "Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 403)

    def test_provider_auto_resolution(self):
        env = {"GEMINI_API_KEY": "", "OPENAI_API_KEY": "sk-test", "ANTHROPIC_API_KEY": "", "OLLAMA_HOST": ""}
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertEqual(desk_cam.resolve_provider("auto"), "openai")
            self.assertEqual(desk_cam.active_model("openai", ""), "gpt-4.1-mini")
        env2 = {"GEMINI_API_KEY": "", "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "sk-ant", "OLLAMA_HOST": ""}
        with mock.patch.dict(os.environ, env2, clear=False):
            self.assertEqual(desk_cam.resolve_provider("auto"), "anthropic")


if __name__ == "__main__":
    unittest.main()
