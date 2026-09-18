import json
import os
import re
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

import bcrypt
from flask import session
from flask.wrappers import Response

_tmp = tempfile.TemporaryDirectory(prefix='listhub-login-hint-test-')
os.environ.setdefault('LISTHUB_DB', os.path.join(_tmp.name, 'listhub.db'))
os.environ.setdefault('LISTHUB_REPO_ROOT', os.path.join(_tmp.name, 'repos'))
os.environ.setdefault('LISTHUB_SECRET', 'test-session-secret')
os.environ.setdefault('IDEAFLOW_OIDC_ENABLED', 'true')
os.environ.setdefault('IDEAFLOW_OIDC_CLIENT_ID', 'test-client-id')
os.environ.setdefault('IDEAFLOW_OIDC_CLIENT_SECRET', 'test-client-secret')
os.environ.setdefault('LISTHUB_PUBLIC_URL', 'https://listhub.globalbr.ai')

import auth
from app import create_app
from db import get_db

COOKIE = auth._LOGIN_HINT_COOKIE


class FakeIdeaflowClient:
    def __init__(self, userinfo=None, fail=False):
        self.userinfo = userinfo
        self.fail = fail

    def authorize_redirect(self, redirect_uri):
        from flask import redirect
        session['_state_ideaflow_test-state'] = {'data': {}, 'exp': time.time() + 3600}
        return redirect('https://id.ideaflow.app/api/auth/oauth2/authorize?state=test-state')

    def authorize_access_token(self, **kwargs):
        if self.fail:
            raise RuntimeError('cancelled')
        return {'access_token': 'fake', 'userinfo': self.userinfo}


def _hint_cookies(response):
    return [h for h in response.headers.getlist('Set-Cookie') if h.startswith(COOKIE + '=')]


def _link_text(html, label):
    """Return the text of the <a> element whose text starts with `label`."""
    for match in re.finditer(r'<a\b[^>]*>(.*?)</a>', html, re.S):
        text = ' '.join(re.sub(r'<[^>]+>', '', match.group(1)).split())
        if text.startswith(label):
            return text
    raise AssertionError(f'no link starting with {label!r}')


class LoginHintTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = self.app.test_client()
        with self.app.app_context():
            db = get_db()
            db.execute('DELETE FROM external_identity')
            db.execute('DELETE FROM api_key')
            db.execute('DELETE FROM item')
            db.execute('DELETE FROM user')
            pw = bcrypt.hashpw(b'correct-horse', bcrypt.gensalt()).decode()
            db.execute(
                'INSERT INTO user (id, username, display_name, password_hash) VALUES (?, ?, ?, ?)',
                ('u1', 'alice', 'Alice', pw),
            )
            db.commit()

    def _password_login(self, password='correct-horse', client=None):
        return (client or self.client).post(
            '/login/local', data={'username': 'alice', 'password': password})

    def _noos_callback(self, noos_user=None, error=None):
        with self.client.session_transaction() as sess:
            sess['oauth_state'] = 's1'
        if error:
            return self.client.get(f'/auth/noos/callback?error={error}')
        body = MagicMock()
        body.__enter__.return_value.read.return_value = json.dumps(
            {'user': noos_user or {'id': 'noos-1', 'email': 'n@example.test', 'name': 'N'}}
        ).encode()
        with patch('auth.urllib.request.urlopen', return_value=body):
            return self.client.get('/auth/noos/callback?state=s1&code=c1')

    def _ideaflow_callback(self, client=None, **kwargs):
        client = client or self.client
        fake = FakeIdeaflowClient(**kwargs)
        with patch('auth._ideaflow_client', return_value=fake):
            client.get('/auth/ideaflow')
            return client.get('/auth/ideaflow/callback?state=test-state&code=fake')

    def _cookie(self, client=None):
        cookie = (client or self.client).get_cookie(COOKIE)
        return cookie.value if cookie else None

    # (a) success records the method, from server-side evidence
    def test_password_login_records_password(self):
        response = self._password_login()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._cookie(), 'password')
        header = _hint_cookies(response)[0]
        self.assertIn('HttpOnly', header)
        self.assertIn('SameSite=Lax', header)

    def test_noos_callback_records_noos(self):
        response = self._noos_callback()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._cookie(), 'noos')

    def test_ideaflow_callback_records_ideaflow_for_new_and_linked_users(self):
        claims = {
            'iss': self.app.config['IDEAFLOW_OIDC_ISSUER'], 'sub': 'sub-1',
            'email': 'new@example.test', 'email_verified': True, 'name': 'New',
        }
        self._ideaflow_callback(userinfo=claims)  # creates the user
        self.assertEqual(self._cookie(), 'ideaflow')
        other = self.app.test_client()
        self._ideaflow_callback(client=other, userinfo=claims)  # existing identity
        self.assertEqual(self._cookie(other), 'ideaflow')

    def test_success_overwrites_previous_method(self):
        self._noos_callback()
        self.assertEqual(self._cookie(), 'noos')
        self.client.get('/logout')
        self._password_login()
        self.assertEqual(self._cookie(), 'password')

    def test_stored_value_contains_only_method_id(self):
        self._password_login()
        self.assertEqual(self._cookie(), 'password')
        self.assertNotIn('alice', ''.join(_hint_cookies(self._password_login())))

    # (b) failed or cancelled attempts do not overwrite or clear the hint
    def test_failed_password_login_keeps_existing_hint(self):
        self._noos_callback()
        self.client.get('/logout')
        response = self._password_login(password='wrong')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_hint_cookies(response), [])
        self.assertEqual(self._cookie(), 'noos')

    def test_failed_password_login_sets_no_hint_on_fresh_browser(self):
        response = self._password_login(password='wrong')
        self.assertEqual(_hint_cookies(response), [])
        self.assertIsNone(self._cookie())

    def test_cancelled_or_failed_external_logins_keep_existing_hint(self):
        self._password_login()
        self.client.get('/logout')
        response = self._ideaflow_callback(fail=True)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(_hint_cookies(response), [])
        response = self._noos_callback(error='access_denied')
        self.assertEqual(_hint_cookies(response), [])
        with patch('auth.urllib.request.urlopen', side_effect=OSError('down')):
            with self.client.session_transaction() as sess:
                sess['oauth_state'] = 's2'
            response = self.client.get('/auth/noos/callback?state=s2&code=c')
        self.assertEqual(_hint_cookies(response), [])
        self.assertEqual(self._cookie(), 'password')

    def test_refused_ideaflow_signin_is_not_recorded(self):
        # Email collision with an existing account refuses sign-in.
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE user SET email = 'alice@example.test' WHERE id = 'u1'")
            db.commit()
        response = self._ideaflow_callback(userinfo={
            'iss': self.app.config['IDEAFLOW_OIDC_ISSUER'], 'sub': 'sub-x',
            'email': 'alice@example.test', 'email_verified': True,
        })
        self.assertEqual(_hint_cookies(response), [])
        self.assertIsNone(self._cookie())

    def test_starting_ideaflow_login_does_not_record_on_click(self):
        with patch('auth._ideaflow_client', return_value=FakeIdeaflowClient()):
            response = self.client.get('/auth/ideaflow')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(_hint_cookies(response), [])
        response = self.client.get('/auth/noos/login')
        self.assertEqual(_hint_cookies(response), [])
        self.assertIsNone(self._cookie())

    # (c) restoring an existing session is not a fresh login
    def test_session_restore_does_not_record(self):
        with self.client.session_transaction() as sess:
            sess['_user_id'] = 'u1'
            sess['_fresh'] = True
        for path in ('/dash', '/login', '/login/local'):
            response = self.client.get(path)
            self.assertEqual(_hint_cookies(response), [], path)
        self.assertIsNone(self._cookie())

    def test_ideaflow_link_from_settings_does_not_record(self):
        with self.client.session_transaction() as sess:
            sess['_user_id'] = 'u1'
            sess['_fresh'] = True
        claims = {'iss': self.app.config['IDEAFLOW_OIDC_ISSUER'], 'sub': 'sub-link'}
        with patch('auth._ideaflow_client', return_value=FakeIdeaflowClient(userinfo=claims)):
            self.client.get('/auth/ideaflow/link')
            response = self.client.get('/auth/ideaflow/callback?state=test-state&code=fake')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/settings'))
        self.assertEqual(_hint_cookies(response), [])
        with self.app.app_context():
            linked = get_db().execute('SELECT 1 FROM external_identity').fetchone()
        self.assertIsNotNone(linked)

    # (d) storage failure or unavailability never breaks login
    def test_login_works_when_cookies_are_unavailable(self):
        client = self.app.test_client(use_cookies=False)
        response = self._password_login(client=client)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/dash'))

    def test_login_works_when_setting_hint_raises(self):
        real_set_cookie = Response.set_cookie

        def flaky(self_, key, *args, **kwargs):
            if key == COOKIE:
                raise ValueError('boom')
            return real_set_cookie(self_, key, *args, **kwargs)

        with patch.object(Response, 'set_cookie', flaky):
            response = self._password_login()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/dash'))
        self.assertIsNone(self._cookie())

    # (e) stale or unknown stored values are ignored
    def test_unknown_and_disabled_values_are_ignored(self):
        for value in ('google', 'PASSWORD', 'noos ', '', 'x' * 500, '<b>x</b>'):
            self.client.set_cookie(COOKIE, value)
            html = self.client.get('/login').get_data(as_text=True)
            self.assertNotIn('Last used', html, repr(value))

    def test_method_disabled_now_is_ignored(self):
        # A stored method that is no longer offered must not be shown, and must
        # not be written either.
        from auth import _login_hint_context, enabled_login_methods
        self.app.config['IDEAFLOW_OIDC_ENABLED'] = False
        with self.app.test_request_context('/login/local'):
            self.assertNotIn('ideaflow', enabled_login_methods(self.app.config))
        self.client.set_cookie(COOKIE, 'ideaflow')
        with self.app.test_request_context('/login/local', headers={'Cookie': f'{COOKIE}=ideaflow'}):
            self.assertIsNone(_login_hint_context()['last_method'])
        # Noos switched off: a stored 'noos' is ignored on the choice screen.
        with patch('auth.NOOS_AUTH_URL', ''):
            with self.app.test_request_context('/login/local', headers={'Cookie': f'{COOKIE}=noos'}):
                self.assertNotIn('noos', enabled_login_methods(self.app.config))
                self.assertIsNone(_login_hint_context()['last_method'])

    def test_register_records_password(self):
        response = self.client.post('/register', data={
            'username': 'bobby', 'display_name': 'Bob', 'email': 'b@example.test',
            'password': 'longenough1'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._cookie(), 'password')

    def test_failed_register_does_not_record(self):
        self.client.set_cookie(COOKIE, 'noos')
        response = self.client.post('/register', data={
            'username': 'b', 'password': 'short'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_hint_cookies(response), [])
        self.assertEqual(self._cookie(), 'noos')

    # (f) marker renders next to the right method, only with 2+ methods
    def test_marker_renders_next_to_matching_method_only(self):
        for method, label in (
            ('ideaflow', 'Continue with Ideaflow'),
            ('noos', 'Continue with Noos'),
            ('password', 'Use a local password'),
        ):
            self.client.set_cookie(COOKIE, method)
            html = self.client.get('/login').get_data(as_text=True)
            self.assertEqual(html.count('Last used'), 1, method)
            self.assertTrue(_link_text(html, label).endswith('Last used'), method)
            for other in ('Continue with Ideaflow', 'Continue with Noos', 'Use a local password'):
                if other != label:
                    self.assertNotIn('Last used', _link_text(html, other))

    def test_no_marker_without_stored_method(self):
        html = self.client.get('/login').get_data(as_text=True)
        self.assertNotIn('Last used', html)

    def test_local_login_page_marks_password_and_noos(self):
        self.client.set_cookie(COOKIE, 'password')
        html = self.client.get('/login/local').get_data(as_text=True)
        self.assertRegex(html, r'<h1>Local Login\s*<span class="last-used">Last used</span>')
        self.client.set_cookie(COOKIE, 'noos')
        html = self.client.get('/login/local').get_data(as_text=True)
        self.assertEqual(html.count('Last used'), 1)
        self.assertIn('sign in with Noos</a> <span class="last-used">Last used</span>', html)

    def test_marker_hidden_when_fewer_than_two_methods_enabled(self):
        self.app.config['IDEAFLOW_OIDC_ENABLED'] = False
        with patch('auth.NOOS_AUTH_URL', ''):
            self.assertEqual(auth.enabled_login_methods(self.app.config), ['password'])
            self.client.set_cookie(COOKIE, 'password')
            html = self.client.get('/login/local').get_data(as_text=True)
        self.assertNotIn('Last used', html)

    def test_failed_local_login_rerender_still_shows_marker(self):
        self._password_login()
        self.client.get('/logout')
        html = self._password_login(password='wrong').get_data(as_text=True)
        self.assertIn('Invalid username or password.', html)
        self.assertEqual(html.count('Last used'), 1)


if __name__ == '__main__':
    unittest.main()
