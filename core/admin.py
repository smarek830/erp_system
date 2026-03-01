from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Sum
from .models import (
    Stroj, Produkt, Operacia, Objednavka, Kontrakt, VyrobnaDavka,
    VyrobnyZaznam, KontrolaKvality, HlasenieVyroby, Material,
    PrijemkaNaSklad, VydajkaZoSkladu, KontrolnyParameter,
    MeraniePriKontrole, Sprievodka, OperaciaVyroby, SkladHotovychDielov, PrijemkaHotovychDielov, VydajkaHotovychDielov
)

# ===== INLINE ADMINS =====
class OperaciaInline(admin.TabularInline):
    model = Operacia
    extra = 1
    fields = ('poradie', 'nazov_operacie', 'stroj', 'cas_pripravy', 'cas_kus')

class VyrobnaDavkaInline(admin.TabularInline):
    model = VyrobnaDavka
    extra = 1
    fields = ('mnozstvo_davky', 'pozadovany_termin', 'stav', 'objednavka_link')
    readonly_fields = ('objednavka_link',)
    
    def objednavka_link(self, obj):
        if obj.objednavka:
            url = reverse('admin:core_objednavka_change', args=[obj.objednavka.pk])
            return format_html('<a href="{}" target="_blank">Objednávka #{}</a>', url, obj.objednavka.cislo_objednavky)
        elif obj.pk:
            return format_html('<span style="color: #666;">Vytvorí sa automaticky</span>')
        return "-"
    objednavka_link.short_description = "Objednávka"

# ===== MODEL ADMINS =====
@admin.register(Kontrakt)
class KontraktAdmin(admin.ModelAdmin):
    list_display = ('cislo_kontraktu', 'zakaznik', 'produkt', 'pocet_kusov_celkovo', 
                    'zostavajuce_mnozstvo', 'datum_do', 'je_skladom_display', 'pocet_davok')
    list_filter = ('je_skladom', 'zakaznik', 'datum_od', 'datum_do')
    search_fields = ('cislo_kontraktu', 'zakaznik', 'produkt__nazov')
    inlines = [VyrobnaDavkaInline]
    
    fieldsets = (
        ('Základné informácie', {
            'fields': ('cislo_kontraktu', 'zakaznik', 'produkt')
        }),
        ('Množstvo', {
            'fields': ('pocet_kusov_celkovo', 'zostavajuce_mnozstvo', 'je_skladom')
        }),
        ('Termíny', {
            'fields': ('datum_od', 'datum_do')
        }),
    )
    
    def je_skladom_display(self, obj):
        if obj.je_skladom:
            skladom = obj.get_dostupne_skladom()
            return format_html('<span style="color: green;">✓ Áno ({} ks)</span>', skladom)
        return format_html('<span style="color: orange;">⚠️ Nie</span>')
    je_skladom_display.short_description = "Skladom"
    
    def pocet_davok(self, obj):
        count = obj.vyrobne_davky.count()
        hotove = obj.vyrobne_davky.filter(stav='hotova').count()
        vo_vyrobe = obj.vyrobne_davky.filter(stav='vo_vyrobe').count()
        return format_html(
            '<span style="color: #666;">{} dávok</span> '
            '<span style="color: green;">(✓ {} hotových)</span> '
            '<span style="color: orange;">(⚙️ {} vo výrobe)</span>',
            count, hotove, vo_vyrobe
        )
    pocet_davok.short_description = "Výrobné dávky"

@admin.register(VyrobnaDavka)
class VyrobnaDavkaAdmin(admin.ModelAdmin):
    list_display = ('cislo_davky', 'kontrakt', 'mnozstvo_davky', 'pozadovany_termin', 
                    'stav_display', 'objednavka_link', 'akcia_vytvor_objednavku')
    list_filter = ('stav', 'kontrakt__zakaznik', 'datum_vytvorenia')
    search_fields = ('cislo_davky', 'kontrakt__cislo_kontraktu', 'kontrakt__zakaznik')
    readonly_fields = ('cislo_davky', 'objednavka')
    
    fieldsets = (
        ('Kontrakt', {
            'fields': ('kontrakt', 'cislo_davky')
        }),
        ('Výroba', {
            'fields': ('mnozstvo_davky', 'datum_vytvorenia', 'pozadovany_termin')
        }),
        ('Stav', {
            'fields': ('stav', 'objednavka', 'poznamka')
        }),
    )
    
    def stav_display(self, obj):
        colors = {
            'planovana': '#17a2b8',
            'vo_vyrobe': '#ffc107',
            'hotova': '#28a745',
            'expedovana': '#6c757d'
        }
        icons = {
            'planovana': '📋',
            'vo_vyrobe': '⚙️',
            'hotova': '✅',
            'expedovana': '📦'
        }
        return format_html(
            '<span style="padding: 3px 8px; background: {}; color: white; border-radius: 3px;">{} {}</span>',
            colors.get(obj.stav, '#6c757d'),
            icons.get(obj.stav, ''),
            obj.get_stav_display()
        )
    stav_display.short_description = "Stav"
    
    def objednavka_link(self, obj):
        if obj.objednavka:
            url = reverse('admin:core_objednavka_change', args=[obj.objednavka.pk])
            return format_html('<a href="{}" target="_blank">#{}</a>', url, obj.objednavka.cislo_objednavky)
        return "-"
    objednavka_link.short_description = "Objednávka"
    
    def akcia_vytvor_objednavku(self, obj):
        if not obj.objednavka and obj.pk:
            url = reverse('vytvor_objednavku_z_davky', args=[obj.pk])
            return format_html(
                '<a href="{}" class="button" style="background: #417690; color: white; '
                'padding: 5px 10px; text-decoration: none; border-radius: 3px;">➕ Vytvoriť objednávku</a>',
                url
            )
        return "-"
    akcia_vytvor_objednavku.short_description = "Akcia"

@admin.register(Objednavka)
class ObjednavkaAdmin(admin.ModelAdmin):
    list_display = ('cislo_objednavky', 'zakaznik', 'produkt', 'mnozstvo', 
                    'vyrobene_mnozstvo', 'datum_pozadovane', 'stav_display', 'kontrakt_info')
    list_filter = ('stav', 'zakaznik', 'datum_zadania', 'datum_pozadovane')
    search_fields = ('cislo_objednavky', 'zakaznik', 'produkt__nazov')
    date_hierarchy = 'datum_pozadovane'
    
    fieldsets = (
        ('Základné informácie', {
            'fields': ('cislo_objednavky', 'zakaznik', 'produkt')
        }),
        ('Množstvo', {
            'fields': ('mnozstvo', 'vyrobene_mnozstvo')
        }),
        ('Termíny', {
            'fields': ('datum_zadania', 'datum_pozadovane')
        }),
        ('Priradenie', {
            'fields': ('priradeni_operatori',)
        }),
        ('Stav', {
            'fields': ('stav', 'poznamka')
        }),
    )
    
    def stav_display(self, obj):
        colors = {
            'nova': '#007bff',
            'vyroba': '#ffc107',
            'hotovo': '#28a745',
            'pozastavene': '#6c757d'
        }
        return format_html(
            '<span style="padding: 3px 8px; background: {}; color: white; border-radius: 3px;">{}</span>',
            colors.get(obj.stav, '#6c757d'),
            obj.get_stav_display()
        )
    stav_display.short_description = "Stav"
    
    def kontrakt_info(self, obj):
        try:
            if hasattr(obj, 'vyrobna_davka') and obj.vyrobna_davka:
                kontrakt = obj.vyrobna_davka.kontrakt
                url = reverse('admin:core_kontrakt_change', args=[kontrakt.pk])
                return format_html(
                    '<a href="{}" target="_blank" style="color: #17a2b8;">📋 Kontrakt {}</a>',
                    url, kontrakt.cislo_kontraktu
                )
        except:
            pass
        
        kontrakty = Kontrakt.objects.filter(
            produkt=obj.produkt,
            zakaznik=obj.zakaznik,
            datum_do__gte=obj.datum_zadania
        )
        if kontrakty.exists():
            kontrakt = kontrakty.first()
            skladom = kontrakt.get_dostupne_skladom()
            url = reverse('admin:core_kontrakt_change', args=[kontrakt.pk])
            if skladom > 0:
                return format_html(
                    '<span style="padding: 3px 8px; background: #28a745; color: white; border-radius: 3px;">'
                    '✓ Skladom {} ks</span> '
                    '<a href="{}" target="_blank" style="color: #17a2b8;">(Kontrakt {})</a>',
                    skladom, url, kontrakt.cislo_kontraktu
                )
            else:
                return format_html(
                    '<span style="padding: 3px 8px; background: #17a2b8; color: white; border-radius: 3px;">'
                    'ℹ️ Existuje kontrakt</span> '
                    '<a href="{}" target="_blank" style="color: #17a2b8;">{}</a>',
                    url, kontrakt.cislo_kontraktu
                )
        return "-"
    kontrakt_info.short_description = "Info o kontrakte"

@admin.register(Produkt)
class ProduktAdmin(admin.ModelAdmin):
    list_display = ('nazov', 'cislo_dielu', 'index', 'material', 'cas_vyroby')
    search_fields = ('nazov', 'cislo_dielu')
    inlines = [OperaciaInline]

@admin.register(Stroj)
class StrojAdmin(admin.ModelAdmin):
    list_display = ('nazov', 'typ', 'status', 'hodinova_sadzba')
    list_filter = ('status',)

admin.site.register(VyrobnyZaznam)
admin.site.register(HlasenieVyroby)
admin.site.register(Material)
admin.site.register(PrijemkaNaSklad)
admin.site.register(VydajkaZoSkladu)
admin.site.register(KontrolnyParameter)
admin.site.register(MeraniePriKontrole)
admin.site.register(Sprievodka)

@admin.register(OperaciaVyroby)
class OperaciaVyrobyAdmin(admin.ModelAdmin):
    list_display = ('objednavka', 'poradie', 'nazov_operacie', 'stroj', 'operator', 'stav', 'vyrobene_kusy', 'nepodarky')
    list_filter = ('stav', 'stroj', 'objednavka__zakaznik')
    search_fields = ('objednavka__cislo_objednavky', 'nazov_operacie', 'objednavka__zakaznik')

@admin.register(KontrolaKvality)
class KontrolaKvalityAdmin(admin.ModelAdmin):
    list_display = ('objednavka', 'operator', 'typ_kontroly', 'pocet_ok_kusov', 'pocet_nok_kusov', 'cas_kontroly', 'vysledok_display', 'namerana_hodnota')
    list_filter = ('typ_kontroly', 'vysledok_ok', 'cas_kontroly', 'objednavka__zakaznik')
    search_fields = ('objednavka__cislo_objednavky', 'objednavka__zakaznik', 'operator__username', 'namerana_hodnota')
    readonly_fields = ('cas_kontroly',)
    date_hierarchy = 'cas_kontroly'

    fieldsets = (
        ('Prepojenie', {
            'fields': ('objednavka', 'operator', 'cas_kontroly')
        }),
        ('Typ záznamu', {
            'fields': ('typ_kontroly', 'pocet_ok_kusov', 'pocet_nok_kusov')
        }),
        ('Výsledok kontroly', {
            'fields': ('namerana_hodnota', 'vysledok_ok', 'fotka', 'fotka_balenia', 'poznamka')
        }),
    )

    def vysledok_display(self, obj):
        if obj.vysledok_ok:
            return format_html('<span style="padding: 3px 8px; background: #28a745; color: white; border-radius: 3px;">✅ OK</span>')
        return format_html('<span style="padding: 3px 8px; background: #dc3545; color: white; border-radius: 3px;">❌ NOK</span>')
    vysledok_display.short_description = "Výsledok"

# INLINE pre príjemky a výdajky
class PrijemkaHotovychDielovInline(admin.TabularInline):
    model = PrijemkaHotovychDielov
    extra = 0
    fields = ('mnozstvo', 'datum', 'objednavka', 'operator', 'poznamka')
    readonly_fields = ('datum',)

class VydajkaHotovychDielovInline(admin.TabularInline):
    model = VydajkaHotovychDielov
    extra = 0
    fields = ('mnozstvo', 'zakaznik', 'datum', 'cislo_dodacieho_listu', 'kontrakt', 'vyrobna_davka')
    readonly_fields = ('datum',)

@admin.register(SkladHotovychDielov)
class SkladHotovychDielovAdmin(admin.ModelAdmin):
    list_display = ('produkt', 'mnozstvo_display', 'minimalna_zasoba', 'optimalna_zasoba', 
                    'status_display', 'datum_poslednej_prijemky', 'datum_poslednej_vydajky')
    list_filter = ('produkt',)
    search_fields = ('produkt__nazov', 'produkt__cislo_dielu')
    inlines = [PrijemkaHotovychDielovInline, VydajkaHotovychDielovInline]
    
    fieldsets = (
        ('Produkt', {
            'fields': ('produkt',)
        }),
        ('Zásoby', {
            'fields': ('mnozstvo', 'minimalna_zasoba', 'optimalna_zasoba')
        }),
        ('Posledné pohyby', {
            'fields': ('datum_poslednej_prijemky', 'datum_poslednej_vydajky', 'poznamka')
        }),
    )
    
    def mnozstvo_display(self, obj):
        if obj.je_pod_minimom():
            return format_html('<span style="color: red; font-weight: bold;">⚠️ {} ks</span>', obj.mnozstvo)
        elif obj.je_nad_optimom():
            return format_html('<span style="color: orange; font-weight: bold;">📦 {} ks</span>', obj.mnozstvo)
        return format_html('<span style="color: green; font-weight: bold;">✓ {} ks</span>', obj.mnozstvo)
    mnozstvo_display.short_description = "Množstvo na sklade"
    
    def status_display(self, obj):
        if obj.je_pod_minimom():
            potrebne = obj.potrebne_mnozstvo()
            return format_html(
                '<span style="padding: 3px 8px; background: #dc3545; color: white; border-radius: 3px;">'
                '⚠️ Pod minimom! Vyrobiť: {} ks</span>',
                potrebne
            )
        elif obj.je_nad_optimom():
            return format_html(
                '<span style="padding: 3px 8px; background: #ffc107; color: black; border-radius: 3px;">'
                '📦 Preplnený sklad</span>'
            )
        return format_html(
            '<span style="padding: 3px 8px; background: #28a745; color: white; border-radius: 3px;">✓ OK</span>'
        )
    status_display.short_description = "Stav"

@admin.register(PrijemkaHotovychDielov)
class PrijemkaHotovychDielovAdmin(admin.ModelAdmin):
    list_display = ('sklad', 'mnozstvo', 'datum', 'objednavka', 'operator')
    list_filter = ('datum', 'sklad__produkt')
    search_fields = ('sklad__produkt__nazov', 'objednavka__cislo_objednavky')
    date_hierarchy = 'datum'
    
    fieldsets = (
        ('Základné informácie', {
            'fields': ('sklad', 'mnozstvo')
        }),
        ('Zdroj', {
            'fields': ('objednavka', 'operator', 'datum')
        }),
        ('Poznámka', {
            'fields': ('poznamka',)
        }),
    )

@admin.register(VydajkaHotovychDielov)
class VydajkaHotovychDielovAdmin(admin.ModelAdmin):
    list_display = ('sklad', 'mnozstvo', 'zakaznik', 'datum', 'cislo_dodacieho_listu', 
                    'objednavka', 'kontrakt', 'operator')
    list_filter = ('datum', 'zakaznik', 'sklad__produkt')
    search_fields = ('sklad__produkt__nazov', 'zakaznik', 'cislo_dodacieho_listu')
    date_hierarchy = 'datum'
    
    fieldsets = (
        ('Základné informácie', {
            'fields': ('sklad', 'mnozstvo', 'zakaznik')
        }),
        ('Prepojenie', {
            'fields': ('objednavka', 'kontrakt', 'vyrobna_davka')
        }),
        ('Expedícia', {
            'fields': ('cislo_dodacieho_listu', 'operator', 'datum')
        }),
        ('Poznámka', {
            'fields': ('poznamka',)
        }),
    )
