# Vane

Vane is parked on `nuc-mini` using the existing `utilities_vane-data` volume.
Its private image is built by the Vane GitLab project. The role preserves
PocketID OIDC configuration and the shared session secret.

## Parked deployment

`vane_enabled: false` is the default. The role renders the preserved service
behind the `vane` Compose profile with `restart: "no"` and
`traefik.enable: "false"`, stops its existing container, and disables that
container's restart policy. It retains the image, environment file, PocketID
client, session secret, data volume, saved settings, and application data.
Routine Ansible deployments keep it stopped. A first deployment while disabled
does not create the application container.

The Komodo Stack remains registered for recovery with automatic pulls and
alerts disabled, the stopped service ignored for status, and `--no-start` for
deployment requests. Default Compose commands also exclude the parked profile.
The Vane availability check is removed from Gatus. The exact
`vane.atelier.house` DNS address record is removed separately in Cloudflare;
DDClient does not manage or recreate that hostname. Local wildcard DNS may
still resolve the name, but Traefik must not route it to Vane.

Apply the parked state with `make deploy-vane`. Verify the existing container
is stopped, its restart policy is `no`, `utilities_vane-data` still exists,
and the Vane host no longer has an application route. Do not run Compose
`down`, remove the container, or delete the volume to park it.

To re-enable:

1. Restore the exact DNS record for `vane.atelier.house` and restore its Gatus
   check if availability monitoring is wanted.
2. Set `vane_enabled: true` in the deployment variables and run
   `make deploy-vane`. This restores the configured restart policy and Docker
   routing labels; the existing external data volume is reused.
3. Remove `--no-start` and the parked status overrides from the Komodo Stack
   declaration and synchronize them before resuming CI-triggered deployments.
4. Verify PocketID sign-in and saved application settings before use.

The historical Degoog cutover below applies when Vane is enabled.

## Web search through Degoog

`vane_searxng_url` defaults to `http://degoog:4444/api`. Vane's SearXNG client
appends `/search?format=json`, so this reaches Degoog's native JSON search.
Vane and Degoog share `proxy-network` on `nuc-mini`; the public Degoog URL
requires TinyAuth and must not be used as the backend endpoint.
See the [Degoog runbook](../degoog/README.md).

After the change is merged:

1. With `vane_enabled: true`, run `make deploy-vane` to update `SEARXNG_API_URL` and recreate Vane.
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
