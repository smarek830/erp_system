#!/bin/bash

# ====================================================
# Deployment script pre ERP System na NAS
# Spustenie: bash deploy.sh
# ====================================================

set -e

echo "🚀 Spúšťanie deployment ERP System na NAS..."
echo "================================================"

# Zastavenie starej verzie
echo "⏹️  Zastavenie starej verzie..."
docker-compose down || true

# Build nového image
echo "🔨 Building Docker image..."
docker-compose build --no-cache

# Spustenie kontajnera
echo "🏃 Spúšťanie kontajnera..."
docker-compose up -d

# Čakanie na spustenie servera
echo "⏳ Čakanie na spustenie aplikácie..."
sleep 5

# Migrácii databázy
echo "🗄️  Migrácia databázy..."
docker-compose exec -T web python manage.py migrate

# Zbieranie static files
echo "📦 Zbieranie statických súborov..."
docker-compose exec -T web python manage.py collectstatic --noinput || true

# Vytvorenie superuser (voliteľné)
# docker-compose exec -T web python manage.py createsuperuser --noinput --username admin --email admin@example.com

echo ""
echo "================================================"
echo "✅ Deployment hotový!"
echo "================================================"
echo ""
echo "📍 Aplikácia je dostupná na: http://192.168.1.94:8000"
echo "🔐 Admin panel: http://192.168.1.94:8000/admin"
echo ""
echo "Logy: docker-compose logs -f"
echo "Status: docker-compose ps"
