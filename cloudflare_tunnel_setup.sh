#!/bin/bash
# Cloudflare Tunnel Setup pre Synology

# 1. Stiahni cloudflared
cd /volume1/docker
wget -O cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod +x cloudflared

# 2. Login do Cloudflare
./cloudflared tunnel login

# 3. Vytvor tunnel
./cloudflared tunnel create erp-system

# 4. Nakonfiguruj routing (nahraď TUNNEL-UUID s UUID z kroku 3)
cat > config.yml << EOF
tunnel: TUNNEL-UUID
credentials-file: /volume1/docker/.cloudflared/TUNNEL-UUID.json

ingress:
  - hostname: erp.TVOJA-DOMENA.com
    service: http://localhost:8000
  - service: http_status:404
EOF

# 5. Pridaj DNS záznam v Cloudflare dashboarde:
# CNAME erp -> TUNNEL-UUID.cfargotunnel.com

# 6. Spusti tunnel
./cloudflared tunnel --config config.yml run erp-system
