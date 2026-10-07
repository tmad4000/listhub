"""Exercise compatibility through HTTP routes with real SQLite and Git state."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from test_ideaflow_auth import app, get_db
from git_backend import REPO_ROOT


class IdentityPreservationTests(unittest.TestCase):
    def test_linked_login_preserves_agent_content_and_git(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        client = app.test_client()
        anonymous = app.test_client()
        transcript = []
        evidence = os.environ.get('LISTHUB_TEST_EVIDENCE')

        def capture(name, response):
            if not evidence:
                return
            # Preserve the actual HTTP-rendered page and inline its stylesheet
            # responses so this evidence opens without a local server.
            html = response.get_data(as_text=True)
            def stylesheet(match):
                with client.get(match[1]) as css:
                    return '<style>' + css.get_data(as_text=True) + '</style>'
            html = re.sub(r'<link rel="stylesheet" href="([^"]+)">',
                          stylesheet, html)
            html = re.sub(r'<script[^>]*src="[^"]+"[^>]*></script>', '', html)
            Path(evidence, name + '.html').write_text(html)

        try:
            registered = anonymous.post('/api/v1/auth/register', json={
                'username': 'linkcheck', 'password': 'test-password-only', 'email': 'linkcheck@example.test'})
            self.assertEqual(registered.status_code, 201)
            account = registered.json
            headers = {'Authorization': 'Bearer ' + account['key']}
            transcript.append({'step': 'Agent registration without browser or verification',
                               'status': 201, 'local_id': account['id'], 'username': account['username']})
            item_response = anonymous.post('/api/v1/items/new', headers=headers, json={
                'title': 'Preserved private note', 'content': 'Owner-only content', 'visibility': 'private'})
            self.assertEqual(item_response.status_code, 201)
            item = item_response.json
            repo = Path(REPO_ROOT, 'linkcheck.git')
            head = subprocess.check_output(['git', '--git-dir=' + str(repo), 'rev-parse', 'HEAD'], text=True).strip()
            self.assertEqual(client.post('/login/local', data={
                'username': 'linkcheck', 'password': 'test-password-only'}).status_code, 302)
            client.post('/auth/ideaflow/link')
            with client.session_transaction() as session:
                state = session['ideaflow_pending']['state']
            claims = dict(sub='preserved-subject', email='different@example.test', email_verified=True)
            with patch('ideaflow_auth.exchange', return_value=claims):
                self.assertEqual(client.get('/auth/ideaflow/callback', query_string={
                    'state': state, 'code': 'fixture-code'}).location, '/dash')
            capture('linked-dashboard', client.get('/dash'))
            client.get('/logout')
            capture('signed-out-login', client.get('/login'))
            self.assertNotIn('prompt=none', client.get('/login').location or '')
            chooser = client.get('/auth/ideaflow/login')
            self.assertEqual(parse_qs(urlparse(chooser.location).query)['prompt'], ['select_account'])
            transcript.append({'step': 'Sign out then sign in', 'provider_prompt': 'select_account'})
            with client.session_transaction() as session:
                state = session['ideaflow_pending']['state']
            with patch('ideaflow_auth.exchange', return_value=claims):
                self.assertEqual(client.get('/auth/ideaflow/callback', query_string={
                    'state': state, 'code': 'fixture-code'}).location, '/dash')
            with client.session_transaction() as session:
                self.assertEqual(session['_user_id'], account['id'])
            self.assertEqual(client.get('/api/v1/items/' + item['id']).json['content'], 'Owner-only content')
            self.assertEqual(anonymous.get('/api/v1/items/' + item['id']).status_code, 401)
            self.assertEqual(anonymous.get('/api/v1/items/' + item['id'], headers=headers).json, item)
            self.assertEqual(anonymous.post('/api/v1/auth/token', json={
                'username': 'linkcheck', 'password': 'test-password-only'}).status_code, 201)
            self.assertEqual(subprocess.check_output([
                'git', '--git-dir=' + str(repo), 'rev-parse', 'HEAD'], text=True).strip(), head)
            self.assertEqual(anonymous.get('/git/linkcheck.git/info/refs?service=git-upload-pack',
                headers={'Authorization': 'Basic ' + base64.b64encode(
                    ('linkcheck:' + account['key']).encode()).decode()}).status_code, 200)
            transcript.append({'step': 'Linked Ideaflow login (provider exchange fixture)',
                'local_id': account['id'], 'item': item, 'anonymous_private_read_status': 401,
                'existing_bearer_key_read_status': 200, 'local_password_token_status': 201,
                'git_head_unchanged': head, 'git_api_key_clone_advertisement_status': 200})
            self.assertEqual(parse_qs(urlparse(client.get('/auth/ideaflow/switch-account').location).query)[
                'prompt'], ['select_account'])
            transcript.append({'step': 'Switch account', 'provider_prompt': 'select_account'})
            if evidence:
                Path(evidence, 'identity-preservation.json').write_text(json.dumps(transcript, indent=2))
        finally:
            with app.app_context():
                db = get_db()
                for table in ('item_tag', 'item_version', 'share', 'item', 'api_key', 'ideaflow_identity', 'user'):
                    db.execute('DELETE FROM ' + table)
                db.commit()


if __name__ == '__main__':
    unittest.main()
