# n8n

n8n runs on `nuc-mini`. The instance Assistant uses Open WebUI for model
requests and its own sandbox service for code execution. The Assistant's
web-search endpoint is independent of workflow-specific credentials and HTTP
Request nodes, which remain application-managed.

## Web search through Degoog

`n8n_instance_ai_searxng_url` defaults to `http://degoog:4444/api`.
n8n's SearXNG client appends `/search?format=json` and reads Degoog's native
`url`, `title`, and `content` result fields. Both containers join
`proxy-network` on `nuc-mini`; do not use Degoog's public TinyAuth URL.
See the [Degoog runbook](../degoog/README.md).

After the change is merged, deploy n8n with:

```sh
make deploy-n8n
```

The environment-file change recreates the running stack. Verify the configured
endpoint and request the same JSON route from n8n:

```sh
docker exec n8n node -e '
  const base = process.env.N8N_INSTANCE_AI_SEARXNG_URL;
  if (base !== "http://degoog:4444/api") throw new Error("Unexpected search endpoint");
  fetch(`${base}/search?format=json&q=Balmy%20Alley%20murals`, {signal: AbortSignal.timeout(10000)})
    .then(async response => {
      if (!response.ok) throw new Error(`Search HTTP ${response.status}`);
      const body = await response.json();
      if (!Array.isArray(body.results) || !body.results.length) throw new Error("No search results");
      console.log(JSON.stringify({endpoint: base, results: body.results.length}));
    }).catch(error => { console.error(error.message); process.exitCode = 1; });
'
```

Ask the Assistant a question requiring web search and verify the returned
sources. Audit any separately configured workflow search nodes before retiring
SearXNG; changing the Assistant endpoint does not rewrite workflows.

Degoog can exceed a client's deadline on an uncached query if an upstream
engine is slow. Cached success alone does not establish cold-query reliability.
Keep SearXNG available until the remaining consumers and timeout issue are
resolved. To roll back the Assistant endpoint, override
`n8n_instance_ai_searxng_url` with the still-running SearXNG service URL and
redeploy; keep database, encryption, and sandbox credentials unchanged.
