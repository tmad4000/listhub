"""Run the stamped vhost configuration locally, without Docker or host changes."""
from contextlib import ExitStack
import hashlib
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class Upstream(BaseHTTPRequestHandler):
    def do_GET(self):
        body = f'{self.server.label} {self.path}'.encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Seen-Host', self.headers['Host'])
        self.send_header('X-Seen-Proto', self.headers.get('X-Forwarded-Proto', ''))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class NginxRuntimeTests(unittest.TestCase):
    def test_vhosts_proxy_and_preserve_existing_routes(self):
        nginx = os.environ.get('NGINX_BINARY') or shutil.which('nginx')
        if not nginx:
            self.skipTest('set NGINX_BINARY to run isolated nginx routing checks')
        nginx = str(Path(nginx).resolve())
        with tempfile.TemporaryDirectory(prefix='nginx-', dir=ROOT) as tmp, ExitStack() as stack:
            prefix = Path(tmp)
            (prefix / 'logs').mkdir()
            source = (ROOT / 'tests/fixtures/noos-nginx.conf').read_text()
            self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),
                             (ROOT / 'deploy/noos-nginx-base.sha256').read_text().strip())
            config = prefix / 'nginx.conf'
            config.write_text(source)
            subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i',
                            str(ROOT / 'deploy/noos-nginx-listhub.patch')],
                           cwd=prefix, check=True, capture_output=True)
            proposed = config.read_text()

            def start_server(server):
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                def stop():
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=5)
                stack.callback(stop)
                return server.server_port

            # Remap only deployment addresses/paths. Keep every vhost, location,
            # proxy URI suffix, and forwarded header from the real configuration.
            for upstream, label in {
                'api:4000': 'noos', 'api-mcp:4100': 'mcp',
                '172.17.0.1:3006': 'notes', '172.17.0.1:5000': 'thoughtstream',
                '172.17.0.1:4001': 'openchat',
            }.items():
                server = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
                server.label = label
                port = start_server(server)
                proposed = proposed.replace(f'http://{upstream}', f'http://127.0.0.1:{port}')

            # Serve the actual ListHub app with a disposable database and OIDC off.
            stack.enter_context(patch.dict(os.environ, {
                'LISTHUB_DB': str(prefix / 'listhub.db'),
                'LISTHUB_REPO_ROOT': str(prefix / 'repos'),
                'LISTHUB_SECRET': 'nginx-routing-test',
                'IDEAFLOW_OIDC_ENABLED': 'false',
            }))
            import db
            stack.enter_context(patch.object(db, 'DB_PATH', str(prefix / 'listhub.db')))
            from app import create_app
            from werkzeug.serving import make_server, WSGIRequestHandler
            class QuietHandler(WSGIRequestHandler):
                def log(self, *args, **kwargs):
                    pass
            port = start_server(make_server('127.0.0.1', 0, create_app(),
                                            request_handler=QuietHandler))
            proposed = proposed.replace('http://172.17.0.1:3200', f'http://127.0.0.1:{port}')
            for path, label in {
                '/usr/share/nginx/html-staging': 'staging',
                '/usr/share/nginx/html': 'noos-spa',
                '/usr/share/nginx/wikihub/agentfirst': 'agentfirst',
            }.items():
                root = prefix / label
                (root / 'assets').mkdir(parents=True)
                (root / 'index.html').write_text(label)
                (root / 'assets/probe.js').write_text(label + '-asset')
                proposed = proposed.replace(path, str(root))
            (prefix / 'mime.types').write_text('types { text/html html; }\n')
            proposed = proposed.replace('/etc/nginx/mime.types', str(prefix / 'mime.types'))
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1', 0))
                listen_port = reservation.getsockname()[1]
            proposed = proposed.replace('listen 80', f'listen 127.0.0.1:{listen_port}')
            config.write_text('daemon off;\nmaster_process off;\n' + proposed)
            command = [nginx, '-p', str(prefix) + '/', '-c', str(config), '-e', 'stderr']
            checked = subprocess.run(command + ['-t'], capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            log = stack.enter_context((prefix / 'runtime.log').open('w+'))
            process = subprocess.Popen(command, stdout=log, stderr=log)
            def stop_nginx():
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
            stack.callback(stop_nginx)
            deadline = time.monotonic() + 5
            while True:
                try:
                    with socket.create_connection(('127.0.0.1', listen_port), timeout=.1):
                        break
                except OSError:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        log.seek(0)
                        self.fail('nginx did not start: ' + log.read())
                    time.sleep(.05)

            def get(host, path):
                connection = HTTPConnection('127.0.0.1', listen_port, timeout=5)
                try:
                    connection.request('GET', path, headers={'Host': host})
                    response = connection.getresponse()
                    return response.status, dict(response.getheaders()), response.read().decode()
                finally:
                    connection.close()

            for host, label in {
                'globalbr.ai': 'noos-spa', 'www.globalbr.ai': 'noos-spa',
                'base.ideaflow.app': 'noos-spa', 'staging.globalbr.ai': 'staging',
                'agentfirst.globalbr.ai': 'agentfirst', 'agentfirst.ideaflow.app': 'agentfirst',
                'unknown.example.test': 'noos-spa',
            }.items():
                with self.subTest(host=host):
                    self.assertEqual(get(host, '/')[::2], (200, label))
                    self.assertEqual(get(host, '/deep/link')[::2], (200, label))
                    self.assertEqual(get(host, '/assets/probe.js')[::2], (200, label + '-asset'))

            for host in ('globalbr.ai', 'www.globalbr.ai', 'base.ideaflow.app',
                         'staging.globalbr.ai', 'unknown.example.test'):
                paths = ['/api/probe?check=1', '/auth/probe', '/bridge/auth/probe',
                         '/bridge/unlock/probe', '/skill.md', '/.well-known/probe']
                if host != 'unknown.example.test':
                    paths.append('/health')
                if host in ('globalbr.ai', 'www.globalbr.ai', 'base.ideaflow.app'):
                    paths.extend(['/slack/events', '/mcp', '/mcp/healthz'])
                for path in paths:
                    with self.subTest(host=host, path=path):
                        label = 'mcp' if path.startswith('/mcp') else 'noos'
                        status, headers, body = get(host, path)
                        upstream_path = '/healthz' if path == '/mcp/healthz' else path
                        self.assertEqual((status, body), (200, f'{label} {upstream_path}'))
                        if path not in ('/health', '/mcp/healthz'):
                            self.assertEqual(headers['X-Seen-Host'], host)
            for host, label in {'notes.globalbr.ai': 'notes', 'ts.globalbr.ai': 'thoughtstream',
                                'chat.globalbr.ai': 'openchat'}.items():
                with self.subTest(host=host):
                    status, headers, body = get(host, '/probe?check=1')
                    self.assertEqual((status, body), (200, label + ' /probe?check=1'))
                    self.assertEqual(headers['X-Seen-Host'], host)
                    self.assertEqual(headers['X-Seen-Proto'], 'http')
            for path in ('/api/docs', '/llms.txt', '/login/local'):
                with self.subTest(host='listhub.globalbr.ai', path=path):
                    status, _, body = get('listhub.globalbr.ai', path)
                    self.assertEqual(status, 200)
                    self.assertIn('ListHub', body)
            status, headers, _ = get('listhub.globalbr.ai', '/login')
            self.assertEqual(status, 302)
            self.assertIn('/auth/noos/login', headers['Location'])
            self.assertEqual(get('listhub.globalbr.ai', '/auth/ideaflow/callback')[0], 404)


if __name__ == '__main__':
    unittest.main()
