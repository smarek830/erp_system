from django.contrib import admin
from .models import (
    Stroj, Produkt, Operacia, Objednavka, Kontrakt, 
    VyrobnyZaznam, KontrolaKvality, HlasenieVyroby,
    Material, PrijemkaNaSklad, VydajkaZoSkladu,
    KontrolnyParameter, MeraniePriKontrole
)

# === STROJE ===
@admin.register(Stroj)
class StrojAdmin(admin.ModelAdmin):
    list_display = ['nazov', 'typ', 'status', 'hodinova_sadzba']
    list_filter = ['status']
    search_fields = ['nazov', 'typ']


# === PRODUKTY ===
class OperaciaInline(admin.TabularInline):
    model = Operacia
    extra = 1

class KontrolnyParameterInline(admin.TabularInline):
    model = KontrolnyParameter
    extra = 1

@admin.register(Produkt)
class ProduktAdmin(admin.ModelAdmin):
    list_display = ['cislo_dielu', 'nazov', 'index', 'material', 'cas_vyroby']
    search_fields = ['nazov', 'cislo_dielu']
    inlines = [OperaciaInline, KontrolnyParameterInline]


# === OBJEDNÁVKY ===
@admin.register(Objednavka)
class ObjednavkaAdmin(admin.ModelAdmin):
    list_display = ['cislo_objednavky', 'zakaznik', 'produkt', 'mnozstvo', 'vyrobene_mnozstvo', 'stav', 'datum_pozadovane']
    list_filter = ['stav', 'datum_pozadovane']
    search_fields = ['cislo_objednavky', 'zakaznik']
    readonly_fields = ['vyrobene_mnozstvo']


# === KONTRAKTY ===
@admin.register(Kontrakt)
class KontraktAdmin(admin.ModelAdmin):
    list_display = ['cislo_kontraktu', 'zakaznik', 'produkt', 'pocet_kusov_celkovo', 'zostavajuce_mnozstvo']
    search_fields = ['cislo_kontraktu', 'zakaznik']


# === VÝROBNÉ ZÁZNAMY ===
@admin.register(VyrobnyZaznam)
class VyrobnyZaznamAdmin(admin.ModelAdmin):
    list_display = ['objednavka', 'operacia', 'operator', 'typ_udalosti', 'cas_zaznamu']
    list_filter = ['typ_udalosti', 'cas_zaznamu']
    search_fields = ['objednavka__cislo_objednavky', 'operator__username']


# === KONTROLA KVALITY ===
@admin.register(KontrolaKvality)
class KontrolaKvalityAdmin(admin.ModelAdmin):
    list_display = ['objednavka', 'operator', 'vysledok_ok', 'cas_kontroly']
    list_filter = ['vysledok_ok', 'cas_kontroly']


# === HLÁSENIA ===
@admin.register(HlasenieVyroby)
class HlasenieVyrobyAdmin(admin.ModelAdmin):
    list_display = ['objednavka', 'typ_problemu', 'pocet_kusov_nepodarkov', 'operator', 'cas_hlasenia']
    list_filter = ['typ_problemu', 'cas_hlasenia']


# === SKLAD ===
@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ['kod', 'nazov', 'typ', 'aktualna_zasoba', 'jednotka', 'minimalna_zasoba']
    list_filter = ['typ']
    search_fields = ['kod', 'nazov']


@admin.register(PrijemkaNaSklad)
class PrijemkaAdmin(admin.ModelAdmin):
    list_display = ['datum', 'material', 'mnozstvo', 'dodavatel']
    list_filter = ['datum']


@admin.register(VydajkaZoSkladu)
class VydajkaAdmin(admin.ModelAdmin):
    list_display = ['datum', 'material', 'mnozstvo', 'objednavka', 'operator']
    list_filter = ['datum', 'material']
