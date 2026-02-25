# ===================================================================
# ERP System - Docker Deployment na Synology NAS
# ===================================================================

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  ERP System - Docker Deploy na NAS" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$NAS_IP = "192.168.1.94"
$NAS_USER = "Marek"
$NAS_PATH = "/volume1/docker/erp_docker"

# ===================================================================
# Krok 1: Príprava lokálnych súborov
# ===================================================================
Write-Host "[1/6] Git commit a push zmien..." -ForegroundColor Yellow
git add . 2>$null
git commit -m "Docker deployment configuration for Synology NAS" 2>$null
git push origin main 2>$null
Write-Host "OK - Zmeny pushnuté na GitHub" -ForegroundColor Green

# ===================================================================
# Krok 2: Vytvorenie adresára na NAS
# ===================================================================
Write-Host ""
Write-Host "[2/6] Vytvorenie adresára na NAS..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} "mkdir -p $NAS_PATH && echo 'Adresar pripraveny'"

# ===================================================================
# Krok 3: Git clone projektu
# ===================================================================
Write-Host ""
Write-Host "[3/6] Git clone z GitHubu..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} 'cd /volume1/docker && rm -rf erp_docker && git clone https://github.com/smarek830/erp_system.git erp_docker'

# ===================================================================
# Krok 4: Export databázy z PC
# ===================================================================
Write-Host ""
Write-Host "[4/6] Export databazy..." -ForegroundColor Yellow
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.Permission -e sessions --indent 2 > data_docker.json 2>&1
if (Test-Path data_docker.json) {
    $size = (Get-Item data_docker.json).Length
    Write-Host "OK - Databaza exportovana ($size bytes)" -ForegroundColor Green
}

# ===================================================================
# Krok 5: Prenos dát na NAS
# ===================================================================
Write-Host ""
Write-Host "[5/6] Prenos dat na NAS..." -ForegroundColor Yellow
$content = Get-Content data_docker.json -Encoding UTF8 -Raw
$content | ssh ${NAS_USER}@${NAS_IP} "cat > $NAS_PATH/data_docker.json"
Write-Host "OK - Fixtures prenesene" -ForegroundColor Green

# ===================================================================
# Krok 6: Backup DB + Docker Compose Build & Deploy
# ===================================================================
Write-Host ""
Write-Host "[6/6] Backup DB, Docker build a spustenie..." -ForegroundColor Yellow
Write-Host "  -> Backup SQLite databazy..." -ForegroundColor Gray
ssh ${NAS_USER}@${NAS_IP} "cd $NAS_PATH && docker-compose exec -T web sh -c 'mkdir -p /data/backups && if [ -f /data/db.sqlite3 ]; then cp /data/db.sqlite3 /data/backups/db_`$(date +%Y%m%d_%H%M%S).sqlite3 && echo Backup hotovy; else echo Databaza este neexistuje; fi' || true"

Write-Host "  -> Zastavenie starych kontajnerov..." -ForegroundColor Gray
ssh ${NAS_USER}@${NAS_IP} "cd $NAS_PATH && docker-compose down 2>/dev/null || true"

Write-Host "  -> Build Docker image..." -ForegroundColor Gray
ssh ${NAS_USER}@${NAS_IP} "cd $NAS_PATH && docker-compose build"

Write-Host "  -> Spustenie kontajnera..." -ForegroundColor Gray  
ssh ${NAS_USER}@${NAS_IP} "cd $NAS_PATH && docker-compose up -d"

Write-Host "  -> Cakanie na start..." -ForegroundColor Gray
Start-Sleep -Seconds 10

Write-Host "  -> Import databazy..." -ForegroundColor Gray
ssh ${NAS_USER}@${NAS_IP} "cd $NAS_PATH && docker-compose exec -T web python manage.py loaddata data_docker.json || echo 'Import zlyhal - databaza prazdna'"

Write-Host "  -> Status kontajnera..." -ForegroundColor Gray
ssh ${NAS_USER}@${NAS_IP} "cd $NAS_PATH && docker-compose ps"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  OK - Docker deployment dokonceny!" -ForegroundColor Green
Write-Host "  -> Backupy DB: /data/backups (volume erp_db)" -ForegroundColor Green
Write-Host "  -> Aplikacia: http://${NAS_IP}:8000" -ForegroundColor Green
Write-Host "  -> Admin: http://${NAS_IP}:8000/admin/login/" -ForegroundColor Green
Write-Host ""
Write-Host "  Prikazy na spravu:" -ForegroundColor Yellow
Write-Host "  - Status:  ssh ${NAS_USER}@${NAS_IP} 'cd $NAS_PATH && docker-compose ps'" -ForegroundColor Gray
Write-Host "  - Logy:    ssh ${NAS_USER}@${NAS_IP} 'cd $NAS_PATH && docker-compose logs -f'" -ForegroundColor Gray
Write-Host "  - Restart: ssh ${NAS_USER}@${NAS_IP} 'cd $NAS_PATH && docker-compose restart'" -ForegroundColor Gray
Write-Host "  - Stop:    ssh ${NAS_USER}@${NAS_IP} 'cd $NAS_PATH && docker-compose down'" -ForegroundColor Gray
Write-Host "============================================================" -ForegroundColor Green
