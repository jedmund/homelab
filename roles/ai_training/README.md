# ai_training

LoRA / QLoRA fine-tuning stack for max. Builds a Blackwell-ready
PyTorch + Unsloth container and keeps it idle (`sleep infinity`) so
training runs are a single `docker compose exec` away. Adapters,
logs, datasets, and HF cache are persisted under
`/opt/docker/ai_training/`.

This is a sibling to the `ai` role (which serves inference via
llama-swap). The two cannot run concurrently because a training run
saturates both GPUs.

## Layout on `max`

```
/opt/docker/ai_training/
├── build/
│   └── Dockerfile            # rendered from templates/Dockerfile.j2
├── compose.yaml              # rendered from templates/compose.yaml.j2
├── base_models/              # downloaded HF safetensors weights (persistent)
├── datasets/                 # HF datasets cache (persistent)
├── adapters/                 # LoRA adapter outputs, one dir per run
├── logs/                     # tensorboard logs, one dir per run
├── runs/                     # rendered training scripts, one .py per run
│   └── qwen3-4b-reasoning-distill.py
└── hf_cache/                 # HF Hub download cache (avoids re-pulling)
```

## Deploy

```sh
ansible-playbook deploy/ai_training.yml
```

First deploy builds the container image, which downloads PyTorch +
unsloth and is large; expect ~10 minutes and ~15 GB image size.
Subsequent deploys only rebuild when `Dockerfile.j2` changes.

## Run the proof-of-concept training

1. Stop inference workloads (training saturates both GPUs):
   ```sh
   ssh max "docker stop llama-swap"
   ```
2. Launch the run:
   ```sh
   ssh max "docker compose -f /opt/docker/ai_training/compose.yaml \
     exec trainer python /runs/qwen3-4b-reasoning-distill.py"
   ```
   First invocation downloads the base model from Hugging Face into
   `hf_cache/` (~8 GB for Qwen3-4B at fp16). Subsequent runs reuse it.
3. Watch progress: `docker exec ai-trainer tail -f /logs/qwen3-4b-reasoning-distill/...`
   or open the tensorboard via `tensorboard --logdir /opt/docker/ai_training/logs`
   from inside the container.
4. When the run completes, the adapter is at
   `/opt/docker/ai_training/adapters/qwen3-4b-reasoning-distill/`. ~150-300 MB.
5. Restart inference:
   ```sh
   ssh max "docker start llama-swap"
   ```

## Test the adapter

You can either:

- Load it directly in a Python shell inside the trainer container
  (`FastLanguageModel.from_pretrained` + `model.load_adapter(...)`)
  for quick eval before deciding to merge.
- Merge it into the base model and export to GGUF for llama-swap:
  ```python
  model.save_pretrained_merged("/adapters/<name>-merged", tokenizer, save_method="merged_16bit")
  model.save_pretrained_gguf("/adapters/<name>-gguf", tokenizer, quantization_method="q8_0")
  ```
  Then drop the resulting GGUF into `/opt/docker/ai/models/` and add a
  new entry to the `ai_models` list in `roles/ai/defaults/main.yml`.

## Adding a new training run

Append an entry to `ai_training_runs` in
`roles/ai_training/defaults/main.yml`. The schema mirrors the existing
qwen3-4b run; the role renders a new `runs/<name>.py` on next deploy.
Hyperparameters that vary per-run live in the entry; anything cross-cutting
(image versions, paths) lives at the top of `defaults/main.yml`.

## Caveats

- **Dataset schema**: the rendered script tries `messages` / `prompt`+`response`
  / `instruction`+`output`. If the dataset uses different keys, edit
  `formatting_func` in the rendered script before running (it lives at
  `/opt/docker/ai_training/runs/<name>.py` on max).
- **Gated models / private datasets**: set `ai_training_hf_token` via vault.
  The token is injected as `HF_TOKEN` into the container env.
- **MoE fine-tunes**: Unsloth's MoE support is newer than its dense path.
  Start with dense bases (Qwen3-4B, Qwen3.6-27B) before attempting the
  35B-A3B or 30B-A3B MoEs; expect more failure modes (expert imbalance,
  router instability).
- **Adapter compatibility**: a LoRA trained against a specific base model
  variant (e.g. instruct vs base) must be merged into the *same* variant.
  Pulling the GGUF from llama-swap's catalog and the safetensors from
  Hugging Face needs to resolve to compatible weights.
