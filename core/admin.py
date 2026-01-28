from django.contrib import admin
from .models import (
    Produkt, 
    Stroj, 
    Objednavka, 
    Kontrakt, 
    VyrobnyZaznam, 
    KontrolaKvality, 
    HlasenieVyroby,
    Operacia
)

class OperaciaInline(admin.TabularInline):
    model = Operacia
    extra = 1  # Počet prázdnych riadkov na pridanie
    classes = ['collapse'] # Aby to nezaberalo miesto, ak nechceš

# 1. PRODUKTY
@admin.register(Produkt)
class ProduktAdmin(admin.ModelAdmin):
    list_display = ('nazov', 'cislo_dielu', 'index', 'material') 
    search_fields = ('nazov', 'cislo_dielu')
    inlines = [OperaciaInline]  # <-- TOTO JE TO KĽÚČOVÉ

@admin.register(Operacia)
class OperaciaAdmin(admin.ModelAdmin):
    list_display = ('poradie', 'nazov_operacie', 'produkt', 'stroj', 'cas_kus')
    list_filter = ('stroj', 'produkt')
    search_fields = ('nazov_operacie', 'produkt__nazov')
    ordering = ('produkt', 'poradie')

# 2. STROJE
@admin.register(Stroj)
class StrojAdmin(admin.ModelAdmin):
    list_display = ('nazov', 'typ', 'status', 'hodinova_sadzba', 'datum_posledneho_servisu')
    list_filter = ('status',)
    search_fields = ('nazov', 'typ')

# 3. OBJEDNÁVKY (Zákazky)
@admin.register(Objednavka)
class ObjednavkaAdmin(admin.ModelAdmin):
    list_display = ('id', 'produkt') 
    # Ostatné riadky som zatiaľ vymazal/zakomentoval, kým nezistíme presné názvy polí
    autocomplete_fields = ['produkt']

# 4. KONTRAKTY
@admin.register(Kontrakt)
class KontraktAdmin(admin.ModelAdmin):
    list_display = ('cislo_kontraktu', 'zakaznik', 'produkt', 'pocet_kusov_celkovo', 'zostavajuce_mnozstvo', 'datum_do')
    list_filter = ('zakaznik', 'datum_do', 'je_skladom')
    search_fields = ('cislo_kontraktu', 'zakaznik')
    autocomplete_fields = ['produkt'] # Toto funguje vďaka search_fields v ProduktAdmin

# 5. ZÁZNAMY VÝROBY (Start/Stop/Pauza)
@admin.register(VyrobnyZaznam)
class VyrobnyZaznamAdmin(admin.ModelAdmin):
    list_display = ('objednavka', 'typ_udalosti', 'operator', 'cas_zaznamu', 'dovod_pauzy')
    list_filter = ('typ_udalosti', 'cas_zaznamu', 'operator')

# 6. KONTROLA KVALITY
@admin.register(KontrolaKvality)
class KontrolaKvalityAdmin(admin.ModelAdmin):
    list_display = ('objednavka', 'namerana_hodnota', 'vysledok_ok', 'operator', 'cas_kontroly')
    list_filter = ('vysledok_ok', 'cas_kontroly')

# 7. HLÁSENIA (Nepodarky, Poruchy)
@admin.register(HlasenieVyroby)
class HlasenieVyrobyAdmin(admin.ModelAdmin):
    list_display = ('objednavka', 'typ_problemu', 'operator', 'cas_hlasenia', 'pocet_kusov_nepodarkov')
    list_filter = ('typ_problemu', 'cas_hlasenia')
