# ===================================================================
# ERP System - Docker Deployment na Synology NAS
# ===================================================================

Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  ERP System - Docker Deploy na NAS" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

$NAS_IP = "192.168.1.94"
$NAS_USER = "Marek"
$NAS_PATH = "/volume1/docker/erp_docker"

# ===================================================================
# Krok 1: Príprava lokálnych súborov
# ===================================================================
Write-Host "[1/6] Git commit a push zmien..." -ForegroundColor Yellow
git add .
git commit -m "Docker deployment configuration for Synology NAS" 2>$null
git push origin main 2>$null
Write-Host "✓ Zmeny pushnuté na GitHub" -ForegroundColor Green

# ===================================================================
# Krok 2: Vytvorenie adresára na NAS
# ===================================================================
Write-Host ""
Write-Host "[2/6] Vytvorenie adresára na NAS..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} @"
mkdir -p ${NAS_PATH}
cd ${NAS_PATH}
echo 'Adresár pripravený: ${NAS_PATH}'
"@

# ===================================================================
# Krok 3: Git clone projektu
# ===================================================================
Write-Host ""
Write-Host "[3/6] Git clone z GitHubu..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} @"
cd /volume1/docker
if [ -d erp_docker/.git ]; then
    cd erp_docker
    git pull
    echo 'Projekt aktualizovaný'
else
    rm -rf erp_docker
    git clone https://github.com/smarek830/erp_system.git erp_docker
    echo 'Projekt naklonovaný'
fi
"@

# ===================================================================
# Krok 4: Export databázy z PC
# ===================================================================
Write-Host ""
Write-Host "[4/6] Export databázy..." -ForegroundColor Yellow
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.Permission -e sessions --indent 2 > data_docker.json
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Databáza exportovaná ($(Get-Item data_docker.json | Select-Object -ExpandProperty Length) bytes)" -ForegroundColor Green
}

# ===================================================================
# Krok 5: Prenos dát na NAS
# ===================================================================
Write-Host ""
Write-Host "[5/6] Prenos dát na NAS..." -ForegroundColor Yellow
Get-Content data_docker.json -Encoding UTF8 -Raw | ssh ${NAS_USER}@${NAS_IP} "cat > ${NAS_PATH}/data_docker.json"
Write-Host "✓ Fixtures prenesené" -ForegroundColor Green

# ===================================================================
# Krok 6: Docker Compose Build & Deploy
# ===================================================================
Write-Host ""
Write-Host "[6/6] Docker build a spustenie..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} @"
cd ${NAS_PATH}

echo ''
echo '═══ Zastavenie starých kontajnerov ═══'
docker-compose down 2>/dev/null || true

echo ''
echo '═══ Build Docker image ═══'
docker-compose build

echo ''
echo '═══ Spustenie kontajnera ═══'
docker-compose up -d

echo ''
echo '═══ Čakanie na štart databázy ═══'
sleep 5

echo ''
echo '═══ Import dát ═══'
docker-compose exec -T web python manage.py loaddata data_docker.json

echo ''
echo '═══ Status kontajnera ═══'
docker-compose ps

echo ''
echo '════════════════════════════════════════════════════════'
echo '  ✓ ERP System beží na http://${NAS_IP}:8000'
echo '  ✓ Admin login: http://${NAS_IP}:8000/admin/login/'
echo '════════════════════════════════════════════════════════'
"@

Write-Host ""
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ✓ Docker deployment dokončený!" -ForegroundColor Green
Write-Host "  → Aplikácia: http://${NAS_IP}:8000" -ForegroundColor Green
Write-Host "  → Admin: http://${NAS_IP}:8000/admin/login/" -ForegroundColor Green
Write-Host ""
Write-Host "  Príkazy na správu:" -ForegroundColor Yellow
Write-Host "  - Status:  ssh ${NAS_USER}@${NAS_IP} 'cd ${NAS_PATH} && docker-compose ps'" -ForegroundColor Gray
Write-Host "  - Logy:    ssh ${NAS_USER}@${NAS_IP} 'cd ${NAS_PATH} && docker-compose logs -f'" -ForegroundColor Gray
Write-Host "  - Restart: ssh ${NAS_USER}@${NAS_IP} 'cd ${NAS_PATH} && docker-compose restart'" -ForegroundColor Gray
Write-Host "  - Stop:    ssh ${NAS_USER}@${NAS_IP} 'cd ${NAS_PATH} && docker-compose down'" -ForegroundColor Gray
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Green
