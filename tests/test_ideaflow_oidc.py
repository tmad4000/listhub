import os
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import secrets
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import bcrypt
from flask import session
from requests.exceptions import HTTPError, Timeout

_tmp = tempfile.TemporaryDirectory(prefix='listhub-oidc-test-')
os.environ['LISTHUB_DB'] = os.path.join(_tmp.name, 'listhub.db')
os.environ['LISTHUB_REPO_ROOT'] = os.path.join(_tmp.name, 'repos')
os.environ['LISTHUB_SECRET'] = 'test-session-secret'
os.environ['IDEAFLOW_OIDC_ENABLED'] = 'true'
os.environ['IDEAFLOW_OIDC_CLIENT_ID'] = 'test-client-id'
os.environ['IDEAFLOW_OIDC_CLIENT_SECRET'] = 'test-client-secret'
os.environ['LISTHUB_PUBLIC_URL'] = 'https://listhub.globalbr.ai'

from authlib.jose import JsonWebKey, jwt as jose_jwt
from authlib.jose.errors import JoseError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import auth
from app import create_app
from db import get_db


class FakeIdeaflowClient:
    def __init__(self, userinfo):
        self.userinfo = userinfo
        self.redirect_uri = None

    def authorize_redirect(self, redirect_uri):
        from flask import redirect
        self.redirect_uri = redirect_uri
        session['_state_ideaflow_test-state'] = {'data': {}, 'exp': time.time() + 3600}
        return redirect(
            'https://id.ideaflow.app/api/auth/oauth2/authorize'
            f'?state=test-state&redirect_uri={redirect_uri}'
        )

    def authorize_access_token(self, **kwargs):
        return {'access_token': 'fake', 'userinfo': self.userinfo}


class IdeaflowOidcTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = self.app.test_client()
        auth.oauth.ideaflow.server_metadata.clear()
        auth.oauth.ideaflow.server_metadata.update(self._provider_metadata())
        with self.app.app_context():
            db = get_db()
            db.execute('DELETE FROM external_identity')
            db.execute('DELETE FROM api_key')
            db.execute('DELETE FROM item')
            db.execute('DELETE FROM user')
            db.commit()

    def _provider_metadata(self):
        return {
            '_loaded_at': time.time(),
            'issuer': self.app.config['IDEAFLOW_OIDC_ISSUER'],
            'authorization_endpoint': 'https://id.ideaflow.app/api/auth/oauth2/authorize',
            'token_endpoint': 'https://id.ideaflow.app/api/auth/oauth2/token',
            'jwks_uri': 'https://id.ideaflow.app/api/auth/jwks',
            'id_token_signing_alg_values_supported': ['EdDSA'],
        }

    def _start_real(self, browser, path='/auth/ideaflow', **kwargs):
        response = browser.get(path, **kwargs)
        self.assertEqual(response.status_code, 302)
        state = parse_qs(urlparse(response.headers['Location']).query)['state'][0]
        with browser.session_transaction() as sess:
            data = sess[auth._IDEAFLOW_STATE_PREFIX + state]['data']
        return response, state, data

    def _create_user(self, user_id, username, email=None):
        with self.app.app_context():
            db = get_db()
            db.execute(
                'INSERT INTO user (id, username, display_name, email, password_hash) '
                'VALUES (?, ?, ?, ?, ?)',
                (user_id, username, username, email, '!test'),
            )
            db.commit()

    def _session_login(self, client, user_id):
        with client.session_transaction() as sess:
            sess['_user_id'] = user_id
            sess['_fresh'] = True

    def _claims(self, **overrides):
        claims = {
            'iss': self.app.config['IDEAFLOW_OIDC_ISSUER'],
            'sub': 'subject-1',
            'email': 'person@example.test',
            'email_verified': True,
            'name': 'Test Person',
        }
        claims.update(overrides)
        return claims

    def _complete(self, client, claims, path='/auth/ideaflow'):
        fake = FakeIdeaflowClient(claims)
        with patch('auth._ideaflow_client', return_value=fake):
            started = client.get(path, follow_redirects=False)
            self.assertEqual(started.status_code, 302)
            return client.get(
                '/auth/ideaflow/callback?state=test-state&code=fake',
                follow_redirects=False,
            )

    def test_kill_flag_preserves_legacy_login_and_hides_routes(self):
        self.app.config['IDEAFLOW_OIDC_ENABLED'] = False
        response = self.client.get('/login', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/noos/login', response.headers['Location'])
        self.assertEqual(self.client.get('/auth/ideaflow').status_code, 404)
        self.assertEqual(self.client.get('/auth/ideaflow/link').status_code, 404)

    def test_new_subject_creates_local_user_and_exact_identity(self):
        response = self._complete(self.client, self._claims())
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            db = get_db()
            identity = db.execute('SELECT * FROM external_identity').fetchone()
            user = db.execute('SELECT * FROM user WHERE id = ?', (identity['user_id'],)).fetchone()
            self.assertEqual(identity['issuer'], self.app.config['IDEAFLOW_OIDC_ISSUER'])
            self.assertEqual(identity['subject'], 'subject-1')
            self.assertEqual(user['email'], 'person@example.test')

        # The same immutable subject resolves to the same local user.
        before = identity['user_id']
        second = self.app.test_client()
        self._complete(second, self._claims(email='changed@example.test'))
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute('SELECT COUNT(*) FROM user').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT user_id FROM external_identity').fetchone()[0], before)

    def test_login_ui_and_callback_use_canonical_origin(self):
        page = self.client.get('/login').get_data(as_text=True)
        self.assertIn('Continue with Ideaflow', page)
        self.assertIn('Continue with Noos', page)
        fake = FakeIdeaflowClient(self._claims())
        with patch('auth._ideaflow_client', return_value=fake):
            self.client.get('/auth/ideaflow', headers={'Host': 'attacker.example.test'})
        self.assertEqual(
            fake.redirect_uri,
            'https://listhub.globalbr.ai/auth/ideaflow/callback',
        )

    def test_next_redirect_is_single_root_relative_and_rejects_backslashes(self):
        fake = FakeIdeaflowClient(self._claims(sub='safe-next'))
        for unsafe in ('https://evil.example.test', '//evil.example.test', '/\\\\evil.example.test', 'relative', '/' + 'x' * 513):
            browser = self.app.test_client()
            with patch('auth._ideaflow_client', return_value=fake):
                browser.get('/auth/ideaflow', query_string={'next': unsafe})
                response = browser.get(
                    '/auth/ideaflow/callback?state=test-state&code=fake',
                    follow_redirects=False,
                )
            self.assertEqual(response.headers['Location'], '/dash')

        browser = self.app.test_client()
        with patch('auth._ideaflow_client', return_value=FakeIdeaflowClient(self._claims(sub='safe-next'))):
            browser.get('/auth/ideaflow', query_string={'next': '/dash/settings'})
            response = browser.get(
                '/auth/ideaflow/callback?state=test-state&code=fake',
                follow_redirects=False,
            )
        self.assertEqual(response.headers['Location'], '/dash/settings')

    def test_matching_email_never_auto_links(self):
        self._create_user('existing', 'existing', 'person@example.test')
        response = self._complete(self.client, self._claims())
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute('SELECT COUNT(*) FROM external_identity').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM user').fetchone()[0], 1)

    def test_unverified_or_string_verified_email_is_not_copied_to_user(self):
        response = self._complete(
            self.client,
            self._claims(sub='string-claim', email_verified='true'),
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            db = get_db()
            row = db.execute('SELECT email FROM user').fetchone()
            identity = db.execute('SELECT email FROM external_identity').fetchone()
            self.assertIsNone(row['email'])
            self.assertEqual(identity['email'], 'person@example.test')

    def test_explicit_link_requires_same_signed_in_account(self):
        self._create_user('user-a', 'usera', 'a@example.test')
        self._create_user('user-b', 'userb', 'b@example.test')
        self._session_login(self.client, 'user-a')
        self._complete(self.client, self._claims(sub='linked'), '/auth/ideaflow/link')
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute('SELECT user_id FROM external_identity').fetchone()[0], 'user-a')

        switched = self.app.test_client()
        self._session_login(switched, 'user-a')
        fake = FakeIdeaflowClient(self._claims(sub='must-not-link'))
        with patch('auth._ideaflow_client', return_value=fake):
            switched.get('/auth/ideaflow/link')
            self._session_login(switched, 'user-b')
            switched.get('/auth/ideaflow/callback?state=test-state&code=fake')
        with self.app.app_context():
            db = get_db()
            self.assertIsNone(
                db.execute("SELECT 1 FROM external_identity WHERE subject = 'must-not-link'").fetchone()
            )

    def test_link_conflicts_fail_closed(self):
        self._create_user('user-a', 'usera')
        self._create_user('user-b', 'userb')
        self._session_login(self.client, 'user-a')
        self._complete(self.client, self._claims(sub='subject-a'), '/auth/ideaflow/link')

        # The same provider identity cannot move to another local account.
        other = self.app.test_client()
        self._session_login(other, 'user-b')
        self._complete(other, self._claims(sub='subject-a'), '/auth/ideaflow/link')
        # A local account cannot gain a second identity from the same issuer.
        self._complete(self.client, self._claims(sub='subject-b'), '/auth/ideaflow/link')
        with self.app.app_context():
            rows = get_db().execute(
                'SELECT user_id, subject FROM external_identity ORDER BY user_id'
            ).fetchall()
            self.assertEqual([(row['user_id'], row['subject']) for row in rows], [('user-a', 'subject-a')])

    def test_logout_and_same_account_login_invalidates_pending_links(self):
        self._create_user('user-a', 'usera')
        with self.app.app_context():
            db = get_db()
            db.execute('UPDATE user SET password_hash = ? WHERE id = ?', (
                bcrypt.hashpw(b'long-enough-password', bcrypt.gensalt()).decode(), 'user-a',
            ))
            db.commit()
        self._session_login(self.client, 'user-a')
        _, state, _ = self._start_real(self.client, '/auth/ideaflow/link')
        self.client.get('/logout')
        with self.client.session_transaction() as sess:
            self.assertNotIn(auth._IDEAFLOW_CONTEXTS_KEY, sess)
            self.assertNotIn(auth._IDEAFLOW_SESSION_KEY, sess)
            self.assertNotIn(auth._IDEAFLOW_STATE_PREFIX + state, sess)
        self.client.post('/login/local', data={
            'username': 'usera', 'password': 'long-enough-password',
        })
        with self.client.session_transaction() as sess:
            self.assertEqual(sess['_user_id'], 'user-a')
        with patch.object(auth.oauth.ideaflow, 'authorize_access_token') as exchange:
            self.client.get('/auth/ideaflow/callback', query_string={'state': state, 'code': 'x'})
            exchange.assert_not_called()
        self._complete(self.client, self._claims(sub='new-link'), '/auth/ideaflow/link')
        with self.app.app_context():
            identities = get_db().execute('SELECT subject FROM external_identity').fetchall()
            self.assertEqual([row['subject'] for row in identities], ['new-link'])

    def test_link_rejects_changed_authentication_nonce(self):
        self._create_user('user-a', 'usera')
        self._session_login(self.client, 'user-a')
        fake = FakeIdeaflowClient(self._claims())
        with patch('auth._ideaflow_client', return_value=fake):
            self.client.get('/auth/ideaflow/link')
            with self.client.session_transaction() as sess:
                sess[auth._IDEAFLOW_SESSION_KEY] = 'another-authentication-session'
            self.client.get('/auth/ideaflow/callback?state=test-state&code=x')
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM external_identity').fetchone()[0], 0)

    def test_signing_in_again_invalidates_pending_links(self):
        self._create_user('user-a', 'usera')
        with self.app.app_context():
            db = get_db()
            db.execute('INSERT INTO external_identity (user_id, issuer, subject) VALUES (?, ?, ?)', (
                'user-a', self.app.config['IDEAFLOW_OIDC_ISSUER'], 'existing-subject',
            ))
            db.commit()
        self._session_login(self.client, 'user-a')
        _, state, _ = self._start_real(self.client, '/auth/ideaflow/link')
        self._complete(self.client, self._claims(sub='existing-subject'))
        with self.client.session_transaction() as sess:
            self.assertEqual(sess['_user_id'], 'user-a')
            self.assertNotIn(auth._IDEAFLOW_CONTEXTS_KEY, sess)
            self.assertNotIn(auth._IDEAFLOW_SESSION_KEY, sess)
            self.assertNotIn(auth._IDEAFLOW_STATE_PREFIX + state, sess)

    def test_pending_attempts_and_authlib_states_are_bounded_together(self):
        self._create_user('user-a', 'usera')
        self._session_login(self.client, 'user-a')
        states = []
        now = time.time()
        with self.client.session_transaction() as sess:
            sess['oauth_state'] = 'legacy-noos-state'
            sess[auth._IDEAFLOW_CONTEXTS_KEY] = {'old': {'mode': 'signin'}}
            sess[auth._IDEAFLOW_STATE_PREFIX + 'old'] = {'exp': now + 3600, 'data': {}}
            sess[auth._IDEAFLOW_STATE_PREFIX + 'orphan'] = {'exp': now + 3600, 'data': {}}
        for index in range(12):
            response, state, _ = self._start_real(
                self.client, '/auth/ideaflow/link' if index % 2 else '/auth/ideaflow',
                query_string={'next': '/' + secrets.token_urlsafe(380)},
            )
            states.append(state)
            self.assertLess(len(response.headers['Set-Cookie']), 4093)
            with self.client.session_transaction() as sess:
                pending = sess[auth._IDEAFLOW_CONTEXTS_KEY]
                self.assertEqual(set(pending), set(states[-auth._IDEAFLOW_MAX_CONTEXTS:]))
                self.assertEqual(
                    {key for key in sess if key.startswith(auth._IDEAFLOW_STATE_PREFIX)},
                    {auth._IDEAFLOW_STATE_PREFIX + state for state in pending},
                )
                for state, context in pending.items():
                    self.assertEqual(sess[auth._IDEAFLOW_STATE_PREFIX + state]['exp'], context['expires_at'])
                self.assertEqual(sess['oauth_state'], 'legacy-noos-state')
                self.assertEqual(sess['_user_id'], 'user-a')
        with patch.object(auth.oauth.ideaflow, 'authorize_access_token') as exchange:
            self.client.get('/auth/ideaflow/callback', query_string={'state': states[0], 'code': 'x'})
            exchange.assert_not_called()
        self.client.get('/auth/ideaflow/callback', query_string={'state': states[-1], 'error': 'access_denied'})
        with self.client.session_transaction() as sess:
            self.assertNotIn(states[-1], sess[auth._IDEAFLOW_CONTEXTS_KEY])
            self.assertNotIn(auth._IDEAFLOW_STATE_PREFIX + states[-1], sess)
            self.assertIn(states[-2], sess[auth._IDEAFLOW_CONTEXTS_KEY])

    def test_expired_attempts_are_rejected_and_removed(self):
        _, state, _ = self._start_real(self.client)
        with self.client.session_transaction() as sess:
            expires_at = sess[auth._IDEAFLOW_CONTEXTS_KEY][state]['expires_at']
        with patch('auth.time.time', return_value=expires_at + 1), patch.object(
            auth.oauth.ideaflow, 'authorize_access_token',
        ) as exchange:
            self.client.get('/auth/ideaflow/callback', query_string={'state': state, 'code': 'x'})
            exchange.assert_not_called()
        with self.client.session_transaction() as sess:
            self.assertNotIn(auth._IDEAFLOW_CONTEXTS_KEY, sess)
            self.assertNotIn(auth._IDEAFLOW_STATE_PREFIX + state, sess)

    def test_discovery_failures_are_bounded_and_handled_for_both_start_routes(self):
        self._create_user('user-a', 'usera')
        self._session_login(self.client, 'user-a')
        for path, target in (('/auth/ideaflow', '/login'), ('/auth/ideaflow/link', '/dash/settings')):
            for error in (Timeout(), HTTPError(), ValueError('Invalid discovery document')):
                with self.subTest(path=path, error=type(error)):
                    auth.oauth.ideaflow.server_metadata.clear()
                    with patch('requests.sessions.Session.request', side_effect=error) as provider:
                        response = self.client.get(path)
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.headers['Location'], target)
                    self.assertEqual(provider.call_args.kwargs['timeout'], 5)
                    with self.client.session_transaction() as sess:
                        self.assertNotIn(auth._IDEAFLOW_CONTEXTS_KEY, sess)
                        self.assertFalse(any(key.startswith(auth._IDEAFLOW_STATE_PREFIX) for key in sess))
                        self.assertIn('temporarily unavailable', sess['_flashes'][-1][1])

    def test_token_and_jwks_requests_have_timeouts(self):
        client = auth.oauth.ideaflow
        for operation in (
            lambda: client.fetch_access_token(code='x', redirect_uri='https://listhub.globalbr.ai/auth/ideaflow/callback'),
            lambda: client.fetch_jwk_set(force=True),
        ):
            with patch('requests.sessions.Session.request', side_effect=Timeout()) as provider:
                with self.assertRaises(Timeout):
                    operation()
            self.assertEqual(provider.call_args.kwargs['timeout'], 5)

    def test_callback_timeout_consumes_attempt(self):
        _, state, _ = self._start_real(self.client)
        with patch('requests.sessions.Session.request', side_effect=Timeout()) as provider:
            response = self.client.get('/auth/ideaflow/callback', query_string={'state': state, 'code': 'x'})
        self.assertEqual(provider.call_args.kwargs['timeout'], 5)
        self.assertEqual(response.headers['Location'], '/login')
        with self.client.session_transaction() as sess:
            self.assertNotIn(auth._IDEAFLOW_CONTEXTS_KEY, sess)
            self.assertNotIn(auth._IDEAFLOW_STATE_PREFIX + state, sess)

    def test_callback_requires_known_state_and_exact_issuer(self):
        fake = FakeIdeaflowClient(self._claims())
        with patch('auth._ideaflow_client', return_value=fake):
            self.client.get('/auth/ideaflow/callback?state=unknown&code=fake')
        bad = self.app.test_client()
        self._complete(bad, self._claims(iss='https://evil.example.test'))
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT COUNT(*) FROM external_identity').fetchone()[0], 0)

    def test_programmatic_registration_remains_available(self):
        response = self.client.post(
            '/api/v1/auth/register',
            json={'username': 'agentuser', 'password': 'long-enough-password'},
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.get_json()['key'].startswith('mem_'))

    def test_existing_account_journey_with_signed_provider_and_evidence(self):
        """Exercise the browser routes, real token exchange and legacy access.

        Only the provider HTTP transport is replaced; Authlib still sends Basic
        authentication/PKCE and verifies the Ed25519 ID token and nonce.
        Optional evidence contains synthetic account data and rendered pages.
        """
        from requests import Response
        from db import init_db

        self.app.config['WTF_CSRF_ENABLED'] = True
        password = 'journey-test-password'
        raw_key = 'mem_journey-test-key'
        self._create_user('stable-user-id', 'journey', 'journey@example.test')
        with self.app.app_context():
            db = get_db()
            db.execute('UPDATE user SET password_hash = ?, noos_id = ? WHERE id = ?', (
                bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
                'existing-noos-id', 'stable-user-id',
            ))
            db.execute('INSERT INTO api_key (id, user_id, key_hash, name) VALUES (?, ?, ?, ?)', (
                'existing-key', 'stable-user-id', auth.hash_api_key(raw_key), 'Existing agent key',
            ))
            db.execute('INSERT INTO item (id, owner_id, slug, title, content) VALUES (?, ?, ?, ?, ?)', (
                'existing-note', 'stable-user-id', 'kept-note', 'My existing private note', 'Keep my content',
            ))
            db.commit()
            before = {table: [dict(row) for row in db.execute(f'SELECT * FROM {table}')]
                      for table in ('user', 'api_key', 'item')}
            # Upgrade a pre-OIDC schema, then rerun the migration for idempotency.
            db.execute('DROP TABLE external_identity')
            db.commit()
            init_db()
            init_db()

        pages = {}
        pages['login'] = self.client.get('/login').get_data(as_text=True)
        pages['register'] = self.client.get('/register').get_data(as_text=True)

        def local_login(browser):
            form = browser.get('/login/local').get_data(as_text=True)
            csrf = re.search(r'name="csrf_token" value="([^"]+)"', form).group(1)
            response = browser.post('/login/local', data={
                'username': 'journey', 'password': password, 'csrf_token': csrf,
            })
            self.assertEqual(response.status_code, 302)
            with browser.session_transaction() as sess:
                self.assertEqual(sess['_user_id'], 'stable-user-id')

        local_login(self.client)
        preserved_session = self.app.test_client()
        local_login(preserved_session)
        pages['settings-before-link'] = self.client.get('/dash/settings').get_data(as_text=True)
        self.assertIn('Link Ideaflow', pages['settings-before-link'])

        private = Ed25519PrivateKey.generate()
        pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption())
        key = JsonWebKey.import_key(pem, {'kty': 'OKP', 'crv': 'Ed25519', 'kid': 'journey'})
        metadata = self._provider_metadata()
        requests_seen = []
        consent = {}
        subject = 'journey-subject'

        def provider_send(prepared, **kwargs):
            nonlocal consent
            requests_seen.append({'method': prepared.method, 'url': prepared.url})
            self.assertEqual(kwargs['timeout'], 5)
            if prepared.url == self.app.config['IDEAFLOW_OIDC_DISCOVERY_URL']:
                payload = metadata
            elif prepared.url == metadata['jwks_uri']:
                payload = {'keys': [key.as_dict(is_private=False)]}
            elif prepared.url == metadata['token_endpoint']:
                expected = base64.b64encode(b'test-client-id:test-client-secret').decode()
                self.assertEqual(prepared.headers['Authorization'], 'Basic ' + expected)
                body = parse_qs(prepared.body)
                self.assertNotIn('client_secret', body)
                self.assertEqual(body['redirect_uri'], ['https://listhub.globalbr.ai/auth/ideaflow/callback'])
                self.assertEqual(body['code'], ['local-test-code'])
                challenge = base64.urlsafe_b64encode(
                    hashlib.sha256(body['code_verifier'][0].encode()).digest()
                ).rstrip(b'=').decode()
                self.assertEqual(challenge, consent['code_challenge'][0])
                claims = self._claims(sub=subject, email='journey@example.test', name='journey',
                                      aud='test-client-id', iat=int(time.time()), exp=int(time.time()) + 300,
                                      nonce=consent['nonce'][0])
                payload = {'access_token': 'local-test-access-token', 'token_type': 'Bearer',
                           'id_token': jose_jwt.encode({'alg': 'EdDSA', 'kid': 'journey'}, claims, key).decode()}
            else:
                self.fail('Unexpected provider request: ' + prepared.url)
            response = Response()
            response.status_code = 200
            response._content = json.dumps(payload).encode()
            response.headers['Content-Type'] = 'application/json'
            return response

        def oidc(browser, path):
            nonlocal consent
            started = browser.get(path)
            self.assertEqual(started.status_code, 302)
            location = urlparse(started.headers['Location'])
            self.assertEqual(location.netloc, 'id.ideaflow.app')
            consent = parse_qs(location.query)
            self.assertEqual(consent['code_challenge_method'], ['S256'])
            self.assertEqual(consent['redirect_uri'], ['https://listhub.globalbr.ai/auth/ideaflow/callback'])
            return browser.get('/auth/ideaflow/callback', query_string={
                'state': consent['state'][0], 'code': 'local-test-code',
            }, follow_redirects=True)

        auth.oauth.ideaflow.server_metadata.clear()
        with patch('requests.sessions.Session.send', side_effect=provider_send):
            # Same email/name must fail closed before an explicit settings link.
            unlinked = self.app.test_client()
            pages['email-collision'] = oidc(unlinked, '/auth/ideaflow').get_data(as_text=True)
            self.assertIn('then link Ideaflow from Settings', pages['email-collision'])
            with unlinked.session_transaction() as sess:
                self.assertNotIn('_user_id', sess)
            linked = oidc(self.client, '/auth/ideaflow/link')
            self.assertEqual(linked.status_code, 200)
            pages['settings-linked'] = linked.get_data(as_text=True)
            self.assertIn('Ideaflow is linked as journey@example.test', pages['settings-linked'])
            self.client.get('/logout')
            signed_in = oidc(self.client, '/auth/ideaflow')
            self.assertEqual(signed_in.status_code, 200)
            pages['dashboard-after-oidc'] = signed_in.get_data(as_text=True)
            self.assertIn('My existing private note', pages['dashboard-after-oidc'])

        api_client = self.app.test_client()
        note = api_client.get('/api/v1/items/existing-note', headers={'Authorization': 'Bearer ' + raw_key})
        self.assertEqual(note.status_code, 200)
        self.assertEqual(note.json['content'], 'Keep my content')
        self.assertEqual(preserved_session.get('/dash/settings').status_code, 200)
        local_login(self.app.test_client())
        git_evidence = []
        for credential in (password, raw_key):
            basic = base64.b64encode(('journey:' + credential).encode()).decode()
            response = api_client.get('/git/journey.git/info/refs?service=git-upload-pack',
                                      headers={'Authorization': 'Basic ' + basic})
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'# service=git-upload-pack', response.data)
            git_evidence.append({'auth': 'password' if credential == password else 'existing API key',
                                 'status': response.status_code, 'content_type': response.content_type,
                                 'service': '# service=git-upload-pack'})

        noos_browser = self.app.test_client()
        started = noos_browser.get('/auth/noos/login')
        noos_state = parse_qs(urlparse(started.headers['Location']).query)['state'][0]
        noos_body = json.dumps({'user': {'id': 'existing-noos-id', 'email': 'journey@example.test'}}).encode()
        with patch('auth.urllib.request.urlopen', return_value=io.BytesIO(noos_body)):
            self.assertEqual(noos_browser.get('/auth/noos/callback', query_string={
                'code': 'noos-test-code', 'state': noos_state,
            }).status_code, 302)
        with noos_browser.session_transaction() as sess:
            self.assertEqual(sess['_user_id'], 'stable-user-id')

        with self.app.app_context():
            db = get_db()
            after = {table: [dict(row) for row in db.execute(f'SELECT * FROM {table}')]
                     for table in ('user', 'api_key', 'item')}
            self.assertEqual(before, after)
            identity = dict(db.execute('SELECT user_id, issuer, subject, email FROM external_identity').fetchone())
        self.assertEqual(identity['user_id'], 'stable-user-id')
        self.app.config['IDEAFLOW_OIDC_ENABLED'] = False
        self.assertEqual(self.client.get('/auth/ideaflow').status_code, 404)
        self.assertEqual(self.client.get('/dash').status_code, 200)
        self.assertNotIn('Connected identity', self.client.get('/dash/settings').get_data(as_text=True))

        evidence = os.environ.get('LISTHUB_TEST_EVIDENCE')
        if evidence:
            destination = Path(evidence)
            destination.mkdir(parents=True, exist_ok=True)
            root = Path(__file__).resolve().parents[1]
            for name, html in pages.items():
                # Embed the actual styles so evidence remains viewable offline.
                html = re.sub(r'<link rel="stylesheet" href="/static/([^"?]+)[^"]*">',
                              lambda match: '<style>' + (root / 'static' / match[1]).read_text() + '</style>', html)
                (destination / (name + '.html')).write_text(html)
            (destination / 'account-journey.json').write_text(json.dumps({
                'provider': 'Local HTTP stand-in; real Authlib Basic/S256 exchange and Ed25519 verification',
                'requests': requests_seen, 'persisted_identity': identity,
                'unchanged_legacy_tables': list(before), 'existing_api_note_response': note.json,
                'git_discovery': git_evidence, 'noos_callback_user_id': 'stable-user-id',
                'preserved_session_after_kill_flag': '/dash returned HTTP 200',
            }, indent=2))

    def test_real_ed25519_verification_and_basic_s256_client(self):
        client = auth.oauth.ideaflow
        self.assertEqual(client.client_kwargs['token_endpoint_auth_method'], 'client_secret_basic')
        self.assertEqual(client.client_kwargs['code_challenge_method'], 'S256')

        oauth_session = client._get_oauth_client()
        client_auth = oauth_session.client_auth(oauth_session.token_endpoint_auth_method)
        _uri, headers, body = client_auth.prepare(
            'POST',
            'https://id.ideaflow.app/api/auth/oauth2/token',
            {},
            'grant_type=authorization_code&code=test',
        )
        self.assertTrue(headers['Authorization'].startswith('Basic '))
        self.assertNotIn('client_secret', body)

        def key(kid):
            private = Ed25519PrivateKey.generate()
            pem = private.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            return JsonWebKey.import_key(pem, {'kty': 'OKP', 'crv': 'Ed25519', 'kid': kid})

        kid = 'listhub-test-key'
        signing_key = key(kid)
        public_jwk = JsonWebKey.import_key(signing_key.as_dict(is_private=False)).as_dict()
        issuer = self.app.config['IDEAFLOW_OIDC_ISSUER']
        nonce = 'test-nonce'

        def sign(overrides=None, signing=signing_key):
            now = int(time.time())
            claims = {
                'iss': issuer,
                'sub': 'crypto-subject',
                'aud': 'test-client-id',
                'iat': now,
                'exp': now + 300,
                'nonce': nonce,
                'email_verified': True,
            }
            claims.update(overrides or {})
            return jose_jwt.encode({'alg': 'EdDSA', 'kid': kid}, claims, signing).decode()

        client.server_metadata.update({
            'jwks': {'keys': [public_jwk]},
        })
        parsed = client.parse_id_token({'access_token': 'x', 'id_token': sign()}, nonce=nonce)
        self.assertEqual(parsed['sub'], 'crypto-subject')
        for token in (
            sign(signing=key(kid)),
            sign({'iss': 'https://evil.example.test'}),
            sign({'aud': 'different-client'}),
        ):
            with self.assertRaises(JoseError):
                client.parse_id_token({'access_token': 'x', 'id_token': token}, nonce=nonce)

        for overrides, accepted in (
            ({}, True),
            ({'aud': ['another-client', 'test-client-id'], 'azp': 'test-client-id'}, True),
            ({'aud': 'different-client', 'azp': 'test-client-id'}, False),
            ({'aud': ['different-client', 'another-client'], 'azp': 'test-client-id'}, False),
            ({'aud': None, 'azp': 'test-client-id'}, False),
            ({'iss': 'https://evil.example.test'}, False),
        ):
            with self.subTest(overrides=overrides):
                browser = self.app.test_client()
                _, state, state_data = self._start_real(browser)
                nonce = state_data['nonce']
                token = {'access_token': 'x', 'id_token': sign(overrides)}
                with patch.object(client, 'fetch_access_token', return_value=token):
                    response = browser.get('/auth/ideaflow/callback', query_string={'state': state, 'code': 'x'})
                self.assertEqual(response.headers['Location'], '/dash' if accepted else '/login')
                with browser.session_transaction() as sess:
                    self.assertEqual('_user_id' in sess, accepted)


if __name__ == '__main__':
    unittest.main()
