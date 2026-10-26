# Vane

Vane runs on `nuc-mini` using the existing `utilities_vane-data` volume.
Its private image is built by the Vane GitLab project. The role preserves
PocketID OIDC configuration and the shared session secret.

## Web search through Degoog

`vane_searxng_url` defaults to `http://degoog:4444/api`. Vane's SearXNG client
appends `/search?format=json`, so this reaches Degoog's native JSON search.
Vane and Degoog share `proxy-network` on `nuc-mini`; the public Degoog URL
requires TinyAuth and must not be used as the backend endpoint.
See the [Degoog runbook](../degoog/README.md).

After the change is merged:

1. Run `make deploy-vane` to update `SEARXNG_API_URL` and recreate Vane.
2. Sign in as a Vane administrator and open Settings → Search. Set **SearXNG URL** to
   `http://degoog:4444/api` and save. Existing installations must perform this
   step: the environment only seeds an empty `search.searxngURL` in
   `/home/vane/data/config.json`. A non-empty saved value wins after restart.
   The role does not overwrite application-managed settings.
3. Verify the environment and saved value without printing the rest of the
   configuration, which can contain credentials:

   ```sh
   docker exec vane node -e '
     const fs = require("fs");
     const config = JSON.parse(fs.readFileSync("/home/vane/data/config.json", "utf8"));
     const env = process.env.SEARXNG_API_URL;
     const saved = config.search.searxngURL;
     if (env !== "http://degoog:4444/api" || saved !== env) throw new Error("Search endpoint mismatch");
     fetch(`${saved}/search?format=json&q=Balmy%20Alley%20murals`, {signal: AbortSignal.timeout(10000)})
       .then(async response => {
         if (!response.ok) throw new Error(`Search HTTP ${response.status}`);
         const body = await response.json();
         if (!Array.isArray(body.results) || !body.results.length) throw new Error("No search results");
         console.log(JSON.stringify({environment: env, saved, results: body.results.length}));
       }).catch(error => { console.error(error.message); process.exitCode = 1; });
   '
   ```

4. Run a web search in Vane and verify source links. Redeploy and confirm the
   saved URL still points at Degoog. Vane is a legacy consumer; image/video
   compatibility remains separate application work after the shared
   [SearXNG retirement](../ai/README.md#retire-the-shared-searxng-service).

### Media compatibility

This endpoint change covers web results. Vane's image agent sends SearXNG
engine names and reads `img_src`; its video agent also requires `iframe_src`.
Degoog's native JSON uses `imageUrl`, and its optional SearXNG-shaped output
always leaves `iframe_src` empty. Enabling that output alone does not complete
the media migration. Vane needs an application adapter for Degoog search types,
media fields, and proxy URLs before image/video parity can be verified.
The legacy media features remain outside this web-search cutover.

Vane's search client has a 10-second deadline. Degoog's slow upstream engines
can exceed that deadline on uncached queries. The environment change and
saved-setting update do not change the client deadline.

To roll back after SearXNG retirement, first restore and verify the AI service,
then restore its URL in both `vane_searxng_url` and Settings → Search and
redeploy. Preserve the existing data volume, OIDC credentials, and session
secret.
