# homelab
Configuration for my Homelab server. 

### Hardware
- Mac mini M1 16GB (soon to be upgraded)
- 4K HDMI dummy plug ([Product link](https://www.amazon.com/gp/product/B07FB8GJ1Z]))

### Software

**[Automounter](https://pixeleyes.co.nz/automounter/)**

Automounter will automatically mount your network drives on boot and whenever they disconnect

**[OrbStack](https://orbstack.dev/)**

OrbStack is a more sane Mac client than Docker Desktop—I tried using a CLI-only solution with [Colima](https://github.com/abiosoft/colima) but ran into issues. I will probably try again since having an app running is annoying.

**[VMWare Fusion](https://www.vmware.com/products/desktop-hypervisor/workstation-and-fusion)**

This is only necessary if you want to run [HomeAssistant](https://www.home-assistant.io/). It's free, but getting a license key was very annoying. I tried using [UTM](https://mac.getutm.app/) but was having a hard time with macOS NFS volumes.

### Containers

#### management.yaml

**[nginx-proxy-manager](https://github.com/NginxProxyManager/nginx-proxy-manager)**

Nginx Proxy Manager is a reverse proxy for if you want external access, or just easier internal access. Put simply, it routes your domain name to the right place. You will need to set up the DNS for your domain name to point to your Dynamic DNS or IP address, and in your router, you will still need to forward the necessary ports to the server's local IP.

**[ddclient](https://ddclient.net/)**

ddclient automatically updates your Dynamic DNS with your current external IP address. You can choose what service you want to use and there are many. I use Cloudflare.

#### automation.yaml
**[jesec/rtorrent-flood](https://hub.docker.com/r/jesec/rtorrent-flood)**

A combined package of [rtorrent](https://github.com/rakshasa/rtorrent) and [Flood](https://flood.js.org/).

**Servarr**

See the [Servarr Wiki](https://wiki.servarr.com/) for more info

- **Prowlarr**: Configure sources
- **Sonarr**: TV Show management
- **Radarr**: Movie management 
- **Lidarr**: Music management
- **Overseerr**: Simple account-based request interface
