from decimal import Decimal
from datetime import date, timedelta

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

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


class ProduktEditPageRenderTest(TestCase):
    def test_upravit_produkt_page_renders_for_user_with_permission(self):
        user = User.objects.create_user('edit_produkt_user', password='pass')
        perm = Permission.objects.get(codename='change_produkt')
        user.user_permissions.add(perm)

        produkt = _produkt('T-EDIT-PAGE-001')

        client = Client()
        client.force_login(user)

        url = reverse('upravit_produkt', kwargs={'pk': produkt.pk})
        resp = client.get(url)

        self.assertEqual(resp.status_code, 200)
        self.assertIn('Upraviť produkt', resp.content.decode('utf-8'))

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


# ---------------------------------------------------------------------------
# New feature tests
# ---------------------------------------------------------------------------

class MaterialVydajkaAutoTest(TestCase):
    """_vydaj_material() deducts raw material when order enters 'vyroba'."""

    def setUp(self):
        from .models import Material, Produkt as P
        self.material = Material.objects.create(
            nazov='Test materiál',
            kod='MAT-AUTO-001',
            aktualna_zasoba=Decimal('100.000'),
            jednotka='kg',
            kg_na_meter=Decimal('2.000'),
            tyc_dlzka_m=Decimal('6.00'),
        )
        self.produkt = Produkt.objects.get_or_create(
            cislo_dielu='T-AUTO-MAT-001',
            defaults={
                'nazov': 'Testovaci produkt auto mat',
                'material_ref': self.material,
                'dlzka_na_kus_mm': Decimal('500.00'),
            }
        )[0]
        self.produkt.material_ref = self.material
        self.produkt.dlzka_na_kus_mm = Decimal('500.00')
        self.produkt.save()

    def test_material_deducted_on_vyroba(self):
        from .models import VydajkaZoSkladu, Material
        obj = _objednavka(produkt=self.produkt, mnozstvo=10)
        self.assertEqual(VydajkaZoSkladu.objects.filter(objednavka=obj).count(), 0)

        obj.stav = 'vyroba'
        obj.save()

        vydajky = VydajkaZoSkladu.objects.filter(objednavka=obj)
        self.assertEqual(vydajky.count(), 1)

        material = Material.objects.get(pk=self.material.pk)
        # 10 ks * 0.5 m/ks * 2 kg/m = 10 kg
        expected_kg = Decimal('10.000')
        self.assertEqual(vydajky.first().mnozstvo, expected_kg)
        self.assertEqual(material.aktualna_zasoba, Decimal('100.000') - expected_kg)

    def test_material_not_double_deducted(self):
        from .models import VydajkaZoSkladu
        obj = _objednavka(produkt=self.produkt, mnozstvo=5)
        obj.stav = 'vyroba'
        obj.save()

        # Call save() again with vyroba – should not create another vydajka
        obj.stav = 'vyroba'
        obj.save()

        self.assertEqual(VydajkaZoSkladu.objects.filter(objednavka=obj).count(), 1)


class EndWorkWarehouseTest(TestCase):
    """end_work view creates PrijemkaHotovychDielov for OK pieces."""

    def setUp(self):
        self.user = User.objects.create_user('op_endwork', password='pass')
        self.produkt = _produkt('T-ENDWORK-001')
        self.obj = _objednavka(produkt=self.produkt, mnozstvo=10)
        self.obj.priradeni_operatori.add(self.user)
        self.client = Client()
        self.client.force_login(self.user)

    def test_end_work_creates_prijemka(self):
        from .models import PrijemkaHotovychDielov
        url = reverse('end_work', kwargs={'pk': self.obj.pk})
        resp = self.client.post(url, {'pocet_ok': 5, 'poznamka': 'test smena'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')

        prijemky = PrijemkaHotovychDielov.objects.filter(objednavka=self.obj)
        self.assertEqual(prijemky.count(), 1)
        self.assertEqual(prijemky.first().mnozstvo, 5)

    def test_end_work_zero_pieces_no_prijemka(self):
        from .models import PrijemkaHotovychDielov
        url = reverse('end_work', kwargs={'pk': self.obj.pk})
        resp = self.client.post(url, {'pocet_ok': 0})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PrijemkaHotovychDielov.objects.filter(objednavka=self.obj).count(), 0)


class OperatorApiValidationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('op_api_valid', password='pass')
        self.produkt = _produkt('T-OP-API-001')
        self.obj = _objednavka(produkt=self.produkt, mnozstvo=10)
        self.obj.priradeni_operatori.add(self.user)
        self.operacia = _operacia_vyroby(self.obj, stav='vyroba', vyrobene_kusy=0)
        self.client = Client()
        self.client.force_login(self.user)

    def test_pause_operation_invalid_json_returns_error(self):
        url = reverse('pause_operation', kwargs={
            'objednavka_pk': self.obj.pk,
            'operacia_pk': self.operacia.pk,
        })
        resp = self.client.post(
            url,
            data='{"dovod": "ok"',
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'error')

    def test_end_work_invalid_integer_returns_error(self):
        url = reverse('end_work', kwargs={'pk': self.obj.pk})
        resp = self.client.post(url, {'pocet_ok': 'abc'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'error')

    def test_report_problem_negative_count_returns_error(self):
        url = reverse('report_problem', kwargs={'pk': self.obj.pk})
        resp = self.client.post(
            url,
            {
                'typ_problemu': 'NEPODAROK',
                'pocet_kusov': -1,
                'popis': 'Test popis',
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'error')

    def test_report_problem_invalid_json_returns_error(self):
        url = reverse('report_problem', kwargs={'pk': self.obj.pk})
        resp = self.client.post(url, data='{invalid', content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'error')


class OperatorEndBatchApiTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('op_end_batch', password='pass')
        self.produkt = _produkt('T-END-BATCH-001')
        self.obj = _objednavka(produkt=self.produkt, mnozstvo=10)
        self.obj.priradeni_operatori.add(self.user)
        self.operacia = _operacia_vyroby(self.obj, stav='vyroba', vyrobene_kusy=0)
        self.client = Client()
        self.client.force_login(self.user)

    def test_end_batch_returns_ok(self):
        url = reverse('end_batch', kwargs={
            'objednavka_pk': self.obj.pk,
            'operacia_pk': self.operacia.pk,
        })
        resp = self.client.post(url, {'vyrobene_kusy': 1, 'nepodarky': 0})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')

    def test_end_batch_invalid_integer_returns_error(self):
        url = reverse('end_batch', kwargs={
            'objednavka_pk': self.obj.pk,
            'operacia_pk': self.operacia.pk,
        })
        resp = self.client.post(url, {'vyrobene_kusy': 'x', 'nepodarky': 0})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'error')


class OperatorTakeoverApiTest(TestCase):
    def setUp(self):
        from .models import OperatorNaOperacii

        self.op1 = User.objects.create_user('op_takeover_1', password='pass')
        self.op2 = User.objects.create_user('op_takeover_2', password='pass')
        self.produkt = _produkt('T-TAKEOVER-001')
        self.obj = _objednavka(produkt=self.produkt, mnozstvo=10)
        self.obj.priradeni_operatori.add(self.op1, self.op2)
        self.operacia = _operacia_vyroby(self.obj, stav='vyroba', vyrobene_kusy=0)
        self.operacia.operator = self.op1
        self.operacia.save(update_fields=['operator'])

        OperatorNaOperacii.objects.create(
            operacia=self.operacia,
            operator=self.op1,
            cas_zaciatku=timezone.now() - timedelta(minutes=30),
        )

        self.client = Client()
        self.client.force_login(self.op2)

    def test_takeover_switches_active_operator(self):
        from .models import OperatorNaOperacii

        url = reverse('take_over_operation', kwargs={
            'objednavka_pk': self.obj.pk,
            'operacia_pk': self.operacia.pk,
        })
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')

        self.operacia.refresh_from_db()
        self.assertEqual(self.operacia.operator_id, self.op2.id)

        old_session = OperatorNaOperacii.objects.filter(operacia=self.operacia, operator=self.op1).first()
        self.assertIsNotNone(old_session.cas_konca)

        new_session = OperatorNaOperacii.objects.filter(
            operacia=self.operacia,
            operator=self.op2,
            cas_konca__isnull=True,
        ).first()
        self.assertIsNotNone(new_session)

    def test_end_batch_requires_takeover_when_other_operator_active(self):
        url = reverse('end_batch', kwargs={
            'objednavka_pk': self.obj.pk,
            'operacia_pk': self.operacia.pk,
        })
        resp = self.client.post(url, {'vyrobene_kusy': 1, 'nepodarky': 0})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'error')
        self.assertIn('Najprv ju prevezmite', data['message'])

    def test_end_batch_after_takeover_counts_productivity_for_new_operator(self):
        from .models import OperatorNaOperacii

        takeover_url = reverse('take_over_operation', kwargs={
            'objednavka_pk': self.obj.pk,
            'operacia_pk': self.operacia.pk,
        })
        takeover_resp = self.client.post(takeover_url)
        self.assertEqual(takeover_resp.status_code, 200)
        self.assertEqual(takeover_resp.json()['status'], 'ok')

        end_batch_url = reverse('end_batch', kwargs={
            'objednavka_pk': self.obj.pk,
            'operacia_pk': self.operacia.pk,
        })
        end_resp = self.client.post(end_batch_url, {'vyrobene_kusy': 2, 'nepodarky': 0})
        self.assertEqual(end_resp.status_code, 200)
        self.assertEqual(end_resp.json()['status'], 'ok')

        session = OperatorNaOperacii.objects.filter(
            operacia=self.operacia,
            operator=self.op2,
        ).order_by('-cas_zaciatku').first()
        self.assertIsNotNone(session)
        self.assertEqual(session.vyrobene_kusy, 2)
        self.assertIsNotNone(session.cas_konca)


class OperatorClaimInProgressOrderTest(TestCase):
    def setUp(self):
        self.marek = User.objects.create_user('marek_claim', password='pass')
        self.jozef = User.objects.create_user('jozef_claim', password='pass')
        self.produkt = _produkt('T-CLAIM-001')
        self.obj = _objednavka(produkt=self.produkt, mnozstvo=10)
        self.obj.stav = 'vyroba'
        self.obj.save(update_fields=['stav'])
        self.obj.priradeni_operatori.add(self.jozef)
        _operacia_vyroby(self.obj, stav='vyroba', vyrobene_kusy=1)

    def test_dashboard_lists_in_progress_takeover_candidates(self):
        client = Client()
        client.force_login(self.marek)
        resp = client.get(reverse('operator_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Rozpracované na prevzatie')
        self.assertContains(resp, self.obj.cislo_objednavky)

    def test_prevziat_zakazku_allows_claim_for_in_progress_order(self):
        client = Client()
        client.force_login(self.marek)
        url = reverse('operator_prevziat_zakazku', kwargs={'pk': self.obj.pk})
        resp = client.post(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')

        self.obj.refresh_from_db()
        self.assertIn(self.marek, self.obj.priradeni_operatori.all())


class OperatorCloseOrderApiTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('op_close_order', password='pass')
        self.produkt = _produkt('T-CLOSE-ORDER-001')
        self.obj = _objednavka(produkt=self.produkt, mnozstvo=5)
        self.obj.priradeni_operatori.add(self.user)
        _operacia_vyroby(self.obj, stav='hotova', vyrobene_kusy=5)
        self.client = Client()
        self.client.force_login(self.user)

    def test_close_order_requires_photo(self):
        url = reverse('close_order', kwargs={'pk': self.obj.pk})
        resp = self.client.post(url, {'poznamka_balenia_final': 'bez fotky'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'error')

    def test_close_order_success(self):
        url = reverse('close_order', kwargs={'pk': self.obj.pk})
        photo = SimpleUploadedFile(
            'balenie.jpg',
            b'\xff\xd8\xff\xe0testjpeg',
            content_type='image/jpeg',
        )
        resp = self.client.post(
            url,
            {'poznamka_balenia_final': 'ok', 'fotka_balenia_final': photo},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.stav, 'hotovo')


class OperatorOperationsFragmentViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('op_fragment', password='pass')
        self.other = User.objects.create_user('op_fragment_other', password='pass')
        self.produkt = _produkt('T-FRAGMENT-001')
        self.obj = _objednavka(produkt=self.produkt, mnozstvo=5)
        self.obj.priradeni_operatori.add(self.user)
        _operacia_vyroby(self.obj, stav='vyroba', vyrobene_kusy=1)

    def test_fragment_authorized_returns_html(self):
        client = Client()
        client.force_login(self.user)
        url = reverse('operator_operacie_fragment', kwargs={'pk': self.obj.pk})
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Operácie', resp.content.decode('utf-8'))
        self.assertIn('ETag', resp)
        self.assertEqual(resp.get('Cache-Control'), 'private, no-cache')

    def test_fragment_if_none_match_returns_304(self):
        client = Client()
        client.force_login(self.user)
        url = reverse('operator_operacie_fragment', kwargs={'pk': self.obj.pk})

        first = client.get(url)
        self.assertEqual(first.status_code, 200)
        etag = first.get('ETag')
        self.assertTrue(etag)

        second = client.get(url, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(second.status_code, 304)

    def test_fragment_unauthorized_operator_gets_403(self):
        client = Client()
        client.force_login(self.other)
        url = reverse('operator_operacie_fragment', kwargs={'pk': self.obj.pk})
        resp = client.get(url)
        self.assertEqual(resp.status_code, 403)


class NaskladniHotoveDielAvoidDoubleCountTest(TestCase):
    """_naskladni_hotove_diely skips pieces already received via end_work."""

    def setUp(self):
        self.user = User.objects.create_user('op_double', password='pass')
        self.produkt = _produkt('T-DOUBLE-001')
        self.obj = _objednavka(produkt=self.produkt, mnozstvo=10)
        _operacia_vyroby(self.obj, stav='hotova', vyrobene_kusy=10)

    def test_no_double_count_when_already_received(self):
        from .models import SkladHotovychDielov, PrijemkaHotovychDielov
        sklad, _ = SkladHotovychDielov.objects.get_or_create(
            produkt=self.produkt,
            defaults={'mnozstvo': 0, 'minimalna_zasoba': 0, 'optimalna_zasoba': 100}
        )
        # Simulate pieces already received via end_work
        PrijemkaHotovychDielov.objects.create(
            sklad=sklad,
            objednavka=self.obj,
            mnozstvo=10,
            operator=self.user,
        )
        sklad_before = SkladHotovychDielov.objects.get(pk=sklad.pk).mnozstvo

        # _naskladni_hotove_diely should add 0 since all pieces already received
        self.obj._naskladni_hotove_diely()

        sklad_after = SkladHotovychDielov.objects.get(pk=sklad.pk).mnozstvo
        self.assertEqual(sklad_after, sklad_before)
