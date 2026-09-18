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

Validate from this repository with a local Noos checkout that contains the
stamped commit:

```bash
NOOS_CHECKOUT=~/code/noos python3 -m unittest tests.test_nginx_route
```

Before production activation:

1. Obtain fresh authorized read access to the shared GCE host and record the
   live Noos git SHA, nginx image ID, nginx config checksum, ListHub service
   health, and current host routing responses.
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
