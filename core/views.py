from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render, get_object_or_404, redirect
from .models import Produkt, Objednavka, Stroj, VyrobnyZaznam, KontrolaKvality, HlasenieVyroby
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
import json


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
    """
    Rázcestník: Presmeruje používateľa podľa toho, aké má práva.
    """
    # 1. Ak má právo vidieť objednávky (Ekonómka / Výroba), pošli ju na Plán
    if request.user.has_perm('core.view_objednavka'):
        return redirect('plan_vyroby')
    
    # 2. Ak má právo vidieť produkty (Technik), pošli ho na Produkty
    elif request.user.has_perm('core.view_produkt'):
        return redirect('zoznam_produktov')
    
    # 3. Ak nemá žiadne práva, zobraz prázdnu stránku alebo správu
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
    """
    Hlavný dashboard operátora - zobrazuje:
    1. Rozpracované zakázky (stav = 'vyroba')
    2. Nové zakázky (stav = 'nova')
    """
    # Rozpracované (operátor už na nich pracuje)
    rozpracovane = Objednavka.objects.filter(
        stav='vyroba',
        zaznamy__operator=request.user,
        zaznamy__typ_udalosti='START'
    ).distinct()
    
    # Nové (ešte nezačaté)
    nove = Objednavka.objects.filter(stav='nova').order_by('datum_pozadovane')
    
    return render(request, 'core/operator/dashboard.html', {
        'rozpracovane': rozpracovane,
        'nove': nove,
    })


@login_required
def operator_zakazka_detail(request, pk):
    """
    Detail zakázky pre operátora s tlačidlami na akcie
    """
    objednavka = get_object_or_404(Objednavka, pk=pk)
    
    # Zisti posledný záznam (START/PAUZA/STOP)
    posledny_zaznam = objednavka.zaznamy.order_by('-cas_zaznamu').first()
    
    # Operácie produktu
    operacie = objednavka.produkt.operacie.all()
    
    context = {
        'objednavka': objednavka,
        'posledny_zaznam': posledny_zaznam,
        'operacie': operacie,
    }
    
    return render(request, 'core/operator/zakazka_detail.html', context)


# ========================================
# AJAX AKCIE (Start, Pauza, Koniec)
# ========================================

@login_required
@require_POST
def start_work(request, pk):
    """Operátor začína prácu na zakázke"""
    objednavka = get_object_or_404(Objednavka, pk=pk)
    
    # Vytvor záznam START
    VyrobnyZaznam.objects.create(
        objednavka=objednavka,
        operator=request.user,
        typ_udalosti='START'
    )
    
    # Zmeň stav na "Vo výrobe"
    objednavka.stav = 'vyroba'
    objednavka.save()
    
    return JsonResponse({'status': 'ok', 'message': 'Práca začatá'})


@login_required
@require_POST
def pause_work(request, pk):
    """Operátor pozastavuje prácu (+ dôvod)"""
    objednavka = get_object_or_404(Objednavka, pk=pk)
    
    data = json.loads(request.body)
    dovod = data.get('dovod', '')
    
    # Vytvor záznam PAUZA
    VyrobnyZaznam.objects.create(
        objednavka=objednavka,
        operator=request.user,
        typ_udalosti='PAUZA',
        dovod_pauzy=dovod
    )
    
    # Zmeň stav na "Pozastavené"
    objednavka.stav = 'pozastavene'
    objednavka.save()
    
    return JsonResponse({'status': 'ok', 'message': 'Práca pozastavená'})


@login_required
@require_POST
def end_work(request, pk):
    """Operátor končí prácu + nahráva fotku kvality"""
    objednavka = get_object_or_404(Objednavka, pk=pk)
    
    # Spracuj multipart form (fotka + data)
    fotka = request.FILES.get('fotka')
    pocet_ok = request.POST.get('pocet_ok', 0)
    pocet_nok = request.POST.get('pocet_nok', 0)
    poznamka = request.POST.get('poznamka', '')
    
    # Vytvor záznam STOP
    VyrobnyZaznam.objects.create(
        objednavka=objednavka,
        operator=request.user,
        typ_udalosti='STOP'
    )
    
    # Ulož kontrolu kvality
    KontrolaKvality.objects.create(
        objednavka=objednavka,
        operator=request.user,
        namerana_hodnota=f"OK: {pocet_ok}, NOK: {pocet_nok}",
        vysledok_ok=(int(pocet_nok) == 0),
        fotka=fotka,
        poznamka=poznamka
    )
    
    # Zmeň stav na "Hotovo" (alebo "Pozastavené" ak sú nepodarky)
    if int(pocet_nok) == 0:
        objednavka.stav = 'hotovo'
    else:
        objednavka.stav = 'pozastavene'
    objednavka.save()
    
    return JsonResponse({'status': 'ok', 'message': 'Práca ukončená'})


@login_required
@require_POST
def report_problem(request, pk):
    """Operátor hlási problém (nepodarok, porucha stroja...)"""
    objednavka = get_object_or_404(Objednavka, pk=pk)
    
    data = json.loads(request.body)
    typ_problemu = data.get('typ_problemu')
    pocet_kusov = data.get('pocet_kusov', 0)
    popis = data.get('popis', '')
    
    # Vytvor hlásenie
    HlasenieVyroby.objects.create(
        objednavka=objednavka,
        operator=request.user,
        typ_problemu=typ_problemu,
        pocet_kusov_nepodarkov=pocet_kusov,
        popis_problemu=popis
    )
    
    return JsonResponse({'status': 'ok', 'message': 'Problém nahlásený'})
