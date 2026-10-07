import io
import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from types import SimpleNamespace
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

root = tempfile.TemporaryDirectory()
os.environ['LISTHUB_DB'] = root.name + '/test.db'
os.environ['LISTHUB_SECRET'] = 'test-secret-fixed'
os.environ['LISTHUB_REPO_ROOT'] = root.name + '/repos'
config_path = Path(root.name) / 'oidc.json'
config_path.write_text(json.dumps(dict(issuer='https://id.ideaflow.app/api/auth', client_id='test-client', client_secret='test-secret', redirect_uris=['https://listhub.globalbr.ai/auth/ideaflow/callback'])))
os.environ['LISTHUB_IDEAFLOW_CONFIG'] = str(config_path)
from app import app
from db import get_db
from ideaflow_auth import resolve_user, local_next, exchange, config

class SharedLoginTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = app.test_client()
        with app.app_context():
            db = get_db(); db.execute('DELETE FROM ideaflow_identity'); db.execute('DELETE FROM user'); db.commit()

    def test_silent_attempt_and_signout_choice(self):
        response = self.client.get('/login?next=/explore?foo=1')
        self.assertIn('prompt=none', response.location)
        self.assertIn('code_challenge_method=S256', response.location)
        response = self.client.get('/login?auto=off')
        self.assertIn(b'Sign in with Ideaflow', response.data)
        with self.client.session_transaction() as s: s['ideaflow_signed_out'] = True
        self.assertIn('prompt=select_account', self.client.get('/auth/ideaflow/login').location)

    def test_state_and_expiry_failure_never_exchanges(self):
        self.client.get('/login')
        with patch('ideaflow_auth.exchange') as exchange:
            self.client.get('/auth/ideaflow/callback?code=x&state=forged')
            exchange.assert_not_called()
        with self.client.session_transaction() as s:
            s['ideaflow_pending'] = dict(state='s', created=time.time()-301, silent=False)
        with patch('ideaflow_auth.exchange') as exchange:
            self.client.get('/auth/ideaflow/callback?code=x&state=s')
            exchange.assert_not_called()

    def test_identity_mapping_stable_and_email_match_cannot_merge(self):
        claims = dict(sub='subject', email='new@example.test', email_verified=True, name='New')
        with app.app_context(), patch('git_backend.init_user_repo'):
            user = resolve_user(claims)
            self.assertEqual(resolve_user(dict(claims, email='changed@example.test')).id, user.id)
            with self.assertRaises(ValueError): resolve_user(dict(claims, sub='other-subject'))
            self.assertEqual(get_db().execute('SELECT count(*) FROM user').fetchone()[0], 1)

    def test_unverified_email_cannot_create(self):
        with app.app_context(), self.assertRaises(ValueError):
            resolve_user(dict(sub='s', email='x@example.test', email_verified=False))

    def test_link_requires_local_account_and_is_exclusive(self):
        with app.app_context():
            db=get_db();db.execute("INSERT INTO user(id,username,email,password_hash) VALUES('legacy','legacy','old@test','!')");db.commit()
        with self.client.session_transaction() as s:
            s['_user_id']='legacy';s['_fresh']=True
        self.client.post('/auth/ideaflow/link')
        with self.client.session_transaction() as s: state=s['ideaflow_pending']['state']
        with patch('ideaflow_auth.exchange', return_value=dict(sub='selected', email_verified=True)):
            self.assertEqual(self.client.get('/auth/ideaflow/callback?code=c&state='+state).status_code,302)
        with app.app_context():
            self.assertEqual(get_db().execute('SELECT user_id FROM ideaflow_identity').fetchone()[0],'legacy')

    def create_account(self, user_id='legacy', email='old@test', noos_id=None):
        with app.app_context():
            db = get_db()
            db.execute('INSERT INTO user(id,username,email,password_hash,noos_id) VALUES(?,?,?,?,?)',
                       (user_id, user_id, email, '!', noos_id))
            db.commit()

    def authenticate(self, user_id='legacy'):
        with self.client.session_transaction() as session:
            session['_user_id'] = user_id
            session['_fresh'] = True

    def noos_callback(self, noos_id, email, link=False):
        self.client.post('/auth/noos/login') if link else self.client.get('/auth/noos/login')
        with self.client.session_transaction() as session:
            state = session['oauth_state']
        payload = io.BytesIO(json.dumps(dict(user=dict(id=noos_id, email=email, name='Noos'))).encode())
        with patch('auth.urllib.request.urlopen', return_value=payload):
            return self.client.get('/auth/noos/callback?code=c&state=' + state)

    def test_noos_email_match_requires_explicit_authenticated_link(self):
        self.create_account()
        for authenticated in (False, True):
            if authenticated:
                self.authenticate()
            self.noos_callback('new-noos', 'OLD@test')
            with app.app_context():
                row = get_db().execute('SELECT noos_id FROM user WHERE id=?', ('legacy',)).fetchone()
                self.assertIsNone(row['noos_id'])
            with self.client.session_transaction() as session:
                self.assertEqual(session.get('_user_id'), 'legacy' if authenticated else None)
        self.noos_callback('new-noos', 'old@test', link=True)
        with app.app_context():
            self.assertEqual(get_db().execute('SELECT noos_id FROM user WHERE id=?', ('legacy',)).fetchone()[0], 'new-noos')
        with self.client.session_transaction() as session:
            self.assertEqual(session['_user_id'], 'legacy')

    def test_noos_cannot_attach_to_oidc_account_on_email(self):
        with app.app_context(), patch('git_backend.init_user_repo'):
            user = resolve_user(dict(sub='oidc', email='new@test', email_verified=True))
        self.noos_callback('noos', 'new@test')
        with app.app_context():
            self.assertIsNone(get_db().execute('SELECT noos_id FROM user WHERE id=?', (user.id,)).fetchone()[0])
        with self.client.session_transaction() as session:
            self.assertNotIn('_user_id', session)

    def test_noos_mapped_login_and_new_account_still_work(self):
        self.create_account(noos_id='mapped')
        self.noos_callback('mapped', 'changed@test')
        with self.client.session_transaction() as session:
            self.assertEqual(session['_user_id'], 'legacy')
        self.client.get('/logout')
        with patch('git_backend.init_user_repo') as init_repo:
            self.noos_callback('new-noos', 'new@test')
            init_repo.assert_called_once_with('new')
        with app.app_context():
            self.assertEqual(get_db().execute('SELECT noos_id FROM user WHERE email=?', ('new@test',)).fetchone()[0], 'new-noos')

    def test_noos_link_cannot_steal_or_replace_mapping(self):
        self.create_account(noos_id='original')
        self.create_account('other', 'other@test', 'taken')
        self.authenticate()
        for identity in ('taken', 'unmapped'):
            self.noos_callback(identity, 'old@test', link=True)
            with app.app_context():
                self.assertEqual(get_db().execute('SELECT noos_id FROM user WHERE id=?', ('legacy',)).fetchone()[0], 'original')
            with self.client.session_transaction() as session:
                self.assertEqual(session['_user_id'], 'legacy')

    def test_noos_link_requires_same_authenticated_account(self):
        self.assertEqual(self.client.post('/auth/noos/login').location, '/login/local')
        self.create_account()
        self.create_account('other', 'other@test')
        self.authenticate()
        self.client.post('/auth/noos/login')
        with self.client.session_transaction() as session:
            state = session['oauth_state']
        self.authenticate('other')
        payload = io.BytesIO(json.dumps(dict(user=dict(id='noos', email='old@test'))).encode())
        with patch('auth.urllib.request.urlopen', return_value=payload):
            self.client.get('/auth/noos/callback?code=c&state=' + state)
        with app.app_context():
            self.assertEqual(get_db().execute('SELECT count(*) FROM user WHERE noos_id IS NOT NULL').fetchone()[0], 0)

    def test_logout_and_switch_reject_old_provider_callbacks(self):
        self.create_account()
        for transition in ('/logout', '/auth/ideaflow/switch-account'):
            self.authenticate()
            self.client.get('/auth/ideaflow/login')
            self.client.get('/auth/noos/login')
            with self.client.session_transaction() as session:
                oidc_state = session['ideaflow_pending']['state']
                noos_state = session['oauth_state']
            self.client.get(transition)
            with patch('ideaflow_auth.exchange') as exchange, patch('auth.urllib.request.urlopen') as noos_exchange:
                self.client.get('/auth/ideaflow/callback?code=c&state=' + oidc_state)
                self.client.get('/auth/noos/callback?code=c&state=' + noos_state)
                exchange.assert_not_called()
                noos_exchange.assert_not_called()
            with self.client.session_transaction() as session:
                self.assertNotIn('_user_id', session)
                self.assertTrue(session['ideaflow_signed_out'])
            self.assertIn('prompt=select_account', self.client.get('/auth/ideaflow/login').location)

    def test_oidc_recoverable_failures_preserve_validated_next(self):
        destination = '/explore?foo=1&bar=2'
        for failure in ('login_required', 'access_denied', 'exchange', 'resolution', 'expired'):
            self.client.get('/login', query_string={'next': destination})
            with self.client.session_transaction() as session:
                state = session['ideaflow_pending']['state']
                if failure == 'expired':
                    session['ideaflow_pending']['created'] = time.time() - 301
                    session.modified = True
            arguments = dict(state=state, code='c')
            if failure in ('login_required', 'access_denied'):
                arguments['error'] = failure
            error = ValueError('Existing account requires linking') if failure == 'resolution' else RuntimeError('Unavailable')
            with patch('ideaflow_auth.exchange', side_effect=error):
                response = self.client.get('/auth/ideaflow/callback', query_string=arguments)
            self.assertEqual(parse_qs(urlparse(response.location).query), {'auto': ['off'], 'next': [destination]})
            page = self.client.get(response.location)
            self.assertIn(b'Sign in with Ideaflow', page.data)
            self.client.get('/auth/ideaflow/login', query_string={'next': destination})
            with self.client.session_transaction() as session:
                self.assertEqual(session['ideaflow_pending']['next'], destination)
                session.pop('ideaflow_pending', None)
                session.pop('ideaflow_auto_attempted', None)

    def test_id_token_signature_nonce_audience_and_expiry(self):
        private = Ed25519PrivateKey.generate()
        claims = dict(sub='s', iss='https://id.ideaflow.app/api/auth', aud='test-client', nonce='n', iat=int(time.time()), exp=int(time.time())+60)
        def attempt(values):
            token=jwt.encode(values,private,algorithm='EdDSA')
            payload=io.BytesIO(json.dumps(dict(id_token=token)).encode())
            with patch('ideaflow_auth.urllib.request.urlopen',return_value=payload), patch('ideaflow_auth.jwt.PyJWKClient') as jwks:
                jwks.return_value.get_signing_key_from_jwt.return_value=SimpleNamespace(key=private.public_key())
                return exchange('code',dict(verifier='v',nonce='n'),config())
        self.assertEqual(attempt(claims)['sub'],'s')
        for changes in [dict(nonce='wrong'),dict(aud='other'),dict(iss='https://evil'),dict(exp=int(time.time())-60)]:
            with self.assertRaises(Exception): attempt(dict(claims,**changes))

    def test_next_rejects_external_and_backslash(self):
        for value in ['https://evil.test','//evil.test','/\\evil.test','/x\n']: self.assertEqual(local_next(value),'/dash')
        self.assertEqual(local_next('/explore?q=one'),'/explore?q=one')

if __name__ == '__main__': unittest.main()
