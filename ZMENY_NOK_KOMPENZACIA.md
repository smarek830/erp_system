# ✅ IMPLEMENTOVANÉ: Kompenzácia NOK kusov pri výrobe

## 📋 Čo sa zmenilo:

### **Problém (PRED):**
- Objednávka: 500 ks
- Vyrobené: 250 ks (230 OK + 20 NOK)
- Zostáva: 500 - 250 = **250 ks** ❌ ZLYHANIE!
- **Výsledok:** 480 OK + 20 NOK = len 480 dobrých kusov!

### **Riešenie (PO):**
- Objednávka: 500 ks
- Vyrobené: 250 ks (230 OK + 20 NOK)
- Zostáva: 500 - 230 = **270 ks** ✅ SPRÁVNE!
- **Výsledok:** 500 OK + 20 NOK = požadovaných 500 dobrých kusov!

---

## 🔧 Technické zmeny:

### 1. **Model `Objednavka` ([core/models.py](core/models.py))**

Pridané computed properties:

```python
@property
def celkom_ok_kusy(self):
    """Celkový počet OK kusov zo všetkých operácií"""
    posledna_operacia = self.operacie.order_by('-poradie').first()
    if posledna_operacia:
        return posledna_operacia.vyrobene_kusy
    return self.vyrobene_mnozstvo

@property
def celkom_nok_kusy(self):
    """Celkový počet NOK kusov zo všetkých operácií"""
    return self.operacie.aggregate(models.Sum('nepodarky'))['nepodarky__sum'] or 0

@property
def celkom_vyrobenych_kusy(self):
    """Celkový počet vyrobených kusov (OK + NOK)"""
    return self.celkom_ok_kusy + self.celkom_nok_kusy

@property
def potrebne_kusy_celkom(self):
    """Celkové potrebné kusy vrátane kompenzácie za NOK"""
    return self.mnozstvo + self.celkom_nok_kusy
```

Upravená logika:

```python
def zostava_vyroba(self):
    """Zostáva vyrobiť - berie do úvahy NOK kusy (kompenzácia)"""
    return self.mnozstvo - self.celkom_ok_kusy  # Len OK kusy!

def je_dokoncena(self):
    if self.celkom_ok_kusy < self.mnozstvo:  # Kontrola OK kusov
        return False
    ...
```

### 2. **Template ([core/templates/core/operator_zakazka_detail.html](core/templates/core/operator_zakazka_detail.html))**

Zobrazuje:
- **Požadované:** Pôvodné množstvo objednávky
- **OK kusy:** Počet dobrých kusov  
- **NOK kusy:** Počet zlých kusov
- **Zostáva OK:** Koľko OK kusov ešte treba vyrobiť
- **Celkom vyrobiť:** Celkové množstvo vrátane kompenzácie NOK

---

## 📊 Príklad použitia:

```
Objednávka #5501-D002: 900 ks
====================================
Požadované:        900 ks
OK kusy:          230 ks  ✅
NOK kusy:          32 ks  ❌
Zostáva OK:       670 ks  ⚠️  (900 - 230)
Celkom vyrobiť:   932 ks  📊  (900 + 32)
```

**Vysvetlenie:**
- Operátor už vyrobil 230 OK kusov
- 32 kusov bolo zlých (NOK)
- Potrebuje vyrobiť ešte **670 OK kusov** (nie 668!)
- Celkovo musí vyrobiť **932 kusov** (+ 32 kompenzácia za NOK)

---

## ✅ Výhody:

1. **Presné počítanie:** NOK kusy sa nepočítajú do požadovaného množstva
2. **Automatická kompenzácia:** Systém automaticky vypočíta potrebné kusy
3. **Prehľadné zobrazenie:** Operátor vidí OK/NOK kusy oddelene
4. **Správna logika:** 500 ks objednávka = 500 OK kusov (nie 480 OK + 20 NOK)

---

## 🧪 Test:

```bash
python test_nok_kompenzacia.py
```

Výstup ukazuje správne počítanie s kompenzáciou NOK kusov.

