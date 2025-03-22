# Homelab Configuration

This repository documents the configuration of my Homelab server, including hardware, software, and containerized services.

---

### Table of Contents

- [Hardware](#hardware)
- [Software](#software)
  - [Plex Media Server](#plex-media-server)
  - [Automounter](#automounter)
  - [OrbStack](#orbstack)
  - [VMWare Fusion](#vmware-fusion)
- [Containers](#containers)
  - [Dockge](#dockge)
  - [Management (management.yaml)](#management-managementyaml)
    - [nginx-proxy-manager](#nginx-proxy-manager)
    - [ddclient](#ddclient)
  - [Automation (automation.yaml)](#automation-automationyaml)
    - [jesec/rtorrent-flood](#jesecrtorrent-flood)
    - [Servarr Suite](#servarr-suite)

---

### Hardware

- **Mac mini M4 24GB**
- **4K HDMI Dummy Plug**  
  [Product Link](https://www.amazon.com/gp/product/B07FB8GJ1Z)

---

### Software

#### Plex Media Server

- [Plex Media Server Download (macOS)](https://www.plex.tv/media-server-downloads/?cat=computer&plat=macos)  
  *I like Plex; others might prefer different solutions, but Plex works well for me.*

#### Automounter

- [Automounter](https://pixeleyes.co.nz/automounter/)  
  *Automatically mounts your network drives on boot and reconnects if they disconnect.*

#### OrbStack

- [OrbStack](https://orbstack.dev/)  
  *A more robust Mac client for Docker compared to Docker Desktop. I tried [Colima](https://github.com/abiosoft/colima) but ran into issues. I might revisit this option in the future.*

#### VMWare Fusion

- [VMWare Fusion](https://www.vmware.com/products/desktop-hypervisor/workstation-and-fusion)  
  *Necessary for running [HomeAssistant](https://www.home-assistant.io/). It's free, but acquiring a license key was challenging. I attempted [UTM](https://mac.getutm.app/), but experienced issues with macOS NFS volumes.*

---

### Containers

#### Dockge

- [Dockge](https://dockge.kuma.pet/)  
  *Manages all Docker containers through a single web interface. It allows you to manage processes, update packages, and edit configuration files.*  
  **Warning:** Do not expose this interface to the public.

---

#### Management (management.yaml)

##### nginx-proxy-manager

- [Nginx Proxy Manager](https://github.com/NginxProxyManager/nginx-proxy-manager)  
  *Acts as a reverse proxy for easier external/internal access. It routes your domain name to the correct service.*  
  **Setup Notes:**  
  - Configure your domain's DNS to point to your Dynamic DNS or external IP address.
  - Forward the necessary ports in your router to the server's local IP.

##### ddclient

- [ddclient](https://ddclient.net/)  
  *Automatically updates your Dynamic DNS with your current external IP address. Supports various services (I use Cloudflare).*

---

#### Automation (automation.yaml)

##### jesec/rtorrent-flood

- [jesec/rtorrent-flood](https://hub.docker.com/r/jesec/rtorrent-flood)  
  *A combined package of [rtorrent](https://github.com/rakshasa/rtorrent) and [Flood](https://flood.js.org/), providing an efficient torrent management solution.*

##### Servarr Suite

Refer to the [Servarr Wiki](https://wiki.servarr.com/) for more details on each component:

- **Prowlarr:** Source configuration
- **Sonarr:** TV show management
- **Radarr:** Movie management
- **Lidarr:** Music management
- **Overseerr:** Account-based request interface

---
