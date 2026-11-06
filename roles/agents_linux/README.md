# Linux agent tooling

This role installs and configures OpenCode and Pi for `justin` on `nuc-mini`.
OpenCode uses `~/.config/opencode/opencode.jsonc`; Pi uses
`~/.pi/agent/models.json`, `settings.json`, and `agents/`.
The role does not manage the Mac's client configuration.

Both clients default to `vllm-max/GLM-5.3-Flash` at
`http://192.168.1.100:11438/v1`. The model entry advertises 950,272 context
tokens and a 32,768-token output limit. The context limit must stay at or below
the live server's `max_model_len`. These are capacity limits, not a guarantee
that multiple full-context requests fit at once. High reasoning is supplied by
the server profile; client thinking-level controls are not separately verified.

Start the GLM Spark profile using the [vLLM runbook](../vllm/README.md) before
using these defaults. Switching the server back to DeepSeek also requires
changing client defaults, the direct provider's endpoint and model entry, and
Pi's planner model. The retained Atelier DeepSeek entry addresses a separate
proxy route. GLM's direct endpoint requires LAN access.

The full `deploy/agents_linux.yml` playbook also installs or updates tools,
plugins, and the Edra MCP server. For a model-only change, back up live configs
and update only the relevant model entries and defaults, preserving credentials
and other local settings. Keep these repository templates in sync so a later
full deployment retains the model selection. Do not print rendered credentials.

Validate template rendering with placeholder credentials and parse the resulting
JSON/JSONC. On each client host, confirm that the model appears in the installed
client's model list and complete a short request using it. Existing sessions may
retain their selected model; select `vllm-max/GLM-5.3-Flash` or start a new session.

## Komodo MCP

OpenCode launches the pinned [Komodo MCP server](https://github.com/MP-Tool/komodo-mcp-server)
image over stdio. The identity is the `agent-ro` Komodo service user; its
permissions come from the `agent-readonly` group declared in
[komodo/stacks.toml](../../komodo/stacks.toml) — Read on all resource types
with the Logs feature gate, and no Execute, Write, Inspect, or Terminal
anywhere. The API key pair renders into `~/.config/opencode/mcp/` files at
mode 0600 and reaches the server through `KOMODO_API_KEY_FILE` /
`KOMODO_API_SECRET_FILE`, so no secret is stored in `opencode.jsonc` or
printed by renders. The `terminal`, `user`, `variable`, `tag`, `builder`, and
`swarm` tool categories are pruned from the server's tool surface.

Rotation: create a new API key on `agent-ro`, replace
`vault_komodo_mcp_api_key` and `vault_komodo_mcp_api_secret` in the vault, and
redeploy; then delete the old key in Komodo. Removal: disable the `komodo`
entry in `opencode.jsonc` and delete the key. After any identity or permission
change, verification is: reads list servers and stacks, and every mutation
attempt fails with a permission error.
