# Návod: Nastavenie SSH kľúča pre Synology NAS

## 1. Vygeneruj SSH kľúč (ak ešte nemáš)
```powershell
ssh-keygen -t ed25519 -C "marek@erp"
# Enter 3x (bez hesla pre automatizáciu)
```

## 2. Skopíruj kľúč na NAS
```powershell
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh Marek@192.168.1.94 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

## 3. Test pripojenia (bez hesla)
```powershell
ssh Marek@192.168.1.94 "echo SSH kluc funguje"
```

## 4. Teraz môžeš použiť automatizované skripty
```powershell
.\deploy_docker_nas.ps1
```
