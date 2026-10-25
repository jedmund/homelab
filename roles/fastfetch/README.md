# fastfetch

Installs [fastfetch](https://github.com/fastfetch-cli/fastfetch) on every
`compute_servers` host so each machine can print the same system summary:

```sh
fastfetch
```

| OS family | Source | Version |
| --- | --- | --- |
| Debian (Ubuntu) | Upstream release `.deb` | `fastfetch_version` |
| Archlinux (CachyOS) | pacman | Distribution package |
| Darwin | Homebrew | Formula |

Ubuntu 24.04 has no fastfetch package, so Ubuntu hosts install the pinned
upstream release instead of mixing apt versions across hosts. Bump
`fastfetch_version` in `defaults/main.yml` to upgrade them. The role does
not upgrade the pacman or Homebrew package; those follow normal system
updates.

Deploy with `make deploy-fastfetch`. Hosts that are off (`gaming-pc`) or
unreachable report as unreachable; rerun with
`make deploy-limit HOST=<host> PLAYBOOK=deploy/fastfetch.yml` later.
Other OS families fail the play.
