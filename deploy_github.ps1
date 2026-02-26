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
$NAS_ENV = "export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

Write-Host "[1/6] Update kódu bez mazania dát..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} "$NAS_ENV; if [ -d ${NAS_PATH}/.git ]; then cd ${NAS_PATH}; git fetch origin main; git reset --hard origin/main; echo 'Kód aktualizovaný cez git'; else mkdir -p /volume1/docker; git clone ${GITHUB_REPO} ${NAS_PATH}; echo 'Kód naklonovaný z GitHubu'; fi"

Write-Host ""
Write-Host "[2/6] Príprava perzistentnej databázy..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} "$NAS_ENV; mkdir -p ${NAS_BACKUP_PATH}; if [ -f ${NAS_PATH}/db.sqlite3 ] && [ ! -f ${NAS_DB_PATH} ]; then cp ${NAS_PATH}/db.sqlite3 ${NAS_DB_PATH}; echo 'Legacy db.sqlite3 presunutá do perzistentného priečinka'; fi; echo 'Perzistentná DB cesta: ${NAS_DB_PATH}'"

Write-Host ""
Write-Host "[3/6] Backup databázy pred aktualizáciou..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} "$NAS_ENV; if [ -f ${NAS_DB_PATH} ]; then cp ${NAS_DB_PATH} ${NAS_BACKUP_PATH}/db_`$(date +%Y%m%d_%H%M%S).sqlite3; echo 'Backup vytvorený v ${NAS_BACKUP_PATH}'; else echo 'Databáza ešte neexistuje - prvé nasadenie'; fi"

Write-Host ""
Write-Host "[4/6] Kontrola Python a závislostí..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} "$NAS_ENV; cd ${NAS_PATH}; echo '=== Python verzia ==='; PYV=`$(python3 --version 2>/dev/null || python --version 2>/dev/null || echo 'Python 0.0'); echo \"`$PYV\"; case \"`$PYV\" in Python\ 3.1[0-9]*|Python\ 4*) : ;; *) echo 'CHYBA: Python na NAS je príliš starý pre Django 5.2 (minimum 3.10).'; echo 'Riešenie: použi Docker deploy (.\\deploy_docker_nas.ps1) alebo nainštaluj Python >= 3.10.'; exit 1 ;; esac; if [ ! -d venv ]; then echo '=== Vytvorenie virtualenv ==='; python3 -m venv venv; fi"

Write-Host ""
Write-Host "[5/6] Inštalácia závislostí..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} "$NAS_ENV; cd ${NAS_PATH}; . venv/bin/activate; pip install --upgrade pip; pip install -r requirements.txt; echo 'Závislosti nainštalované'"

Write-Host ""
Write-Host "[6/6] Migrácie a štart servera s perzistentnou DB..." -ForegroundColor Yellow
ssh ${NAS_USER}@${NAS_IP} "$NAS_ENV; cd ${NAS_PATH}; . venv/bin/activate; export SQLITE_PATH=${NAS_DB_PATH}; python manage.py migrate; pkill -f 'manage.py runserver 0.0.0.0:8000' 2>/dev/null || true; nohup python manage.py runserver 0.0.0.0:8000 > runserver.log 2>&1 &; echo 'Server beží na http://${NAS_IP}:8000'"

Write-Host ""
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Deployment dokončený bez straty dát" -ForegroundColor Green
Write-Host "  DB cesta: ${NAS_DB_PATH}" -ForegroundColor Green
Write-Host "  Backupy: ${NAS_BACKUP_PATH}" -ForegroundColor Green
Write-Host "  Aplikácia beží na: http://${NAS_IP}:8000" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Green
