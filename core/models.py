from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User

# 1. MODEL: STROJE
class Stroj(models.Model):
    STATUS_CHOICES = [
        ('OK', '🟢 Funkčný'),
        ('PORUCHA', '🔴 Porucha'),
        ('SERVIS', '🟡 V servise'),
    ]

    nazov = models.CharField(max_length=100, verbose_name="Názov stroja")
    typ = models.CharField(max_length=100, blank=True, verbose_name="Typ/Model")
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='OK', verbose_name="Aktuálny stav")
    hodinova_sadzba = models.DecimalField(max_digits=6, decimal_places=2, default=0.00, verbose_name="Cena za hodinu (€)")
    datum_posledneho_servisu = models.DateField(null=True, blank=True, verbose_name="Posledný servis")
    manual_pdf = models.FileField(upload_to='manualy_strojov/', null=True, blank=True, verbose_name="Manuál (PDF)")

    def __str__(self):
        return f"{self.nazov} ({self.get_status_display()})"


# 2. MODEL: PRODUKTY
class Produkt(models.Model):
    nazov = models.CharField(max_length=200, verbose_name="Názov produktu")
    cislo_dielu = models.CharField(max_length=50, unique=True, verbose_name="Číslo dielu")
    cislo_vykresu = models.CharField(max_length=50, blank=True, null=True, verbose_name="Číslo výkresu")
    index = models.IntegerField(default=0, verbose_name="Index zmeny")
    
    # Materiál a rozmery
    material = models.CharField(max_length=100, blank=True, verbose_name="Materiál (napr. Ocel 11373)")
    rozmer_polotovaru = models.CharField(max_length=100, blank=True, verbose_name="Rozmer polotovaru")
    spotreba_ks = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Spotreba na kus")

    # Výroba
    cas_vyroby = models.IntegerField(default=0, verbose_name="Čas výroby (min)")
    norma_hod = models.IntegerField(default=0, verbose_name="Norma (ks/hod)")

    # Súbory
    vykres_pdf = models.FileField(upload_to='vykresy/', blank=True, null=True, verbose_name="Výkres (PDF)")
    baliaci_predpis_pdf = models.FileField(upload_to='baliace_predpisy/', null=True, blank=True, verbose_name="Baliaci predpis (PDF)")

    def __str__(self):
        return f"{self.nazov} (Index: {self.index if self.index else '-'})"

    class Meta:
        verbose_name = "Produkt"
        verbose_name_plural = "Produkty"


# 3. MODEL: OPERÁCIE
class Operacia(models.Model):
    produkt = models.ForeignKey(Produkt, on_delete=models.CASCADE, related_name='operacie')
    stroj = models.ForeignKey(Stroj, on_delete=models.PROTECT, verbose_name="Stroj")
    poradie = models.IntegerField(default=1, verbose_name="Poradie operácie")
    nazov_operacie = models.CharField(max_length=100, verbose_name="Názov (napr. Hrubovanie)")
    cas_pripravy = models.IntegerField(default=0, verbose_name="Čas prípravy (min)")
    cas_kus = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Čas na kus (min)")

    def __str__(self):
        return f"{self.poradie}. {self.nazov_operacie} - {self.produkt.nazov}"

    class Meta:
        ordering = ['poradie']
        verbose_name = "Operácia"
        verbose_name_plural = "Operácie"


# 4. MODEL: OBJEDNÁVKY
class Objednavka(models.Model):
    STAVY = [
        ('nova', '🆕 Nová'),
        ('vyroba', '⚙️ Vo výrobe'),
        ('hotovo', '✅ Hotovo'),
        ('pozastavene', '⏸️ Pozastavené'),
    ]

    cislo_objednavky = models.CharField(max_length=50, unique=True, verbose_name="Číslo objednávky")
    zakaznik = models.CharField(max_length=100, verbose_name="Zákazník")
    produkt = models.ForeignKey(Produkt, on_delete=models.PROTECT, verbose_name="Produkt")
    mnozstvo = models.IntegerField(verbose_name="Množstvo (ks)")
    
    datum_zadania = models.DateField(default=timezone.now, verbose_name="Dátum zadania")
    datum_pozadovane = models.DateField(verbose_name="Požadovaný termín")
    
    stav = models.CharField(max_length=20, choices=STAVY, default='nova', verbose_name="Stav")
    poznamka = models.TextField(blank=True, verbose_name="Poznámka")

    def __str__(self):
        return f"#{self.cislo_objednavky} - {self.zakaznik} ({self.mnozstvo} ks)"

    class Meta:
        verbose_name = "Objednávka"
        verbose_name_plural = "Objednávky"
        ordering = ['datum_pozadovane']


# 5. MODEL: KONTRAKTY
class Kontrakt(models.Model):
    zakaznik = models.CharField(max_length=100, verbose_name="Zákazník")
    cislo_kontraktu = models.CharField(max_length=50, unique=True, verbose_name="Číslo kontraktu")
    produkt = models.ForeignKey(Produkt, on_delete=models.PROTECT, verbose_name="Produkt (Diel + Index)")
    
    pocet_kusov_celkovo = models.PositiveIntegerField(verbose_name="Celkový počet kusov")
    zostavajuce_mnozstvo = models.PositiveIntegerField(verbose_name="Zostáva dodať", blank=True)
    
    datum_od = models.DateField(verbose_name="Platnosť OD")
    datum_do = models.DateField(verbose_name="Platnosť DO")
    je_skladom = models.BooleanField(default=False, verbose_name="Je tovar skladom?")
    
    def save(self, *args, **kwargs):
        if self.zostavajuce_mnozstvo is None:
            self.zostavajuce_mnozstvo = self.pocet_kusov_celkovo
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Kontrakt {self.cislo_kontraktu} - {self.zakaznik}"


# 6. MODEL: ZÁZNAMY VÝROBY (Start/Stop)
class VyrobnyZaznam(models.Model):
    TYPY_UDALOSTI = [
        ('START', '🟢 Začiatok práce'),
        ('PAUZA', '🟠 Pauza'),
        ('STOP', '🔴 Koniec práce'),
    ]
    
    objednavka = models.ForeignKey(Objednavka, on_delete=models.CASCADE, related_name='zaznamy')
    operator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Operátor")
    cas_zaznamu = models.DateTimeField(auto_now_add=True)
    typ_udalosti = models.CharField(max_length=10, choices=TYPY_UDALOSTI)
    dovod_pauzy = models.TextField(blank=True, null=True, verbose_name="Dôvod pauzy")
    
    def __str__(self):
        return f"{self.get_typ_udalosti_display()} - {self.objednavka}"


# 7. MODEL: KONTROLA KVALITY
class KontrolaKvality(models.Model):
    objednavka = models.ForeignKey(Objednavka, on_delete=models.CASCADE, related_name='kontroly')
    operator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    cas_kontroly = models.DateTimeField(auto_now_add=True)
    
    namerana_hodnota = models.CharField(max_length=50, verbose_name="Nameraná hodnota")
    vysledok_ok = models.BooleanField(default=True, verbose_name="Je to OK?")
    fotka = models.ImageField(upload_to='kontrola_kvality/', verbose_name="Fotka produktu", null=True, blank=True)
    poznamka = models.TextField(blank=True, verbose_name="Poznámka ku kontrole")

    def __str__(self):
        return f"Kontrola {self.objednavka.id} - {'OK' if self.vysledok_ok else 'NOK'}"


# 8. MODEL: HLÁSENIA (Nepodarky, Poruchy)
class HlasenieVyroby(models.Model):
    TYPY_HLASENIA = [
        ('NEPODAROK', '🗑️ Nepodarok (Scrap)'),
        ('PORUCHA_STROJA', '⚙️ Porucha stroja'),
        ('POSKODENY_NASTROJ', '🔧 Poškodený nástroj'),
        ('INA_CHYBA', '⚠️ Iný problém'),
    ]
    
    objednavka = models.ForeignKey(Objednavka, on_delete=models.CASCADE, related_name='hlasenia')
    operator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    cas_hlasenia = models.DateTimeField(auto_now_add=True)
    
    typ_problemu = models.CharField(max_length=20, choices=TYPY_HLASENIA)
    pocet_kusov_nepodarkov = models.PositiveIntegerField(default=0, verbose_name="Počet zlých kusov")
    popis_problemu = models.TextField(verbose_name="Popis problému")

    def __str__(self):
        return f"{self.get_typ_problemu_display()} - {self.objednavka}"
