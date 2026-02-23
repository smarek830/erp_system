# ===================================================================
# ERP System - GitHub Deployment na Synology NAS
# ===================================================================

Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  ERP System - Čistý štart z GitHubu" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

$NAS_IP = "192.168.1.94"
$NAS_USER = "Marek"
$GITHUB_REPO = "https://github.com/smarek830/erp_system.git"
$NAS_PATH = "/volume1/docker/erp"

Write-Host "[1/5] Vyčistenie starého adresára..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} "cd /volume1/docker && rm -rf erp && mkdir -p erp && echo 'Adresár vyčistený'"

Write-Host ""
Write-Host "[2/5] Git clone z GitHubu..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} "cd /volume1/docker && git clone ${GITHUB_REPO} erp && echo 'Kód stiahnutý z GitHubu'"

Write-Host ""
Write-Host "[3/5] Kontrola Python a závislostí..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} @"
cd ${NAS_PATH}
echo '=== Python verzia ==='
python3 --version || python --version
echo ''
echo '=== Vytvorenie virtualenv ==='
python3 -m venv venv 2>/dev/null || python -m venv venv 2>/dev/null || echo 'Venv sa nepodarilo vytvoriť - pokračujem bez neho'
echo ''
"@

Write-Host ""
Write-Host "[4/5] Inštalácia závislostí..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} @"
cd ${NAS_PATH}
if [ -d venv ]; then
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    pip3 install -r requirements.txt || pip install -r requirements.txt
fi
echo 'Závislosti nainštalované'
"@

Write-Host ""
Write-Host "[5/5] Migrácie a spustenie servera..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} @"
cd ${NAS_PATH}
if [ -d venv ]; then
    source venv/bin/activate
fi
python3 manage.py migrate || python manage.py migrate
echo ''
echo '════════════════════════════════════════════════════════'
echo '  Server sa spúšťa na http://${NAS_IP}:8000'
echo '════════════════════════════════════════════════════════'
echo ''
python3 manage.py runserver 0.0.0.0:8000 || python manage.py runserver 0.0.0.0:8000
"@

Write-Host ""
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Deployment dokončený!" -ForegroundColor Green
Write-Host "  Aplikácia beží na: http://${NAS_IP}:8000" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Green
