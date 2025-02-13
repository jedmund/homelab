# homelab
Configuration for my Homelab server. Currently running on a Mac mini M1.

I set things up with the following programs:
- [Automounter](https://pixeleyes.co.nz/automounter/)
  Automounter will automatically mount your network drives on boot and whenever they disconnect
- [OrbStack](https://orbstack.dev/)
  OrbStack is a more sane Mac client than Docker Desktop—I tried using a CLI-only solution with [Colima](https://github.com/abiosoft/colima) but ran into issues. I will probably try again.

### management.yaml

- [nginx-proxy-manager](https://github.com/NginxProxyManager/nginx-proxy-manager)
  Nginx Proxy Manager is a reverse proxy that will route your domain names to different services. You will need to set up the DNS for your domain name to point to your Dynamic DNS or IP address, and in your router, you will still need to forward the necessary ports to the server's local IP.
- [ddclient](https://ddclient.net/)
  ddclient automatically updates your Dynamic DNS with your current external IP address. You can choose what service you want to use and there are many. I use Cloudflare.

### automation.yaml
- [jesec/rtorrent-flood](https://hub.docker.com/r/jesec/rtorrent-flood)
  A combined package of [rtorrent](https://github.com/rakshasa/rtorrent) and [Flood](https://flood.js.org/).
- prowlarr
- sonarr
- radarr
- lidarr
- overseer

See the [Servarr Wiki](https://wiki.servarr.com/) for more info
