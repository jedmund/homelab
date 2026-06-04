# utilities role

Compose stack on `nuc-mini` for general-purpose services.  Today:

| Service | Domain | Networking |
|---|---|---|
| n8n | `n8n.atelier.house` | proxy + backend bridges |
| n8n-db (Postgres 16) | — | backend bridge |
| ChangeDetection.io | `track.atelier.house` | proxy bridge |
| Copyparty | `files.atelier.house` | proxy bridge |

Feederhub used to live here too; it now has its own role at
`roles/feederhub/` and its own Komodo Stack so CI pushes to
`registry.atelier.house/jedmund/feederhub` auto-deploy.
