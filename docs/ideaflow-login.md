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
display name alone, even if the provider says that email is verified: ListHub has
no email-verification flow, so a typed local email proves nothing (its creator may
be a squatter who knows the password). Instead, when a strictly verified Ideaflow
email matches exactly one existing account that has a local password, sign-in asks
once for that account's password (`/auth/ideaflow/confirm`: five attempts, ten
minutes, single use) and then binds the identity automatically. Accounts without a
local password (Noos-only or Ideaflow-only), several matching accounts, or an account
already connected to a different Ideaflow identity are never guessed or bound: the
person gets a page offering only the way out (sign in to the existing account
another way and use Connect Ideaflow in Settings, or create a new account). An
unverified Ideaflow email that matches an account is refused with the same
guidance. The confirmation page also offers **Create a new ListHub account**
(`/auth/ideaflow/confirm/new`) for a person whose address someone else typed or who forgot that password: it leaves the
existing account untouched and creates a fresh one (its UNIQUE `user.email` stays
with the existing row, so the new row has no email; the identity row keeps it). A
per-account failure cap (ten wrong passwords in ten minutes, in process, per
gunicorn worker) backs the per-check attempt counter, which lives in the
client-held session cookie.
That fallback ([web sign-in instructions](../README.md#web)) always forces a fresh
Ideaflow sign-in (`prompt=login`), requires a fresh `auth_time`, and must finish in
the same signed-in ListHub session that started it.
**Use another Ideaflow account** on the login page (`?switch=1`) sends
`prompt=login`; no other query parameter is forwarded to the provider.
An unlinked subject with no matching email creates a new local account.
Signing in again or signing out invalidates pending links and pending password
confirmations, including when the same account signs back in. The callback validates the canonical issuer and
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

## Last-used hint

The sign-in screens label the method last used successfully on this browser
(**Last used**) whenever two or more methods are offered. After a completed login
(the local password handler, the validated Noos callback, a validated Ideaflow
callback that signs a user in, or a completed Ideaflow ownership check or
**Create a new account** confirmation) the server sets the `listhub_last_login` cookie
(HttpOnly, SameSite=Lax, one year) holding only `password`, `noos`, or
`ideaflow`. Clicking a button (including **Use another Ideaflow account**), reaching or
failing the ownership check, cancelling it, failed or cancelled attempts,
restoring an existing session, and Ideaflow linking from Settings never write or
clear it. The value is
ignored unless it is one of the methods currently enabled, and it never contains
tokens, emails, or user IDs. It does not change account mapping or sessions.

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
