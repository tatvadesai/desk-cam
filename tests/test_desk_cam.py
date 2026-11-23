import http.client
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
        self.server = desk_cam.DeskCamServer(("127.0.0.1", 0), desk_cam.Handler)
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

    def test_health_and_html_security_and_js_syntax(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health") as r:
            health = json.loads(r.read())
        self.assertTrue(health["ok"])
        self.assertEqual(health["outDir"], self.tmpdir)

        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/") as r:
            html = r.read().decode("utf-8")
        self.assertIn("escHtml(", html)
        self.assertNotIn("dev.innerHTML", html)
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
        self.assertIn("captured_at:", body)
        self.assertTrue(body.endswith("$y = 2x$\n"))

    def test_csrf_and_dns_rebinding_guards(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/confirm",
            data=b"{}",
            headers={"Origin": "https://evil.example", "Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 403)

        req_sfs = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/confirm",
            data=b"{}",
            headers={"Sec-Fetch-Site": "cross-site", "Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx2:
            urllib.request.urlopen(req_sfs)
        self.assertEqual(ctx2.exception.code, 403)

        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.putrequest("GET", "/health", skip_host=True)
        conn.putheader("Host", "evil.rebind.example:8765")
        conn.endheaders()
        resp = conn.getresponse()
        self.assertEqual(resp.status, 403)
        conn.close()

    def test_symlink_protection_and_bad_content_length(self):
        outside = tempfile.NamedTemporaryFile(delete=False)
        outside.write(b"secret")
        outside.close()
        try:
            link_path = os.path.join(self.tmpdir, "leak.md")
            os.symlink(outside.name, link_path)
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/file?name=leak.md")
            self.assertEqual(ctx.exception.code, 404)
        finally:
            os.unlink(outside.name)

        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("POST", "/confirm", body=b"", headers={"Content-Length": "abc"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 400)
        conn.close()

    def test_capture_unique_names_and_delete(self):
        fake_jpeg = b"\xff\xd8\xff\xe0test"
        with mock.patch.object(desk_cam, "stream_transcribe_chunks", return_value=iter([{"done": True, "markdown": "$x$", "model": "m"}])):
            r1 = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{self.port}/capture", data=fake_jpeg, method="POST"))
            self.assertEqual(r1.status, 200)
            r2 = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{self.port}/capture", data=fake_jpeg, method="POST"))
            self.assertEqual(r2.status, 200)
        snaps = sorted(f for f in os.listdir(self.tmpdir) if f.startswith("snap-"))
        self.assertEqual(len(snaps), 2)

        del_req = urllib.request.Request(f"http://127.0.0.1:{self.port}/delete?name={snaps[0]}", method="POST")
        with urllib.request.urlopen(del_req) as r:
            self.assertEqual(json.loads(r.read())["deleted"], snaps[0])

    def test_validation_and_provider_auto_resolution(self):
        with self.assertRaises(ValueError):
            desk_cam._validated_model("../bad?x=1")
        with self.assertRaises(ValueError):
            desk_cam._validated_http_url("file:///etc/passwd", "OPENAI_BASE_URL")

        env = {"GEMINI_API_KEY": "", "OPENAI_API_KEY": "sk-test", "ANTHROPIC_API_KEY": "", "OLLAMA_HOST": ""}
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertEqual(desk_cam.resolve_provider("auto"), "openai")
            self.assertEqual(desk_cam.active_model("openai", ""), "gpt-4.1-mini")
        env2 = {"GEMINI_API_KEY": "", "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "sk-ant", "OLLAMA_HOST": ""}
        with mock.patch.dict(os.environ, env2, clear=False):
            self.assertEqual(desk_cam.resolve_provider("auto"), "anthropic")


if __name__ == "__main__":
    unittest.main()
