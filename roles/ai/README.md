# ai

GPU-bound AI services on `max`. Six service definitions in one stack (jina TEI is profile-gated):

| Service | Container | Host port | OpenAI-compatible |
|---|---|---|---|
| llama-swap (+ llama.cpp) | `mostlygeek/llama-swap:cuda` | `11434` | yes (chat, embeddings, page-image OCR) |
| whisper STT (speaches) | `speaches-ai/speaches:latest-cuda` | `9000` | yes (`/v1/audio/transcriptions`) |
| kokoro TTS | `remsky/kokoro-fastapi-gpu` | `8880` | yes (`/v1/audio/speech`) |
| TEI embeddings (Qwen3) | `huggingface/text-embeddings-inference:cuda-latest` | `11435` | yes (`/v1/embeddings`) |
| TEI embeddings (jina-v5) | `huggingface/text-embeddings-inference:cuda-latest` | `11436` | not running (profile-gated; see MODELS.md) |
| Playwright | `mcr.microsoft.com/playwright` | `3000` | n/a (WebSocket only) |

OpenWebUI (running on `nuc-mini`) consumes these shared services via env vars in
`roles/open_webui`. Most env vars take effect on first deploy only —
OpenWebUI persists them to its database and subsequent restarts use the
DB value, so changing an env var on an existing install requires either
editing it in Admin -> Settings or a one-shot start with
`RESET_CONFIG_ON_START=true`.

## llama-swap access

Port 11434 is published on IPv4 loopback and `max`'s inventory address.
The default allowlist is the `192.168.1.0/24` LAN. Clients on that network
can use `http://192.168.1.100:11434` directly. Open WebUI connects from
`nuc-mini`, as do Traefik's TinyAuth-protected `models.atelier.house` route
and Kizuna's PDF OCR worker. Clients outside the LAN should use Open WebUI's
authenticated endpoint or an administrative SSH tunnel.

The AI role owns the `inet homelab_llama_swap` nftables table. It filters
forwarded traffic using the original destination address and port, before
Docker's accept rules, and covers host listeners on the LAN address too.
Rules replace only that table atomically and do not exempt existing client
connections. UFW source restrictions alone do not protect Docker-published
ports. The allowlist trusts hosts and workloads on the LAN; it does not
authenticate individual users. Source filtering assumes the router preserves
the original source address for incoming traffic. Keep port forwarding
disabled so externally sourced traffic is not translated to a trusted LAN
source address.

The `ai-llama-swap-firewall.service` unit loads the rules before Docker starts.
A Docker unit drop-in requires it, so failure to load the rules prevents
Docker startup on `max`. Installing the drop-in does not restart Docker.
Allowlist updates reload rules without restarting Docker.
Stopping the firewall unit leaves its rules installed. Remove the published
port before retiring the rules, unit, and Docker drop-in. Do not flush the
host ruleset or restart Docker to test this on a live host.

Child llama.cpp servers listen only on `127.0.0.1` inside the llama-swap
container and restrict CORS to localhost. CORS applies to browser clients.
Network filtering controls access to the published llama-swap API.
Open WebUI's saved connections do not need to change.

Keep router/NAT forwarding for port 11434 disabled. Use the authenticated
Open WebUI endpoint or the administrative SSH tunnel described below for
remote access.

Validate locally:

```sh
make check
python3 tests/test_ai_access.py
git diff --check
```

After deployment is authorized, review the rendered AI stack against the
live configuration, including GPU assignments and installed models. Deploy
with cached images to keep this configuration change separate from upgrades:

```sh
ansible-playbook -i inventory/hosts.yml deploy/ai.yml -e docker_pull_policy=never
```

On `max`, verify `sudo nft list table inet homelab_llama_swap`,
`systemctl is-active ai-llama-swap-firewall.service`, the IPv4-only published
bindings, and local `http://127.0.0.1:11434/health`. From `nuc-mini`, verify
`http://192.168.1.100:11434/v1/models` and an authenticated Open WebUI chat.
From another `192.168.1.X` client, verify direct port 11434 works; from
outside the allowed subnet, verify it cannot connect. Verify TinyAuth still gates `models.atelier.house` and
Kizuna's OCR workflow still works. Repeat deployment to check idempotence.
Reboot persistence requires a separate authorized maintenance window.

For direct administrative access from another host, use an SSH tunnel:

```sh
ssh -L 18134:127.0.0.1:11434 max
```

Then use `http://127.0.0.1:18134`. The firewall does not change the AI stack's
other published services; review those separately when investigating router
forwarding.

## Web loading

The Playwright sidecar exists because OpenWebUI's default web loader is
LangChain's httpx-based `WebBaseLoader`, which most modern sites block;
without Playwright, web search "succeeds" but every page fetch returns
0 bytes and the chat reports "No sources found". The image tag is
pinned to match the `playwright==X.Y.Z` line in OpenWebUI's
`backend/requirements.txt` — bump `playwright_version` (and the image
tag in `playwright_image`) together when OpenWebUI updates Playwright.

## Layout

```
{{ docker_base_path }}/ai/
├── compose.yaml                # rendered from templates/compose.yaml.j2
├── config/
│   └── llama-swap.yaml         # rendered from templates/config/llama-swap.yaml.j2
└── models/                     # GGUF files, populated out of band
```

## Retire the shared SearXNG service

Web search is provided by [Degoog](../degoog/README.md) on `nuc-mini`.
The AI role no longer defines SearXNG, publishes port 8889, or renders its
settings. Its existing Compose deployment uses `remove_orphans: true`, so
applying this revision removes the old `ai` project's SearXNG container.
Komodo deployments using the newly rendered file also stop defining it.

Before deploying the retirement:

1. Confirm the n8n/Vane consumer migration is deployed. Verify Open WebUI's
   saved endpoint and n8n's running environment use Degoog. Vane is a legacy
   consumer; its image/video compatibility work is outside this retirement.
   Check separately configured workflow URLs for references to `max:8889`.
2. Disable the instance SearXNG provider in Kizuna Admin → Agent tools, leaving
   Degoog enabled. This is required: removing the container does not change
   Kizuna's database rows. Confirm fresh web and image requests succeed
   through Degoog from the API and chat worker.
3. Retain `/opt/docker/ai/config/searxng` and the encrypted
   `searxng_secret_key` vault entry for recovery. This change does not delete
   historical settings or rotate credentials.

Deploy only after reviewing the rendered AI configuration against the live
stack, including GPU assignments and model configuration:

```sh
ansible-playbook -i inventory/hosts.yml deploy/ai.yml -e docker_pull_policy=never
```

The pull override keeps cached images for this configuration change; ensure
those images exist first. The regular role still reconciles the entire AI
stack and may recreate services if the llama-swap configuration changed.
Do not use `docker compose down` for retirement.

On `max`, confirm no SearXNG container remains and no listener serves port
8889. Compare other AI container states and health with the pre-deploy
snapshot. On `nuc-mini`, repeat Kizuna's Degoog web/image probes and verify
only Degoog is enabled for the instance. Repeat the AI deployment to check
that SearXNG does not return.

Rollback requires restoring the removed service definition and settings
rendering from Git, keeping the retained settings and secret, and deploying
the AI role. Verify the restored endpoint before re-enabling any consumer's
SearXNG provider. Re-enabling a provider alone cannot restore the service.

## Models

The model catalogue (what's installed, why, how to pull each GGUF, how to add
or swap one) lives in [MODELS.md](MODELS.md). The `ai_models` list in
`defaults/main.yml` is the source of truth for what llama-swap serves;
MODELS.md is the human-readable companion.

OpenJev Q8 adds text and image judgments through `/v1/systemone`. Download
its weights and matching vision projector before deployment; see the
[OpenJev catalogue entry](MODELS.md#openjev-text-and-vision-decisions) for
the command, runtime prerequisites, license, and text/image verification.

Embeddings split across two surfaces:

- **Always-on (TEI)** for OpenWebUI RAG and any other "no cold-load tax"
  consumer. Two containers, each pinned to one model:
  - `tei` -> `Qwen/Qwen3-Embedding-0.6B` at `:11435` (read from local
    snapshot at `models/Qwen3-Embedding-0.6B/`).
  - `tei-jina` -> `jina-embeddings-v5-text-small-retrieval` at `:11436`, deployed but not started (read from local
    snapshot at `models/jina-embeddings-v3/`).
- **Swap-loaded (llama-swap)** for project experimentation. The `embed`
  group has `swap: true`, so only one of `bge-m3`, `qwen3-embed-0_6b`,
  `qwen3-embed-4b` is resident at a time, served at `:11434/v1/embeddings`.

Kizuna's scanned-PDF fallback uses the swap-loaded `unlimited-ocr` vision
model at `:11434/v1/chat/completions`. It has a five-minute idle TTL and a
non-exclusive `ocr` group, so it loads on demand without displacing chat or
embedding models. Install the community llama.cpp conversion before deploy:

```sh
mkdir -p /mnt/storage/models/ai/Unlimited-OCR
cd /mnt/storage/models/ai/Unlimited-OCR
hf download sahilchachra/Unlimited-OCR-GGUF Unlimited-OCR-BF16.gguf mmproj-Unlimited-OCR-F16.gguf --local-dir .
```

## Hardware notes

Host inspection on September 21, 2026 confirmed three NVIDIA RTX PRO 6000
Blackwell cards on `max`: two 300 W Max-Q cards (GPUs 0 and 1) and one
600 W Workstation card (GPU 2), each with 96 GB nominal VRAM. The configured
split mode assigns llama-swap to GPU 2 and vLLM to GPUs 0 and 1. See
[AI defaults](defaults/main.yml) for allocation modes and the
[inference upgrade plan](../../docs/inference-upgrade-plan.md) for planned work.

## Temporary two-card test, October 7, 2026

The Workstation card was removed for the power-event investigation. On max,
only llama-swap's device reservation in `/opt/docker/ai/compose.yaml` was
temporarily changed from `["2"]` to `["0", "1"]`. The existing image and
split-mode model catalogue were retained; larger shared-mode models remain
excluded. Whisper, TEI, and PCSX2 still require the absent GPU 2.

The original Compose file is saved beside it as
`compose.yaml.before-maxq-test-20261007`. An AI deployment overwrites this
temporary assignment. When the Workstation card returns, verify GPU identities
before restoring the assignment and recreating llama-swap. Compare the backup
first so later configuration changes are preserved.

The card-removal boot began around 19:01 PDT on kernel `7.0.0-34-generic`;
llama-swap resumed around 19:08. CI remained active. Three-hour transient
systemd services record availability on nuc-mini and GPU readings on max:

```sh
ssh nuc 'sudo journalctl -u max-card-removal-watch-20261007.service'
ssh max 'sudo journalctl -u max-card-removal-gpu-sample-20261007.service'
ssh max 'sudo journalctl -t host-health --since "2026-10-07 19:01:00"'
```

These recorders do not restart the host or run stress workloads. Gatus supplies
the existing outage alerts. Stability with the card removed changes both hardware
and load distribution; it does not by itself identify a faulty component.

## Llama.cpp version requirement

The `qwen3.8` / `qwen3.8-q8` entries use the `--spec-type draft-mtp` flag,
which requires llama.cpp from 2026-05-16 or later. Before first deploy, run
`docker pull ghcr.io/mostlygeek/llama-swap:cuda` on `max` to ensure the
bundled llama-server is recent enough; if MTP-enabled models fail to start
with a flag error in `docker logs llama-swap`, the image is stale and a
pull will fix it.

The Qwen3.8 entries are also the Qwen3.5-lineage hybrid architecture
(`qwen35` in the GGUF metadata), which needs a llama.cpp build that
knows it. Same symptom and same fix: an unknown-architecture or
unknown-flag error at load means the image is stale.

Without `--jinja` the chat template and tool-calling break for Gemma 4
and Qwen3.8.

## First-time deploy

`docker compose up` on a fresh `max` has to pull roughly 20–30 GB of CUDA
images, and Ansible buffers task output until the module returns, so the
`Deploy ai stack` task can look frozen for many minutes. Pre-pull the images
(`docker pull` each one in `compose.yaml.j2`) before running the playbook for
the first time to avoid the perceived hang.
