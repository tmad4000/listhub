import hashlib
import json
import os
from pathlib import Path
import subprocess
import re
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
        if checkout:
            base = subprocess.check_output(
                ["git", "-C", str(Path(checkout).expanduser()), "show",
                 f"{BASE_COMMIT}:nginx.conf"],
                text=True,
            )
        else:
            base = (ROOT / "tests/fixtures/noos-nginx.conf").read_text()
        expected_sha = BASE_SHA_FILE.read_text().strip()
        self.assertEqual(hashlib.sha256(base.encode()).hexdigest(), expected_sha)

        with tempfile.TemporaryDirectory() as tmp:
            nginx_path = Path(tmp) / "nginx.conf"
            nginx_path.write_text(base)
            applied = subprocess.run(
                ["patch", "--batch", "--fuzz=0", "-p1", "-i", str(PATCH)],
                cwd=tmp,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertNotIn('offset', applied.stdout.lower())
            patched = nginx_path.read_text()

        addition = '\n'.join(
            line[1:] for line in PATCH.read_text().splitlines()
            if line.startswith('+') and not line.startswith('+++')
        ) + '\n'
        self.assertEqual(patched.replace(addition, '', 1), base,
                         'Every existing route must remain byte-for-byte unchanged')

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

        evidence = os.environ.get('LISTHUB_TEST_EVIDENCE')
        if evidence:
            destination = Path(evidence)
            destination.mkdir(parents=True, exist_ok=True)
            (destination / 'nginx.conf.proposed').write_text(patched)
            (destination / 'routing-validation.json').write_text(json.dumps({
                'base_commit': BASE_COMMIT,
                'base_sha256': expected_sha,
                'existing_routes_byte_identical': patched.replace(addition, '', 1) == base,
                'preserved_server_names': re.findall(r'server_name\s+([^;]+);', base),
                'added_host': 'listhub.globalbr.ai',
                'added_upstream': 'http://172.17.0.1:3200',
                'applied_to_production': False,
                'validation_scope': 'Source patch only; nginx runtime and live routing require separate validation',
            }, indent=2))


if __name__ == "__main__":
    unittest.main()
