# Deployment script pre ERP System na NAS (PowerShell)
# Spustenie: .\deploy.ps1

Write-Host "🚀 Spúšťanie deployment ERP System na NAS..." -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan

# Zastavenie starej verzie
Write-Host "⏹️  Zastavenie starej verzie..." -ForegroundColor Yellow
docker-compose down 2>$null

# Build nového image
Write-Host "🔨 Building Docker image..." -ForegroundColor Yellow
docker-compose build --no-cache

# Spustenie kontajnera
Write-Host "🏃 Spúšťanie kontajnera..." -ForegroundColor Yellow
docker-compose up -d

# Čakanie na spustenie servera
Write-Host "⏳ Čakanie na spustenie aplikácie..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Migrácii databázy
Write-Host "🗄️  Migrácia databázy..." -ForegroundColor Yellow
docker-compose exec -T web python manage.py migrate

# Zbieranie static files
Write-Host "📦 Zbieranie statických súborov..." -ForegroundColor Yellow
docker-compose exec -T web python manage.py collectstatic --noinput 2>$null

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "✅ Deployment hotový!" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "📍 Aplikácia je dostupná na: http://192.168.1.94:8000" -ForegroundColor Cyan
Write-Host "🔐 Admin panel: http://192.168.1.94:8000/admin" -ForegroundColor Cyan
Write-Host ""
Write-Host "Príkazy:" -ForegroundColor Yellow
Write-Host "  Logy: docker-compose logs -f"
Write-Host "  Status: docker-compose ps"
Write-Host "  Restart: docker-compose restart"
