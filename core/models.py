from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

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
    
    # NOVÉ POLE
    servis_interval_dni = models.PositiveIntegerField(
        default=180, 
        verbose_name="Interval servisu (dni)",
        help_text="Každých koľko dní je potrebný servis"
    )
    
    manual_pdf = models.FileField(upload_to='manualy_strojov/', null=True, blank=True, verbose_name="Manuál (PDF)")
    
    @property
    def datum_dalsieho_servisu(self):
        """Vypočíta dátum ďalšieho servisu"""
        if self.datum_posledneho_servisu:
            return self.datum_posledneho_servisu + timedelta(days=self.servis_interval_dni)
        return None
    
    @property
    def dni_do_servisu(self):
        """Koľko dní zostáva do servisu"""
        dalsi_servis = self.datum_dalsieho_servisu
        if dalsi_servis:
            delta = dalsi_servis - timezone.now().date()
            return delta.days
        return None
    
    @property
    def servis_status(self):
        """Vracia status servisu: ok / warning / overdue"""
        dni = self.dni_do_servisu
        if dni is None:
            return 'unknown'
        elif dni < 0:
            return 'overdue'  # po termíne
        elif dni <= 7:
            return 'warning'  # do 7 dní
        else:
            return 'ok'
    
    def vytazenost_poslednych_7_dni(self):
        """Vráti odhad vyťaženosti stroja za posledných 7 dní v percentách"""
        koniec = timezone.now()
        zaciatok = koniec - timedelta(days=7)
        celkovy_interval_hodiny = 7 * 24

        zaznamy = VyrobnyZaznam.objects.filter(
            operacia__stroj=self,
            cas_zaznamu__gte=zaciatok,
            cas_zaznamu__lte=koniec,
        ).order_by("cas_zaznamu")

        posledny_start = None
        odrobene_sekundy = 0

        for z in zaznamy:
            if z.typ_udalosti == "START":
                posledny_start = z.cas_zaznamu
            elif z.typ_udalosti == "STOP" and posledny_start:
                odrobene_sekundy += (z.cas_zaznamu - posledny_start).total_seconds()
                posledny_start = None

        if posledny_start:
            odrobene_sekundy += (koniec - posledny_start).total_seconds()

        odrobene_hodiny = odrobene_sekundy / 3600
        if celkovy_interval_hodiny == 0:
            return 0

        percenta = int(min(100, round((odrobene_hodiny / celkovy_interval_hodiny) * 100)))
        return percenta
    
    def __str__(self):
        return f"{self.nazov} ({self.get_status_display()})"
    
    class Meta:
        verbose_name = "Stroj"
        verbose_name_plural = "Stroje"


# 2. MODEL: PRODUKTY
class Produkt(models.Model):
    nazov = models.CharField(max_length=200, verbose_name="Názov produktu")
    cislo_dielu = models.CharField(max_length=50, unique=True, verbose_name="Číslo dielu")
    cislo_vykresu = models.CharField(max_length=50, blank=True, null=True, verbose_name="Číslo výkresu")
    index = models.IntegerField(default=0, verbose_name="Index zmeny")
    
    material = models.CharField(max_length=100, blank=True, verbose_name="Materiál")
    rozmer_polotovaru = models.CharField(max_length=100, blank=True, verbose_name="Rozmer polotovaru")
    spotreba_ks = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Spotreba na kus")
    
    cas_vyroby = models.IntegerField(default=0, verbose_name="Čas výroby (min)")
    norma_hod = models.IntegerField(default=0, verbose_name="Norma (ks/hod)")
    
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
    nazov_operacie = models.CharField(max_length=100, verbose_name="Názov")
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
    vyrobene_mnozstvo = models.IntegerField(default=0, verbose_name="Vyrobené množstvo (ks)")
    
    datum_zadania = models.DateField(default=timezone.now, verbose_name="Dátum zadania")
    datum_pozadovane = models.DateField(verbose_name="Požadovaný termín")
    
    stav = models.CharField(max_length=20, choices=STAVY, default='nova', verbose_name="Stav")
    poznamka = models.TextField(blank=True, verbose_name="Poznámka")
    
    def zostava_vyroba(self):
        return self.mnozstvo - self.vyrobene_mnozstvo
    
    def je_dokoncena(self):
        return self.vyrobene_mnozstvo >= self.mnozstvo
    
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
    produkt = models.ForeignKey(Produkt, on_delete=models.PROTECT, verbose_name="Produkt")
    
    pocet_kusov_celkovo = models.PositiveIntegerField(verbose_name="Celkový počet kusov")
    zostavajuce_mnozstvo = models.PositiveIntegerField(verbose_name="Zostáva dodať", blank=True)
    
    datum_od = models.DateField(verbose_name="Platnosť OD")
    datum_do = models.DateField(verbose_name="Platnosť DO")
    je_skladom = models.BooleanField(default=False, verbose_name="Je tovar skladom?")
    
    def save(self, *args, **kwargs):
        if self.zostavajuce_mnozstvo is None:
            self.zostavajuce_mnozstvo = self.pocet_kusov_celkovo
        super().save(*args, **kwargs)
    
    def get_vyrobene_davky_mnozstvo(self):
        """Vráti celkové množstvo vo výrobných dávkach"""
        from django.db.models import Sum
        return self.vyrobne_davky.aggregate(Sum('mnozstvo_davky'))['mnozstvo_davky__sum'] or 0
    
    def get_dostupne_skladom(self):
        """Vráti množstvo hotových dávek skladom"""
        from django.db.models import Sum
        hotove = self.vyrobne_davky.filter(stav='hotova').aggregate(Sum('mnozstvo_davky'))['mnozstvo_davky__sum'] or 0
        return hotove
    
    def __str__(self):
        return f"Kontrakt {self.cislo_kontraktu} - {self.zakaznik}"
    
    class Meta:
        verbose_name = "Kontrakt"
        verbose_name_plural = "Kontrakty"

# 5A. MODEL: VÝROBNÁ DÁVKA Z KONTRAKTU
class VyrobnaDavka(models.Model):
    """Čiastková výroba z kontraktu - umožňuje vyrábať kontrakt po častiach"""
    kontrakt = models.ForeignKey(Kontrakt, on_delete=models.CASCADE, related_name='vyrobne_davky')
    cislo_davky = models.CharField(max_length=50, unique=True, verbose_name="Číslo výrobnej dávky")
    
    mnozstvo_davky = models.PositiveIntegerField(verbose_name="Množstvo v dávke (ks)")
    datum_vytvorenia = models.DateField(default=timezone.now, verbose_name="Dátum vytvorenia")
    pozadovany_termin = models.DateField(verbose_name="Požadovaný termín dodania")
    
    # Prepojenie s objednávkou (ak sa vytvorí)
    objednavka = models.OneToOneField(
        'Objednavka', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='vyrobna_davka',
        verbose_name="Vytvorená objednávka"
    )
    
    stav = models.CharField(
        max_length=20,
        choices=[
            ('planovana', '📋 Plánovaná'),
            ('vo_vyrobe', '⚙️ Vo výrobe'),
            ('hotova', '✅ Hotová'),
            ('expedovana', '📦 Expedovaná'),
        ],
        default='planovana',
        verbose_name="Stav dávky"
    )
    
    poznamka = models.TextField(blank=True, verbose_name="Poznámka")
    
    def save(self, *args, **kwargs):
        # Automaticky vygeneruj číslo dávky
        if not self.cislo_davky:
            pocet = VyrobnaDavka.objects.filter(kontrakt=self.kontrakt).count()
            self.cislo_davky = f"{self.kontrakt.cislo_kontraktu}-D{pocet + 1:03d}"
        super().save(*args, **kwargs)
    
    def vytvor_objednavku(self):
        """Vytvorí objednávku z výrobnej dávky"""
        if self.objednavka:
            return self.objednavka
        
        objednavka = Objednavka.objects.create(
            cislo_objednavky=self.cislo_davky,
            zakaznik=self.kontrakt.zakaznik,
            produkt=self.kontrakt.produkt,
            mnozstvo=self.mnozstvo_davky,
            datum_zadania=self.datum_vytvorenia,
            datum_pozadovane=self.pozadovany_termin,
            stav='nova',
            poznamka=f"Výrobná dávka z kontraktu {self.kontrakt.cislo_kontraktu}"
        )
        
        self.objednavka = objednavka
        self.stav = 'vo_vyrobe'
        self.save()
        
        return objednavka
    
    def __str__(self):
        return f"{self.cislo_davky} - {self.mnozstvo_davky} ks ({self.get_stav_display()})"
    
    class Meta:
        verbose_name = "Výrobná dávka"
        verbose_name_plural = "Výrobné dávky"
        ordering = ['-datum_vytvorenia']

    def vytvor_operacie(self):
        """Automaticky vytvorí operácie podľa kusovníka produktu"""
        if self.operacie.exists():
            return  # Už existujú operácie
        
        # Získaj operácie z kusovníka produktu
        produkt = self.kontrakt.produkt
        operacie_sablony = produkt.operacie.all().order_by('poradie')
        
        # Vytvor konkrétne operácie pre túto dávku
        for sablona in operacie_sablony:
            OperaciaVyroby.objects.create(
                vyrobna_davka=self,
                objednavka=self.objednavka,
                operacia_sablona=sablona,
                stroj=sablona.stroj,
                poradie=sablona.poradie,
                nazov_operacie=sablona.nazov_operacie,
                cas_pripravy=sablona.cas_pripravy,
                cas_kus=sablona.cas_kus,
                stav='caka'
            )
    
    def vytvor_objednavku(self):
        """Vytvorí objednávku z výrobnej dávky"""
        if self.objednavka:
            return self.objednavka
        
        objednavka = Objednavka.objects.create(
            cislo_objednavky=self.cislo_davky,
            zakaznik=self.kontrakt.zakaznik,
            produkt=self.kontrakt.produkt,
            mnozstvo=self.mnozstvo_davky,
            datum_zadania=self.datum_vytvorenia,
            datum_pozadovane=self.pozadovany_termin,
            stav='nova',
            poznamka=f"Výrobná dávka z kontraktu {self.kontrakt.cislo_kontraktu}"
        )
        
        self.objednavka = objednavka
        self.stav = 'vo_vyrobe'
        self.save()
        
        # AUTOMATICKY VYTVOR OPERÁCIE
        self.vytvor_operacie()
        
        return objednavka    

# 5B. MODEL: OPERÁCIA VÝROBY (konkrétna operácia priradená k dávke)
class OperaciaVyroby(models.Model):
    """Konkrétna operácia priradená k výrobnej dávke alebo objednávke"""
    STAV_CHOICES = [
        ('caka', '⏳ Čaká'),
        ('vyroba', '⚙️ V práci'),
        ('hotova', '✅ Hotová'),
        ('pozastavena', '⏸️ Pozastavená'),
    ]
    
    vyrobna_davka = models.ForeignKey(
        VyrobnaDavka, 
        on_delete=models.CASCADE, 
        related_name='operacie',
        null=True, 
        blank=True,
        verbose_name="Výrobná dávka"
    )
    objednavka = models.ForeignKey(
        Objednavka, 
        on_delete=models.CASCADE, 
        related_name='operacie',
        verbose_name="Objednávka"
    )
    
    # Operácia z kusovníka (šablóna)
    operacia_sablona = models.ForeignKey(
        Operacia, 
        on_delete=models.PROTECT, 
        verbose_name="Operácia (šablóna)"
    )
    
    # Konkrétne priradenie
    stroj = models.ForeignKey(Stroj, on_delete=models.PROTECT, verbose_name="Stroj")
    operator = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        verbose_name="Priradený operátor"
    )
    
    poradie = models.IntegerField(verbose_name="Poradie")
    nazov_operacie = models.CharField(max_length=100, verbose_name="Názov operácie")
    
    # Časy
    cas_pripravy = models.IntegerField(verbose_name="Čas prípravy (min)")
    cas_kus = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Čas na kus (min)")
    cas_realny = models.IntegerField(null=True, blank=True, verbose_name="Reálny čas (min)")
    
    stav = models.CharField(max_length=20, choices=STAV_CHOICES, default='caka', verbose_name="Stav operácie")
    
    datum_zaciatku = models.DateTimeField(null=True, blank=True, verbose_name="Začiatok práce")
    datum_ukoncenia = models.DateTimeField(null=True, blank=True, verbose_name="Koniec práce")
    
    vyrobene_kusy = models.IntegerField(default=0, verbose_name="Vyrobené kusy")
    nepodarky = models.IntegerField(default=0, verbose_name="Nepodarky")
    
    poznamka = models.TextField(blank=True, verbose_name="Poznámka")
    
    def __str__(self):
        return f"{self.poradie}. {self.nazov_operacie} - {self.objednavka.cislo_objednavky}"
    
    class Meta:
        verbose_name = "Operácia výroby"
        verbose_name_plural = "Operácie výroby"
        ordering = ['poradie']

# 5C. MODEL: SKLAD HOTOVÝCH DIELOV
class SkladHotovychDielov(models.Model):
    """Evidencia hotových dielov na sklade"""
    produkt = models.ForeignKey(Produkt, on_delete=models.PROTECT, verbose_name="Produkt")
    mnozstvo = models.PositiveIntegerField(default=0, verbose_name="Množstvo na sklade (ks)")
    
    # Minimálna zásoba pre upozornenia
    minimalna_zasoba = models.PositiveIntegerField(default=0, verbose_name="Minimálna zásoba (ks)")
    optimalna_zasoba = models.PositiveIntegerField(default=100, verbose_name="Optimálna zásoba (ks)")
    
    # Dátumy
    datum_poslednej_prijemky = models.DateTimeField(null=True, blank=True, verbose_name="Posledná príjemka")
    datum_poslednej_vydajky = models.DateTimeField(null=True, blank=True, verbose_name="Posledná výdajka")
    
    poznamka = models.TextField(blank=True, verbose_name="Poznámka")
    
    def je_pod_minimom(self):
        """Kontrola, či je zásoba pod minimom"""
        return self.mnozstvo < self.minimalna_zasoba
    
    def je_nad_optimom(self):
        """Kontrola, či je zásoba nad optimom (preplnený sklad)"""
        return self.mnozstvo > self.optimalna_zasoba
    
    def potrebne_mnozstvo(self):
        """Koľko treba vyrobiť na dosiahnutie optima"""
        if self.mnozstvo >= self.optimalna_zasoba:
            return 0
        return self.optimalna_zasoba - self.mnozstvo
    
    def __str__(self):
        return f"{self.produkt.nazov} - {self.mnozstvo} ks na sklade"
    
    class Meta:
        verbose_name = "Sklad hotových dielov"
        verbose_name_plural = "Sklad hotových dielov"
        ordering = ['produkt__nazov']


# 5D. MODEL: PRÍJEMKA HOTOVÝCH DIELOV
class PrijemkaHotovychDielov(models.Model):
    """Naskladnenie hotových dielov z výroby"""
    sklad = models.ForeignKey('SkladHotovychDielov', on_delete=models.PROTECT, related_name='prijemky')
    objednavka = models.ForeignKey(Objednavka, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Objednávka")
    
    mnozstvo = models.PositiveIntegerField(verbose_name="Naskladnené množstvo (ks)")
    datum = models.DateTimeField(default=timezone.now, verbose_name="Dátum príjemky")
    operator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Operátor")
    
    poznamka = models.TextField(blank=True, verbose_name="Poznámka")
    
    def save(self, *args, **kwargs):
        # Automaticky zvýš zásobu
        if not self.pk:
            self.sklad.mnozstvo += self.mnozstvo
            self.sklad.datum_poslednej_prijemky = self.datum
            self.sklad.save()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Príjemka: {self.sklad.produkt.nazov} +{self.mnozstvo} ks ({self.datum.strftime('%d.%m.%Y')})"
    
    class Meta:
        verbose_name = "Príjemka hotových dielov"
        verbose_name_plural = "Príjemky hotových dielov"
        ordering = ['-datum']


# 5E. MODEL: VÝDAJKA HOTOVÝCH DIELOV
class VydajkaHotovychDielov(models.Model):
    """Vydanie hotových dielov zákazníkovi"""
    sklad = models.ForeignKey('SkladHotovychDielov', on_delete=models.PROTECT, related_name='vydajky')
    
    # Môže byť priradená k objednávke alebo kontraktu
    objednavka = models.ForeignKey(Objednavka, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Objednávka")
    kontrakt = models.ForeignKey(Kontrakt, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Kontrakt")
    vyrobna_davka = models.ForeignKey(VyrobnaDavka, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Výrobná dávka")
    
    zakaznik = models.CharField(max_length=100, verbose_name="Zákazník")
    mnozstvo = models.PositiveIntegerField(verbose_name="Vydané množstvo (ks)")
    datum = models.DateTimeField(default=timezone.now, verbose_name="Dátum výdajky")
    
    cislo_dodacieho_listu = models.CharField(max_length=100, blank=True, verbose_name="Číslo dodacieho listu")
    operator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Operátor")
    
    poznamka = models.TextField(blank=True, verbose_name="Poznámka")
    
    def save(self, *args, **kwargs):
        # Automaticky zníž zásobu
        if not self.pk:
            if self.mnozstvo > self.sklad.mnozstvo:
                raise ValueError(f"Nedostatok na sklade! Dostupné: {self.sklad.mnozstvo} ks")
            
            self.sklad.mnozstvo -= self.mnozstvo
            self.sklad.datum_poslednej_vydajky = self.datum
            self.sklad.save()
            
            # Ak je priradené k dávke, zníž zostávajúce množstvo kontraktu
            if self.vyrobna_davka:
                kontrakt = self.vyrobna_davka.kontrakt
                kontrakt.zostavajuce_mnozstvo = max(0, kontrakt.zostavajuce_mnozstvo - self.mnozstvo)
                kontrakt.save()
                
                # Označ dávku ako expedovanú
                self.vyrobna_davka.stav = 'expedovana'
                self.vyrobna_davka.save()
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Výdajka: {self.sklad.produkt.nazov} -{self.mnozstvo} ks pre {self.zakaznik}"
    
    class Meta:
        verbose_name = "Výdajka hotových dielov"
        verbose_name_plural = "Výdajky hotových dielov"
        ordering = ['-datum']

# 6. MODEL: VÝROBNÉ ZÁZNAMY
class VyrobnyZaznam(models.Model):
    TYPY_UDALOSTI = [
        ('START', '🟢 Začiatok práce'),
        ('PAUZA', '🟠 Pauza'),
        ('STOP', '🔴 Koniec práce'),
    ]
    
    objednavka = models.ForeignKey(Objednavka, on_delete=models.CASCADE, related_name='zaznamy')
    operacia = models.ForeignKey(Operacia, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Operácia")
    operator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Operátor")
    cas_zaznamu = models.DateTimeField(auto_now_add=True)
    typ_udalosti = models.CharField(max_length=10, choices=TYPY_UDALOSTI)
    dovod_pauzy = models.TextField(blank=True, null=True, verbose_name="Dôvod pauzy")
    
    def __str__(self):
        if self.operacia:
            return f"{self.get_typ_udalosti_display()} - {self.objednavka} - {self.operacia.nazov_operacie}"
        return f"{self.get_typ_udalosti_display()} - {self.objednavka}"
    
    class Meta:
        ordering = ['-cas_zaznamu']


# 7. MODEL: KONTROLA KVALITY
class KontrolaKvality(models.Model):
    objednavka = models.ForeignKey(Objednavka, on_delete=models.CASCADE, related_name='kontroly')
    operator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    cas_kontroly = models.DateTimeField(auto_now_add=True)
    
    namerana_hodnota = models.CharField(max_length=50, verbose_name="Nameraná hodnota")
    vysledok_ok = models.BooleanField(default=True, verbose_name="Je to OK?")
    fotka = models.ImageField(upload_to='kontrola_kvality/', verbose_name="Fotka produktu", null=True, blank=True)
    poznamka = models.TextField(blank=True, verbose_name="Poznámka")
    
    def __str__(self):
        return f"Kontrola {self.objednavka.id} - {'OK' if self.vysledok_ok else 'NOK'}"


# 8. MODEL: HLÁSENIA
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
    fotka_problemu = models.ImageField(upload_to='hlasenia/', null=True, blank=True, verbose_name="Fotka problému")
    
    def __str__(self):
        return f"{self.get_typ_problemu_display()} - {self.objednavka}"
# 9. SKLAD - MATERIÁL
class Material(models.Model):
    TYPY_MATERIALU = [
        ('SUROVINA', 'Surovina (tyč, plech...)'),
        ('POLOTOVAR', 'Polotovar'),
        ('KOMPONENT', 'Komponent'),
    ]
    
    nazov = models.CharField(max_length=200, verbose_name="Názov materiálu")
    kod = models.CharField(max_length=50, unique=True, verbose_name="Kód materiálu")
    typ = models.CharField(max_length=20, choices=TYPY_MATERIALU, default='SUROVINA')
    
    aktualna_zasoba = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Aktuálna zásoba")
    jednotka = models.CharField(max_length=20, default="kg", verbose_name="Jednotka")
    minimalna_zasoba = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Minimálna zásoba")
    
    cena_za_jednotku = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Cena za jednotku (€)")
    
    def __str__(self):
        return f"{self.nazov} ({self.kod}) - {self.aktualna_zasoba} {self.jednotka}"
    
    class Meta:
        verbose_name = "Materiál"
        verbose_name_plural = "Materiály"


# 10. PRÍJEMKA NA SKLAD
class PrijemkaNaSklad(models.Model):
    material = models.ForeignKey(Material, on_delete=models.PROTECT)
    mnozstvo = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Množstvo")
    datum = models.DateTimeField(default=timezone.now)
    dodavatel = models.CharField(max_length=200, blank=True, verbose_name="Dodávateľ")
    cislo_dodaciho_listu = models.CharField(max_length=100, blank=True, verbose_name="Číslo dodacieho listu")
    poznamka = models.TextField(blank=True)
    
    def save(self, *args, **kwargs):
        if not self.pk:
            self.material.aktualna_zasoba += self.mnozstvo
            self.material.save()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Príjem: {self.material.nazov} +{self.mnozstvo} {self.material.jednotka}"
    
    class Meta:
        verbose_name = "Príjemka na sklad"
        verbose_name_plural = "Príjemky na sklad"
        ordering = ['-datum']


# 11. VÝDAJKA ZO SKLADU
class VydajkaZoSkladu(models.Model):
    material = models.ForeignKey(Material, on_delete=models.PROTECT)
    objednavka = models.ForeignKey(Objednavka, on_delete=models.CASCADE, related_name='vydajky')
    operacia = models.ForeignKey(Operacia, on_delete=models.SET_NULL, null=True, blank=True)
    mnozstvo = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Množstvo")
    datum = models.DateTimeField(default=timezone.now)
    operator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    poznamka = models.TextField(blank=True)
    
    def save(self, *args, **kwargs):
        if not self.pk:
            self.material.aktualna_zasoba -= self.mnozstvo
            self.material.save()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Výdaj: {self.material.nazov} -{self.mnozstvo} {self.material.jednotka} (#{self.objednavka.cislo_objednavky})"
    
    class Meta:
        verbose_name = "Výdajka zo skladu"
        verbose_name_plural = "Výdajky zo skladu"
        ordering = ['-datum']


# 12. KONTROLNÉ PARAMETRE
class KontrolnyParameter(models.Model):
    produkt = models.ForeignKey(Produkt, on_delete=models.CASCADE, related_name='kontrolne_parametre')
    nazov = models.CharField(max_length=100, verbose_name="Názov parametra")
    hodnota_nominalna = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Nominálna hodnota")
    tolerancia_plus = models.DecimalField(max_digits=10, decimal_places=3, default=0, verbose_name="Tolerancia +")
    tolerancia_minus = models.DecimalField(max_digits=10, decimal_places=3, default=0, verbose_name="Tolerancia -")
    jednotka = models.CharField(max_length=20, default="mm", verbose_name="Jednotka")
    poradie = models.IntegerField(default=1, verbose_name="Poradie")
    
    def __str__(self):
        return f"{self.nazov}: {self.hodnota_nominalna} +{self.tolerancia_plus}/-{self.tolerancia_minus} {self.jednotka}"
    
    class Meta:
        verbose_name = "Kontrolný parameter"
        verbose_name_plural = "Kontrolné parametre"
        ordering = ['poradie']


# 13. MERANIA PRI KONTROLE
class MeraniePriKontrole(models.Model):
    kontrola = models.ForeignKey(KontrolaKvality, on_delete=models.CASCADE, related_name='merania')
    parameter = models.ForeignKey(KontrolnyParameter, on_delete=models.PROTECT)
    namerana_hodnota = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Nameraná hodnota")
    
    def je_v_tolerancii(self):
        min_hodnota = self.parameter.hodnota_nominalna - self.parameter.tolerancia_minus
        max_hodnota = self.parameter.hodnota_nominalna + self.parameter.tolerancia_plus
        return min_hodnota <= self.namerana_hodnota <= max_hodnota
    
    def __str__(self):
        status = "✅ OK" if self.je_v_tolerancii() else "❌ NOK"
        return f"{self.parameter.nazov}: {self.namerana_hodnota} {status}"
    
    class Meta:
        verbose_name = "Meranie pri kontrole"
        verbose_name_plural = "Merania pri kontrole"
        
# 14. MODEL: SPRIEVODKA
class Sprievodka(models.Model):
    objednavka = models.OneToOneField(Objednavka, on_delete=models.CASCADE, related_name='sprievodka')
    datum_vytvorenia = models.DateTimeField(auto_now_add=True)
    pdf_file = models.FileField(upload_to='sprievodky/', null=True, blank=True, verbose_name="PDF Sprievodka")
    qr_kod = models.ImageField(upload_to='qr_kody/', null=True, blank=True, verbose_name="QR kód")
    
    # Podpisy operátorov
    podpis_operator_1 = models.CharField(max_length=100, blank=True, verbose_name="Operátor 1")
    podpis_operator_2 = models.CharField(max_length=100, blank=True, verbose_name="Operátor 2")
    podpis_operator_3 = models.CharField(max_length=100, blank=True, verbose_name="Operátor 3")
    
    def __str__(self):
        return f"Sprievodka: {self.objednavka.cislo_objednavky}"
    
    class Meta:
        verbose_name = "Sprievodka"
        verbose_name_plural = "Sprievodky"
