# core/forms.py
from django import forms
from .models import Objednavka, Kontrakt, Produkt
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
                'placeholder': 'napr. OBJ-2026-001'
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
            'cislo_objednavky': 'Číslo objednávky *',
            'zakaznik': 'Zákazník *',
            'produkt': 'Produkt *',
            'mnozstvo': 'Množstvo (ks) *',
            'datum_pozadovane': 'Požadovaný termín dodania *',
            'poznamka': 'Poznámka',
        }

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
                'placeholder': 'napr. KONTR-2026-001'
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
            'cislo_kontraktu': 'Číslo kontraktu *',
            'zakaznik': 'Zákazník *',
            'produkt': 'Produkt *',
            'pocet_kusov_celkovo': 'Celkový počet kusov *',
            'datum_od': 'Platnosť od *',
            'datum_do': 'Platnosť do *',
            'je_skladom': 'Tovar bude skladom?',
        }

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
