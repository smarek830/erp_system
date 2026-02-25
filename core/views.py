from multiprocessing import context
from urllib import request
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth import logout
from django.shortcuts import render, get_object_or_404, redirect
from .models import (
    Produkt, Objednavka, Stroj, VyrobnyZaznam, KontrolaKvality, 
    HlasenieVyroby, Operacia, Kontrakt, Material, VyrobnaDavka,
    SkladHotovychDielov, PrijemkaHotovychDielov, VydajkaHotovychDielov,
    PrijemkaNaSklad, VydajkaZoSkladu, OperaciaVyroby, OperatorNaOperacii,
    KontrolnyParameter, MeraniePriKontrole,
)
from decimal import Decimal, InvalidOperation
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.template.loader import render_to_string
from django.db.models import Q, Sum, Count, F, Prefetch  # ← DÔLEŽITÉ: F je tu!
from django.db.models.functions import TruncDate
import json
import hashlib
from .pdf_generator import generate_sprievodka_pdf
from datetime import datetime, timedelta
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment


@login_required
def quick_logout(request):
    logout(request)
    return redirect('/accounts/login/')


def offline_page(request):
    return render(request, 'core/offline.html')


def service_worker(request):
    content = """const CACHE_NAME = 'erp-pwa-v1';
const OFFLINE_URL = '/offline/';
const PRECACHE_URLS = [
    OFFLINE_URL,
    '/',
    '/manifest.webmanifest',
    '/pwa-icon.svg'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((key) => key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            )
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;

    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    const copy = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
                    return response;
                })
                .catch(async () => {
                    const cached = await caches.match(event.request);
                    if (cached) return cached;
                    return caches.match(OFFLINE_URL);
                })
        );
        return;
    }

    const url = new URL(event.request.url);
    if (url.origin !== self.location.origin) return;

    event.respondWith(
        caches.match(event.request).then((cached) => {
            const networkFetch = fetch(event.request)
                .then((response) => {
                    const copy = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
                    return response;
                })
                .catch(() => cached);

            return cached || networkFetch;
        })
    );
});
"""
    response = HttpResponse(content, content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    return response


def web_manifest(request):
    manifest = {
        'name': 'ERP Systém - Kovovýroba',
        'short_name': 'ERP Kov',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'background_color': '#f8f9fa',
        'theme_color': '#0d6efd',
        'lang': 'sk',
        'icons': [
            {
                'src': '/pwa-icon.svg',
                'sizes': '512x512',
                'type': 'image/svg+xml',
                'purpose': 'any'
            }
        ]
    }
    return HttpResponse(
        json.dumps(manifest, ensure_ascii=False),
        content_type='application/manifest+json'
    )


def pwa_icon(request):
    content = render_to_string('core/pwa/icon.svg')
    return HttpResponse(content, content_type='image/svg+xml')

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
    """Read-only manažérsky prehľad zakázky."""
    zakazka = get_object_or_404(Objednavka, pk=pk)

    vyrobne_davky = []
    if hasattr(zakazka, 'vyrobna_davka') and zakazka.vyrobna_davka:
        vyrobna_davka = zakazka.vyrobna_davka
        if not vyrobna_davka.operacie.exists():
            vyrobna_davka.vytvor_operacie()
        vyrobne_davky.append(vyrobna_davka)

    operacie = (
        zakazka.operacie
        .select_related('stroj', 'operator')
        .prefetch_related('operatori__operator')
        .order_by('poradie')
    )

    for operacia in operacie:
        operacia.spracovane_celkom = operacia.kusy_spracovane_celkom()
        operacia.ciel_kusy = operacia.cielove_kusy_na_spracovanie()
        if operacia.ciel_kusy > 0:
            operacia.progres_percent = int(min(100, round((operacia.spracovane_celkom / operacia.ciel_kusy) * 100)))
        else:
            operacia.progres_percent = 0
        operacia.dostupne_kusy = operacia.get_dostupne_kusy_na_vstupe()
        operacia.operatori_unikatni = list(dict.fromkeys(
            operacia.operatori.values_list('operator__username', flat=True)
        ))

    kontroly = (
        zakazka.kontroly
        .select_related('operator')
        .prefetch_related(
            Prefetch('merania', queryset=MeraniePriKontrole.objects.select_related('parameter'))
        )
        .order_by('-cas_kontroly')
    )

    for kontrola in kontroly:
        kontrola.merani_spolu = kontrola.merania.count()
        kontrola.merani_nok = sum(1 for meranie in kontrola.merania.all() if not meranie.je_v_tolerancii())

    kvalita_sumar = kontroly.aggregate(
        pocet_kontrol=Count('id'),
        ok_kusy=Sum('pocet_ok_kusov'),
        nok_kusy=Sum('pocet_nok_kusov'),
        nok_zaznamy=Count('id', filter=Q(vysledok_ok=False)),
    )
    kvalita_sumar['ok_kusy'] = kvalita_sumar['ok_kusy'] or 0
    kvalita_sumar['nok_kusy'] = kvalita_sumar['nok_kusy'] or 0
    kvalita_sumar['pocet_kontrol'] = kvalita_sumar['pocet_kontrol'] or 0
    kvalita_sumar['nok_zaznamy'] = kvalita_sumar['nok_zaznamy'] or 0

    context = {
        'zakazka': zakazka,
        'vyrobne_davky': vyrobne_davky,
        'operacie': operacie,
        'kontroly': kontroly,
        'kvalita_sumar': kvalita_sumar,
        'dnes': timezone.now().date(),
    }

    return render(request, 'core/detail_zakazky.html', context)



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


@login_required
@permission_required("core.view_kontrolakvality", raise_exception=True)
def kvalita_dashboard(request):
    """Manažérske vyhodnotenie kvality výroby."""
    dnes = timezone.now().date()
    default_od = dnes - timedelta(days=30)

    datum_od = request.GET.get('od') or default_od.isoformat()
    datum_do = request.GET.get('do') or dnes.isoformat()
    typ_kontroly = request.GET.get('typ', '')
    operator_id = request.GET.get('operator', '')

    kontroly = KontrolaKvality.objects.select_related('objednavka', 'operator').order_by('-cas_kontroly')

    try:
        od_date = datetime.strptime(datum_od, '%Y-%m-%d').date()
        kontroly = kontroly.filter(cas_kontroly__date__gte=od_date)
    except ValueError:
        od_date = default_od
        kontroly = kontroly.filter(cas_kontroly__date__gte=od_date)

    try:
        do_date = datetime.strptime(datum_do, '%Y-%m-%d').date()
        kontroly = kontroly.filter(cas_kontroly__date__lte=do_date)
    except ValueError:
        do_date = dnes
        kontroly = kontroly.filter(cas_kontroly__date__lte=do_date)

    if typ_kontroly in {'PRIEBEZNA', 'FINALNA'}:
        kontroly = kontroly.filter(typ_kontroly=typ_kontroly)

    if operator_id.isdigit():
        kontroly = kontroly.filter(operator_id=int(operator_id))

    suma = kontroly.aggregate(
        ok_sum=Sum('pocet_ok_kusov'),
        nok_sum=Sum('pocet_nok_kusov'),
        nok_zaznamy=Count('id', filter=Q(vysledok_ok=False)),
    )
    ok_sum = suma['ok_sum'] or 0
    nok_sum = suma['nok_sum'] or 0
    spolu_kusy = ok_sum + nok_sum
    nok_percento = round((nok_sum / spolu_kusy) * 100, 2) if spolu_kusy else 0

    top_nok_zakazky = list(
        kontroly.values(
            'objednavka__id',
            'objednavka__cislo_objednavky',
            'objednavka__zakaznik',
        )
        .annotate(
            nok_sum=Sum('pocet_nok_kusov'),
            ok_sum=Sum('pocet_ok_kusov'),
            zaznamy=Count('id'),
        )
        .order_by('-nok_sum', '-zaznamy')[:5]
    )

    trend_data = []
    trend_qs = (
        kontroly.annotate(den=F('pocet_ok_kusov') + F('pocet_nok_kusov'))
        .annotate(den_datum=TruncDate('cas_kontroly'))
        .values('den_datum')
        .annotate(
            ok_sum=Sum('pocet_ok_kusov'),
            nok_sum=Sum('pocet_nok_kusov'),
            spolu=Sum('den'),
        )
        .order_by('den_datum')
    )
    for row in trend_qs:
        den_spolu = row['spolu'] or 0
        trend_data.append({
            'datum': row['den_datum'],
            'ok_sum': row['ok_sum'] or 0,
            'nok_sum': row['nok_sum'] or 0,
            'nok_percento': round(((row['nok_sum'] or 0) / den_spolu) * 100, 2) if den_spolu else 0,
        })

    operatori = (
        KontrolaKvality.objects.exclude(operator__isnull=True)
        .values('operator__id', 'operator__username')
        .distinct()
        .order_by('operator__username')
    )

    context = {
        'kontroly': kontroly[:100],
        'operatori': operatori,
        'top_nok_zakazky': top_nok_zakazky,
        'trend_data': trend_data,
        'filtre': {
            'od': od_date.isoformat(),
            'do': do_date.isoformat(),
            'typ': typ_kontroly,
            'operator': operator_id,
        },
        'kpi': {
            'pocet_kontrol': kontroly.count(),
            'ok_kusy': ok_sum,
            'nok_kusy': nok_sum,
            'nok_zaznamy': suma['nok_zaznamy'] or 0,
            'nok_percento': nok_percento,
        },
    }
    return render(request, 'core/kvalita_dashboard.html', context)

@login_required
@permission_required("core.view_stroj", raise_exception=True)
def zoznam_strojov(request):
    stroje = Stroj.objects.all().order_by("nazov")
    from .models import OperaciaVyroby

    for s in stroje:
        operacie = OperaciaVyroby.objects.filter(
            stroj=s,
            stav__in=['caka', 'vyroba', 'pozastavena'],
            objednavka__stav__in=['nova', 'vyroba', 'pozastavene']
        )

        rezervacia_min = 0.0
        for op in operacie:
            zostava = op.get_dostupne_kusy_na_vstupe()
            if zostava <= 0:
                continue
            cas_pripravy = 0
            if op.stav == 'caka' and op.vyrobene_kusy == 0 and op.nepodarky == 0:
                cas_pripravy = op.cas_pripravy
            rezervacia_min += (float(op.cas_kus) * zostava) + cas_pripravy

        s.rezervacia_hodin = round(rezervacia_min / 60, 1)
        s.rezervacia_percent = int(min(100, round((s.rezervacia_hodin / 168) * 100)))
        
        # Pridaj absolútnu hodnotu dní do servisu
        if s.dni_do_servisu is not None and s.dni_do_servisu < 0:
            s.dni_po_termine = abs(s.dni_do_servisu)
        else:
            s.dni_po_termine = None

    return render(request, "core/zoznam_strojov.html", {"stroje": stroje})



@login_required
def operator_dashboard(request):
    now = timezone.now()
    last_30_days = now - timedelta(days=30)

    rozpracovane = Objednavka.objects.filter(
        stav='vyroba', zaznamy__operator=request.user,
        zaznamy__typ_udalosti='START'
    ).select_related('produkt').distinct()

    for obj in rozpracovane:
        total = obj.mnozstvo or 0
        ok_kusy = obj.celkom_ok_kusy or 0
        obj.progress_pct = int(round((ok_kusy / total) * 100)) if total > 0 else 0

    nove_priradene = Objednavka.objects.filter(
        stav='nova', priradeni_operatori=request.user
    ).select_related('produkt').order_by('datum_pozadovane')

    nove_dostupne = Objednavka.objects.filter(
        stav='nova'
    ).exclude(
        priradeni_operatori__isnull=False
    ).select_related('produkt').order_by('datum_pozadovane')

    vyrobene_spolu = OperatorNaOperacii.objects.filter(
        operator=request.user
    ).aggregate(total=Sum('vyrobene_kusy'))['total'] or 0

    vyrobene_30 = OperatorNaOperacii.objects.filter(
        operator=request.user,
        cas_zaciatku__gte=last_30_days
    ).aggregate(total=Sum('vyrobene_kusy'))['total'] or 0

    nepodarky_spolu = HlasenieVyroby.objects.filter(
        operator=request.user,
        typ_problemu='NEPODAROK'
    ).aggregate(total=Sum('pocet_kusov_nepodarkov'))['total'] or 0

    celkove_kusy = vyrobene_spolu + nepodarky_spolu
    zmetkovitost_pct = round((nepodarky_spolu / celkove_kusy) * 100, 1) if celkove_kusy > 0 else 0
    vykonnost_ks_den = round(vyrobene_30 / 30, 1)

    dokoncene_zakazky = Objednavka.objects.filter(
        stav='hotovo',
        zaznamy__operator=request.user,
        zaznamy__typ_udalosti='STOP'
    ).distinct().count()

    posledne_ukony = VyrobnyZaznam.objects.filter(
        operator=request.user
    ).select_related('objednavka').order_by('-cas_zaznamu')[:8]

    operator_name = request.user.get_full_name().strip() or request.user.username
    initials = ''.join(part[0] for part in operator_name.split()[:2]).upper() or request.user.username[:2].upper()
    email = (request.user.email or '').strip().lower()
    avatar_hash = hashlib.md5(email.encode('utf-8')).hexdigest() if email else None
    operator_avatar_url = (
        f"https://www.gravatar.com/avatar/{avatar_hash}?d=identicon&s=200"
        if avatar_hash
        else f"https://ui-avatars.com/api/?name={initials}&background=0d6efd&color=fff&size=200"
    )

    return render(request, 'core/operator/dashboard.html', {
        'rozpracovane': rozpracovane,
        'nove_priradene': nove_priradene,
        'nove_dostupne': nove_dostupne,
        'operator_name': operator_name,
        'operator_initials': initials,
        'operator_avatar_url': operator_avatar_url,
        'vyrobene_spolu': vyrobene_spolu,
        'nepodarky_spolu': nepodarky_spolu,
        'zmetkovitost_pct': zmetkovitost_pct,
        'vykonnost_ks_den': vykonnost_ks_den,
        'dokoncene_zakazky': dokoncene_zakazky,
        'aktivne_zakazky': rozpracovane.count(),
        'priradene_cakajuce': nove_priradene.count(),
        'dostupne_nove': nove_dostupne.count(),
        'posledne_ukony': posledne_ukony,
    })

@login_required
def operator_zakazka_detail(request, pk):
    """Detail zakázky pre operátora s možnosťou riadenia operácií"""
    from django.contrib import messages
    from django.utils import timezone
    from .models import OperaciaVyroby, OperatorNaOperacii
    
    zakazka = get_object_or_404(Objednavka, pk=pk)
    
    # Kontrola, či je operátor priradený k objednávke
    if request.user not in zakazka.priradeni_operatori.all() and not zakazka.zaznamy.filter(operator=request.user).exists():
        messages.error(request, '⚠️ Nie ste priradený k tejto objednávke!')
        return redirect('operator_dashboard')
    
    operacie = zakazka.operacie.all().order_by('poradie')
    
    # Spracovanie akcií operátora
    if request.method == "POST":
        akcia = request.POST.get('akcia')
        operacia_id = request.POST.get('operacia_id')
        
        if operacia_id:
            operacia = get_object_or_404(OperaciaVyroby, pk=operacia_id, objednavka=zakazka)
            
            if akcia == 'zacat':
                # Validácia - môžem začať?
                if not operacia.moze_zacat():
                    predch = operacia.get_predchadzajuca_operacia()
                    if predch and predch.vyrobene_kusy <= 0:
                        messages.error(
                            request, 
                            f'⚠️ Nemôžete začať operáciu {operacia.nazov_operacie}! '
                            f'Predchádzajúca operácia "{predch.nazov_operacie}" ešte nevyrobila žiadne kusy.'
                        )
                    else:
                        messages.error(request, '⚠️ Nemôžete začať túto operáciu!')
                else:
                    operacia.stav = 'vyroba'
                    operacia.datum_zaciatku = timezone.now()
                    operacia.operator = request.user
                    operacia.save()
                    
                    # Vytvor záznam operátora len ak neexistuje otvorený
                    otvoreny = OperatorNaOperacii.objects.filter(
                        operacia=operacia,
                        operator=request.user,
                        cas_konca__isnull=True
                    ).first()
                    if not otvoreny:
                        OperatorNaOperacii.objects.create(
                            operacia=operacia,
                            operator=request.user,
                            cas_zaciatku=timezone.now()
                        )
                    
                    dostupne = operacia.get_dostupne_kusy_na_vstupe()
                    messages.success(
                        request, 
                        f'✅ Začali ste prácu na operácii: {operacia.nazov_operacie}<br>'
                        f'Dostupné kusy: {dostupne} ks'
                    )
            
            elif akcia == 'pauza':
                operacia.stav = 'pozastavena'
                operacia.save()
                
                # Ukončiť aktuálny záznam operátora
                operator_zaznam = operacia.operatori.filter(
                    operator=request.user,
                    cas_konca__isnull=True
                ).first()
                if operator_zaznam:
                    operator_zaznam.cas_konca = timezone.now()
                    operator_zaznam.save()
                
                messages.warning(request, f'⏸️ Operácia pozastavená: {operacia.nazov_operacie}')
            
            elif akcia == 'pokracovat':
                if not operacia.moze_pokracovat():
                    messages.error(request, '⚠️ Nemôžete pokračovať - nie sú dostupné žiadne kusy!')
                else:
                    operacia.stav = 'vyroba'
                    operacia.save()
                    
                    # Vytvor nový záznam operátora len ak neexistuje otvorený
                    otvoreny = OperatorNaOperacii.objects.filter(
                        operacia=operacia,
                        operator=request.user,
                        cas_konca__isnull=True
                    ).first()
                    if not otvoreny:
                        OperatorNaOperacii.objects.create(
                            operacia=operacia,
                            operator=request.user,
                            cas_zaciatku=timezone.now()
                        )
                    
                    dostupne = operacia.get_dostupne_kusy_na_vstupe()
                    messages.success(
                        request, 
                        f'▶️ Pokračujete v práci na: {operacia.nazov_operacie}<br>'
                        f'Zostávajúce kusy: {dostupne} ks'
                    )
            
            elif akcia == 'ukonci_davku':
                vyrobene = int(request.POST.get('vyrobene_kusy', 0))
                nepodarky = int(request.POST.get('nepodarky', 0))
                
                try:
                    operacia.ukonci_davku(vyrobene, nepodarky)
                    
                    # Ukončiť záznam operátora
                    operator_zaznam = operacia.operatori.filter(
                        operator=request.user,
                        cas_konca__isnull=True
                    ).first()
                    if operator_zaznam:
                        operator_zaznam.cas_konca = timezone.now()
                        operator_zaznam.vyrobene_kusy += vyrobene
                        operator_zaznam.save()
                    
                    zostava = operacia.get_dostupne_kusy_na_vstupe()
                    if operacia.stav == 'hotova':
                        messages.success(
                            request, 
                            f'✅ Operácia ÚPLNE UKONČENÁ!<br>'
                            f'Celkovo vyrobené: {operacia.vyrobene_kusy} ks, Nepodarky: {operacia.nepodarky} ks'
                        )
                    else:
                        messages.success(
                            request, 
                            f'✅ Dávka ukončená! Vyrobené: {vyrobene} ks, Nepodarky: {nepodarky} ks<br>'
                            f'Zostáva ešte: {zostava} ks'
                        )
                    
                except ValueError as e:
                    messages.error(request, f'❌ Chyba: {str(e)}')
        
        # Uzavretie zakázky
        elif akcia == 'uzavri_zakazku':
            try:
                fotka_balenia = request.FILES.get('fotka_balenia_final')
                poznamka_balenia = request.POST.get('poznamka_balenia_final', '')

                if not fotka_balenia:
                    messages.error(request, '❌ Pri finálnom uzavretí je povinná fotka balenia.')
                    return redirect('operator_zakazka_detail', pk=pk)

                KontrolaKvality.objects.create(
                    objednavka=zakazka,
                    operator=request.user,
                    typ_kontroly='FINALNA',
                    pocet_ok_kusov=zakazka.celkom_ok_kusy,
                    pocet_nok_kusov=zakazka.celkom_nok_kusy,
                    namerana_hodnota='Finálna kontrola balenia',
                    vysledok_ok=True,
                    fotka_balenia=fotka_balenia,
                    poznamka=poznamka_balenia,
                )

                zakazka.uzavri_zakazku()
                messages.success(
                    request, 
                    f'✅ Zakázka #{zakazka.cislo_objednavky} bola uzavretá a hotové diely boli naskladnené!'
                )
                return redirect('operator_dashboard')
            except ValueError as e:
                messages.error(request, f'❌ {str(e)}')
        
        return redirect('operator_zakazka_detail', pk=pk)
    
    # Výpočet pre každú operáciu
    for op in operacie:
        op.dostupne_kusy = op.get_dostupne_kusy_na_vstupe()
        op.max_kusy = op.get_max_vyrobitelne_kusy()
        op.operatori_list = op.operatori.all()
        op.operatori_unikatni = list(dict.fromkeys(
            op.operatori.select_related('operator').values_list('operator__username', flat=True)
        ))
        op.moze_zacat_teraz = op.moze_zacat()
        # moze_pokracovat_teraz je @property v modele, nemožno priraďovať
    
    # Skontroluj, či sa môže zakázka uzavrieť
    moze_uzavriet, dovod = zakazka.moze_sa_uzavriet()
    
    context = {
        'zakazka': zakazka,
        'operacie': operacie,
        'moze_uzavriet': moze_uzavriet,
        'dovod_neuzvretia': dovod if not moze_uzavriet else None,
        'dnes': timezone.now().date(),
        'kontrolne_parametre': zakazka.produkt.kontrolne_parametre.all(),
        'posledne_kontroly': zakazka.kontroly.select_related('operator').order_by('-cas_kontroly')[:10],
    }
    
    return render(request, 'core/operator_zakazka_detail.html', context)

# ========================================
# AJAX AKCIE - TRACKING PER OPERÁCIA
# ========================================

@login_required
@require_POST
def start_operation(request, objednavka_pk, operacia_pk):
    objednavka = get_object_or_404(Objednavka, pk=objednavka_pk)
    operacia_vyroby = get_object_or_404(OperaciaVyroby, pk=operacia_pk)
    
    # Kontrola, či je operátor priradený k objednávke
    if request.user not in objednavka.priradeni_operatori.all() and not objednavka.zaznamy.filter(operator=request.user).exists():
        return JsonResponse({'status': 'error', 'message': 'Nie ste priradený k tejto objednávke!'})
    
    # Kontrola, či operácia patrí k objednávke
    if operacia_vyroby.objednavka != objednavka:
        return JsonResponse({'status': 'error', 'message': 'Operácia nepatrí k tejto objednávke'})
    
    # Kontrola, či operácia môže pokračovať (pre pozastavené a hotové operácie)
    if operacia_vyroby.stav in ['pozastavena', 'hotova']:
        if not operacia_vyroby.moze_pokracovat():
            return JsonResponse({'status': 'error', 'message': 'Operácia nemôže pokračovať - nie sú dostupné kusy'})
    
    VyrobnyZaznam.objects.create(
        objednavka=objednavka,
        operacia=operacia_vyroby.operacia_sablona,
        operator=request.user,
        typ_udalosti='START'
    )

    otvoreny = OperatorNaOperacii.objects.filter(
        operacia=operacia_vyroby,
        operator=request.user,
        cas_konca__isnull=True
    ).first()
    if not otvoreny:
        OperatorNaOperacii.objects.create(
            operacia=operacia_vyroby,
            operator=request.user,
            cas_zaciatku=timezone.now()
        )
    
    # Priradenie operátora k operácii
    operacia_vyroby.operator = request.user
    operacia_vyroby.stav = 'vyroba'
    operacia_vyroby.datum_zaciatku = timezone.now()
    operacia_vyroby.save()
    
    if objednavka.stav == 'nova':
        objednavka.stav = 'vyroba'
        objednavka.save()
    
    return JsonResponse({'status': 'ok', 'message': f'Operácia {operacia_vyroby.nazov_operacie} začatá'})

@login_required
@require_POST
def pause_operation(request, objednavka_pk, operacia_pk):
    objednavka = get_object_or_404(Objednavka, pk=objednavka_pk)
    operacia_vyroby = get_object_or_404(OperaciaVyroby, pk=operacia_pk)
    
    # Kontrola, či je operátor priradený k objednávke
    if request.user not in objednavka.priradeni_operatori.all() and not objednavka.zaznamy.filter(operator=request.user).exists():
        return JsonResponse({'status': 'error', 'message': 'Nie ste priradený k tejto objednávke!'})
    
    # Kontrola, či operácia patrí k objednávke
    if operacia_vyroby.objednavka != objednavka:
        return JsonResponse({'status': 'error', 'message': 'Operácia nepatrí k tejto objednávke'})
    
    data = json.loads(request.body)
    dovod = data.get('dovod', '')
    
    VyrobnyZaznam.objects.create(
        objednavka=objednavka,
        operacia=operacia_vyroby.operacia_sablona,
        operator=request.user,
        typ_udalosti='PAUZA',
        dovod_pauzy=dovod
    )
    
    operacia_vyroby.stav = 'pozastavena'
    operacia_vyroby.save()

    operator_zaznam = operacia_vyroby.operatori.filter(
        operator=request.user,
        cas_konca__isnull=True
    ).first()
    if operator_zaznam:
        operator_zaznam.cas_konca = timezone.now()
        operator_zaznam.save()
    
    objednavka.stav = 'pozastavene'
    objednavka.save()
    
    return JsonResponse({'status': 'ok', 'message': 'Operácia pozastavená'})

@login_required
@require_POST
def end_operation(request, objednavka_pk, operacia_pk):
    objednavka = get_object_or_404(Objednavka, pk=objednavka_pk)
    operacia_vyroby = get_object_or_404(OperaciaVyroby, pk=operacia_pk)
    
    # Kontrola, či je operátor priradený k objednávke
    if request.user not in objednavka.priradeni_operatori.all() and not objednavka.zaznamy.filter(operator=request.user).exists():
        return JsonResponse({'status': 'error', 'message': 'Nie ste priradený k tejto objednávke!'})
    
    # Kontrola, či operácia patrí k objednávke
    if operacia_vyroby.objednavka != objednavka:
        return JsonResponse({'status': 'error', 'message': 'Operácia nepatrí k tejto objednávke'})
    
    VyrobnyZaznam.objects.create(
        objednavka=objednavka,
        operacia=operacia_vyroby.operacia_sablona,
        operator=request.user,
        typ_udalosti='STOP'
    )
    
    operacia_vyroby.stav = 'hotova'
    operacia_vyroby.datum_ukoncenia = timezone.now()
    operacia_vyroby.save()

    operator_zaznam = operacia_vyroby.operatori.filter(
        operator=request.user,
        cas_konca__isnull=True
    ).first()
    if operator_zaznam:
        operator_zaznam.cas_konca = timezone.now()
        operator_zaznam.save()
    
    return JsonResponse({'status': 'ok', 'message': f'Operácia {operacia_vyroby.nazov_operacie} ukončená'})

@login_required
@require_POST
def end_work(request, pk):
    objednavka = get_object_or_404(Objednavka, pk=pk)
    
    # Kontrola, či je operátor priradený k objednávke
    if request.user not in objednavka.priradeni_operatori.all() and not objednavka.zaznamy.filter(operator=request.user).exists():
        return JsonResponse({'status': 'error', 'message': 'Nie ste priradený k tejto objednávke!'})
    
    # Kontrola, či sú všetky operácie ukončené
    running_operations = objednavka.operacie.filter(stav='vyroba')
    if running_operations.exists():
        operation_names = ', '.join([op.nazov_operacie for op in running_operations])
        return JsonResponse({
            'status': 'error', 
            'message': f'Nemôžete ukončiť prácu! Nasledujúce operácie sú stále aktívné: {operation_names}'
        })
    
    fotka = request.FILES.get('fotka')
    pocet_ok = int(request.POST.get('pocet_ok', 0))
    pocet_nok = int(request.POST.get('pocet_nok', 0))
    poznamka = request.POST.get('poznamka', '')
    
    # Validácia - ak sú NOK kusy, musia byť najprv nahlásené ako problém
    if pocet_nok > 0:
        return JsonResponse({
            'status': 'error', 
            'message': f'Nemôžete ukončiť prácu s {pocet_nok} NOK kusmi! Najprv nahláste problém pomocou formulára "Nahlásiť problém".'
        })
    
    KontrolaKvality.objects.create(
        objednavka=objednavka,
        operator=request.user,
        namerana_hodnota=f"OK: {pocet_ok}, NOK: {pocet_nok}",
        vysledok_ok=True,
        fotka=fotka,
        poznamka=poznamka
    )
    
    objednavka.vyrobene_mnozstvo += pocet_ok
    
    if objednavka.je_dokoncena():
        objednavka.stav = 'hotovo'
    else:
        objednavka.stav = 'nova'
    
    objednavka.save()
    
    return JsonResponse({'status': 'ok', 'message': 'Práca ukončená'})

@login_required
@require_POST
def uloz_kontrolu_kvality(request, pk):
    """Uloženie záznamu kontroly kvality s meraniami a fotkou"""
    objednavka = get_object_or_404(Objednavka, pk=pk)

    if request.user not in objednavka.priradeni_operatori.all() and not objednavka.zaznamy.filter(operator=request.user).exists():
        return JsonResponse({'status': 'error', 'message': 'Nie ste priradený k tejto objednávke!'})

    fotka = request.FILES.get('fotka_kontroly')
    typ_kontroly = request.POST.get('typ_kontroly', 'PRIEBEZNA')
    if typ_kontroly not in ['PRIEBEZNA', 'FINALNA']:
        typ_kontroly = 'PRIEBEZNA'

    try:
        pocet_ok_kusov = int(request.POST.get('pocet_ok_kontroly') or 0)
        pocet_nok_kusov = int(request.POST.get('pocet_nok_kontroly') or 0)
    except ValueError:
        return JsonResponse({'status': 'error', 'message': 'Počet kusov musí byť celé číslo.'})

    if pocet_ok_kusov < 0 or pocet_nok_kusov < 0:
        return JsonResponse({'status': 'error', 'message': 'Počet kusov nemôže byť záporný.'})

    poznamka = request.POST.get('poznamka_kontroly', '')

    parametre = objednavka.produkt.kontrolne_parametre.all()
    merania_data = []
    vsetky_ok = True

    for param in parametre:
        hodnota_str = request.POST.get(f'meranie_{param.id}', '').strip()
        if hodnota_str:
            try:
                hodnota = Decimal(hodnota_str)
                min_h = param.hodnota_nominalna - param.tolerancia_minus
                max_h = param.hodnota_nominalna + param.tolerancia_plus
                if not (min_h <= hodnota <= max_h):
                    vsetky_ok = False
                merania_data.append((param, hodnota))
            except InvalidOperation:
                return JsonResponse({'status': 'error', 'message': f'Neplatná hodnota pre parameter "{param.nazov}"'})

    namerana_text = ', '.join([f"{p.nazov}: {v} {p.jednotka}" for p, v in merania_data]) if merania_data else 'Bez meraní'

    kontrola = KontrolaKvality.objects.create(
        objednavka=objednavka,
        operator=request.user,
        typ_kontroly=typ_kontroly,
        pocet_ok_kusov=pocet_ok_kusov,
        pocet_nok_kusov=pocet_nok_kusov,
        namerana_hodnota=namerana_text,
        vysledok_ok=vsetky_ok,
        fotka=fotka,
        poznamka=poznamka,
    )

    for param, hodnota in merania_data:
        MeraniePriKontrole.objects.create(
            kontrola=kontrola,
            parameter=param,
            namerana_hodnota=hodnota,
        )

    vysledok_text = '✅ OK' if vsetky_ok else '❌ NOK – niektoré hodnoty sú mimo tolerancie'
    typ_text = 'Priebežná kontrola' if typ_kontroly == 'PRIEBEZNA' else 'Finálna kontrola'
    return JsonResponse({
        'status': 'ok',
        'message': f'{typ_text} uložená. Výsledok: {vysledok_text}',
        'vysledok_ok': vsetky_ok,
        'kontrola_id': kontrola.id,
    })

@login_required
@require_POST
def report_problem(request, pk):
    objednavka = get_object_or_404(Objednavka, pk=pk)
    
    # Kontrola, či je operátor priradený k objednávke
    if request.user not in objednavka.priradeni_operatori.all() and not objednavka.zaznamy.filter(operator=request.user).exists():
        return JsonResponse({'status': 'error', 'message': 'Nie ste priradený k tejto objednávke!'})
    
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
@require_POST
def operator_prevziat_zakazku(request, pk):
    """Operátor prevzme novú objednávku priamo bez sub-batch"""
    objednavka = get_object_or_404(Objednavka, pk=pk)
    
    # Kontrola, či je objednávka v stave 'nova' a nie je už priradená
    if objednavka.stav != 'nova':
        return JsonResponse({'status': 'error', 'message': 'Objednávka nie je dostupná na prevzatie!'})
    
    if objednavka.priradeni_operatori.exists():
        return JsonResponse({'status': 'error', 'message': 'Objednávka už má priradených operátorov!'})
    
    # Priradiť operátora k objednávke
    objednavka.priradeni_operatori.add(request.user)
    objednavka.stav = 'vyroba'
    objednavka.save()
    
    # Vytvoriť záznam o začatí práce
    VyrobnyZaznam.objects.create(
        objednavka=objednavka,
        operator=request.user,
        typ_udalosti='START'
    )
    
    return JsonResponse({'status': 'ok', 'message': f'Zakázka #{objednavka.cislo_objednavky} bola prevzatá!'})

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
    from math import ceil
    materialy = Material.objects.all().order_by('nazov')
    otvorene_zakazky = Objednavka.objects.exclude(stav='hotovo').select_related('produkt', 'produkt__material_ref')

    potreby = {}
    for zakazka in otvorene_zakazky:
        produkt = zakazka.produkt
        material = produkt.material_ref
        if not material:
            continue
        if not produkt.dlzka_na_kus_mm or produkt.dlzka_na_kus_mm <= 0:
            continue
        if not material.kg_na_meter or material.kg_na_meter <= 0:
            continue

        dlzka_m = (float(produkt.dlzka_na_kus_mm) * zakazka.mnozstvo) / 1000
        kg = dlzka_m * float(material.kg_na_meter)
        tyc_dlzka_m = float(material.tyc_dlzka_m or 0)
        tyce = ceil(dlzka_m / tyc_dlzka_m) if tyc_dlzka_m > 0 else 0

        data = potreby.setdefault(material.id, {'m': 0.0, 'kg': 0.0, 'tyce': 0})
        data['m'] += dlzka_m
        data['kg'] += kg
        data['tyce'] += tyce

    for material in materialy:
        data = potreby.get(material.id, {'m': 0.0, 'kg': 0.0, 'tyce': 0})
        material.potreba_m = round(data['m'], 2)
        material.potreba_kg = round(data['kg'], 2)
        material.potreba_tyce = data['tyce']
        if material.jednotka.lower() == 'kg':
            material.nedostatok_kg = round(max(0.0, material.potreba_kg - float(material.aktualna_zasoba)), 2)
        else:
            material.nedostatok_kg = None
    
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


# ========================================
# WEB FORMULÁRE PRE OBJEDNÁVKY A KONTRAKTY
# ========================================

@login_required
@permission_required("core.add_objednavka", raise_exception=True)
def nova_objednavka(request):
    """Vytvorenie novej objednávky cez webový formulár"""
    from .forms import ObjednavkaForm
    from django.contrib import messages
    from .models import SkladHotovychDielov
    from .models import Produkt
    
    if request.method == 'POST':
        form = ObjednavkaForm(request.POST)
        if form.is_valid():
            objednavka = form.save(commit=False)
            objednavka.stav = 'nova'
            objednavka.vyrobene_mnozstvo = 0
            objednavka.save()
            
            messages.success(request, f'✅ Objednávka #{objednavka.cislo_objednavky} bola úspešne vytvorená!')
            return redirect('plan_vyroby')
    else:
        form = ObjednavkaForm()
    
    sklad_map = {
        sklad.produkt_id: sklad.mnozstvo
        for sklad in SkladHotovychDielov.objects.all()
    }

    produkt_material_map = {}
    for produkt in Produkt.objects.select_related('material_ref'):
        material = produkt.material_ref
        if not material:
            continue
        produkt_material_map[produkt.id] = {
            'material_nazov': material.nazov,
            'material_kod': material.kod,
            'jednotka': material.jednotka,
            'zasoba': float(material.aktualna_zasoba),
            'dlzka_na_kus_mm': float(produkt.dlzka_na_kus_mm or 0),
            'tyc_dlzka_m': float(material.tyc_dlzka_m or 0),
            'kg_na_meter': float(material.kg_na_meter or 0),
            'priemer_mm': float(material.priemer_mm or 0),
        }

    context = {
        'form': form,
        'title': 'Nová objednávka',
        'submit_text': 'Vytvoriť objednávku',
        'sklad_map': sklad_map,
        'produkt_material_map': produkt_material_map,
    }
    return render(request, 'core/nova_objednavka.html', context)


@login_required
@permission_required("core.add_kontrakt", raise_exception=True)
def novy_kontrakt(request):
    """Vytvorenie nového kontraktu cez webový formulár"""
    from .forms import KontraktForm
    from django.contrib import messages
    
    if request.method == 'POST':
        form = KontraktForm(request.POST)
        if form.is_valid():
            kontrakt = form.save()
            messages.success(request, f'✅ Kontrakt #{kontrakt.cislo_kontraktu} bol úspešne vytvorený!')
            return redirect('plan_vyroby')
    else:
        form = KontraktForm()
    
    context = {
        'form': form,
        'title': 'Nový kontrakt',
        'submit_text': 'Vytvoriť kontrakt',
    }
    return render(request, 'core/novy_kontrakt.html', context)


@login_required
@permission_required("core.change_objednavka", raise_exception=True)
def upravit_objednavku(request, pk):
    """Úprava existujúcej objednávky"""
    from .forms import ObjednavkaForm
    from django.contrib import messages
    from .models import SkladHotovychDielov
    from .models import Produkt
    
    objednavka = get_object_or_404(Objednavka, pk=pk)
    
    if request.method == 'POST':
        form = ObjednavkaForm(request.POST, instance=objednavka)
        if form.is_valid():
            form.save()
            messages.success(request, f'✅ Objednávka #{objednavka.cislo_objednavky} bola aktualizovaná!')
            return redirect('detail_zakazky', pk=objednavka.pk)
    else:
        form = ObjednavkaForm(instance=objednavka)
    
    sklad_map = {
        sklad.produkt_id: sklad.mnozstvo
        for sklad in SkladHotovychDielov.objects.all()
    }

    produkt_material_map = {}
    for produkt in Produkt.objects.select_related('material_ref'):
        material = produkt.material_ref
        if not material:
            continue
        produkt_material_map[produkt.id] = {
            'material_nazov': material.nazov,
            'material_kod': material.kod,
            'jednotka': material.jednotka,
            'zasoba': float(material.aktualna_zasoba),
            'dlzka_na_kus_mm': float(produkt.dlzka_na_kus_mm or 0),
            'tyc_dlzka_m': float(material.tyc_dlzka_m or 0),
            'kg_na_meter': float(material.kg_na_meter or 0),
            'priemer_mm': float(material.priemer_mm or 0),
        }

    context = {
        'form': form,
        'title': f'Upraviť objednávku #{objednavka.cislo_objednavky}',
        'submit_text': 'Uložiť zmeny',
        'objednavka': objednavka,
        'sklad_map': sklad_map,
        'produkt_material_map': produkt_material_map,
    }
    return render(request, 'core/nova_objednavka.html', context)


@login_required
@permission_required("core.change_kontrakt", raise_exception=True)
def upravit_kontrakt(request, pk):
    """Úprava existujúceho kontraktu"""
    from .forms import KontraktForm
    from django.contrib import messages
    
    kontrakt = get_object_or_404(Kontrakt, pk=pk)
    
    if request.method == 'POST':
        form = KontraktForm(request.POST, instance=kontrakt)
        if form.is_valid():
            form.save()
            messages.success(request, f'✅ Kontrakt #{kontrakt.cislo_kontraktu} bol aktualizovaný!')
            return redirect('plan_vyroby')
    else:
        form = KontraktForm(instance=kontrakt)
    
    context = {
        'form': form,
        'title': f'Upraviť kontrakt #{kontrakt.cislo_kontraktu}',
        'submit_text': 'Uložiť zmeny',
        'kontrakt': kontrakt,
    }
    return render(request, 'core/novy_kontrakt.html', context)


# ========================================
# WEBOVÉ ROZHRANIA PRE STROJE
# ========================================

@login_required
@permission_required("core.add_stroj", raise_exception=True)
def novy_stroj(request):
    """Vytvorenie nového stroja"""
    from .forms import StrojForm
    from django.contrib import messages

    if request.method == "POST":
        form = StrojForm(request.POST, request.FILES)  # DÔLEŽITÉ: request.FILES
        if form.is_valid():
            stroj = form.save()
            messages.success(request, f'✅ Stroj "{stroj.nazov}" bol vytvorený!')
            return redirect("zoznam_strojov")
    else:
        form = StrojForm()

    context = {
        "form": form,
        "title": "Nový stroj",
        "submit_text": "Vytvoriť stroj",
    }

    return render(request, "core/novy_stroj.html", context)


@login_required
@permission_required("core.change_stroj", raise_exception=True)
def upravit_stroj(request, pk):
    """Úprava existujúceho stroja"""
    from .forms import StrojForm
    from django.contrib import messages

    stroj = get_object_or_404(Stroj, pk=pk)

    if request.method == "POST":
        form = StrojForm(request.POST, request.FILES, instance=stroj)  # DÔLEŽITÉ: request.FILES
        if form.is_valid():
            stroj = form.save()
            messages.success(request, f'✅ Stroj "{stroj.nazov}" bol aktualizovaný!')
            return redirect("zoznam_strojov")
    else:
        form = StrojForm(instance=stroj)

    context = {
        "form": form,
        "title": f"Upraviť stroj: {stroj.nazov}",
        "submit_text": "Uložiť zmeny",
        "stroj": stroj,
    }

    return render(request, "core/upravit_stroj.html", context)




# ========================================
# WEBOVÉ ROZHRANIA PRE PRODUKTY
# ========================================

@login_required
@permission_required("core.add_produkt", raise_exception=True)
def novy_produkt(request):
    """Vytvorenie nového produktu"""
    from .forms import ProduktForm
    from django.contrib import messages
    
    if request.method == 'POST':
        form = ProduktForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f'✅ Produkt "{form.instance.nazov}" bol vytvorený!')
            return redirect('zoznam_produktov')
    else:
        form = ProduktForm()
    
    context = {
        'form': form,
        'title': 'Nový produkt',
        'submit_text': 'Vytvoriť produkt',
    }
    
    return render(request, 'core/form_universal.html', context)

@login_required
@permission_required("core.change_produkt", raise_exception=True)
def upravit_produkt(request, pk):
    """Uprava existujúceho produktu"""
    from .forms import ProduktForm
    from django.contrib import messages
    
    produkt = get_object_or_404(Produkt, pk=pk)
    
    if request.method == 'POST':
        form = ProduktForm(request.POST, instance=produkt)
        if form.is_valid():
            form.save()
            messages.success(request, f'✅ Produkt "{produkt.nazov}" bol aktualizovaný!')
            return redirect('detail_produkt', pk=produkt.pk)
    else:
        form = ProduktForm(instance=produkt)
    
    context = {
        'form': form,
        'title': f'Upraviť produkt #{produkt.nazov}',
        'submit_text': 'Uložiť zmeny',
        'produkt': produkt,
    }
    
    return render(request, 'core/novy_produkt.html', context)


@login_required
@permission_required("core.add_material", raise_exception=True)
def novy_material(request):
    """Vytvorenie nového materiálu"""
    from .forms import MaterialForm
    from django.contrib import messages

    if request.method == 'POST':
        form = MaterialForm(request.POST)
        if form.is_valid():
            material = form.save()
            messages.success(request, f'✅ Materiál "{material.nazov}" bol vytvorený!')
            return redirect('sklad_materialu')
    else:
        form = MaterialForm()

    context = {
        'form': form,
        'title': 'Nový materiál',
        'submit_text': 'Vytvoriť materiál',
    }

    return render(request, 'core/form_universal.html', context)


@login_required
@permission_required("core.change_material", raise_exception=True)
def upravit_material(request, pk):
    """Úprava existujúceho materiálu"""
    from .forms import MaterialForm
    from django.contrib import messages

    material = get_object_or_404(Material, pk=pk)

    if request.method == 'POST':
        form = MaterialForm(request.POST, instance=material)
        if form.is_valid():
            form.save()
            messages.success(request, f'✅ Materiál "{material.nazov}" bol aktualizovaný!')
            return redirect('sklad_materialu')
    else:
        form = MaterialForm(instance=material)

    context = {
        'form': form,
        'title': f'Upraviť materiál: {material.nazov}',
        'submit_text': 'Uložiť zmeny',
    }

    return render(request, 'core/form_universal.html', context)


@login_required
@permission_required("core.change_skladhotovychdielov", raise_exception=True)
def upravit_sklad_hotovych_dielov(request, pk):
    """Úprava položky skladu hotových dielov"""
    from .forms import SkladHotovychDielovForm
    from django.contrib import messages

    sklad = get_object_or_404(SkladHotovychDielov, pk=pk)

    if request.method == 'POST':
        form = SkladHotovychDielovForm(request.POST, instance=sklad)
        if form.is_valid():
            form.save()
            messages.success(request, f'✅ Skladová položka "{sklad.produkt.nazov}" bola aktualizovaná!')
            return redirect('sklad_hotovych_dielov')
    else:
        form = SkladHotovychDielovForm(instance=sklad)

    context = {
        'form': form,
        'title': f'Upraviť skladovú položku: {sklad.produkt.nazov}',
        'submit_text': 'Uložiť zmeny',
    }

    return render(request, 'core/form_universal.html', context)


@login_required
@permission_required("core.add_skladhotovychdielov", raise_exception=True)
def novy_sklad_hotovych_dielov(request):
    """Vytvorenie novej položky skladu hotových dielov"""
    from .forms import SkladHotovychDielovForm
    from django.contrib import messages

    if request.method == 'POST':
        form = SkladHotovychDielovForm(request.POST)
        if form.is_valid():
            sklad = form.save()
            messages.success(request, f'✅ Skladová položka "{sklad.produkt.nazov}" bola vytvorená!')
            return redirect('sklad_hotovych_dielov')
    else:
        form = SkladHotovychDielovForm()

    context = {
        'form': form,
        'title': 'Nová skladová položka',
        'submit_text': 'Vytvoriť položku',
    }

    return render(request, 'core/form_universal.html', context)


# ========================================
# WEBOVÉ ROZHRANIA PRE VÝROBNÉ DÁVKY
# ========================================

@login_required
@permission_required("core.add_vyrobnadavka", raise_exception=True)
def nova_vyrobna_davka(request, kontrakt_pk):
    """Vytvorenie novej výrobnej dávky z kontraktu"""
    from .forms import VyrobnaDavkaForm
    from django.contrib import messages
    
    kontrakt = get_object_or_404(Kontrakt, pk=kontrakt_pk)
    
    if request.method == 'POST':
        form = VyrobnaDavkaForm(request.POST)
        if form.is_valid():
            davka = form.save(commit=False)
            davka.kontrakt = kontrakt
            davka.save()
            messages.success(request, f'✅ Výrobná dávka "{davka.cislo_davky}" bola vytvorená!')
            return redirect('detail_kontrakt', pk=kontrakt.pk)
    else:
        form = VyrobnaDavkaForm()
    
    context = {
        'form': form,
        'title': f'Nová výrobná dávka pre kontrakt {kontrakt.cislo_kontraktu}',
        'submit_text': 'Vytvoriť dávku',
        'kontrakt': kontrakt,
    }
    
    return render(request, 'core/form_universal.html', context)

# ========================================
# WEBOVÉ ROZHRANIA PRE SKLAD HOTOVÝCH DIELOV
# ========================================

@login_required
@permission_required("core.add_prijemkahotovychdielov", raise_exception=True)
def nova_prijemka(request):
    """Príjemka hotových dielov na sklad"""
    from .forms import PrijemkaHotovychDielovForm
    from django.contrib import messages
    
    initial = {}
    sklad_id = request.GET.get('sklad')
    if sklad_id:
        initial['sklad'] = sklad_id

    if request.method == 'POST':
        form = PrijemkaHotovychDielovForm(request.POST)
        if form.is_valid():
            prijemka = form.save(commit=False)
            prijemka.operator = request.user
            prijemka.save()
            messages.success(request, f'✅ Príjemka +{prijemka.mnozstvo} ks bola zaznamemaná!')
            return redirect('sklad_hotovych_dielov')
    else:
        form = PrijemkaHotovychDielovForm(initial=initial)
    
    context = {
        'form': form,
        'title': 'Nová príjemka',
        'submit_text': 'Naskladniť',
    }
    
    return render(request, 'core/form_universal.html', context)

@login_required
@permission_required("core.add_vydajkahotovychdielov", raise_exception=True)
def nova_vydajka(request):
    """Výdajka hotových dielov zo skladu"""
    from .forms import VydajkaHotovychDielovForm
    from django.contrib import messages
    
    initial = {}
    sklad_id = request.GET.get('sklad')
    if sklad_id:
        initial['sklad'] = sklad_id

    if request.method == 'POST':
        form = VydajkaHotovychDielovForm(request.POST)
        if form.is_valid():
            try:
                vydajka = form.save(commit=False)
                vydajka.operator = request.user
                vydajka.save()
                messages.success(request, f'✅ Výdajka -{vydajka.mnozstvo} ks bola zaznamemaná!')
                return redirect('sklad_hotovych_dielov')
            except ValueError as e:
                messages.error(request, f'❌ {str(e)}')
    else:
        form = VydajkaHotovychDielovForm(initial=initial)
    
    context = {
        'form': form,
        'title': 'Nová výdajka',
        'submit_text': 'Vydať',
    }
    
    return render(request, 'core/form_universal.html', context)


@login_required
@permission_required("core.add_prijemkanasklad", raise_exception=True)
def nova_prijemka_materialu(request):
    """Príjemka materiálu na sklad"""
    from .forms import PrijemkaNaSkladForm
    from django.contrib import messages

    initial = {}
    material_id = request.GET.get('material')
    if material_id:
        initial['material'] = material_id

    if request.method == 'POST':
        form = PrijemkaNaSkladForm(request.POST)
        if form.is_valid():
            prijemka = form.save()
            messages.success(request, f'✅ Príjemka +{prijemka.mnozstvo} {prijemka.material.jednotka} bola zaznamenaná!')
            return redirect('sklad_materialu')
    else:
        form = PrijemkaNaSkladForm(initial=initial)

    context = {
        'form': form,
        'title': 'Nová príjemka materiálu',
        'submit_text': 'Naskladniť',
    }

    return render(request, 'core/form_universal.html', context)


@login_required
@permission_required("core.add_vydajkazoskladu", raise_exception=True)
def nova_vydajka_materialu(request):
    """Výdajka materiálu zo skladu"""
    from .forms import VydajkaZoSkladuForm
    from django.contrib import messages

    initial = {}
    material_id = request.GET.get('material')
    if material_id:
        initial['material'] = material_id

    if request.method == 'POST':
        form = VydajkaZoSkladuForm(request.POST)
        if form.is_valid():
            vydajka = form.save(commit=False)
            vydajka.operator = request.user

            if vydajka.mnozstvo > vydajka.material.aktualna_zasoba:
                messages.error(
                    request,
                    f'❌ Nedostatok materiálu na sklade. Dostupné: {vydajka.material.aktualna_zasoba} {vydajka.material.jednotka}.',
                )
            else:
                vydajka.save()
                messages.success(request, f'✅ Výdajka -{vydajka.mnozstvo} {vydajka.material.jednotka} bola zaznamenaná!')
                return redirect('sklad_materialu')
    else:
        form = VydajkaZoSkladuForm(initial=initial)

    context = {
        'form': form,
        'title': 'Nová výdajka materiálu',
        'submit_text': 'Vydať',
    }

    return render(request, 'core/form_universal.html', context)
