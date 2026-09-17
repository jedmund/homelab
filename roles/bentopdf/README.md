# BentoPDF

BentoPDF is a stateless browser-side PDF toolkit. The stack has no mounts,
database, cache, or server-side user data. The maintenance preflight enforces
that zero-mount state; it is the service's backup exemption.

## Image and health

The `2.8.8` image is pinned to its multi-platform OCI digest in
[defaults](defaults/main.yml). The container health check uses the image's
existing `wget` to request its local nginx endpoint on port 8080.

Render approved files on `nuc-mini` without invoking Compose:

```sh
make -C deploy stage STACK=bentopdf
```

Only roles in the deployment Makefile's staging allowlist accept this command.
After staging, use the admin-only `maintain-bentopdf` Komodo Procedure. Its
preflight records the current container image and state, checks that the
rendered image is the Git-pinned reference, and rejects any mount. After Komodo
deploys the stack, the Procedure waits for Docker health and verifies the
running repository digest.

## Recovery

Restore the previous tag and digest in
[defaults/main.yml](defaults/main.yml), validate and merge that change, then:

```sh
make -C deploy stage STACK=bentopdf
```

Run `maintain-bentopdf` and confirm its final health and digest checks pass.
BentoPDF has no server-side database migration or persistent data to reverse.
