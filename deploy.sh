#!/bin/sh

# ====================================================
# Deployment script pre ERP System na NAS
# Spustenie: sh deploy.sh
# ====================================================

set -e

# Ensure common Synology binary paths are available
PATH="/usr/local/bin:/var/packages/ContainerManager/target/usr/bin:$PATH"

COMPOSE_STYLE=""
COMPOSE_BIN=""

if command -v docker-compose >/dev/null 2>&1; then
	COMPOSE_STYLE="standalone"
	COMPOSE_BIN="$(command -v docker-compose)"
elif command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
	COMPOSE_STYLE="plugin"
elif [ -x "/usr/local/bin/docker-compose" ]; then
	COMPOSE_STYLE="standalone"
	COMPOSE_BIN="/usr/local/bin/docker-compose"
elif [ -x "/var/packages/ContainerManager/target/usr/bin/docker-compose" ]; then
	COMPOSE_STYLE="standalone"
	COMPOSE_BIN="/var/packages/ContainerManager/target/usr/bin/docker-compose"
else
	echo "❌ Docker Compose nebol nájdený." >&2
	echo "   Skontrolujte, či je nainštalovaný Synology Container Manager." >&2
	exit 1
fi

compose() {
	if [ "$COMPOSE_STYLE" = "plugin" ]; then
		docker compose "$@"
	else
		"$COMPOSE_BIN" "$@"
	fi
}

echo "🚀 Spúšťanie deployment ERP System na NAS..."
echo "================================================"

# Backup databázy pred nasadením (best-effort)
echo "💾 Backup SQLite databázy..."
BACKUP_TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_PATH="/data/backups/db_${BACKUP_TS}.sqlite3"

if compose exec -T web sh -c "if [ -f /data/db.sqlite3 ]; then mkdir -p /data/backups && cp /data/db.sqlite3 $BACKUP_PATH; fi" >/dev/null 2>&1; then
	echo "✅ Backup uložený: $BACKUP_PATH"
else
	echo "⚠️  Backup sa nepodarilo vytvoriť (kontajner možno ešte nebeží). Pokračujem..."
fi

# Zastavenie starej verzie
echo "⏹️  Zastavenie starej verzie..."
compose down || true

# Build nového image
echo "🔨 Building Docker image..."
compose build --no-cache

# Spustenie kontajnera
echo "🏃 Spúšťanie kontajnera..."
compose up -d

# Čakanie na spustenie servera
echo "⏳ Čakanie na spustenie aplikácie..."
sleep 5

# Migrácii databázy
echo "🗄️  Migrácia databázy..."
compose exec -T web python manage.py migrate

# Zbieranie static files
echo "📦 Zbieranie statických súborov..."
compose exec -T web python manage.py collectstatic --noinput || true

# Vytvorenie superuser (voliteľné)
# compose exec -T web python manage.py createsuperuser --noinput --username admin --email admin@example.com

echo ""
echo "================================================"
echo "✅ Deployment hotový!"
echo "================================================"
echo ""
echo "📍 Aplikácia je dostupná na: http://192.168.1.94:8000"
echo "🔐 Admin panel: http://192.168.1.94:8000/admin"
echo ""
if [ "$COMPOSE_STYLE" = "plugin" ]; then
	echo "Logy: docker compose logs -f"
	echo "Status: docker compose ps"
else
	echo "Logy: $COMPOSE_BIN logs -f"
	echo "Status: $COMPOSE_BIN ps"
fi
