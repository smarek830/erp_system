from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render, get_object_or_404, redirect
from .models import Produkt, Objednavka, Stroj, VyrobnyZaznam, KontrolaKvality, HlasenieVyroby, Operacia
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
import json
from django.http import HttpResponse
from .pdf_generator import generate_sprievodka_pdf

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
    objednavky = Objednavka.objects.exclude(stav="hotovo").order_by("datum_pozadovane")
    return render(request, "core/plan.html", {"objednavky": objednavky})

@login_required
@permission_required("core.view_objednavka", raise_exception=True)
def detail_zakazky(request, pk):
    objednavka = get_object_or_404(Objednavka, pk=pk)
    return render(request, "core/detail_zakazky.html", {"objednavka": objednavka})

@login_required
def home(request):
    if request.user.has_perm('core.view_objednavka'):
        return redirect('plan_vyroby')
    elif request.user.has_perm('core.view_produkt'):
        return redirect('zoznam_produktov')
    else:
        return render(request, 'core/no_access.html')

def zoznam_strojov(request):
    stroje = Stroj.objects.all().order_by('nazov')
    return render(request, 'core/stroje.html', {'stroje': stroje})

# ========================================
# OPERÁTORSKÝ DASHBOARD
# ========================================
@login_required
def operator_dashboard(request):
    rozpracovane = Objednavka.objects.filter(
        stav='vyroba',
        zaznamy__operator=request.user,
        zaznamy__typ_udalosti='START'
    ).distinct()
    
    nove = Objednavka.objects.filter(stav='nova').order_by('datum_pozadovane')
    
    return render(request, 'core/operator/dashboard.html', {
        'rozpracovane': rozpracovane,
        'nove': nove,
    })

@login_required
def operator_zakazka_detail(request, pk):
    objednavka = get_object_or_404(Objednavka, pk=pk)
    operacie = objednavka.produkt.operacie.all()
    
    # Pre každú operáciu nájdi posledný záznam
    for op in operacie:
        op.posledny_zaznam = VyrobnyZaznam.objects.filter(
            objednavka=objednavka,
            operacia=op
        ).order_by('-cas_zaznamu').first()
    
    context = {
        'objednavka': objednavka,
        'operacie': operacie,
    }
    
    return render(request, 'core/operator/zakazka_detail.html', context)

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
    
    # Generuj PDF
    pdf_buffer = generate_sprievodka_pdf(objednavka, request)
    
    # Vráť ako stiahnuteľný súbor
    response = HttpResponse(pdf_buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="sprievodka_{objednavka.cislo_objednavky}.pdf"'
    
    return response