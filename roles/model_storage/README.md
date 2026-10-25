# Model storage

This role mounts max's second NVMe, a Samsung 990 PRO 4TB, at `/mnt/storage`,
and creates the model directories on it. Model weights are large and
re-downloadable, so they live off the 2 TB root volume that Docker, CI, and the
journal depend on. The [AI](../ai/README.md) and [vLLM](../vllm/README.md)
deployments include this role before their own.

| Path | Used by |
| --- | --- |
| `/mnt/storage/models/ai` | llama-swap GGUFs and TEI models (`ai_models_dir`), mounted at `/models` |
| `/mnt/storage/models/huggingface` | vLLM's Hugging Face cache (`vllm_hf_cache_dir`) |

`~/.cache/huggingface` on max links to `/mnt/storage/models/huggingface`, so a
hand-run `hf download` uses the drive by default. The cache also holds the
Hugging Face CLI login token.

## When the drive is missing

The mount uses `nofail`, so max still boots if the drive fails. Docker, CI, and
the other stacks keep running. The model containers do not start: their bind
mounts set `create_host_path: false`, so Docker refuses to start them rather
than creating empty directories on the root volume. The ai and vLLM deployments
also stop if their model directory is missing.

Check the mount with `findmnt /mnt/storage`. The partition UUID is
`model_storage_mount_src` in `inventory/hosts.yml`.

## Deploy

The role runs as part of `make deploy-ai`, `make deploy-ai-split`, and
`make deploy-vllm`. To apply only the mount and directories:

```sh
ansible-playbook -i inventory/hosts.yml deploy/ai.yml --tags model_storage
```

The Hugging Face link task refuses to replace an existing
`~/.cache/huggingface` directory. To move an existing cache onto the drive,
copy it, rename the old directory, and then run the role. Skip the link with
`--skip-tags model_storage_hf_link` while copying.
