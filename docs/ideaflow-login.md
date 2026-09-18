# Ideaflow login for ListHub

ListHub is an independent confidential OIDC relying party of the canonical
issuer `https://id.ideaflow.app/api/auth`. The production callback is exactly
`https://listhub.globalbr.ai/auth/ideaflow/callback`. The provider client must
use authorization code flow, S256 PKCE, and `client_secret_basic`.
Authlib discovers provider metadata and JWKS and verifies signed ID tokens,
including EdDSA with Ed25519 keys. The signing algorithms accepted by Authlib
come from discovery metadata; see the signed-token coverage in
[`tests/test_ideaflow_oidc.py`](../tests/test_ideaflow_oidc.py).

## Identity contract

The durable key is `(issuer, subject)` in `external_identity`. ListHub keeps
its existing user IDs, ownership, local sessions, Noos links, local passwords,
and API keys. A new subject never attaches to an existing account by email or
display name, even if the provider says that email is verified. Existing-account
linking follows the [web sign-in instructions](../README.md#web); the callback
must finish in the same signed-in ListHub session that started it.
An unlinked subject creates a new local account unless its email matches an
existing user's email case-insensitively. That collision blocks sign-in and
directs the user to sign in to the existing account and link from Settings.
Signing in again or signing out invalidates pending links, including when the
same account signs back in. The callback validates the canonical issuer and
requires the ListHub client ID in the ID token audience, even when `azp` matches.

Authorization attempts expire after ten minutes; only the three newest pending
attempts are retained, together with their PKCE and nonce state. Provider requests
use a five-second timeout. Discovery failures return to login or Settings with a
retry message, and failed or cancelled callbacks consume their pending attempt.

The callback trusts `email_verified` only when the claim is the JSON boolean
`true`. An unverified email may be retained on the external identity for
display but is not copied into the local user record. Database uniqueness on
both `(issuer, subject)` and `(user_id, issuer)` fails closed on conflicts.

New Ideaflow-only users have no local password. For git authentication, create
an API key in Settings and use it as the HTTP Basic password. Linking an existing
account preserves its password and git credentials.

## Migration

[`create_app()`](../app.py) calls [`init_db()`](../db.py) at startup. The
idempotent schema initialization adds the external identity table and its index
even while OIDC is disabled; it does not backfill links or rewrite existing users
or content. Install the pinned dependencies from [`requirements.txt`](../requirements.txt)
before starting this version, including when the feature is disabled.

## Rollout

Production activation follows the authorization and shared-host window in the
[routing runbook](listhub-production-routing.md#production-activation). Keep the
existing `LISTHUB_SECRET` when restarting to preserve signed sessions.

The feature is disabled by default and unavailable unless all three settings
are present when the app starts:

- `IDEAFLOW_OIDC_ENABLED=true`
- `IDEAFLOW_OIDC_CLIENT_ID`
- `IDEAFLOW_OIDC_CLIENT_SECRET`

`LISTHUB_PUBLIC_URL` supplies the callback origin (default:
`https://listhub.globalbr.ai`); production must keep the exact callback above.
Set the flag to `false` and restart to hide the Ideaflow UI and make its sign-in,
link, and callback routes return 404. Existing identity rows and ListHub sessions
remain intact for a reversible rollback. ListHub does not call a provider logout
endpoint.

Programmatic `POST /api/v1/auth/register`, API keys, local passwords, and the
legacy Noos OAuth flow remain available and keep their current behavior.
