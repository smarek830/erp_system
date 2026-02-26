from django.db import models
from django.db.models import Sum
from django.utils import timezone
from django.contrib.auth.models import User
from datetime import timedelta
from decimal import Decimal
from django.db.models.signals import post_save
from django.dispatch import receiver


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

    servis_interval_dni = models.PositiveIntegerField(
        default=180,
        verbose_name="Interval servisu (dni)",
        help_text="Každých koľko dní je potrebný servis"
    )

    manual_pdf = models.FileField(upload_to='manualy_strojov/', null=True, blank=True, verbose_name="Manuál (PDF)")

    @property
    def datum_dalsieho_servisu(self):
        if self.datum_posledneho_servisu:
            return self.datum_posledneho_servisu + timedelta(days=self.servis_interval_dni)
        return None

    @property
    def dni_do_servisu(self):
        dalsi_servis = self.datum_dalsieho_servisu
        if dalsi_servis:
            delta = dalsi_servis - timezone.now().date()
            return delta.days
        return None

    @property
    def servis_status(self):
        dni = self.dni_do_servisu
        if dni is None:
            return 'unknown'
        elif dni < 0:
            return 'overdue'
        elif dni <= 7:
            return 'warning'
        else:
            return 'ok'

    def vytazenost_poslednych_7_dni(self):
        koniec = timezone.now()
        zaciatok = koniec - timedelta(days=7)
        celkovy_interval_hodiny = 7 * 24
        from django.apps import apps

        OperatorNaOperacii = apps.get_model('core', 'OperatorNaOperacii')
        VyrobnyZaznam = apps.get_model('core', 'VyrobnyZaznam')

        odrobene_sekundy = 0

        operator_zaznamy = OperatorNaOperacii.objects.filter(
            operacia__stroj=self,
            cas_zaciatku__lte=koniec,
        ).filter(
            models.Q(cas_konca__isnull=True) | models.Q(cas_konca__gte=zaciatok)
        )

        if operator_zaznamy.exists():
            for zaznam in operator_zaznamy:
                start = max(zaznam.cas_zaciatku, zaciatok)
                end = zaznam.cas_konca or koniec
                end = min(end, koniec)
                if end > start:
                    odrobene_sekundy += (end - start).total_seconds()
        else:
            zaznamy = VyrobnyZaznam.objects.filter(
                operacia__stroj=self,
                cas_zaznamu__gte=zaciatok,
                cas_zaznamu__lte=koniec,
            ).order_by("cas_zaznamu")

            posledny_start = None

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
    index = models.CharField(max_length=20, default='0', verbose_name="Index zmeny")

    material = models.CharField(max_length=100, blank=True, verbose_name="Materiál")
    rozmer_polotovaru = models.CharField(max_length=100, blank=True, verbose_name="Rozmer polotovaru")
    spotreba_ks = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Spotreba na kus")

    material_ref = models.ForeignKey(
        'Material',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='produkty',
        verbose_name="Materiál (sklad)")
    dlzka_na_kus_mm = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Dĺžka na kus (mm)")

    cas_vyroby = models.IntegerField(default=0, verbose_name="Čas výroby (min)")
    norma_hod = models.IntegerField(default=0, verbose_name="Norma (ks/hod)")

    vykres_pdf = models.FileField(upload_to='vykresy/', blank=True, null=True, verbose_name="Výkres (PDF)")
    baliaci_predpis_pdf = models.FileField(upload_to='baliace_predpisy/', null=True, blank=True, verbose_name="Baliaci predpis (PDF)")

    def __str__(self):
        return f"{self.nazov} (Index: {self.index if self.index else '-'})"

    def kusov_na_tyc(self):
        if not self.material_ref or not self.material_ref.tyc_dlzka_m or not self.dlzka_na_kus_mm:
            return None
        if self.dlzka_na_kus_mm <= 0:
            return None
        return int((self.material_ref.tyc_dlzka_m * 1000) // self.dlzka_na_kus_mm)

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
    TYPY = [
        ('standard', 'Štandardná výroba'),
        ('kontrakt', 'Kontraktová výroba'),
        ('prototyp', 'Vzorka / prototyp'),
    ]

    STAVY = [
        ('nova', '🆕 Nová'),
        ('vyroba', '⚙️ Vo výrobe'),
        ('hotovo', '✅ Hotovo'),
        ('pozastavene', '⏸️ Pozastavené'),
    ]

    typ = models.CharField(
        max_length=20,
        choices=TYPY,
        default='standard',
        verbose_name="Typ objednávky",
    )

    cislo_objednavky = models.CharField(max_length=50, unique=True, verbose_name="Číslo objednávky")
    zakaznik = models.CharField(max_length=100, verbose_name="Zákazník")
    produkt = models.ForeignKey(Produkt, on_delete=models.PROTECT, verbose_name="Produkt")
    mnozstvo = models.IntegerField(verbose_name="Množstvo (ks)")
    vyrobene_mnozstvo = models.IntegerField(default=0, verbose_name="Vyrobené množstvo (ks)")

    datum_zadania = models.DateField(default=timezone.now, verbose_name="Dátum zadania")
    datum_pozadovane = models.DateField(verbose_name="Požadovaný termín")

    stav = models.CharField(max_length=20, choices=STAVY, default='nova', verbose_name="Stav")
    poznamka = models.TextField(blank=True, verbose_name="Poznámka")

    priradeni_operatori = models.ManyToManyField(
        User,
        blank=True,
        related_name='priradene_objednavky',
        verbose_name="Priradení operátori",
        help_text="Operátori priradení k tejto objednávke"
    )

    kontrakt = models.ForeignKey(
        'Kontrakt',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='objednavky',
        verbose_name="Kontrakt",
    )

    # --- PROTOTYP / VZORKOVANIE ---
    je_prototyp = models.BooleanField(
        default=False,
        verbose_name="Je prototyp / vzorka?",
        help_text="Interné vzorkovanie alebo prototypovanie",
    )
    prototyp_iteracia = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Iterácia prototypu",
    )
    prototyp_zakaznik_schvalil = models.BooleanField(
        default=False,
        verbose_name="Prototyp schválený zákazníkom",
    )
    prototyp_poznamka = models.TextField(
        blank=True,
        verbose_name="Poznámka k prototypu",
    )
    prototyp_pre_objednavku = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='prototypy',
        verbose_name="Vzťahuje sa k objednávke",
    )
    # ------------------------------

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

    def zostava_vyroba(self):
        """Zostáva vyrobiť - berie do úvahy NOK kusy (kompenzácia)"""
        # Potrebujeme dosiahnuť self.mnozstvo OK kusov
        # Takže zostáva = mnozstvo - OK kusy (NOK kusy sa nepočítajú)
        return self.mnozstvo - self.celkom_ok_kusy
    
    @property
    def potrebne_kusy_celkom(self):
        """Celkové potrebné kusy vrátane kompenzácie za NOK"""
        return self.mnozstvo + self.celkom_nok_kusy

    def je_dokoncena(self):
        # Kontrola množstva - musí byť dosť OK kusov
        if self.celkom_ok_kusy < self.mnozstvo:
            return False
        
        # Kontrola kvality - všetky kontroly musia byť OK
        posledna_kontrola = self.kontroly.last()
        if posledna_kontrola and not posledna_kontrola.vysledok_ok:
            return False
            
        return True

    def _vygeneruj_cislo_objednavky(self):
        """Vygeneruje nové číslo objednávky vo formáte OBJ-YYYY-XXX."""
        year = timezone.now().year
        prefix = f"OBJ-{year}-"
        posledna = Objednavka.objects.filter(
            cislo_objednavky__startswith=prefix
        ).order_by('-cislo_objednavky').first()

        poradie = 1
        if posledna:
            cast = posledna.cislo_objednavky.replace(prefix, "")
            if cast.isdigit():
                poradie = int(cast) + 1

        kandidat = f"{prefix}{poradie:03d}"
        while Objednavka.objects.filter(cislo_objednavky=kandidat).exists():
            poradie += 1
            kandidat = f"{prefix}{poradie:03d}"

        return kandidat

    def save(self, *args, **kwargs):
        if not self.cislo_objednavky:
            self.cislo_objednavky = self._vygeneruj_cislo_objednavky()

        if self.pk:
            stara_objednavka = Objednavka.objects.get(pk=self.pk)
            if stara_objednavka.stav != 'vyroba' and self.stav == 'vyroba':
                super().save(*args, **kwargs)
                self._vytvor_operacie_z_kusovnika()
                self._vydaj_material()
                return

        super().save(*args, **kwargs)

    def _vytvor_operacie_z_kusovnika(self):
        if self.operacie.exists():
            return

        operacie_sablony = self.produkt.operacie.all().order_by('poradie')

        if not operacie_sablony.exists():
            return

        for sablona in operacie_sablony:
            OperaciaVyroby.objects.create(
                objednavka=self,
                vyrobna_davka=getattr(self, 'vyrobna_davka', None),
                operacia_sablona=sablona,
                stroj=sablona.stroj,
                poradie=sablona.poradie,
                nazov_operacie=sablona.nazov_operacie,
                cas_pripravy=sablona.cas_pripravy,
                cas_kus=sablona.cas_kus,
                stav='caka'
            )

    def _vydaj_material(self):
        """Automaticky odpíše materiál zo skladu pri spustení výroby."""
        if self.vydajky_material.exists():
            return

        produkt = self.produkt
        material = getattr(produkt, 'material_ref', None)
        if not material:
            return

        dlzka_na_kus = float(produkt.dlzka_na_kus_mm or 0)
        kg_na_meter = float(material.kg_na_meter or 0)
        if dlzka_na_kus <= 0 or kg_na_meter <= 0:
            return

        dlzka_m = (dlzka_na_kus * self.mnozstvo) / 1000.0
        kg = round(dlzka_m * kg_na_meter, 3)

        if kg > 0:
            VydajkaZoSkladu.objects.create(
                material=material,
                objednavka=self,
                mnozstvo=Decimal(str(kg)),
                poznamka=f"Automatická výdajka pre zákazku #{self.cislo_objednavky}",
            )

    def __str__(self):
        return f"#{self.cislo_objednavky} - {self.zakaznik} ({self.mnozstvo} ks)"

    def moze_sa_uzavriet(self):
        operacie = self.operacie.all()
        if not operacie.exists():
            return False, "Zakázka nemá vytvorené operácie"

        nehotove = operacie.exclude(stav='hotova')
        if nehotove.exists():
            zoznam = ", ".join([f"{op.nazov_operacie}" for op in nehotove])
            return False, f"Neukončené operácie: {zoznam}"

        # Kontrola, či je dosť OK kusov
        if self.celkom_ok_kusy < self.mnozstvo:
            zostava = self.zostava_vyroba()
            return False, f"Nedostatočný počet OK kusov: zostáva {zostava} ks (+ {self.celkom_nok_kusy} NOK)"

        return True, "OK"


    def uzavri_zakazku(self):
        moze, popis = self.moze_sa_uzavriet()
        if not moze:
            raise ValueError(f"Nemožno uzavrieť zakázku: {popis}")

        self.stav = 'hotovo'
        self.save()
        self._naskladni_hotove_diely()

    def _naskladni_hotove_diely(self):
        sklad, created = SkladHotovychDielov.objects.get_or_create(
            produkt=self.produkt,
            defaults={
                'mnozstvo': 0,
                'minimalna_zasoba': 10,
                'optimalna_zasoba': 100,
            }
        )

        # Zistí, koľko kusov bolo už naskladnených (napr. po smenách)
        uz_naskladnene = PrijemkaHotovychDielov.objects.filter(
            objednavka=self
        ).aggregate(Sum('mnozstvo'))['mnozstvo__sum'] or 0

        mnozstvo_ok = self.celkom_ok_kusy - uz_naskladnene

        if mnozstvo_ok > 0:
            PrijemkaHotovychDielov.objects.create(
                sklad=sklad,
                objednavka=self,
                mnozstvo=mnozstvo_ok,
                datum=timezone.now(),
                operator=None,
                poznamka=f"Finálne naskladnenie z zákazky #{self.cislo_objednavky} ({self.celkom_ok_kusy} OK, {self.celkom_nok_kusy} NOK)"
            )

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

    def _vygeneruj_cislo_kontraktu(self):
        """Vygeneruje nové číslo kontraktu vo formáte KONTR-YYYY-XXX."""
        year = timezone.now().year
        prefix = f"KONTR-{year}-"
        posledny = Kontrakt.objects.filter(
            cislo_kontraktu__startswith=prefix
        ).order_by('-cislo_kontraktu').first()

        poradie = 1
        if posledny:
            cast = posledny.cislo_kontraktu.replace(prefix, "")
            if cast.isdigit():
                poradie = int(cast) + 1

        kandidat = f"{prefix}{poradie:03d}"
        while Kontrakt.objects.filter(cislo_kontraktu=kandidat).exists():
            poradie += 1
            kandidat = f"{prefix}{poradie:03d}"

        return kandidat

    def save(self, *args, **kwargs):
        if not self.cislo_kontraktu:
            self.cislo_kontraktu = self._vygeneruj_cislo_kontraktu()
        if self.zostavajuce_mnozstvo is None:
            self.zostavajuce_mnozstvo = self.pocet_kusov_celkovo
        super().save(*args, **kwargs)

    def get_vyrobene_davky_mnozstvo(self):
        from django.db.models import Sum
        return self.vyrobne_davky.aggregate(Sum('mnozstvo_davky'))['mnozstvo_davky__sum'] or 0

    def get_dostupne_skladom(self):
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
    kontrakt = models.ForeignKey(Kontrakt, on_delete=models.CASCADE, related_name='vyrobne_davky')
    cislo_davky = models.CharField(max_length=50, unique=True, verbose_name="Číslo výrobnej dávky")

    mnozstvo_davky = models.PositiveIntegerField(verbose_name="Množstvo v dávke (ks)")
    datum_vytvorenia = models.DateField(default=timezone.now, verbose_name="Dátum vytvorenia")
    pozadovany_termin = models.DateField(verbose_name="Požadovaný termín dodania")

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
        if not self.cislo_davky:
            pocet = VyrobnaDavka.objects.filter(kontrakt=self.kontrakt).count()
            self.cislo_davky = f"{self.kontrakt.cislo_kontraktu}-D{pocet + 1:03d}"
        super().save(*args, **kwargs)

    def vytvor_operacie(self):
        if self.operacie.exists():
            return

        produkt = self.kontrakt.produkt
        operacie_sablony = produkt.operacie.all().order_by('poradie')

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
            typ='kontrakt',
            kontrakt=self.kontrakt,
            poznamka=f"Výrobná dávka z kontraktu {self.kontrakt.cislo_kontraktu}"
        )

        self.objednavka = objednavka
        self.stav = 'vo_vyrobe'
        self.save()

        self.vytvor_operacie()

        return objednavka

    def __str__(self):
        return f"{self.cislo_davky} - {self.mnozstvo_davky} ks ({self.get_stav_display()})"

    class Meta:
        verbose_name = "Výrobná dávka"
        verbose_name_plural = "Výrobné dávky"
        ordering = ['-datum_vytvorenia']
# 5B. MODEL: OPERÁCIA VÝROBY
class OperaciaVyroby(models.Model):
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

    operacia_sablona = models.ForeignKey(
        Operacia,
        on_delete=models.PROTECT,
        verbose_name="Operácia (šablóna)"
    )

    stroj = models.ForeignKey(Stroj, on_delete=models.PROTECT, verbose_name="Stroj")
    operator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Hlavný operátor"
    )

    poradie = models.IntegerField(verbose_name="Poradie")
    nazov_operacie = models.CharField(max_length=100, verbose_name="Názov operácie")

    cas_pripravy = models.IntegerField(verbose_name="Čas prípravy (min)")
    cas_kus = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Čas na kus (min)")
    cas_realny = models.IntegerField(null=True, blank=True, verbose_name="Reálny čas (min)")

    stav = models.CharField(max_length=20, choices=STAV_CHOICES, default='caka', verbose_name="Stav operácie")

    datum_zaciatku = models.DateTimeField(null=True, blank=True, verbose_name="Začiatok práce")
    datum_ukoncenia = models.DateTimeField(null=True, blank=True, verbose_name="Koniec práce")

    kusy_na_vstupe = models.IntegerField(default=0, verbose_name="Kusy na vstupe (z predch. operácie)")
    vyrobene_kusy = models.IntegerField(default=0, verbose_name="Vyrobené kusy (OK)")
    nepodarky = models.IntegerField(default=0, verbose_name="Nepodarky (NOK)")
    kusy_na_vystupe = models.IntegerField(default=0, verbose_name="Kusy na výstupe (pre ďalšiu operáciu)")

    poznamka = models.TextField(blank=True, verbose_name="Poznámka")

    def get_predchadzajuca_operacia(self):
        if self.poradie <= 1:
            return None
        return OperaciaVyroby.objects.filter(
            objednavka=self.objednavka,
            poradie=self.poradie - 1
        ).first()

    def get_nasledujuca_operacia(self):
        return OperaciaVyroby.objects.filter(
            objednavka=self.objednavka,
            poradie=self.poradie + 1
        ).first()

    def cielove_kusy_na_spracovanie(self):
        """Koľko kusov musí táto operácia celkovo spracovať (OK+NOK)."""
        nok_od_tejto_operacie = self.objednavka.operacie.filter(
            poradie__gte=self.poradie
        ).aggregate(models.Sum('nepodarky'))['nepodarky__sum'] or 0
        return self.objednavka.mnozstvo + nok_od_tejto_operacie

    def get_dostupne_kusy_na_vstupe(self):
        """Vráti počet kusov dostupných na spracovanie"""
        predch = self.get_predchadzajuca_operacia()
        
        # Pre všetky operácie - dynamika podľa NOK kompenzácie
        if predch is None:
            ciel = self.cielove_kusy_na_spracovanie()
            return max(ciel - self.kusy_spracovane_celkom(), 0)
        else:
            ciel = self.cielove_kusy_na_spracovanie()
            limit_vstupu = min(predch.vyrobene_kusy, ciel)
            return max(limit_vstupu - self.kusy_spracovane_celkom(), 0)

    def kusy_spracovane_celkom(self):
        return self.vyrobene_kusy + self.nepodarky

    def get_max_vyrobitelne_kusy(self):
        return self.get_dostupne_kusy_na_vstupe()

    def moze_zacat(self):
        if self.stav in ['vyroba', 'hotova']:
            return False

        predch = self.get_predchadzajuca_operacia()
        if predch is None:
            return True

        if predch.vyrobene_kusy <= 0:
            return False

        dostupne = self.get_dostupne_kusy_na_vstupe()
        return dostupne > 0

    def moze_pokracovat(self):
        """Môže pokračovať vo výrobe?"""
        # Pozastavené operácie môžu pokračovať ak sú dostupné kusy
        if self.stav == 'pozastavena':
            dostupne = self.get_dostupne_kusy_na_vstupe()
            return dostupne > 0
        
        # Hotové operácie môžu pokračovať ak ešte nie je dosiahnutý požadovaný počet OK kusov
        # (pre medzioperácie: ak sú dostupné kusy; pre poslednú: ak chýbajú OK kusy)
        if self.stav == 'hotova':
            nasledujuca = self.get_nasledujuca_operacia()
            if nasledujuca is None:  # Posledná operácia
                return self.vyrobene_kusy < self.objednavka.mnozstvo
            else:  # Medzioperácia
                if self.objednavka.zostava_vyroba() <= 0:
                    return False
                dostupne = self.get_dostupne_kusy_na_vstupe()
                return dostupne > 0
        
        return False
    
    @property
    def moze_pokracovat_teraz(self):
        """Či môže operácia ihneď pokračovať (read-only property pre UI)"""
        return self.moze_pokracovat()
    
    @property
    def ok_kusy(self):
        """Alias pre vyrobene_kusy (OK kusy) pre UI"""
        return self.vyrobene_kusy
    
    @property
    def nok_kusy(self):
        """Alias pre nepodarky (NOK kusy) pre UI"""
        return self.nepodarky
    
    @property
    def posledny_zaznam(self):
        """Posledný výrobný záznam tejto operácie"""
        return VyrobnyZaznam.objects.filter(
            objednavka=self.objednavka,
            operacia=self.operacia_sablona
        ).order_by('-cas_zaznamu').first()

    def ukonci_davku(self, vyrobene, nepodarky):
        max_kusy = self.get_max_vyrobitelne_kusy()
        if vyrobene + nepodarky > max_kusy:
            raise ValueError(
                f"Nemôžete vyrobiť viac kusov ({vyrobene + nepodarky}) "
                f"ako je dostupných na vstupe ({max_kusy})!"
            )

        self.vyrobene_kusy += vyrobene
        self.nepodarky += nepodarky
        self.kusy_na_vystupe = self.vyrobene_kusy

        nasledujuca = self.get_nasledujuca_operacia()
        if nasledujuca:
            nasledujuca.kusy_na_vstupe = self.vyrobene_kusy
            nasledujuca.save()

        # Pre POSLEDNÚ operáciu - kontroluj či je dosť OK kusov pre objednávku
        # Pre MEDZIOPERÁCIE - kontroluj či sú spracované všetky vstupné kusy
        if nasledujuca is None:
            # Posledná operácia - kontroluj požadovaný počet OK kusov
            je_hotova = self.vyrobene_kusy >= self.objednavka.mnozstvo
        else:
            # Medzioperácia - kontroluj či sú spracované všetky vstupné kusy
            zostava = self.get_dostupne_kusy_na_vstupe()
            je_hotova = zostava <= 0
        
        if je_hotova:
            self.stav = 'hotova'
            self.datum_ukoncenia = timezone.now()

            if self.datum_zaciatku:
                delta = self.datum_ukoncenia - self.datum_zaciatku
                self.cas_realny = int(delta.total_seconds() / 60)

            if nasledujuca is None:
                self.objednavka.vyrobene_mnozstvo = self.vyrobene_kusy
                self.objednavka.save()
        else:
            # Ešte zostávajú kusy - operácia pokračuje
            self.stav = 'pozastavena'

        # Ak je posledná operácia, vždy aktualizuj vyrobene_mnozstvo
        if nasledujuca is None and self.vyrobene_kusy > 0:
            self.objednavka.vyrobene_mnozstvo = self.vyrobene_kusy
            self.objednavka.save()

        self.save()

    
    def __str__(self):
        return f"{self.poradie}. {self.nazov_operacie} - {self.objednavka.cislo_objednavky}"
    
    @property
    def get_stav_display(self):
        """Display method for state badge"""
        display_map = {
            'caka': '⏳ Čaká',
            'vyroba': '⚙️ V práci',
            'pozastavena': '⏸️ Pozastavená',
            'hotova': '✅ Hotová',
        }
        return display_map.get(self.stav, self.stav)

    class Meta:
        verbose_name = "Operácia výroby"
        verbose_name_plural = "Operácie výroby"
        ordering = ['poradie']


class OperatorNaOperacii(models.Model):
    operacia = models.ForeignKey(
        OperaciaVyroby,
        on_delete=models.CASCADE,
        related_name='operatori'
    )
    operator = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Operátor")

    cas_zaciatku = models.DateTimeField(verbose_name="Začiatok práce")
    cas_konca = models.DateTimeField(null=True, blank=True, verbose_name="Koniec práce")

    vyrobene_kusy = models.IntegerField(default=0, verbose_name="Vyrobené kusy týmto operátorom")

    def get_odpracovany_cas_min(self):
        if self.cas_konca:
            delta = self.cas_konca - self.cas_zaciatku
            return int(delta.total_seconds() / 60)
        return 0

    def __str__(self):
        return f"{self.operator.username} na {self.operacia}"

    class Meta:
        verbose_name = "Operátor na operácii"
        verbose_name_plural = "Operátori na operáciách"
# 5D. MODEL: SKLAD HOTOVÝCH DIELOV
class SkladHotovychDielov(models.Model):
    """Evidencia hotových dielov na sklade"""
    produkt = models.ForeignKey(Produkt, on_delete=models.PROTECT, verbose_name="Produkt")
    mnozstvo = models.PositiveIntegerField(default=0, verbose_name="Množstvo na sklade (ks)")

    minimalna_zasoba = models.PositiveIntegerField(default=0, verbose_name="Minimálna zásoba (ks)")
    optimalna_zasoba = models.PositiveIntegerField(default=100, verbose_name="Optimálna zásoba (ks)")

    datum_poslednej_prijemky = models.DateTimeField(null=True, blank=True, verbose_name="Posledná príjemka")
    datum_poslednej_vydajky = models.DateTimeField(null=True, blank=True, verbose_name="Posledná výdajka")

    poznamka = models.TextField(blank=True, verbose_name="Poznámka")

    def je_pod_minimom(self):
        return self.mnozstvo < self.minimalna_zasoba

    def je_nad_optimom(self):
        return self.mnozstvo > self.optimalna_zasoba

    def potrebne_mnozstvo(self):
        if self.mnozstvo >= self.optimalna_zasoba:
            return 0
        return self.optimalna_zasoba - self.mnozstvo

    def __str__(self):
        return f"{self.produkt.nazov} - {self.mnozstvo} ks na sklade"

    class Meta:
        verbose_name = "Sklad hotových dielov"
        verbose_name_plural = "Sklad hotových dielov"
        ordering = ['produkt__nazov']


# 5E. MODEL: PRÍJEMKA HOTOVÝCH DIELOV
class PrijemkaHotovychDielov(models.Model):
    """Naskladnenie hotových dielov z výroby"""
    sklad = models.ForeignKey('SkladHotovychDielov', on_delete=models.PROTECT, related_name='prijemky')
    objednavka = models.ForeignKey(Objednavka, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Objednávka")

    mnozstvo = models.PositiveIntegerField(verbose_name="Naskladnené množstvo (ks)")
    datum = models.DateTimeField(default=timezone.now, verbose_name="Dátum príjemky")
    operator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Operátor")

    poznamka = models.TextField(blank=True, verbose_name="Poznámka")

    def save(self, *args, **kwargs):
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


# 5F. MODEL: VÝDAJKA HOTOVÝCH DIELOV
class VydajkaHotovychDielov(models.Model):
    """Vydanie hotových dielov zákazníkovi"""
    sklad = models.ForeignKey('SkladHotovychDielov', on_delete=models.PROTECT, related_name='vydajky')

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
        if not self.pk:
            if self.mnozstvo > self.sklad.mnozstvo:
                raise ValueError(f"Nedostatok na sklade! Dostupné: {self.sklad.mnozstvo} ks")

            self.sklad.mnozstvo -= self.mnozstvo
            self.sklad.datum_poslednej_vydajky = self.datum
            self.sklad.save()

            if self.vyrobna_davka:
                kontrakt = self.vyrobna_davka.kontrakt
                kontrakt.zostavajuce_mnozstvo = max(0, kontrakt.zostavajuce_mnozstvo - self.mnozstvo)
                kontrakt.save()

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
    TYPY_KONTROLY = [
        ('PRIEBEZNA', '🔬 Priebežná kontrola'),
        ('FINALNA', '📦 Finálne balenie'),
    ]

    objednavka = models.ForeignKey(Objednavka, on_delete=models.CASCADE, related_name='kontroly')
    operator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    cas_kontroly = models.DateTimeField(auto_now_add=True)
    typ_kontroly = models.CharField(max_length=20, choices=TYPY_KONTROLY, default='PRIEBEZNA', verbose_name="Typ kontroly")
    pocet_ok_kusov = models.PositiveIntegerField(default=0, verbose_name="OK kusy v zázname")
    pocet_nok_kusov = models.PositiveIntegerField(default=0, verbose_name="NOK kusy v zázname")

    namerana_hodnota = models.CharField(max_length=500, verbose_name="Nameraná hodnota")
    vysledok_ok = models.BooleanField(default=True, verbose_name="Je to OK?")
    fotka = models.ImageField(upload_to='kontrola_kvality/', verbose_name="Fotka produktu", null=True, blank=True)
    fotka_balenia = models.ImageField(upload_to='kontrola_kvality/balenie/', verbose_name="Fotka balenia", null=True, blank=True)
    poznamka = models.TextField(blank=True, verbose_name="Poznámka")

    def __str__(self):
        return f"{self.get_typ_kontroly_display()} #{self.objednavka.cislo_objednavky} - {'OK' if self.vysledok_ok else 'NOK'}"


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

    priemer_mm = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Priemer (mm)")
    tyc_dlzka_m = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Dĺžka tyče (m)")
    kg_na_meter = models.DecimalField(max_digits=10, decimal_places=3, default=0, verbose_name="Hmotnosť (kg/m)")

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
    objednavka = models.ForeignKey(Objednavka, on_delete=models.CASCADE, related_name='vydajky_material')
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

    podpis_operator_1 = models.CharField(max_length=100, blank=True, verbose_name="Operátor 1")
    podpis_operator_2 = models.CharField(max_length=100, blank=True, verbose_name="Operátor 2")
    podpis_operator_3 = models.CharField(max_length=100, blank=True, verbose_name="Operátor 3")

    def __str__(self):
        return f"Sprievodka: {self.objednavka.cislo_objednavky}"

    class Meta:
        verbose_name = "Sprievodka"
        verbose_name_plural = "Sprievodky"
