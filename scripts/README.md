# Utility scripts

- `setup_backup_task.ps1` – vytvorí Windows Scheduled Task pre denný ERP backup.
- `setup_backup_cron.sh` – nastaví cron job pre denný ERP backup na Linux/NAS.
- `deploy_export_nas.ps1` – vytvorí POSIX export (`tar.gz`), nahrá ho na NAS a nasadí Docker update.

Použitie je popísané v `BACKUP_AUTOMATION.md`.

## Windows server operation (monitoring + control)

### One-click migration bundle (odporúčané)

- Vytvorenie ZIP balíka na aktuálnom PC:
	- `powershell -ExecutionPolicy Bypass -File scripts/windows/create_erp_migration_bundle.ps1`
	- Výsledok: `dist/erp_bundle_YYYYMMDD_HHMMSS.zip`

- Inštalácia balíka na cieľovom PC:
	1. Skopíruj ZIP na cieľový PC a rozbaľ.
	2. Otvor PowerShell v rozbalenom priečinku.
	3. Spusť:
		- `powershell -ExecutionPolicy Bypass -File scripts/windows/install_erp_from_bundle.ps1 -BundleRoot <nazov_rozbaleneho_priecinka> -TargetDir C:\erp_system -Port 8000`
	4. Skontroluj tasky:
		- `powershell -ExecutionPolicy Bypass -File scripts/windows/check_erp_tasks.ps1`

- Skripty balíka:
	- `windows/create_erp_migration_bundle.ps1`
	- `windows/install_erp_from_bundle.ps1`

- `windows/run_erp_server.ps1` – spustí ERP cez Waitress na porte 8000, urobí migrate + collectstatic, loguje do `logs/erp_server.log`.
- `windows/check_erp_status.ps1` – skontroluje `healthz` endpoint a DB check.
- `windows/check_erp_endpoints.ps1` – skontroluje kľúčové endpointy (`/healthz/`, `/admin/`, `/objednavka/import/mrp-pdf/`) a ich HTTP statusy.
- `windows/restart_erp_server.ps1` – zreštartuje ERP proces na porte 8000 (najprv ukonci listener aj zostatkove `runserver`/`waitress` procesy z ERP root, potom spusti jednu cistu instanciu).
- `windows/monitor_erp_once.ps1` – vykoná health check a pri chybe spustí restart.
- `windows/install_erp_monitor_task.ps1` – nainštaluje Scheduled Task, ktorý kontroluje ERP každé 2 minúty.
- `windows/install_erp_startup_task.ps1` – nainštaluje Scheduled Task na automatický štart ERP po boote Windows.
- `windows/check_erp_tasks.ps1` – vypíše stav ERP taskov a overí dostupnosť Telegram env premenných.
- `windows/daily_erp_report.ps1` – vykoná denný OK/FAIL report do `logs/erp_daily_report.log`.
- `windows/install_erp_daily_report_task.ps1` – nainštaluje denný Scheduled Task pre report.
- `windows/send_erp_alert.ps1` – odošle alert do logu + webhook/Telegram/e-mail (ak sú nastavené env premenné).
- `windows/set_erp_alert_env.ps1` – nastaví alert env premenné na Machine scope.

Príklady:

- Štart servera:
	- `powershell -ExecutionPolicy Bypass -File scripts/windows/run_erp_server.ps1 -Port 8000`
- Stav servera:
	- `powershell -ExecutionPolicy Bypass -File scripts/windows/check_erp_status.ps1 -TargetIp 127.0.0.1 -Port 8000`
- Reštart servera:
	- `powershell -ExecutionPolicy Bypass -File scripts/windows/restart_erp_server.ps1 -Port 8000`
- Inštalácia monitor tasku:
	- `powershell -ExecutionPolicy Bypass -File scripts/windows/install_erp_monitor_task.ps1 -TaskName ERP-Health-Monitor -TargetIp 127.0.0.1 -Port 8000`

- Inštalácia startup tasku (po boote):
  - `powershell -ExecutionPolicy Bypass -File scripts/windows/install_erp_startup_task.ps1 -TaskName ERP-Autostart -Port 8000`

- User-level fallback bez admin práv (Startup folder):
	- vytvor `.cmd` launcher v Startup priečinku, ktorý spustí `scripts/windows/run_erp_server.ps1`

- Kontrola endpointov:
	- `powershell -ExecutionPolicy Bypass -File scripts/windows/check_erp_endpoints.ps1 -BaseUrl http://127.0.0.1:8000`
	- `powershell -ExecutionPolicy Bypass -File scripts/windows/check_erp_endpoints.ps1 -BaseUrl http://100.85.178.1:8000`

- Inštalácia denného reportu (07:30):
  - `powershell -ExecutionPolicy Bypass -File scripts/windows/install_erp_daily_report_task.ps1 -TaskName ERP-Daily-Report -TargetIp 127.0.0.1 -Port 8000 -At 07:30`

- Rýchly test alertu:
  - `powershell -ExecutionPolicy Bypass -File scripts/windows/send_erp_alert.ps1 -Severity INFO -Source ManualTest -Message "ERP alert test"`

### Alert channels

Podporované kanály (môžeš kombinovať):

- Lokálny log: `logs/erp_alerts.log`
- Generic webhook: `ERP_ALERT_WEBHOOK_URL` (Teams/Slack/Discord kompatibilný incoming webhook)
- Telegram bot:
  - `ERP_ALERT_TELEGRAM_BOT_TOKEN`
  - `ERP_ALERT_TELEGRAM_CHAT_ID`
- SMTP e-mail:
  - `ERP_ALERT_SMTP_HOST`, `ERP_ALERT_SMTP_PORT`, `ERP_ALERT_SMTP_USER`, `ERP_ALERT_SMTP_PASS`
  - `ERP_ALERT_EMAIL_FROM`, `ERP_ALERT_EMAIL_TO`

Nastavenie env premenných (Machine scope, pri zamietnutí User scope):

- `powershell -ExecutionPolicy Bypass -File scripts/windows/set_erp_alert_env.ps1 -TelegramBotToken "<token>" -TelegramChatId "<chat_id>"`

## Presun aplikácie na iný Windows PC

1. Na starom PC:
	- Zastav ERP server.
	- Urob export projektu (bez `venv`) a skopíruj aj `db.sqlite3` + priečinok `media/`.

2. Na novom PC:
	- Nainštaluj Python 3.11+.
	- Rozbaľ projekt do napr. `C:\erp_system`.
	- V projekte vytvor venv:
		- `python -m venv venv`
		- `venv\Scripts\python.exe -m pip install --upgrade pip`
		- `venv\Scripts\python.exe -m pip install -r requirements.txt`
	- Skopíruj `db.sqlite3` a `media/` do koreňa projektu.
	- Spusť:
		- `venv\Scripts\python.exe manage.py migrate --noinput`
		- `venv\Scripts\python.exe manage.py collectstatic --noinput`

3. Test:
	- `powershell -ExecutionPolicy Bypass -File scripts/windows/run_erp_server.ps1 -Port 8000`

4. Produkčný test v kancelárii:
	- Skontroluj startup + monitor + daily report tasky cez `scripts/windows/check_erp_tasks.ps1`.
	- Otvor firewall pre port 8000 iba pre LAN.

## Deploy export na NAS

- Dry run (iba export):
	- `powershell -ExecutionPolicy Bypass -File scripts/deploy_export_nas.ps1 -DryRun`
- Full deploy:
	- `powershell -ExecutionPolicy Bypass -File scripts/deploy_export_nas.ps1`
