# core/forms.py
from django import forms
from .models import (
    Objednavka,
    Kontrakt,
    Produkt,
    Stroj,
    VyrobnaDavka,
    PrijemkaHotovychDielov,
    VydajkaHotovychDielov,
    Material,
    SkladHotovychDielov,
    PrijemkaNaSklad,
    VydajkaZoSkladu,
)
from django.utils import timezone

class ObjednavkaForm(forms.ModelForm):
    """Formulár pre vytvorenie novej objednávky"""
    
    class Meta:
        model = Objednavka
        fields = [
            'cislo_objednavky', 
            'zakaznik', 
            'produkt', 
            'mnozstvo', 
            'datum_pozadovane', 
            'poznamka'
        ]
        widgets = {
            'cislo_objednavky': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'nechajte prázdne pre auto'
            }),
            'zakaznik': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Názov zákazníka'
            }),
            'produkt': forms.Select(attrs={
                'class': 'form-select'
            }),
            'mnozstvo': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': 'Počet kusov'
            }),
            'datum_pozadovane': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'poznamka': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Dodatočné informácie...'
            }),
        }
        labels = {
            'cislo_objednavky': 'Číslo objednávky',
            'zakaznik': 'Zákazník *',
            'produkt': 'Produkt *',
            'mnozstvo': 'Množstvo (ks) *',
            'datum_pozadovane': 'Požadovaný termín dodania *',
            'poznamka': 'Poznámka',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cislo_objednavky'].required = False

    def clean_mnozstvo(self):
        mnozstvo = self.cleaned_data.get('mnozstvo')
        if mnozstvo and mnozstvo <= 0:
            raise forms.ValidationError('Množstvo musí byť väčšie ako 0')
        return mnozstvo

    def clean_datum_pozadovane(self):
        datum = self.cleaned_data.get('datum_pozadovane')
        if datum and datum < timezone.now().date():
            raise forms.ValidationError('Termín nemôže byť v minulosti')
        return datum


class KontraktForm(forms.ModelForm):
    """Formulár pre vytvorenie nového kontraktu"""
    
    class Meta:
        model = Kontrakt
        fields = [
            'cislo_kontraktu',
            'zakaznik',
            'produkt',
            'pocet_kusov_celkovo',
            'datum_od',
            'datum_do',
            'je_skladom',
        ]
        widgets = {
            'cislo_kontraktu': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'nechajte prázdne pre auto'
            }),
            'zakaznik': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Názov zákazníka'
            }),
            'produkt': forms.Select(attrs={
                'class': 'form-select'
            }),
            'pocet_kusov_celkovo': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': 'Celkový počet kusov v kontrakte'
            }),
            'datum_od': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'datum_do': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'je_skladom': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'cislo_kontraktu': 'Číslo kontraktu',
            'zakaznik': 'Zákazník *',
            'produkt': 'Produkt *',
            'pocet_kusov_celkovo': 'Celkový počet kusov *',
            'datum_od': 'Platnosť od *',
            'datum_do': 'Platnosť do *',
            'je_skladom': 'Tovar bude skladom?',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cislo_kontraktu'].required = False

    def clean(self):
        cleaned_data = super().clean()
        datum_od = cleaned_data.get('datum_od')
        datum_do = cleaned_data.get('datum_do')
        pocet_kusov = cleaned_data.get('pocet_kusov_celkovo')

        if datum_od and datum_do:
            if datum_do <= datum_od:
                raise forms.ValidationError('Dátum konca musí byť po dátume začiatku')

        if pocet_kusov and pocet_kusov <= 0:
            raise forms.ValidationError('Počet kusov musí byť väčší ako 0')

        return cleaned_data


# FORMULÁRE PRE VÝROBNÉ DÁVKY
class VyrobnaDavkaForm(forms.ModelForm):
    """Formulár pre vytvorenie výrobnej dávky z kontraktu"""
    
    class Meta:
        model = VyrobnaDavka
        fields = [
            'mnozstvo_davky',
            'pozadovany_termin',
            'poznamka'
        ]
        widgets = {
            'mnozstvo_davky': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Množstvo kusov v dávke',
                'min': '1'
            }),
            'pozadovany_termin': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'poznamka': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Poznámka k výrobnej dávke...'
            }),
        }
        labels = {
            'mnozstvo_davky': 'Množstvo v dávke (ks) *',
            'pozadovany_termin': 'Požadovaný termín *',
            'poznamka': 'Poznámka',
        }


# FORMULÁRE PRE STROJE
class StrojForm(forms.ModelForm):
    class Meta:
        model = Stroj
        fields = ['nazov', 'typ', 'status', 'hodinova_sadzba', 'datum_posledneho_servisu', 'servis_interval_dni', 'manual_pdf']
        widgets = {
            'nazov': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Názov stroja'}),
            'typ': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Typ/Model'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'hodinova_sadzba': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'datum_posledneho_servisu': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'servis_interval_dni': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '180'}),
            'manual_pdf': forms.FileInput(attrs={'class': 'form-control'}),
        }


# FORMULÁRE PRE PRODUKTY
class ProduktForm(forms.ModelForm):
    """Formulár pre vytvorenie a úpravu produktu"""
    
    class Meta:
        model = Produkt
        fields = [
            'nazov',
            'cislo_dielu',
            'cislo_vykresu',
            'index',
            'material',
            'rozmer_polotovaru',
            'spotreba_ks',
            'material_ref',
            'dlzka_na_kus_mm',
            'cas_vyroby',
            'norma_hod',
        ]
        widgets = {
            'nazov': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Názov produktu'
            }),
            'cislo_dielu': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Číslo dielu'
            }),
            'cislo_vykresu': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Číslo výkresu'
            }),
            'index': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Napr. 0, A, B2'
            }),
            'material': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Materiál'
            }),
            'rozmer_polotovaru': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Rozmer polotovaru'
            }),
            'spotreba_ks': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'material_ref': forms.Select(attrs={
                'class': 'form-select'
            }),
            'dlzka_na_kus_mm': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'cas_vyroby': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0'
            }),
            'norma_hod': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0'
            }),
        }
        labels = {
            'nazov': 'Názov produktu *',
            'cislo_dielu': 'Číslo dielu *',
            'cislo_vykresu': 'Číslo výkresu',
            'index': 'Index zmeny',
            'material': 'Materiál',
            'rozmer_polotovaru': 'Rozmer polotovaru',
            'spotreba_ks': 'Spotreba na kus',
            'material_ref': 'Materiál (sklad)',
            'dlzka_na_kus_mm': 'Dĺžka na kus (mm)',
            'cas_vyroby': 'Čas výroby (min)',
            'norma_hod': 'Norma (ks/hod)',
        }


# FORMULÁRE PRE SKLAD HOTOVÝCH DIELOV
class PrijemkaHotovychDielovForm(forms.ModelForm):
    """Formulár pre príjemku hotových dielov"""
    
    class Meta:
        model = PrijemkaHotovychDielov
        fields = [
            'sklad',
            'objednavka',
            'mnozstvo',
            'poznamka'
        ]
        widgets = {
            'sklad': forms.Select(attrs={
                'class': 'form-select'
            }),
            'objednavka': forms.Select(attrs={
                'class': 'form-select'
            }),
            'mnozstvo': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1'
            }),
            'poznamka': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Poznámka k príjemke...'
            }),
        }
        labels = {
            'sklad': 'Sklad *',
            'objednavka': 'Objednávka',
            'mnozstvo': 'Naskladnené množstvo (ks) *',
            'poznamka': 'Poznámka',
        }


class VydajkaHotovychDielovForm(forms.ModelForm):
    """Formulár pre výdajku hotových dielov"""
    
    class Meta:
        model = VydajkaHotovychDielov
        fields = [
            'sklad',
            'zakaznik',
            'mnozstvo',
            'objednavka',
            'kontrakt',
            'vyrobna_davka',
            'cislo_dodacieho_listu',
            'poznamka'
        ]
        widgets = {
            'sklad': forms.Select(attrs={
                'class': 'form-select'
            }),
            'zakaznik': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Názov zákazníka'
            }),
            'mnozstvo': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1'
            }),
            'objednavka': forms.Select(attrs={
                'class': 'form-select'
            }),
            'kontrakt': forms.Select(attrs={
                'class': 'form-select'
            }),
            'vyrobna_davka': forms.Select(attrs={
                'class': 'form-select'
            }),
            'cislo_dodacieho_listu': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Číslo dodacieho listu'
            }),
            'poznamka': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Poznámka k výdajke...'
            }),
        }
        labels = {
            'sklad': 'Sklad *',
            'zakaznik': 'Zákazník *',
            'mnozstvo': 'Vydané množstvo (ks) *',
            'objednavka': 'Objednávka',
            'kontrakt': 'Kontrakt',
            'vyrobna_davka': 'Výrobná dávka',
            'cislo_dodacieho_listu': 'Číslo dodacieho listu',
            'poznamka': 'Poznámka',
        }


class MaterialForm(forms.ModelForm):
    """Formulár pre úpravu materiálu"""

    class Meta:
        model = Material
        fields = [
            'nazov',
            'kod',
            'typ',
            'jednotka',
            'minimalna_zasoba',
            'cena_za_jednotku',
            'priemer_mm',
            'tyc_dlzka_m',
            'kg_na_meter',
            'aktualna_zasoba',
        ]
        widgets = {
            'nazov': forms.TextInput(attrs={'class': 'form-control'}),
            'kod': forms.TextInput(attrs={'class': 'form-control'}),
            'typ': forms.Select(attrs={'class': 'form-select'}),
            'jednotka': forms.TextInput(attrs={'class': 'form-control'}),
            'minimalna_zasoba': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'cena_za_jednotku': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'priemer_mm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'tyc_dlzka_m': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'kg_na_meter': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001', 'min': '0'}),
            'aktualna_zasoba': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
        }


class SkladHotovychDielovForm(forms.ModelForm):
    """Formulár pre úpravu skladovej položky hotových dielov"""

    class Meta:
        model = SkladHotovychDielov
        fields = [
            'produkt',
            'mnozstvo',
            'minimalna_zasoba',
            'optimalna_zasoba',
            'poznamka',
        ]
        widgets = {
            'produkt': forms.Select(attrs={'class': 'form-select'}),
            'mnozstvo': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'minimalna_zasoba': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'optimalna_zasoba': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'poznamka': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class PrijemkaNaSkladForm(forms.ModelForm):
    """Formulár pre príjem materiálu na sklad"""

    class Meta:
        model = PrijemkaNaSklad
        fields = [
            'material',
            'mnozstvo',
            'dodavatel',
            'cislo_dodaciho_listu',
            'poznamka',
        ]
        widgets = {
            'material': forms.Select(attrs={'class': 'form-select'}),
            'mnozstvo': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'dodavatel': forms.TextInput(attrs={'class': 'form-control'}),
            'cislo_dodaciho_listu': forms.TextInput(attrs={'class': 'form-control'}),
            'poznamka': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class VydajkaZoSkladuForm(forms.ModelForm):
    """Formulár pre výdaj materiálu zo skladu"""

    class Meta:
        model = VydajkaZoSkladu
        fields = [
            'material',
            'objednavka',
            'mnozstvo',
            'poznamka',
        ]
        widgets = {
            'material': forms.Select(attrs={'class': 'form-select'}),
            'objednavka': forms.Select(attrs={'class': 'form-select'}),
            'mnozstvo': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'poznamka': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
