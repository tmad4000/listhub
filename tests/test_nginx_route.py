import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "deploy" / "noos-nginx-listhub.patch"
BASE_SHA_FILE = ROOT / "deploy" / "noos-nginx-base.sha256"
BASE_COMMIT = "31231f6e362590b8330765a98d656ab03fcc6c24"


class ListHubNginxRouteTest(unittest.TestCase):
    def test_patch_is_additive_and_exactly_scoped(self):
        text = PATCH.read_text()
        changed = [line for line in text.splitlines() if line.startswith(("+", "-"))]
        removed = [line for line in changed if line.startswith("-") and not line.startswith("---")]
        self.assertEqual(removed, [], "route patch must not remove or rewrite existing nginx lines")
        added = "\n".join(line[1:] for line in changed if line.startswith("+") and not line.startswith("+++"))
        self.assertEqual(added.count("server_name listhub.globalbr.ai;"), 1)
        self.assertIn("proxy_pass http://172.17.0.1:3200;", added)
        self.assertIn("proxy_set_header Host $host;", added)
        self.assertNotIn("default_server", added)
        for existing_host in (
            "globalbr.ai", "staging.globalbr.ai", "notes.globalbr.ai",
            "ts.globalbr.ai", "chat.globalbr.ai", "agentfirst.globalbr.ai",
        ):
            self.assertNotIn(f"server_name {existing_host};", added)

    def test_patch_applies_cleanly_to_stamped_noos_source(self):
        checkout = os.environ.get("NOOS_CHECKOUT")
        if not checkout:
            self.skipTest("set NOOS_CHECKOUT for the source-grounded integration check")
        checkout = str(Path(checkout).expanduser())
        base = subprocess.check_output(
            ["git", "-C", checkout, "show", f"{BASE_COMMIT}:nginx.conf"],
            text=True,
        )
        expected_sha = BASE_SHA_FILE.read_text().strip()
        self.assertEqual(hashlib.sha256(base.encode()).hexdigest(), expected_sha)

        with tempfile.TemporaryDirectory() as tmp:
            nginx_path = Path(tmp) / "nginx.conf"
            nginx_path.write_text(base)
            subprocess.run(
                ["patch", "--batch", "--fuzz=0", "-p1", "-i", str(PATCH)],
                cwd=tmp,
                check=True,
                capture_output=True,
                text=True,
            )
            patched = nginx_path.read_text()

        self.assertEqual(patched.count("server_name listhub.globalbr.ai;"), 1)
        self.assertLess(
            patched.index("server_name listhub.globalbr.ai;"),
            patched.index("listen 80 default_server;"),
        )
        self.assertEqual(patched.count("proxy_pass http://172.17.0.1:3200;"), 1)
        representative_routes = {
            "globalbr.ai www.globalbr.ai base.ideaflow.app": "proxy_pass http://api:4000/api/;",
            "staging.globalbr.ai": "root /usr/share/nginx/html-staging;",
            "notes.globalbr.ai": "proxy_pass http://172.17.0.1:3006;",
            "ts.globalbr.ai": "proxy_pass http://172.17.0.1:5000;",
            "chat.globalbr.ai": "proxy_pass http://172.17.0.1:4001;",
            "agentfirst.globalbr.ai agentfirst.ideaflow.app": "root /usr/share/nginx/wikihub/agentfirst;",
        }
        for server_name, behavior in representative_routes.items():
            self.assertIn(f"server_name {server_name};", patched)
            self.assertIn(behavior, patched)
        self.assertEqual(patched.count("listen 80 default_server;"), 1)
        self.assertEqual(patched.count("server_name _;"), 1)
        self.assertEqual(patched.count("{"), patched.count("}"))


if __name__ == "__main__":
    unittest.main()
