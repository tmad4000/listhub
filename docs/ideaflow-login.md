# Ideaflow login for ListHub

ListHub is an independent confidential OIDC relying party of the canonical
issuer `https://id.ideaflow.app/api/auth`. The production callback is exactly
`https://listhub.globalbr.ai/auth/ideaflow/callback`. The provider client must
use authorization code flow, S256 PKCE, and `client_secret_basic`.

## Identity contract

The durable key is `(issuer, subject)` in `external_identity`. ListHub keeps
its existing user IDs, ownership, local sessions, Noos links, local passwords,
and API keys. A new subject never attaches to an existing account by email or
display name, even if the provider says that email is verified. An existing
user signs in with a current method and explicitly links Ideaflow in Settings;
the callback must finish in the same signed-in ListHub session that started it.
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

## Rollout

The feature is absent unless all three settings are present:

- `IDEAFLOW_OIDC_ENABLED=true`
- `IDEAFLOW_OIDC_CLIENT_ID`
- `IDEAFLOW_OIDC_CLIENT_SECRET`

`LISTHUB_PUBLIC_URL` supplies the callback origin; production must keep the
default exact apex. Disabling the flag removes the login and link routes while
leaving existing identity rows intact for a reversible rollback. ListHub does
not call a provider logout endpoint.

Programmatic `POST /api/v1/auth/register`, API keys, local passwords, and the
legacy Noos OAuth flow remain available and keep their current behavior.
