import os
import tempfile
import time
import unittest
from unittest.mock import patch

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
        return redirect(
            'https://id.ideaflow.app/api/auth/oauth2/authorize'
            f'?state=test-state&redirect_uri={redirect_uri}'
        )

    def authorize_access_token(self):
        return {'access_token': 'fake', 'userinfo': self.userinfo}


class IdeaflowOidcTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = self.app.test_client()
        with self.app.app_context():
            db = get_db()
            db.execute('DELETE FROM external_identity')
            db.execute('DELETE FROM api_key')
            db.execute('DELETE FROM user')
            db.commit()

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
        for unsafe in ('https://evil.example.test', '//evil.example.test', '/\\\\evil.example.test', 'relative'):
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

        client.server_metadata.clear()
        client.server_metadata.update({
            '_loaded_at': time.time(),
            'issuer': issuer,
            'jwks': {'keys': [public_jwk]},
            'id_token_signing_alg_values_supported': ['EdDSA'],
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


if __name__ == '__main__':
    unittest.main()
