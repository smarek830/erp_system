from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render, get_object_or_404
from .models import Produkt, Objednavka, Stroj
from django.shortcuts import redirect

def zoznam_produktov(request):
    # Vytiahni všetky produkty z databázy
    produkty = Produkt.objects.all()
    return render(request, 'core/zoznam.html', {'produkty': produkty})

def detail_produkt(request, pk):
    # Vytiahni konkrétny produkt podľa ID (pk), alebo vyhoď chybu 404
    produkt = get_object_or_404(Produkt, pk=pk)
    return render(request, 'core/detail.html', {'produkt': produkt})

def plan_vyroby(request):
    # Ukáž len objednávky, ktoré NIE SÚ hotové
    objednavky = Objednavka.objects.exclude(stav='hotovo').order_by('datum_pozadovane')
    return render(request, 'core/plan.html', {'objednavky': objednavky})

def detail_zakazky(request, pk):
    objednavka = get_object_or_404(Objednavka, pk=pk)
    return render(request, 'core/detail_zakazky.html', {'objednavka': objednavka})

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
    