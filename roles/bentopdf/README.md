# BentoPDF

BentoPDF is a stateless browser-side PDF toolkit. The stack has no mounts,
database, cache, or server-side user data, so it requires no application-data
backup.

## Image and health

The application image is pinned to its release tag and multi-platform OCI digest in
[defaults](defaults/main.yml). The container health check uses the image's
existing `wget` to request its local nginx endpoint on port 8080.

## Deployment

After reviewing and merging an image update, deploy to `nuc-mini`:

```sh
make -C deploy bentopdf
```

Ansible writes the Compose file and deploys the stack in the same run. Komodo's
`bentopdf` Stack can redeploy the existing host-rendered configuration; a new
image pin must first be applied through Ansible.

If the earlier maintenance pilot was installed, retire its obsolete Komodo
resources as described in the [Komodo runbook](../../komodo/README.md#bentopdf-updates),
then remove `/opt/docker/bentopdf/scripts/maintenance-check.sh` on `nuc-mini`.

On `nuc-mini`, verify the container and local endpoint:

```sh
docker compose -f /opt/docker/bentopdf/compose.yaml ps
docker inspect --format '{{.Config.Image}} {{.State.Health.Status}}' bentopdf
docker exec bentopdf wget --quiet --spider http://127.0.0.1:8080/
```

Confirm the configured image matches the approved tag and digest, health is
`healthy`, and the local endpoint succeeds. Sign in through TinyAuth at
`https://pdf.atelier.house` and exercise a PDF tool to verify browser behavior.

## Recovery

Restore the previous tag and digest in
[defaults/main.yml](defaults/main.yml), validate and merge that change, then:

```sh
make -C deploy bentopdf
```

Repeat the deployment verification above.
BentoPDF has no server-side database migration or persistent data to reverse.
