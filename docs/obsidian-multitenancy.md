# Multi-Tenant Obsidian Setup

## Overview

This document outlines approaches for implementing multi-tenant Obsidian with single-URL access, where multiple users can access their own vaults through `notes.atelier.house` with authentication-based routing.

## The Challenge

The linuxserver.io Obsidian Docker image doesn't support native multi-tenancy. Each container instance is designed for a single user. However, we can achieve multi-user support by:

1. Running multiple Obsidian container instances (one per user)
2. Using authentication-aware routing to direct users to their specific container
3. Presenting a single URL to all users

## Architecture Options

### Option 1: Traefik Multi-Layer Routing ⭐ (Recommended)

**Best fit for:** Existing Traefik-based homelab setups

**How it works:**
1. **PocketID/TinyAuth/Authelia** authenticates the user
2. **oauth2-proxy** or ForwardAuth middleware injects user identity into headers (e.g., `X-Forwarded-User: alice`)
3. **Traefik child routers** route to different Obsidian containers based on the header value
4. All users access via `notes.atelier.house`

**Example Traefik Configuration:**

```yaml
services:
  # Obsidian instance for Alice
  obsidian-alice:
    container_name: obsidian-alice
    image: lscr.io/linuxserver/obsidian:latest
    volumes:
      - obsidian-alice-config:/config
    environment:
      - PUID=977
      - PGID=988
      - TZ=America/Los_Angeles
    labels:
      # Parent router - handles base routing
      traefik.http.routers.obsidian-alice.rule: "Host(`notes.atelier.house`) && HeadersRegexp(`X-Forwarded-User`, `alice`)"
      traefik.http.routers.obsidian-alice.entrypoints: "websecure"
      traefik.http.routers.obsidian-alice.tls.certresolver: "letsencrypt"
      traefik.http.routers.obsidian-alice.middlewares: "authelia@docker"
      traefik.http.services.obsidian-alice.loadbalancer.server.port: "3000"

  # Obsidian instance for Bob
  obsidian-bob:
    container_name: obsidian-bob
    image: lscr.io/linuxserver/obsidian:latest
    volumes:
      - obsidian-bob-config:/config
    environment:
      - PUID=977
      - PGID=988
      - TZ=America/Los_Angeles
    labels:
      traefik.http.routers.obsidian-bob.rule: "Host(`notes.atelier.house`) && HeadersRegexp(`X-Forwarded-User`, `bob`)"
      traefik.http.routers.obsidian-bob.entrypoints: "websecure"
      traefik.http.routers.obsidian-bob.tls.certresolver: "letsencrypt"
      traefik.http.routers.obsidian-bob.middlewares: "authelia@docker"
      traefik.http.services.obsidian-bob.loadbalancer.server.port: "3000"
```

**Pros:**
- ✅ Works with existing Traefik setup
- ✅ Compatible with PocketID, TinyAuth, or Authelia
- ✅ No additional services needed
- ✅ Native Traefik feature
- ✅ Easy to add/remove users

**Cons:**
- ⚠️ Requires manual configuration for each new user
- ⚠️ Header-based routing needs to be supported by auth provider

### Option 2: Pomerium Identity-Aware Proxy

**Best fit for:** Greenfield deployments or if replacing existing auth

**How it works:**
1. **Pomerium** handles both authentication AND routing
2. Policy files define which users can access which backend containers
3. Single URL: `notes.atelier.house`
4. Built-in identity provider integration (Google, GitHub, etc.)

**Example Pomerium Configuration:**

```yaml
# pomerium-config.yaml
authenticate_service_url: https://auth.atelier.house

routes:
  - from: https://notes.atelier.house
    to: http://obsidian-alice:3000
    policy:
      - allow:
          and:
            - email:
                is: alice@atelier.house

  - from: https://notes.atelier.house
    to: http://obsidian-bob:3000
    policy:
      - allow:
          and:
            - email:
                is: bob@atelier.house
```

**Pros:**
- ✅ Purpose-built for identity-aware routing
- ✅ Simple policy-based configuration
- ✅ Supports complex authorization rules
- ✅ Well-documented and maintained
- ✅ Supports device trust, location-based policies

**Cons:**
- ⚠️ Replaces existing auth setup (Traefik ForwardAuth)
- ⚠️ Additional service to manage
- ⚠️ Learning curve for policy syntax

### Option 3: Custom Middleware Proxy

**Best fit for:** Custom requirements or learning opportunities

**How it works:**
1. Build a lightweight proxy service (Go/Node.js/Python)
2. Service sits behind PocketID/TinyAuth authentication
3. Reads authenticated user from headers
4. Proxies requests to appropriate Obsidian container

**Example Architecture:**

```
User → Traefik → PocketID/TinyAuth → Custom Proxy → Obsidian Container (User-Specific)
                     (Auth)              (Routing Logic)
```

**Pseudocode:**

```javascript
app.use(async (req, res) => {
  const user = req.headers['x-forwarded-user'];
  const targetHost = `http://obsidian-${user}:3000`;

  // Proxy request to user-specific container
  proxy(req, res, targetHost);
});
```

**Pros:**
- ✅ Full control over routing logic
- ✅ Can add custom features (usage metrics, quotas, etc.)
- ✅ Works with any auth provider that sets headers

**Cons:**
- ⚠️ Requires custom development and maintenance
- ⚠️ Additional service to deploy and monitor
- ⚠️ Potential single point of failure

## Implementation Considerations

### Per-User Resources

Each user needs:
- Dedicated Obsidian container
- Dedicated volume for `/config` storage
- Unique container name
- Optional: Resource limits (CPU/memory)

### Authentication Provider Setup

Ensure your auth provider (PocketID/TinyAuth/Authelia) is configured to:
1. Pass user identity in HTTP headers
2. Common header names:
   - `X-Forwarded-User`
   - `Remote-User`
   - `X-Auth-Request-User`
3. Verify header format matches your routing rules

### User Management

Consider:
- **Onboarding:** Automate container creation for new users (Ansible playbook)
- **Offboarding:** Clean up containers and volumes for removed users
- **Backup:** Per-user vault backups
- **Monitoring:** Track per-user resource usage

### Security Considerations

- Ensure authentication is properly configured (no bypass routes)
- Use HTTPS/TLS for all connections
- Isolate user containers (no shared volumes)
- Regular security updates for Obsidian containers
- Consider network policies to prevent container-to-container access

## Alternative: Subdomain-Based Multi-Tenancy

If single-URL routing proves complex, consider subdomain-based access:

- `alice.notes.atelier.house` → obsidian-alice
- `bob.notes.atelier.house` → obsidian-bob

**Pros:**
- Simpler routing configuration
- Still uses authentication
- Easier troubleshooting

**Cons:**
- Multiple DNS entries required
- Not a "single URL" solution

## Next Steps

When ready to implement:

1. Choose an approach based on your requirements
2. Update Ansible productivity role to support multiple users
3. Configure authentication provider for header forwarding
4. Set up routing rules (Traefik/Pomerium)
5. Test with a couple of users before full rollout
6. Document user onboarding process

## References

- [Pocket ID GitHub](https://github.com/pocket-id/pocket-id)
- [Securing with oauth2-proxy](https://thesynack.com/posts/securing-with-oauth2-proxy/)
- [TinyAuth Documentation](https://tinyauth.app/docs/getting-started/)
- [Traefik Multi-Layer Routing](https://doc.traefik.io/traefik/reference/routing-configuration/http/routing/multi-layer-routing/)
- [Traefik ForwardAuth Middleware](https://doc.traefik.io/traefik/reference/routing-configuration/http/middlewares/forwardauth/)
- [Pomerium Documentation](https://www.pomerium.com/docs)
- [Authelia Traefik Integration](https://www.authelia.com/integration/proxies/traefik/)
- [linuxserver.io Obsidian Documentation](https://docs.linuxserver.io/images/docker-obsidian/)

---

*Last updated: 2026-02-06*
