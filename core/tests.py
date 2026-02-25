from decimal import Decimal
from datetime import date, timedelta

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.contrib.auth.models import Permission
from django.utils import timezone

from .models import (
    Stroj, Produkt, Operacia, Objednavka, OperaciaVyroby,
    KontrolnyParameter, KontrolaKvality, MeraniePriKontrole,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stroj():
    return Stroj.objects.get_or_create(nazov='Testovaci stroj')[0]


def _produkt(cislo='T-TEST-001'):
    return Produkt.objects.get_or_create(
        cislo_dielu=cislo,
        defaults={'nazov': f'Testovaci produkt ({cislo})'},
    )[0]


def _objednavka(produkt=None, mnozstvo=10):
    p = produkt or _produkt()
    return Objednavka.objects.create(
        produkt=p,
        zakaznik='Testovaci zakaznik',
        mnozstvo=mnozstvo,
        datum_pozadovane=date.today() + timedelta(days=30),
    )


def _operacia_sablona(produkt, stroj=None):
    s = stroj or _stroj()
    return Operacia.objects.get_or_create(
        produkt=produkt,
        nazov_operacie='Testovacia operacia',
        defaults={'stroj': s, 'cas_kus': 5, 'poradie': 1},
    )[0]


def _operacia_vyroby(objednavka, stav='hotova', vyrobene_kusy=None):
    s = _stroj()
    sablona = _operacia_sablona(objednavka.produkt, s)
    return OperaciaVyroby.objects.create(
        objednavka=objednavka,
        operacia_sablona=sablona,
        stroj=s,
        nazov_operacie=sablona.nazov_operacie,
        cas_kus=sablona.cas_kus,
        cas_pripravy=0,
        stav=stav,
        poradie=1,
        vyrobene_kusy=vyrobene_kusy if vyrobene_kusy is not None else objednavka.mnozstvo,
    )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class ObjednavkaMozeUzavrietTest(TestCase):
    """moze_sa_uzavriet() returns correct (bool, reason) tuples."""

    def test_bez_operacii_nemoze(self):
        obj = _objednavka()
        ok, dovod = obj.moze_sa_uzavriet()
        self.assertFalse(ok)
        self.assertIn('operácie', dovod.lower())

    def test_hotova_operacia_dostatok_kusov_moze(self):
        obj = _objednavka(mnozstvo=5)
        _operacia_vyroby(obj, stav='hotova', vyrobene_kusy=5)
        ok, dovod = obj.moze_sa_uzavriet()
        self.assertTrue(ok, dovod)

    def test_nehotova_operacia_nemoze(self):
        obj = _objednavka(mnozstvo=5)
        _operacia_vyroby(obj, stav='vyroba', vyrobene_kusy=0)
        ok, _ = obj.moze_sa_uzavriet()
        self.assertFalse(ok)

    def test_malo_kusov_nemoze(self):
        obj = _objednavka(mnozstvo=10)
        _operacia_vyroby(obj, stav='hotova', vyrobene_kusy=5)
        ok, dovod = obj.moze_sa_uzavriet()
        self.assertFalse(ok)
        self.assertIn('5', dovod)


class KontrolnyParameterToleranciaTest(TestCase):
    """MeraniePriKontrole.je_v_tolerancii() works correctly."""

    def setUp(self):
        self.produkt = _produkt('T-KP-001')
        self.param = KontrolnyParameter.objects.create(
            produkt=self.produkt,
            nazov='Priemer',
            hodnota_nominalna=Decimal('10.000'),
            tolerancia_plus=Decimal('0.100'),
            tolerancia_minus=Decimal('0.100'),
            jednotka='mm',
            poradie=1,
        )
        self.obj = _objednavka(produkt=self.produkt)
        self.kontrola = KontrolaKvality.objects.create(
            objednavka=self.obj,
            operator=User.objects.create_user('op_kp', password='pass'),
            namerana_hodnota='test',
            vysledok_ok=True,
        )

    def _meranie(self, hodnota):
        return MeraniePriKontrole(
            kontrola=self.kontrola,
            parameter=self.param,
            namerana_hodnota=Decimal(str(hodnota)),
        )

    def test_nominalna_hodnota_je_ok(self):
        self.assertTrue(self._meranie('10.000').je_v_tolerancii())

    def test_horna_hranica_je_ok(self):
        self.assertTrue(self._meranie('10.100').je_v_tolerancii())

    def test_dolna_hranica_je_ok(self):
        self.assertTrue(self._meranie('9.900').je_v_tolerancii())

    def test_nad_toleranciou_je_nok(self):
        self.assertFalse(self._meranie('10.101').je_v_tolerancii())

    def test_pod_toleranciou_je_nok(self):
        self.assertFalse(self._meranie('9.899').je_v_tolerancii())


# ---------------------------------------------------------------------------
# View / API tests
# ---------------------------------------------------------------------------

class UlozKontrolaKvalityViewTest(TestCase):
    """POST /api/operator/kontrola-kvality/<pk>/ behaves correctly."""

    def setUp(self):
        self.user = User.objects.create_user('operator', password='testpass')
        self.produkt = _produkt('T-API-001')
        self.param = KontrolnyParameter.objects.create(
            produkt=self.produkt,
            nazov='Dlzka',
            hodnota_nominalna=Decimal('50.000'),
            tolerancia_plus=Decimal('0.500'),
            tolerancia_minus=Decimal('0.500'),
            jednotka='mm',
            poradie=1,
        )
        self.obj = _objednavka(produkt=self.produkt, mnozstvo=5)
        self.obj.priradeni_operatori.add(self.user)
        self.url = f'/api/operator/kontrola-kvality/{self.obj.pk}/'
        self.client = Client()
        self.client.force_login(self.user)

    def _post(self, extra=None):
        data = {'poznamka_kontroly': 'CI test'}
        if extra:
            data.update(extra)
        return self.client.post(self.url, data=data)

    def test_bez_prihlasenia_presmeruje(self):
        c = Client()
        resp = c.post(self.url, data={})
        self.assertIn(resp.status_code, [302, 403])

    def test_bez_merania_vrati_ok(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        self.assertTrue(data['vysledok_ok'])

    def test_meranie_v_tolerancii_vrati_ok(self):
        resp = self._post({f'meranie_{self.param.id}': '50.000'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        self.assertTrue(data['vysledok_ok'])
        self.assertEqual(MeraniePriKontrole.objects.count(), 1)

    def test_meranie_mimo_tolerancie_vrati_nok(self):
        resp = self._post({f'meranie_{self.param.id}': '999.999'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        self.assertFalse(data['vysledok_ok'])

    def test_neplatna_hodnota_vrati_error(self):
        resp = self._post({f'meranie_{self.param.id}': 'abc'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'error')

    def test_vytvori_zaznam_kontroly(self):
        self._post({f'meranie_{self.param.id}': '50.000'})
        self.assertEqual(KontrolaKvality.objects.filter(objednavka=self.obj).count(), 1)

    def test_cudzemu_operatorovi_vrati_error(self):
        other = User.objects.create_user('other_op', password='pass')
        c = Client()
        c.force_login(other)
        resp = c.post(self.url, data={'poznamka_kontroly': 'x'})
        data = resp.json()
        self.assertEqual(data['status'], 'error')


class KvalitaDashboardViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('manager', password='pass')
        perm = Permission.objects.get(codename='view_kontrolakvality')
        self.user.user_permissions.add(perm)

        self.op = User.objects.create_user('operator_kvalita', password='pass')
        self.produkt = _produkt('T-KVAL-001')
        self.obj = _objednavka(produkt=self.produkt, mnozstvo=10)

        KontrolaKvality.objects.create(
            objednavka=self.obj,
            operator=self.op,
            typ_kontroly='PRIEBEZNA',
            pocet_ok_kusov=8,
            pocet_nok_kusov=2,
            namerana_hodnota='OK/NOK test A',
            vysledok_ok=False,
        )
        KontrolaKvality.objects.create(
            objednavka=self.obj,
            operator=self.op,
            typ_kontroly='FINALNA',
            pocet_ok_kusov=5,
            pocet_nok_kusov=0,
            namerana_hodnota='OK/NOK test B',
            vysledok_ok=True,
        )

        self.client = Client()
        self.client.force_login(self.user)

    def test_dashboard_access(self):
        resp = self.client.get('/kvalita/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['kpi']['pocet_kontrol'], 2)
        self.assertEqual(resp.context['kpi']['ok_kusy'], 13)
        self.assertEqual(resp.context['kpi']['nok_kusy'], 2)

    def test_dashboard_filter_typ(self):
        resp = self.client.get('/kvalita/', {'typ': 'FINALNA'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['kpi']['pocet_kontrol'], 1)
        self.assertEqual(resp.context['kpi']['nok_kusy'], 0)
