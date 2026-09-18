# ListHub production routing

`listhub.globalbr.ai` is proxied by Cloudflare to the shared Noos GCE host. The
ListHub Flask service itself listens on host port `3200`; the shared
`noos_nginx` container reaches host services through `172.17.0.1`.

On 2026-09-17, the DNS record and ListHub service were healthy, but deployed
Noos commit `31231f6e362590b8330765a98d656ab03fcc6c24` had no
`server_name listhub.globalbr.ai`. Nginx therefore selected its default server
and returned the Noos SPA for the ListHub hostname.

[`deploy/noos-nginx-listhub.patch`](../deploy/noos-nginx-listhub.patch) is a
single additive server block against that exact deployed Noos commit. It routes
only `listhub.globalbr.ai` to `http://172.17.0.1:3200`; existing Noos, staging,
Notes, Thoughtstreams, OpenChat, Agent-First, and default-server blocks remain
byte-for-byte unchanged. The corresponding base `nginx.conf` SHA-256 is recorded
in `deploy/noos-nginx-base.sha256` so drift fails closed.

Validate from this repository using the checksum-pinned source fixture in
`tests/fixtures/noos-nginx.conf` (the stamped commit's original configuration):

```bash
python3 -m unittest discover -s tests -p 'test_nginx*.py' -v
```

`NOOS_CHECKOUT` optionally checks the original commit from a local Noos checkout
instead of the fixture. The fixture matches `deploy/noos-nginx-base.sha256`;
it was recovered from the prior source-grounded validation capture by removing
the exact additive patch and verifying that checksum.

Set `NGINX_BINARY=/absolute/path/to/nginx` (or put nginx on `PATH`) to also run
the runtime test. It starts an isolated, unprivileged nginx on loopback with
temporary data, substituting only listen/upstream addresses and filesystem
paths. It checks configuration loading, ListHub Flask responses, existing
vhosts and route prefixes, forwarded headers, and the unknown-host fallback.
Other services use local stand-ins. The runtime test skips explicitly if nginx
is unavailable; the source preservation tests always run. A local nginx 1.26.3
build passed these checks; this does not validate the live Docker network or
authorize production changes.

## Production activation

This change prepares source artifacts only; it does not deploy or mutate the
shared host. The retired Lightsail host and `noos-prod` SSH alias must not be
used. The current access route is:

```bash
gcloud compute ssh noos --project=lightsail-migration --zone=us-central1-a
```

Before production activation:

1. Obtain fresh gcloud authorization for read access to the shared GCE host and
   record the live Noos git SHA, nginx image ID, nginx config checksum, ListHub
   service health, and current host routing responses.
2. Rebase/regenerate the patch if the live nginx source differs from the
   stamped base. Never apply it with fuzz or offset.
3. Coordinate one shared-host window with the Noos owner. Back up
   `nginx.conf`, apply the reviewed patch in the Noos source checkout, run
   `nginx -t` inside the exact production nginx image/container, and reload
   nginx without restarting unrelated application containers.
4. Verify `listhub.globalbr.ai` reaches ListHub and representative existing
   hosts still reach their prior destinations.

Rollback is the inverse source change followed by `nginx -t` and a reload.
DNS, ListHub data, and application processes are unchanged by this route patch.

Application deployment is separate from the nginx reload and shares the same
authorization and coordination gates. Changes go through git, not SCP. Before
planning a pull/restart, verify the checkout path, branch, systemd unit, virtual
environment, and persistent database/repository paths on the live host. Use the
[OIDC migration and rollout reference](ideaflow-login.md#migration) for this app
change. A full `python git_sync.py` from the app checkout's virtual environment
is for changes that require rebuilding git mirrors; the additive identity table
does not require it.
