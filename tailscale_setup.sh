#!/bin/bash
# Tailscale setup pre Synology NAS

# 1. Stiahni Tailscale
cd /tmp
wget https://pkgs.tailscale.com/stable/tailscale_1.58.2_amd64.tgz
tar xzf tailscale_1.58.2_amd64.tgz
cd tailscale_1.58.2_amd64

# 2. Spusti daemon
sudo ./tailscaled --state=/volume1/docker/tailscale.state &

# 3. Pripoj sa (otvorí sa odkaz v prehliadači)
sudo ./tailscale up

# Poznač si Tailscale IP (napr. 100.64.1.5)
./tailscale ip -4

echo "✓ Tailscale nastavený!"
echo "Pripojiť sa môžeš z mobilu cez: http://TAILSCALE-IP:8000"
echo "Nainštaluj Tailscale app na mobile a prihlás sa rovnakým účtom"
