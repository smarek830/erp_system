# ✅ OVERENIE DASHBOARD FUNKCIONALITY

## 1. Reštartujte server
```powershell
# Zastavte starý server (Ctrl+C)
cd c:\Users\stary\Desktop\erp_system
python manage.py runserver
```

## 2. Otvorte nové inkognito okno v prehliadači
- Chrome/Edge: Ctrl + Shift + N
- Firefox: Ctrl + Shift + P

## 3. Choďte na URL:
```
http://127.0.0.1:8000/operator/
```

## 4. Prihláste sa:
- Používateľ: `test_operator`
- Heslo: `test123`

## 5. Čo by ste mali vidieť:

### Tri sekcie:
1. **📦 Moje rozpracované zakázky** (prázdne)
2. **🆕 Priradené zakázky** (prázdne)
3. **📋 Dostupné nové zakázky** ← **TU SÚ TLAČIDLÁ!**

### V sekcii "Dostupné nové zakázky":
- 7 objednávok
- Každá má zelené tlačidlo: **📥 Prevziať zakázku**

## 6. Test prevzatia:
1. Kliknite na **📥 Prevziať zakázku** pri ľubovoľnej objednávke
2. Potvrdíte dialóg
3. Objednávka sa presunie do "Moje rozpracované zakázky"
4. Stránka sa automaticky obnoví

## 📸 Ako to má vyzerať:
```
📋 Dostupné nové zakázky
┌─────────────────────────────────────────────────────┐
│ #28 - Testovací produkt (10 ks)    [📥 Prevziať...] │
│ #5 - Ritzel Z18 m=0,8 (10 ks)      [📥 Prevziať...] │
│ #5501-D002 - Ritzel... (900 ks)    [📥 Prevziať...] │
│ a ďalšie...                                          │
└─────────────────────────────────────────────────────┘
```

## ⚠️ Ak stále nevidíte:
1. Skontrolujte konzolu prehliadača (F12) - hľadajte chyby
2. Overte URL - musí byť `/operator/` (nie `/admin/`)
3. Overte, že ste prihlásený ako `test_operator`
4. Skúste vymazať cookies prehliadača

## 🧪 Overenie, že to funguje (cez Python):
```powershell
cd c:\Users\stary\Desktop\erp_system
python test_dashboard.py
```
Mali by ste vidieť:
```
✅ Sekcia Dostupné nové zakázky
✅ Tlačidlo Prevziať zakázku
✅ JavaScript funkcia
```
