"""
Test kompenzácie NOK kusov pri výpočte zostávajúceho množstva

Scenár:
- Objednávka: 500 ks
- 1. dávka: 250 ks vyrobených, z toho 20 NOK, 230 OK
- Zostáva: 500 - 230 = 270 ks OK (nie 250!)
- Celkom potrebné: 500 + 20 = 520 ks (kompenzácia za NOK)
"""

import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Objednavka, Produkt, OperaciaVyroby, Operacia
from datetime import date

print("=" * 60)
print("TEST: Kompenzácia NOK kusov pri výpočte zostáva/potrebné")
print("=" * 60)

# Nájdi existujúcu objednávku
try:
    # Skús nájsť objednávku #5501-D002 (ktorá má 900 ks)
    objednavka = Objednavka.objects.filter(cislo_objednavky='5501-D002').first()
    
    if not objednavka:
        # Ak neexistuje, použi prvú dostupnú
        objednavka = Objednavka.objects.filter(stav__in=['nova', 'vyroba']).first()
    
    if not objednavka:
        raise Exception("Nenašla sa žiadna objednávka!")
    
    print(f"\n✅ Použijeme objednávku: #{objednavka.cislo_objednavky}")
    print(f"   Produkt: {objednavka.produkt.nazov}")
    print(f"   Pôvodné množstvo: {objednavka.mnozstvo} ks")
    
    # Skontroluj, či má operácie
    operacie = objednavka.operacie.all()
    if not operacie.exists():
        print("\n⚠️  Objednávka nemá operácie - vytváram...")
        objednavka.stav = 'vyroba'
        objednavka.save()
        operacie = objednavka.operacie.all()
    
    print(f"\n📋 Operácie: {operacie.count()}")
    for op in operacie:
        print(f"   {op.poradie}. {op.nazov_operacie}: {op.stav}")
    
    # Simuluj výrobu s NOK kusmi
    posledna = operacie.order_by('-poradie').first()
    if posledna:
        print(f"\n🔧 Simulujem výrobu na operácii: {posledna.nazov_operacie}")
        
        # Nastav začiatočné hodnoty
        posledna.stav = 'vyroba'
        posledna.kusy_na_vstupe = objednavka.mnozstvo
        posledna.save()
        
        # Simuluj dávku: 250 ks celkom, 20 NOK, 230 OK
        print("\n   📦 Dávka 1: vyrobím 230 OK + 20 NOK = 250 celkom")
        posledna.ukonci_davku(vyrobene=230, nepodarky=20)
        
        # Načítaj znova objednávku
        objednavka.refresh_from_db()
        
        print("\n" + "=" * 60)
        print("VÝSLEDKY:")
        print("=" * 60)
        print(f"PožadovanÃ© množstvo:      {objednavka.mnozstvo} ks")
        print(f"Celkom OK kusov:          {objednavka.celkom_ok_kusy} ks  ✅")
        print(f"Celkom NOK kusov:         {objednavka.celkom_nok_kusy} ks  ❌")
        print(f"Celkom vyrobených kusov:  {objednavka.celkom_vyrobenych_kusy} ks")
        print(f"")
        print(f"Zostáva vyrobiť (OK):     {objednavka.zostava_vyroba()} ks  ⚠️")
        print(f"Potrebné kusy celkom:     {objednavka.potrebne_kusy_celkom} ks  📊")
        print("")
        print("Vysvetlenie:")
        print("  - Požadované: 500 OK kusov")
        print("  - Vyrobené: 230 OK + 20 NOK = 250 celkom")
        print("  - Zostáva: 500 - 230 = 270 OK kusov ✅")
        print("  - Celkom treba vyrobiť: 500 + 20 = 520 ks (kompenzácia za NOK)")
        print("")
        
        # Overenie
        assert objednavka.celkom_ok_kusy == 230, f"Chyba: OK kusy by mali byť 230, nie {objednavka.celkom_ok_kusy}"
        assert objednavka.celkom_nok_kusy == 20, f"Chyba: NOK kusy by mali byť 20, nie {objednavka.celkom_nok_kusy}"
        assert objednavka.zostava_vyroba() == 270, f"Chyba: Zostáva by malo byť 270, nie {objednavka.zostava_vyroba()}"
        assert objednavka.potrebne_kusy_celkom == 520, f"Chyba: Potrebné celkom by malo byť 520, nie {objednavka.potrebne_kusy_celkom}"
        
        print("✅ VŠETKY TESTY PREŠLI!")
        print("")
        print("💡 Logika funguje správne:")
        print("   Ak operátor vyrobí 20 NOK kusov, musí vyrobiť navyše 20 ks,")
        print("   aby bolo celkovo 500 OK kusov!")
        
except Exception as e:
    print(f"\n❌ Chyba: {e}")
    import traceback
    traceback.print_exc()
