# 🐳 Docker Deployment na Synology NAS

## 📋 Metóda A: Automatický deploy (odporúčané)

### 1. Spustenie deploy skriptu

```powershell
.\deploy_docker_nas.ps1
```

Skript automaticky:
- ✅ Commitne a pushne zmeny na GitHub
- ✅ Nakopíruje projekt na NAS
- ✅ Exportuje databázu z PC
- ✅ Spustí Docker build & deploy
- ✅ Naimportuje dáta

---

## 📋 Metóda B: Manuálny deploy cez Container Manager

### 1. Otvor Container Manager na Synology

- Prejdi na **DSM** → **Container Manager**
- Ak nemáš nainštalovaný, nainštaluj z **Package Center**

### 2. Priprav súbory na NAS

**Cez File Station:**
1. Vytvor adresár `/volume1/docker/erp_docker`
2. Nahraj všetky súbory projektu (alebo git clone)

**Alebo cez SSH:**
```bash
ssh Marek@192.168.1.94
cd /volume1/docker
git clone https://github.com/smarek830/erp_system.git erp_docker
cd erp_docker
```

### 3. Vytvor Container cez GUI

**V Container Manager:**

1. **Projekt**
   - Klikni na **Project** (ľavý panel)
   - **Create** → **Create docker-compose.yml project**

2. **Nastavenie projektu**
   - **Project Name:** `erp_system`
   - **Path:** Vyber `/volume1/docker/erp_docker`
   - **Source:** Local

3. **docker-compose.yml**
   - Container Manager automaticky načíta tvoj `docker-compose.yml`
   - Skontroluj nastavenia:
     ```yaml
     ports:
       - "8000:8000"
     restart: unless-stopped
     ```

4. **Build & Deploy**
   - Klikni **Next**
   - Potvrď nastavenia
   - Klikni **Done**
   - Container Manager spustí build a deploy automaticky

### 4. Import databázy

**Po spustení kontajnera:**

```bash
# 1. Pripoj sa na NAS
ssh Marek@192.168.1.94

# 2. Prejdi do projektu
cd /volume1/docker/erp_docker

# 3. Spusti migrácie
docker-compose exec web python manage.py migrate

# 4. Import dát (ak máš data_docker.json)
docker-compose exec web python manage.py loaddata data_docker.json

# 5. Vytvor admin účet (ak nemáš fixtures)
docker-compose exec web python manage.py createsuperuser
```

### 5. Overenie

Otvor v prehliadači:
- **Aplikácia:** http://192.168.1.94:8000
- **Admin:** http://192.168.1.94:8000/admin/login/

---

## 🔧 Správa kontajnera

### Cez Container Manager GUI:

- **Status:** Project → `erp_system` → Detail
- **Logy:** Klikni na container → **Logs**
- **Restart:** Pravý klik → **Restart**
- **Stop:** Pravý klik → **Stop**

### Cez SSH:

```bash
cd /volume1/docker/erp_docker

# Status
docker-compose ps

# Logy (live view)
docker-compose logs -f

# Restart
docker-compose restart

# Stop
docker-compose down

# Start
docker-compose up -d

# Rebuild po zmenách
docker-compose build
docker-compose up -d
```

---

## 🔄 Update aplikácie

### Automaticky:

```powershell
.\deploy_docker_nas.ps1
```

### Manuálne:

```bash
ssh Marek@192.168.1.94
cd /volume1/docker/erp_docker

# 1. Pull nový kód z GitHub
git pull

# 2. Rebuild kontajner
docker-compose build

# 3. Restart s novým image
docker-compose up -d

# 4. Migrácie (ak sú zmeny v modeloch)
docker-compose exec web python manage.py migrate
```

---

## 📊 Monitorovanie

### Logy v reálnom čase:
```bash
ssh Marek@192.168.1.94
cd /volume1/docker/erp_docker
docker-compose logs -f web
```

### Použitie zdrojov (Container Manager):
- **Dashboard** → CPU/RAM usage
- **Container** → Detail → **Resource**

### Shell v kontajneri:
```bash
docker-compose exec web bash
# Teraz si v kontajneri
python manage.py shell
```

---

## 🚨 Riešenie problémov

### Kontajner sa nespustí:
```bash
# Zisti chybu z logov
docker-compose logs web

# Rebuild od nuly
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Port 8000 obsadený:
```bash
# Zisti čo drží port
netstat -tuln | grep 8000

# Zmeň port v docker-compose.yml
ports:
  - "8001:8000"  # Externý port 8001
```

### Databáza sa nestartuje:
```bash
# Vstúp do kontajnera
docker-compose exec web bash

# Spusti migrácie manuálne
python manage.py migrate

# Skontroluj db.sqlite3
ls -lh db.sqlite3
```

---

## 🎯 Po nasadení

Aplikácia je dostupná:
- **Lokálna sieť:** http://192.168.1.94:8000
- **Tailscale VPN:** http://100.88.66.23:8000 (ak máš Tailscale na NAS)

Kontajner sa reštartuje automaticky pri:
- ✅ Reštarte NAS
- ✅ Páde aplikácie
- ✅ Upgrade Container Manager

**PC môžeš vypnúť**, aplikácia beží na NAS 24/7! 🚀
