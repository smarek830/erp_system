# ===================================================================
# ERP System - GitHub Deployment na Synology NAS (bez straty dát)
# ===================================================================

Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  ERP System - Bezpečný update z GitHubu" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

$NAS_IP = "192.168.1.94"
$NAS_USER = "Marek"
$GITHUB_REPO = "https://github.com/smarek830/erp_system.git"
$NAS_PATH = "/volume1/docker/erp"
$NAS_DATA_PATH = "/volume1/docker/erp_data"
$NAS_DB_PATH = "${NAS_DATA_PATH}/db.sqlite3"
$NAS_BACKUP_PATH = "${NAS_DATA_PATH}/backups"

Write-Host "[1/6] Update kódu bez mazania dát..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} @"
if [ -d ${NAS_PATH}/.git ]; then
    cd ${NAS_PATH}
    git fetch origin main
    git reset --hard origin/main
    echo 'Kód aktualizovaný cez git'
else
    mkdir -p /volume1/docker
    git clone ${GITHUB_REPO} ${NAS_PATH}
    echo 'Kód naklonovaný z GitHubu'
fi
"@

Write-Host ""
Write-Host "[2/6] Príprava perzistentnej databázy..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} @"
mkdir -p ${NAS_BACKUP_PATH}
if [ -f ${NAS_PATH}/db.sqlite3 ] && [ ! -f ${NAS_DB_PATH} ]; then
    cp ${NAS_PATH}/db.sqlite3 ${NAS_DB_PATH}
    echo 'Legacy db.sqlite3 presunutá do perzistentného priečinka'
fi
echo 'Perzistentná DB cesta: ${NAS_DB_PATH}'
"@

Write-Host ""
Write-Host "[3/6] Backup databázy pred aktualizáciou..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} @"
if [ -f ${NAS_DB_PATH} ]; then
    cp ${NAS_DB_PATH} ${NAS_BACKUP_PATH}/db_`$(date +%Y%m%d_%H%M%S).sqlite3
    echo 'Backup vytvorený v ${NAS_BACKUP_PATH}'
else
    echo 'Databáza ešte neexistuje - prvé nasadenie'
fi
"@

Write-Host ""
Write-Host "[4/6] Kontrola Python a závislostí..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} @"
cd ${NAS_PATH}
echo '=== Python verzia ==='
python3 --version || python --version
echo ''
if [ ! -d venv ]; then
    echo '=== Vytvorenie virtualenv ==='
    python3 -m venv venv 2>/dev/null || python -m venv venv 2>/dev/null || echo 'Venv sa nepodarilo vytvoriť - pokračujem bez neho'
fi
echo ''
"@

Write-Host ""
Write-Host "[5/6] Inštalácia závislostí..." -ForegroundColor Yellow
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
Write-Host "[6/6] Migrácie a štart servera s perzistentnou DB..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} @"
cd ${NAS_PATH}
if [ -d venv ]; then
    source venv/bin/activate
fi
export SQLITE_PATH=${NAS_DB_PATH}
python3 manage.py migrate || python manage.py migrate
pkill -f 'manage.py runserver 0.0.0.0:8000' 2>/dev/null || true
nohup python3 manage.py runserver 0.0.0.0:8000 > runserver.log 2>&1 &
echo 'Server beží na http://${NAS_IP}:8000'
"@

Write-Host ""
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Deployment dokončený bez straty dát" -ForegroundColor Green
Write-Host "  DB cesta: ${NAS_DB_PATH}" -ForegroundColor Green
Write-Host "  Backupy: ${NAS_BACKUP_PATH}" -ForegroundColor Green
Write-Host "  Aplikácia beží na: http://${NAS_IP}:8000" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Green
