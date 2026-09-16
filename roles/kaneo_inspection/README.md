# Dedicated Kaneo inspections

This role manages only `kaneo-inspection` on `nuc-mini`. It does not manage the personal mac-mini daemon.

Supply immutable adapter and Paseo image digests, and an approved catalog containing `ref`, `displayName`, HTTPS `cloneUrl` (without credentials), and `branch`. The initial compatibility target is Paseo 0.1.88 and OpenCode 1.17.5. Build both targets from `apps/inspection-adapter/Dockerfile` in the Kaneo repository.

Provision dedicated Vault values: `vault_kaneo_inspection_bearer_token` (32+ characters), `vault_kaneo_inspection_paseo_password` (64 hex characters), `vault_kaneo_agent_service_encryption_key` (32+ characters), and `vault_kaneo_inspection_git_username` / `vault_kaneo_inspection_git_token` (read_repository only, scoped to approved projects). Set `vault_kaneo_inspection_model_auth` if local inference requires authentication. Back up the agent-service encryption key with Kaneo's database recovery material; losing it makes saved service credentials unreadable.

Run `ansible-playbook deploy/kaneo-inspection.yml --syntax-check`, validate the rendered compose file, then deploy with the approved catalog and immutable images. The API has no host port. Join the Kaneo container to the external internal network `kaneo-inspection-api` by setting `kaneo_agent_inspections_enabled: true` on its deployment. Exact origin: `http://adapter:1338` (the only adapter on this network). Git, model, and relay traffic traverse fixed-target TCP proxies; neither application container joins the egress network. No production database credentials, Docker socket, or personal home directories are mounted.

Pair the new daemon as **Kaneo Inspections**, using its own persistent state and the existing relay. Treat pairing output as a credential. Do not restart the personal daemon. Register the bearer connection in Kaneo's Instance → Agent Services, grant only the intended workspace, then configure the project's repository mappings. Pilot task and approved repositories must be designated before production inspection.

Rollout: validate synthetic jobs and isolation first; back up Kaneo; deploy the additive migrations and UI; register the service; enable only the pilot project. Source snapshots and adapter jobs expire after seven days; validated results remain in Kaneo until task deletion. `/health` is a liveness probe; local inference and Git outages must also be monitored through failed/queued jobs. The bearer-protected `/v1/metrics` endpoint exposes retained job counts by state in Prometheus format.

Rollback: disable the connection, cancel active runs, wait for cancellation/deadline, then stop this stack. Keep its state and Kaneo's encryption key. Existing task functionality remains independent of this service. Do not roll back by removing database tables.

Runtime isolation and live pilot acceptance must pass before enabling production use. Configuration assertions alone are not proof that OpenCode's tool policies enforce every restriction.
