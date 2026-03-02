# ===================================================================
# ERP System - GitHub Docker deployment na Synology NAS
# ===================================================================

$ErrorActionPreference = 'Stop'

Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  ERP System - Docker update z GitHubu" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

$NAS_IP = "192.168.1.94"
$NAS_USER = "Marek"
$GITHUB_REPO = "https://github.com/smarek830/erp_system.git"
$NAS_PATH = "/volume1/docker/erp"
$NAS_ENV = "export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

function Invoke-NasCommand {
	param(
		[Parameter(Mandatory=$true)][string]$Command,
		[Parameter(Mandatory=$true)][string]$StepName
	)

	ssh ${NAS_USER}@${NAS_IP} $Command
	if ($LASTEXITCODE -ne 0) {
		throw "Krok '$StepName' zlyhal (exit code: $LASTEXITCODE)."
	}
}

try {

Write-Host "[1/6] Update kódu bez mazania dát..." -ForegroundColor Yellow
Invoke-NasCommand "$NAS_ENV; if [ -d ${NAS_PATH}/.git ]; then cd ${NAS_PATH}; git fetch origin main; git reset --hard origin/main; echo 'Kód aktualizovaný cez git'; else mkdir -p /volume1/docker; git clone ${GITHUB_REPO} ${NAS_PATH}; echo 'Kód naklonovaný z GitHubu'; fi" "Update kódu"

Write-Host ""
Write-Host "[2/6] Kontrola Docker prostredia..." -ForegroundColor Yellow
Invoke-NasCommand "$NAS_ENV; docker --version; docker compose version" "Kontrola Docker prostredia"

Write-Host ""
Write-Host "[3/6] Backup databázy pred aktualizáciou..." -ForegroundColor Yellow
Invoke-NasCommand "$NAS_ENV; cd ${NAS_PATH}; docker compose exec -T web sh -c 'mkdir -p /data/backups && if [ -f /data/db.sqlite3 ]; then cp /data/db.sqlite3 /data/backups/db_`$(date +%Y%m%d_%H%M%S).sqlite3 && echo Backup hotovy; else echo Databaza este neexistuje; fi' || echo 'Backup preskočený (prvé nasadenie alebo kontajner nebeží)'" "Backup databázy"

Write-Host ""
Write-Host "[4/6] Zastavenie starých kontajnerov..." -ForegroundColor Yellow
Invoke-NasCommand "$NAS_ENV; cd ${NAS_PATH}; docker compose down 2>/dev/null || true" "Zastavenie kontajnerov"

Write-Host ""
Write-Host "[5/6] Docker build a štart..." -ForegroundColor Yellow
Invoke-NasCommand "$NAS_ENV; cd ${NAS_PATH}; docker compose build && docker compose up -d" "Docker build a štart"

Write-Host ""
Write-Host "[6/6] Kontrola stavu kontajnera..." -ForegroundColor Yellow
Invoke-NasCommand "$NAS_ENV; cd ${NAS_PATH}; docker compose ps; echo ''; docker compose logs --tail=20 web" "Kontrola kontajnera"

Write-Host ""
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Docker deployment dokončený" -ForegroundColor Green
Write-Host "  Aplikácia beží na: http://${NAS_IP}:8000" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Green

} catch {
	Write-Host "" 
	Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Red
	Write-Host "  Deployment zlyhal" -ForegroundColor Red
	Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
	Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Red
	exit 1
}
