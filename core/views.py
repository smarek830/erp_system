from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render, get_object_or_404, redirect
from .models import (
    Produkt, Objednavka, Stroj, VyrobnyZaznam, KontrolaKvality, 
    HlasenieVyroby, Operacia, Kontrakt, Material, VyrobnaDavka,
    SkladHotovychDielov, PrijemkaHotovychDielov, VydajkaHotovychDielov,
    PrijemkaNaSklad, VydajkaZoSkladu
)
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Q, Sum, Count, F  # ← DÔLEŽITÉ: F je tu!
import json
from .pdf_generator import generate_sprievodka_pdf
from datetime import datetime, timedelta
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

# ========================================
# ZÁKLADNÉ VIEWS (Pre adminov/technikov)
# ========================================

@login_required
@permission_required("core.view_produkt", raise_exception=True)
def zoznam_produktov(request):
    produkty = Produkt.objects.all()
    return render(request, "core/zoznam.html", {"produkty": produkty})

@login_required
@permission_required("core.view_produkt", raise_exception=True)
def detail_produkt(request, pk):
    produkt = get_object_or_404(Produkt, pk=pk)
    return render(request, "core/detail.html", {"produkt": produkt})

@login_required
@permission_required("core.view_objednavka", raise_exception=True)
def plan_vyroby(request):
    """Plán výroby s filtrovaním a vyhľadávaním"""
    search = request.GET.get('search', '')
    stav_filter = request.GET.get('stav', '')
    zakaznik_filter = request.GET.get('zakaznik', '')
    
    kontrakty = Kontrakt.objects.filter(datum_do__gte=timezone.now().date()).select_related('produkt')
    zakazky = Objednavka.objects.exclude(stav="hotovo").select_related('produkt')
    
    if search:
        kontrakty = kontrakty.filter(
            Q(cislo_kontraktu__icontains=search) | Q(zakaznik__icontains=search) |
            Q(produkt__nazov__icontains=search) | Q(produkt__cislo_dielu__icontains=search)
        )
        zakazky = zakazky.filter(
            Q(cislo_objednavky__icontains=search) | Q(zakaznik__icontains=search) |
            Q(produkt__nazov__icontains=search) | Q(produkt__cislo_dielu__icontains=search)
        )
    
    if stav_filter:
        zakazky = zakazky.filter(stav=stav_filter)
    
    if zakaznik_filter:
        kontrakty = kontrakty.filter(zakaznik__icontains=zakaznik_filter)
        zakazky = zakazky.filter(zakaznik__icontains=zakaznik_filter)
    
    kontrakty = kontrakty.order_by('datum_do')
    zakazky = zakazky.order_by('datum_pozadovane')
    
    zakaznici_objednavky = Objednavka.objects.values_list('zakaznik', flat=True).distinct()
    zakaznici_kontrakty = Kontrakt.objects.values_list('zakaznik', flat=True).distinct()
    zakaznici = sorted(set(list(zakaznici_objednavky) + list(zakaznici_kontrakty)))
    
    return render(request, "core/plan.html", {
        "kontrakty": kontrakty, "zakazky": zakazky, "search": search,
        "stav_filter": stav_filter, "zakaznik_filter": zakaznik_filter,
        "zakaznici": zakaznici, "dnes": timezone.now().date(),
    })

@login_required
@permission_required("core.view_objednavka", raise_exception=True)
def export_plan_excel(request):
    """Export plánu výroby do Excel"""
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Kontrakty"
    
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    
    headers1 = ['Číslo kontraktu', 'Zákazník', 'Produkt', 'Číslo dielu', 
                'Celkovo kusov', 'Zostáva dodať', 'Platnosť od', 'Platnosť do', 'Skladom']
    ws1.append(headers1)
    
    for cell in ws1[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    kontrakty = Kontrakt.objects.filter(datum_do__gte=timezone.now().date()).select_related('produkt').order_by('datum_do')
    
    for kontrakt in kontrakty:
        ws1.append([
            kontrakt.cislo_kontraktu, kontrakt.zakaznik, kontrakt.produkt.nazov,
            kontrakt.produkt.cislo_dielu, kontrakt.pocet_kusov_celkovo,
            kontrakt.zostavajuce_mnozstvo, kontrakt.datum_od.strftime('%d.%m.%Y'),
            kontrakt.datum_do.strftime('%d.%m.%Y'), 'Áno' if kontrakt.je_skladom else 'Nie'
        ])
    
    for column in ws1.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws1.column_dimensions[column_letter].width = adjusted_width
    
    ws2 = wb.create_sheet("Zakázky")
    header_fill2 = PatternFill(start_color="70AD47", end_color="70AD47", fill_type="solid")
    
    headers2 = ['Číslo zakázky', 'Zákazník', 'Produkt', 'Číslo dielu', 
                'Množstvo', 'Vyrobené', 'Zostáva', 'Termín', 'Stav', 'Poznámka']
    ws2.append(headers2)
    
    for cell in ws2[1]:
        cell.fill = header_fill2
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    zakazky = Objednavka.objects.exclude(stav="hotovo").select_related('produkt').order_by('datum_pozadovane')
    
    for zakazka in zakazky:
        ws2.append([
            zakazka.cislo_objednavky, zakazka.zakaznik, zakazka.produkt.nazov,
            zakazka.produkt.cislo_dielu, zakazka.mnozstvo, zakazka.vyrobene_mnozstvo,
            zakazka.zostava_vyroba(), zakazka.datum_pozadovane.strftime('%d.%m.%Y'),
            zakazka.get_stav_display(), zakazka.poznamka
        ])
    
    for column in ws2.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws2.column_dimensions[column_letter].width = adjusted_width
    
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="plan_vyroby_{timezone.now().strftime("%Y%m%d")}.xlsx"'
    wb.save(response)
    return response

@login_required
@permission_required("core.view_objednavka", raise_exception=True)
def detail_zakazky(request, pk):
    objednavka = get_object_or_404(Objednavka, pk=pk)
    return render(request, "core/detail_zakazky.html", {"objednavka": objednavka})

@login_required
def home(request):
    """Home dashboard so štatistikami"""
    if not request.user.has_perm('core.view_objednavka'):
        if request.user.has_perm('core.view_produkt'):
            return redirect('zoznam_produktov')
        else:
            return render(request, 'core/no_access.html')
    
    dnes = timezone.now().date()
    celkom_zakazok = Objednavka.objects.exclude(stav='hotovo').count()
    vo_vyrobe = Objednavka.objects.filter(stav='vyroba').count()
    nove_zakazky = Objednavka.objects.filter(stav='nova').count()
    pozastavene = Objednavka.objects.filter(stav='pozastavene').count()
    po_termine = Objednavka.objects.exclude(stav='hotovo').filter(datum_pozadovane__lt=dnes).count()
    dnes_termine = Objednavka.objects.exclude(stav='hotovo').filter(datum_pozadovane=dnes).count()
    tento_tyzden_termine = Objednavka.objects.exclude(stav='hotovo').filter(
        datum_pozadovane__gte=dnes, datum_pozadovane__lt=dnes + timedelta(days=7)
    ).count()
    aktivne_kontrakty = Kontrakt.objects.filter(datum_do__gte=dnes).count()
    kontrakt_exspiruje = Kontrakt.objects.filter(
        datum_do__gte=dnes, datum_do__lt=dnes + timedelta(days=30)
    ).count()
    posledne_zakazky = Objednavka.objects.exclude(stav='hotovo').order_by('-datum_zadania')[:5]
    urgentne_zakazky = Objednavka.objects.exclude(stav='hotovo').filter(
        datum_pozadovane__lte=dnes + timedelta(days=3)
    ).order_by('datum_pozadovane')[:5]
    material_pod_minimum = Material.objects.filter(aktualna_zasoba__lt=F('minimalna_zasoba')).count()
    
    return render(request, 'core/home.html', {
        'celkom_zakazok': celkom_zakazok, 'vo_vyrobe': vo_vyrobe,
        'nove_zakazky': nove_zakazky, 'pozastavene': pozastavene,
        'po_termine': po_termine, 'dnes_termine': dnes_termine,
        'tento_tyzden_termine': tento_tyzden_termine,
        'aktivne_kontrakty': aktivne_kontrakty,
        'kontrakt_exspiruje': kontrakt_exspiruje,
        'posledne_zakazky': posledne_zakazky,
        'urgentne_zakazky': urgentne_zakazky,
        'material_pod_minimum': material_pod_minimum, 'dnes': dnes,
    })

def zoznam_strojov(request):
    stroje = Stroj.objects.all().order_by('nazov')
    return render(request, 'core/stroje.html', {'stroje': stroje})

@login_required
def operator_dashboard(request):
    rozpracovane = Objednavka.objects.filter(
        stav='vyroba', zaznamy__operator=request.user,
        zaznamy__typ_udalosti='START'
    ).distinct()
    nove = Objednavka.objects.filter(stav='nova').order_by('datum_pozadovane')
    return render(request, 'core/operator/dashboard.html', {
        'rozpracovane': rozpracovane, 'nove': nove,
    })

@login_required
def operator_zakazka_detail(request, pk):
    objednavka = get_object_or_404(Objednavka, pk=pk)
    operacie = objednavka.produkt.operacie.all()
    for op in operacie:
        op.posledny_zaznam = VyrobnyZaznam.objects.filter(
            objednavka=objednavka, operacia=op
        ).order_by('-cas_zaznamu').first()
    return render(request, 'core/operator/zakazka_detail.html', {
        'objednavka': objednavka, 'operacie': operacie,
    })
# ========================================
# AJAX AKCIE - TRACKING PER OPERÁCIA
# ========================================

@login_required
@require_POST
def start_operation(request, objednavka_pk, operacia_pk):
    objednavka = get_object_or_404(Objednavka, pk=objednavka_pk)
    operacia = get_object_or_404(Operacia, pk=operacia_pk)
    
    VyrobnyZaznam.objects.create(
        objednavka=objednavka,
        operacia=operacia,
        operator=request.user,
        typ_udalosti='START'
    )
    
    if objednavka.stav == 'nova':
        objednavka.stav = 'vyroba'
        objednavka.save()
    
    return JsonResponse({'status': 'ok', 'message': f'Operácia {operacia.nazov_operacie} začatá'})

@login_required
@require_POST
def pause_operation(request, objednavka_pk, operacia_pk):
    objednavka = get_object_or_404(Objednavka, pk=objednavka_pk)
    operacia = get_object_or_404(Operacia, pk=operacia_pk)
    
    data = json.loads(request.body)
    dovod = data.get('dovod', '')
    
    VyrobnyZaznam.objects.create(
        objednavka=objednavka,
        operacia=operacia,
        operator=request.user,
        typ_udalosti='PAUZA',
        dovod_pauzy=dovod
    )
    
    objednavka.stav = 'pozastavene'
    objednavka.save()
    
    return JsonResponse({'status': 'ok', 'message': 'Operácia pozastavená'})

@login_required
@require_POST
def end_operation(request, objednavka_pk, operacia_pk):
    objednavka = get_object_or_404(Objednavka, pk=objednavka_pk)
    operacia = get_object_or_404(Operacia, pk=operacia_pk)
    
    VyrobnyZaznam.objects.create(
        objednavka=objednavka,
        operacia=operacia,
        operator=request.user,
        typ_udalosti='STOP'
    )
    
    return JsonResponse({'status': 'ok', 'message': f'Operácia {operacia.nazov_operacie} ukončená'})

@login_required
@require_POST
def end_work(request, pk):
    objednavka = get_object_or_404(Objednavka, pk=pk)
    
    fotka = request.FILES.get('fotka')
    pocet_ok = request.POST.get('pocet_ok', 0)
    pocet_nok = request.POST.get('pocet_nok', 0)
    poznamka = request.POST.get('poznamka', '')
    
    KontrolaKvality.objects.create(
        objednavka=objednavka,
        operator=request.user,
        namerana_hodnota=f"OK: {pocet_ok}, NOK: {pocet_nok}",
        vysledok_ok=(int(pocet_nok) == 0),
        fotka=fotka,
        poznamka=poznamka
    )
    
    objednavka.vyrobene_mnozstvo += int(pocet_ok)
    
    if objednavka.je_dokoncena():
        objednavka.stav = 'hotovo'
    else:
        objednavka.stav = 'nova'
    
    objednavka.save()
    
    return JsonResponse({'status': 'ok', 'message': 'Práca ukončená'})

@login_required
@require_POST
def report_problem(request, pk):
    objednavka = get_object_or_404(Objednavka, pk=pk)
    
    data = json.loads(request.body)
    typ_problemu = data.get('typ_problemu')
    pocet_kusov = data.get('pocet_kusov', 0)
    popis = data.get('popis', '')
    
    HlasenieVyroby.objects.create(
        objednavka=objednavka,
        operator=request.user,
        typ_problemu=typ_problemu,
        pocet_kusov_nepodarkov=pocet_kusov,
        popis_problemu=popis
    )
    
    return JsonResponse({'status': 'ok', 'message': 'Problém nahlásený'})

@login_required
def download_sprievodka(request, pk):
    """Stiahnutie PDF sprievodky"""
    objednavka = get_object_or_404(Objednavka, pk=pk)
    pdf_buffer = generate_sprievodka_pdf(objednavka, request)
    response = HttpResponse(pdf_buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="sprievodka_{objednavka.cislo_objednavky}.pdf"'
    return response

@login_required
@permission_required("core.view_objednavka", raise_exception=True)
def vytvor_objednavku_z_davky(request, davka_pk):
    """Vytvorí objednávku z výrobnej dávky"""
    from .models import VyrobnaDavka
    from django.contrib import messages
    
    davka = get_object_or_404(VyrobnaDavka, pk=davka_pk)
    
    if davka.objednavka:
        messages.warning(request, f'Objednávka už existuje: #{davka.objednavka.cislo_objednavky}')
        return redirect('admin:core_objednavka_change', davka.objednavka.pk)
    
    objednavka = davka.vytvor_objednavku()
    messages.success(request, f'✅ Objednávka #{objednavka.cislo_objednavky} bola vytvorená z dávky {davka.cislo_davky}')
    
    return redirect('admin:core_objednavka_change', objednavka.pk)

@login_required
@permission_required("core.view_objednavka", raise_exception=True)
def vytvor_davku_z_kontraktu(request, kontrakt_pk):
    """Rýchle vytvorenie dávky + objednávky z kontraktu"""
    from .models import Kontrakt, VyrobnaDavka
    from django.contrib import messages
    from datetime import timedelta
    
    kontrakt = get_object_or_404(Kontrakt, pk=kontrakt_pk)
    
    if request.method == 'POST':
        mnozstvo = int(request.POST.get('mnozstvo', 0))
        termin_dni = int(request.POST.get('termin_dni', 7))
        
        if mnozstvo <= 0:
            messages.error(request, '❌ Množstvo musí byť väčšie ako 0')
            return redirect('vytvor_davku_z_kontraktu', kontrakt_pk=kontrakt_pk)
        
        if mnozstvo > kontrakt.zostavajuce_mnozstvo:
            messages.error(request, f'❌ Množstvo ({mnozstvo} ks) je väčšie ako zostáva dodať ({kontrakt.zostavajuce_mnozstvo} ks)')
            return redirect('vytvor_davku_z_kontraktu', kontrakt_pk=kontrakt_pk)
        
        pozadovany_termin = timezone.now().date() + timedelta(days=termin_dni)
        
        davka = VyrobnaDavka.objects.create(
            kontrakt=kontrakt,
            mnozstvo_davky=mnozstvo,
            pozadovany_termin=pozadovany_termin,
            datum_vytvorenia=timezone.now().date()
        )
        
        objednavka = davka.vytvor_objednavku()
        
        kontrakt.zostavajuce_mnozstvo -= mnozstvo
        kontrakt.save()
        
        messages.success(request, f'✅ Vytvorená dávka {davka.cislo_davky} a objednávka #{objednavka.cislo_objednavky}')
        return redirect('plan_vyroby')
    
    context = {
        'kontrakt': kontrakt,
    }
    return render(request, 'core/vytvor_davku_form.html', context)
# ========================================
# SKLAD HOTOVÝCH DIELOV
# ========================================

@login_required
@permission_required("core.view_skladhotovychdielov", raise_exception=True)
def sklad_hotovych_dielov(request):
    """Dashboard skladu hotových dielov"""
    from .models import SkladHotovychDielov
    
    sklady = SkladHotovychDielov.objects.select_related('produkt').all()
    
    # Štatistiky
    celkom_produktov = sklady.count()
    pod_minimom = sklady.filter(mnozstvo__lt=F('minimalna_zasoba')).count()
    nad_optimom = sklady.filter(mnozstvo__gt=F('optimalna_zasoba')).count()
    
    # Posledné pohyby
    from .models import PrijemkaHotovychDielov, VydajkaHotovychDielov
    posledne_prijemky = PrijemkaHotovychDielov.objects.select_related('sklad__produkt', 'objednavka').order_by('-datum')[:10]
    posledne_vydajky = VydajkaHotovychDielov.objects.select_related('sklad__produkt', 'objednavka', 'kontrakt').order_by('-datum')[:10]
    
    context = {
        'sklady': sklady,
        'celkom_produktov': celkom_produktov,
        'pod_minimom': pod_minimom,
        'nad_optimom': nad_optimom,
        'posledne_prijemky': posledne_prijemky,
        'posledne_vydajky': posledne_vydajky,
    }
    
    return render(request, 'core/sklad.html', context)

@login_required
@permission_required("core.view_material", raise_exception=True)
def sklad_materialu(request):
    """Dashboard skladu materiálu"""
    materialy = Material.objects.all().order_by('nazov')
    
    # Štatistiky
    celkom = materialy.count()
    pod_minimom = materialy.filter(aktualna_zasoba__lt=F('minimalna_zasoba')).count()
    
    # Posledné pohyby
    posledne_prijemky = PrijemkaNaSklad.objects.select_related('material').order_by('-datum')[:10]
    posledne_vydajky = VydajkaZoSkladu.objects.select_related('material', 'objednavka').order_by('-datum')[:10]
    
    context = {
        'materialy': materialy,
        'celkom': celkom,
        'pod_minimom': pod_minimom,
        'posledne_prijemky': posledne_prijemky,
        'posledne_vydajky': posledne_vydajky,
    }
    
    return render(request, 'core/sklad_materialu.html', context)
