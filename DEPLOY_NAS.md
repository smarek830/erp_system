# Nasadenie na NAS (192.168.1.94)

## Krok 1: Pushlovať kód na NAS (z vášho počítača)

```powershell
# Skopírovať do NASu cez SSH alebo SFTP
# Alebo ak máte Git repo na NASe:
git push origin main

# Alebo manuálne skopírovať cez remote:
# scp -r c:\Users\stary\Desktop\erp_system user@192.168.1.94:/path/to/app
```

## Krok 2: Na NASe - spustiť Docker kontajner

Prihlásenie na NAS a navigácia do priečinka projektu:

```bash
# SSH na NAS
ssh user@192.168.1.94

# Navigácia do projektu
cd /path/to/erp_system

# Zastavenie starej verzie (ak beh)
docker-compose down

# Build a spustenie novej verzie
docker-compose up -d --build

# Checknutie stavu
docker-compose ps
docker-compose logs -f

# Migrácii (prvé spustenie)
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py collectstatic --noinput
```

## Krok 3: Prístup k aplikácii

- **URL**: http://192.168.1.94:8000
- **Admin**: http://192.168.1.94:8000/admin

## Aktualizácia aplikácie (bez zastavenia):

```bash
# Pullnúť nový kód
git pull origin main

# Rebuild a restart
docker-compose up -d --build
```

## Konfigurácia (ak je potrebná):

- **DEBUG**: V settings.py je nastavený na `False` pre production
- **ALLOWED_HOSTS**: `192.168.1.94, localhost, 127.0.0.1`
- **Databáza**: SQLite v `db.sqlite3` (na NASe)
- **Media files**: V `/app/media` (persístentný volume)

## Troubleshooting

```bash
# Checknutie logov
docker-compose logs web

# Restart služby
docker-compose restart web

# Full reset
docker-compose down
docker-compose up -d --build
```
