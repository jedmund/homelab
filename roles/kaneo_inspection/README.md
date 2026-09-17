# Dedicated Kaneo inspections

This role manages only `kaneo-inspection` on `nuc-mini`. It does not manage the personal mac-mini daemon.

The application and adapter use the reusable `inspection` tag during feature iteration. The dedicated Paseo image remains pinned until its runtime is deliberately updated. Kaneo supplies immutable source archives using its existing workspace SCM access; the adapter needs no catalog or Git credentials. The initial compatibility target is Paseo 0.1.88 and OpenCode 1.17.5. Build both targets from `apps/inspection-adapter/Dockerfile` in the Kaneo repository.

Provision dedicated Vault values: `vault_kaneo_inspection_bearer_token` (32+ characters), `vault_kaneo_inspection_paseo_password` (64 hex characters), `vault_kaneo_agent_service_encryption_key` (32+ characters). Set `vault_kaneo_inspection_model_auth` if local inference requires authentication. Back up the agent-service encryption key with Kaneo's database recovery material; losing it makes saved service credentials unreadable.

Run `ansible-playbook deploy/kaneo-inspection.yml --syntax-check`, validate the rendered compose file, then deploy only after active inspections finish. The API has no host port. Join the Kaneo container to the external internal network `kaneo-inspection-api` by setting `kaneo_agent_inspections_enabled: true` on its deployment. Exact origin: `http://adapter:1338` (the only adapter on this network). Model and relay traffic traverse fixed-target TCP proxies; neither application container joins the egress network. No production database credentials, Docker socket, or personal home directories are mounted.

Pair the new daemon as **Kaneo Inspections**, using its own persistent state and the existing relay. Treat pairing output as a credential. Do not restart the personal daemon. Register the bearer connection in Kaneo's Instance → Agent Services, grant only the intended workspace, then select the inspection service in Project Settings → Agents. Connected repositories are available automatically. Add other sources, such as `kizuna/docs`, from the workspace SCM connection; they need no Kaneo project or task integration. The user selects repositories and starts the first task inspection in the UI.

Rollout: validate synthetic jobs and isolation first; back up Kaneo; deploy the additive migrations and UI; register the service; enable only the pilot project. Source snapshots and adapter jobs expire after seven days; validated results remain in Kaneo until task deletion. `/health` is a liveness probe; local inference and SCM outages must also be monitored through failed/queued jobs. The bearer-protected `/v1/metrics` endpoint exposes retained job counts by state in Prometheus format.

Rollback: disable the connection, cancel active runs, wait for cancellation/deadline, then stop this stack. Keep its state and Kaneo's encryption key. Existing task functionality remains independent of this service. Do not roll back by removing database tables.

Runtime isolation and live pilot acceptance must pass before enabling production use. Configuration assertions alone are not proof that OpenCode's tool policies enforce every restriction.

## Iteration and recovery

Publish the application and adapter `inspection` tags only after testing their exact commit images. Publishing does not restart production: explicitly deploy during an idle inspection window. The inspection playbook pulls these tags on deployment. Record resolved image digests, back up the application database/configuration and the adapter SQLite state, and verify health after cutover. Roll back to those recorded digests if needed; do not remove additive database migrations. No per-build image-pin PR is needed.

This stack has no public route and no Komodo auto-deployment. The existing Kaneo inventory group supplies its Vault inputs. Include `/opt/docker/kaneo-inspection` in host backup coverage, including adapter SQLite state, snapshots, and dedicated daemon state; use a stopped stack or SQLite-consistent backup for the live job database. Keep secrets encrypted in offline recovery material. The separate personal daemon is outside this role.

## Models and inspection instructions

The adapter implements protocol v2 alongside v1. Deploy the compatible adapter before the application. Instance administrators edit the model and inspection instructions in Kaneo's saved Agent Service dialog. Projects inherit that configuration. New runs snapshot it; active runs keep their original model and instructions. Task readers see the model but not administrator instructions.

`kaneo_inspection_configuration` is an operator-owned catalog of permitted OpenCode models. Each provider declares `id`, `label`, `npm`, `baseURL`, `apiKeyEnvironment`, and a list of models with `id` and `label`. `defaultModel` uses `provider-id/model-id`. Supported SDKs are OpenAI-compatible, OpenAI, Anthropic, and Google. Keep credentials out of this catalog; use environment references. The default remains local DeepSeek and requires no new provider.

Additional credentials belong in the encrypted `vault_kaneo_inspection_provider_credentials` dictionary. Keys must begin with `INSPECTION_PROVIDER_` and contain only uppercase letters, digits, and underscores; reference the same key in `apiKeyEnvironment`. They are delivered only to the dedicated daemon using a raw environment file (Docker Compose 2.30+). Values must be single-line strings; dollar signs, quotes, and backslashes are preserved literally. Catalog and credential changes recreate the affected stack on deployment. Remove a model only after its active inspections finish.

Adding a catalog entry does not provision a provider or grant network access. Operators must first configure a working endpoint and an explicitly permitted egress route. The existing fixed-target model and relay proxies remain the only default egress. Do not attach the daemon directly to an unrestricted network. Verify model access with a synthetic inspection before advertising it. No additional provider credentials or routes are provisioned by this change.

Before application cutover, verify the encryption key is present without displaying it, the exact adapter origin is allowed, and the application joins `kaneo-inspection-api`. Then make an authenticated capability/options request from the application network. `/health` alone does not verify these dependencies. Preserve the original encryption key across redeployments, since replacing it makes existing service credentials unreadable.
