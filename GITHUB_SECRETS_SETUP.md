# Nastavenie GitHub Secrets pre automatický deploy

Tento návod vysvetľuje, kde nájdeš každý secret, ktorý potrebuje workflow
`.github/workflows/deploy.yml`.

---

## 1. NAS_SSH_KEY — kde ho nájdem / ako ho vygenerujem?

`NAS_SSH_KEY` je **obsah súboru so súkromným SSH kľúčom** (`id_rsa` alebo `id_ed25519`).
Treba ho vygenerovať raz na tvojom PC, verejnú časť nahrať na NAS a súkromnú
vložiť do GitHub Secrets.

### Krok 1 — Vygeneruj SSH kľúč na svojom PC

**Windows (PowerShell) / Mac / Linux — rovnaký príkaz:**

```bash
ssh-keygen -t ed25519 -C "github-deploy" -f ~/.ssh/github_deploy
```

> Ak systém `ed25519` nepodporuje, použi `rsa`:
> ```bash
> ssh-keygen -t rsa -b 4096 -C "github-deploy" -f ~/.ssh/github_deploy
> ```

Príkaz vytvorí **dva súbory**:
| Súbor | Čo obsahuje |
|-------|-------------|
| `~/.ssh/github_deploy` | **SÚKROMNÝ kľúč** — vloží sa do GitHub Secret `NAS_SSH_KEY` |
| `~/.ssh/github_deploy.pub` | **VEREJNÝ kľúč** — skopíruje sa na NAS |

> **NIKDY nezdieľaj súkromný kľúč** — je ako heslo.

---

### Krok 2 — Skopíruj VEREJNÝ kľúč na NAS

Na NASe musí byť verejný kľúč v súbore `~/.ssh/authorized_keys`.

**Zo svojho PC:**

```bash
# Mac / Linux — automaticky:
ssh-copy-id -i ~/.ssh/github_deploy.pub Marek@192.168.1.94

# Alebo manuálne (Windows aj Linux):
cat ~/.ssh/github_deploy.pub | ssh Marek@192.168.1.94 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

**Windows PowerShell (ak ssh-copy-id nie je k dispozícii):**

```powershell
$pubkey = Get-Content "$env:USERPROFILE\.ssh\github_deploy.pub"
ssh Marek@192.168.1.94 "mkdir -p ~/.ssh && echo '$pubkey' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

**Overenie — mal by si sa pripojiť BEZ hesla:**

```bash
ssh -i ~/.ssh/github_deploy Marek@192.168.1.94
```

---

### Krok 3 — Skopíruj SÚKROMNÝ kľúč do GitHub Secret

1. Zobraz obsah súkromného kľúča:

   ```bash
   # Mac / Linux:
   cat ~/.ssh/github_deploy

   # Windows PowerShell:
   Get-Content "$env:USERPROFILE\.ssh\github_deploy"
   ```

2. **Skopíruj celý výstup** (vrátane riadkov `-----BEGIN ...-----` a `-----END ...-----`).

3. Choď na GitHub → tvoj repozitár → **Settings → Secrets and variables → Actions → New repository secret**

4. Vyplň:
   - **Name:** `NAS_SSH_KEY`
   - **Secret:** vlož skopírovaný obsah kľúča

---

## 2. Všetky ostatné secrets — kde ich nájdeš

| Secret | Kde ho nájdeš / čo tam vložiť |
|--------|-------------------------------|
| `NAS_HOST` | IP adresa tvojho NASu — napr. `192.168.1.94`. Nájdeš ju v Synology DSM → Ovládací panel → Sieť, alebo v routeri. |
| `NAS_USER` | SSH používateľské meno na NASe — napr. `Marek`. Je to rovnaký login, ktorým sa prihliasuješ cez SSH. |
| `NAS_APP_PATH` | Absolútna cesta k priečinku projektu **na NASe**, napr. `/volume1/docker/erp`. Vieš si ju overiť po prihlásení: `ssh Marek@192.168.1.94 "ls /volume1/docker/"` |
| `NAS_SSH_KEY` | Súkromný kľúč — viz postup vyššie. |
| `TAILSCALE_AUTHKEY` | *(voliteľné)* Len ak NAS nie je priamo dostupný z internetu. Vygeneruj ho na https://login.tailscale.com/admin/settings/keys → **Generate auth key** (zaškrtni *Reusable*). |

---

## 3. Kde zadáš secrets v GitHub UI

```
GitHub → smarek830/erp_system
  └─ Settings
       └─ Secrets and variables
            └─ Actions
                 └─ New repository secret
```

![GitHub Secrets UI](https://docs.github.com/assets/cb-30868/mw-1440/images/help/repository/repo-actions-settings.webp)

Po nastavení všetkých secrets každý push na vetvu `main` automaticky:
1. Spustí Django testy ✅
2. Otestuje SSH spojenie na NAS ✅
3. Nasadí aplikáciu na NAS cez SSH 🚀
4. Overí, že app beží na porte 8000 🩺

---

## 4. Rýchly zhrnutý postup (copy-paste)

```bash
# 1. Vygeneruj kľúč
ssh-keygen -t ed25519 -C "github-deploy" -f ~/.ssh/github_deploy

# 2. Nakopíruj verejný kľúč na NAS
ssh-copy-id -i ~/.ssh/github_deploy.pub Marek@192.168.1.94

# 3. Zobraz súkromný kľúč — skopíruj celý výstup do GitHub Secret NAS_SSH_KEY
cat ~/.ssh/github_deploy
```
