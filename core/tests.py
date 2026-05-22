from decimal import Decimal
from datetime import date, timedelta
from io import StringIO, BytesIO
import json
from unittest.mock import patch
from reportlab.pdfgen import canvas

from django.core.management import call_command
from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.contrib.auth.models import Permission, Group
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

from .models import (
    Stroj, Produkt, Operacia, Objednavka, OperaciaVyroby,
    KontrolnyParameter, KontrolaKvality, MeraniePriKontrole,
    Material, MaterialAINavrh, UserProfile, DochadzkovyToken, DochadzkovyZaznam,
    DovolenkaZiadost, Kontrakt,
)
from .admin import UserCreateWithPinForm


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


class HangslerCsvImportTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('import_user', password='pass')
        add_perm = Permission.objects.get(codename='add_objednavka')
        view_perm = Permission.objects.get(codename='view_objednavka')
        self.user.user_permissions.add(add_perm, view_perm)
        self.client.force_login(self.user)
        self.produkt = Produkt.objects.create(nazov='Hangsler Part', cislo_dielu='3532011901', index='A')

    def _upload(self, rows):
        csv_content = (
            'Odberateľ;číslo;text položky;Dát.dod.;počet mj.\n'
            + '\n'.join(rows)
            + '\n'
        )
        upload = SimpleUploadedFile(
            'mrp_export.csv',
            csv_content.encode('utf-8'),
            content_type='text/csv',
        )
        return self.client.post(reverse('import_objednavok_hangsler_csv'), {'subor': upload}, follow=True)

    def _upload_raw(self, content):
        upload = SimpleUploadedFile(
            'mrp_export.csv',
            content.encode('cp1250'),
            content_type='text/csv',
        )
        return self.client.post(reverse('import_objednavok_hangsler_csv'), {'subor': upload}, follow=True)

    def _build_test_pdf(self, lines):
        buf = BytesIO()
        c = canvas.Canvas(buf)
        y = 800
        for line in lines:
            c.drawString(40, y, line)
            y -= 18
        c.save()
        return buf.getvalue()

    def test_import_creates_only_hangsler_rows(self):
        response = self._upload([
            'Hangsler;PO-001;3532011901;31.12.2026;15',
            'Iny odberatel;PO-002;3532011901;31.12.2026;10',
        ])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Objednavka.objects.count(), 1)
        objednavka = Objednavka.objects.first()
        self.assertEqual(objednavka.zakaznik, 'Hangsler')
        self.assertEqual(objednavka.mnozstvo, 15)
        self.assertEqual(objednavka.cislo_objednavky_zakaznika, 'PO-001')

    def test_import_updates_existing_order_by_customer_product_date(self):
        Objednavka.objects.create(
            zakaznik='Hangsler',
            produkt=self.produkt,
            mnozstvo=5,
            datum_pozadovane=date(2026, 12, 31),
            cislo_objednavky_zakaznika='PO-OLD',
        )

        response = self._upload([
            'Hangsler;PO-NEW;3532011901;31.12.2026;20',
        ])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Objednavka.objects.count(), 1)
        objednavka = Objednavka.objects.get()
        self.assertEqual(objednavka.mnozstvo, 20)
        self.assertEqual(objednavka.cislo_objednavky_zakaznika, 'PO-NEW')

    def test_import_parses_block_mrp_layout(self):
        content = (
            'FIRMA: Strojmacher s.r.o;;;;;;;;;;;Dátum tlače: 21.05.2026;;;\n'
            'Objednávka 260297;;;;;;;;;\n'
            'Odberateľ: Hengstler, s.r.o.;;;;;;IČO: 31718094;;;;;;;\n'
            'Zo dňa: 04.05.2026;;;stav: Vybavené;;;\n'
            'číslo karty;;názov;;;objednaných;;stav na sklade;rezervovaných;vybavených;;;;vybaviť;;\n'
            ';; 3532011901 Test diel;;;300,000;;0,000;0,000;300,000;;;; ;0,000;\n'
        )

        response = self._upload_raw(content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Objednavka.objects.count(), 1)
        objednavka = Objednavka.objects.first()
        self.assertEqual(objednavka.zakaznik, 'Hengstler, s.r.o.')
        self.assertEqual(objednavka.mnozstvo, 300)
        self.assertEqual(objednavka.cislo_objednavky_zakaznika, '260297')
        self.assertEqual(objednavka.stav, 'hotovo')
        self.assertEqual(objednavka.vyrobene_mnozstvo, 300)

    def test_import_matches_product_code_with_spaces(self):
        Produkt.objects.create(nazov='Space Code', cislo_dielu='1890 10821', index='B')
        content = (
            'FIRMA: Strojmacher s.r.o;;;;;;;;;;;Dátum tlače: 21.05.2026;;;\n'
            'Objednávka 260301;;;;;;;;;\n'
            'Odberateľ: Hengstler, s.r.o.;;;;;;IČO: 31718094;;;;;;;\n'
            'Zo dňa: 05.05.2026;;;stav: Vybavené;;;\n'
            'číslo karty;;názov;;;objednaných;;stav na sklade;rezervovaných;vybavených;;;;vybaviť;;\n'
            ';; 189010821 Test diel;;;25,000;;0,000;0,000;25,000;;;; ;0,000;\n'
        )

        response = self._upload_raw(content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Objednavka.objects.filter(cislo_objednavky_zakaznika='260301').count(), 1)
        objednavka = Objednavka.objects.get(cislo_objednavky_zakaznika='260301')
        self.assertEqual(objednavka.produkt.cislo_dielu, '1890 10821')

    def test_plan_can_show_completed_and_sort_orders(self):
        Objednavka.objects.create(
            zakaznik='Hengstler',
            produkt=self.produkt,
            mnozstvo=10,
            vyrobene_mnozstvo=10,
            datum_pozadovane=date(2026, 5, 25),
            stav='hotovo',
        )
        Objednavka.objects.create(
            zakaznik='Hengstler',
            produkt=self.produkt,
            mnozstvo=5,
            vyrobene_mnozstvo=0,
            datum_pozadovane=date(2026, 5, 20),
            stav='nova',
        )

        response = self.client.get(reverse('plan_vyroby'), {
            'stav': 'hotovo',
            'sort': 'mnozstvo',
            'direction': 'desc',
        })

        self.assertEqual(response.status_code, 200)
        zakazky = list(response.context['zakazky'])
        self.assertTrue(zakazky)
        self.assertTrue(all(z.stav == 'hotovo' for z in zakazky))
        self.assertEqual(response.context['sort_key'], 'mnozstvo')
        self.assertEqual(response.context['sort_direction'], 'desc')

    def test_dual_import_assigns_order_to_kontrakt_from_pdf(self):
        kontrakt = Kontrakt.objects.create(
            zakaznik='Hengstler, s.r.o.',
            cislo_kontraktu='KONTR-2026-999',
            produkt=self.produkt,
            pocet_kusov_celkovo=1000,
            zostavajuce_mnozstvo=1000,
            datum_od=date(2026, 1, 1),
            datum_do=date(2026, 12, 31),
            je_skladom=False,
        )

        csv_content = (
            'Odberateľ;číslo;text položky;Dát.dod.;počet mj.\n'
            'Hengstler, s.r.o.;260777;3532011901;05.05.2026;300\n'
        )
        csv_file = SimpleUploadedFile('op03_002.csv', csv_content.encode('utf-8'), content_type='text/csv')

        pdf_bytes = self._build_test_pdf([
            'Objednávka ČísloObjednávky/dátum 4501198725 / 05.05.2026',
            '00010 3532011901 Test diel',
            '300 ks',
            'Cislo kontraktu: KONTR-2026-999',
        ])
        pdf_file = SimpleUploadedFile(
            'Purchase Order Nr. 4501198725 on 05.05.2026.pdf',
            pdf_bytes,
            content_type='application/pdf',
        )

        response = self.client.post(
            reverse('import_objednavok_mrp_pdf'),
            {'csv_file': csv_file, 'pdf_files': [pdf_file]},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        objednavka = Objednavka.objects.get(cislo_objednavky_zakaznika='4501198725')
        self.assertEqual(objednavka.kontrakt, kontrakt)

    def test_staff_admin_can_open_dual_import_view(self):
        admin = User.objects.create_user('staff_import', password='pass')
        admin.is_staff = True
        admin.save(update_fields=['is_staff'])

        client = Client()
        client.force_login(admin)
        response = client.get(reverse('import_objednavok_mrp_pdf'))
        self.assertEqual(response.status_code, 200)


class UserProfilePinTest(TestCase):
    def test_user_profile_is_created_and_pin_must_have_six_digits(self):
        user = User.objects.create_user('pin_user', password='pass')
        profile = UserProfile.objects.get(user=user)

        profile.set_pin('123456')
        profile.save()
        profile.refresh_from_db()

        self.assertTrue(profile.has_pin)
        self.assertTrue(profile.check_pin('123456'))
        self.assertFalse(profile.check_pin('654321'))

        with self.assertRaises(ValueError):
            profile.set_pin('12345')

        with self.assertRaises(ValueError):
            profile.set_pin('12ab56')


class UserCreateWithPinFormTest(TestCase):
    def test_create_user_with_pin_on_add_form(self):
        form = UserCreateWithPinForm(data={
            'username': 'new_admin_user',
            'first_name': 'Test',
            'last_name': 'User',
            'email': 'new_admin_user@example.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
            'pin': '123456',
            'pin_confirm': '123456',
        })

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        profile = UserProfile.objects.get(user=user)
        self.assertTrue(profile.has_pin)
        self.assertTrue(profile.check_pin('123456'))

    def test_create_user_with_invalid_pin_is_rejected(self):
        form = UserCreateWithPinForm(data={
            'username': 'bad_pin_user',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
            'pin': '12ab56',
            'pin_confirm': '12ab56',
        })

        self.assertFalse(form.is_valid())


class QuickLogoutSecurityTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('logout_user', password='pass')

    def test_logout_requires_post_and_returns_no_store(self):
        client = Client()
        client.force_login(self.user)
        url = reverse('logout_quick')

        get_response = client.get(url)
        self.assertEqual(get_response.status_code, 405)

        post_response = client.post(url)
        self.assertEqual(post_response.status_code, 302)
        self.assertEqual(post_response['Location'], '/accounts/login/')
        self.assertIn('no-store', post_response.get('Cache-Control', ''))
        self.assertEqual(client.get('/').wsgi_request.user.is_authenticated, False)


class KioskLandingLoginTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('kiosk_user', password='pass')
        profile = UserProfile.objects.get(user=self.user)
        profile.set_pin('123456')
        profile.save()

    def test_anonymous_home_shows_kiosk_landing(self):
        client = Client()
        response = client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dotknite sa pre prihlásenie')
        self.assertContains(response, 'kiosk_user')

    def test_touch_login_authenticates_and_returns_redirect(self):
        client = Client()
        response = client.post(
            reverse('touch_login'),
            {'username': 'kiosk_user', 'password': 'pass', 'next': '/'},
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode('utf-8'))
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(payload['redirect_url'], '/')

    def test_touch_pin_login_authenticates_with_valid_pin(self):
        client = Client()
        response = client.post(
            reverse('touch_pin_login'),
            {'user_id': str(self.user.id), 'pin': '123456', 'next': '/'},
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode('utf-8'))
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(payload['redirect_url'], '/')

    def test_touch_pin_login_rejects_invalid_pin(self):
        client = Client()
        response = client.post(
            reverse('touch_pin_login'),
            {'user_id': str(self.user.id), 'pin': '000000', 'next': '/'},
        )
        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.content.decode('utf-8'))
        self.assertEqual(payload['status'], 'error')


class AttendanceKioskTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('attendance_user', password='pass', first_name='Jozef', last_name='Mravec')
        profile = UserProfile.objects.get(user=self.user)
        profile.set_pin('123456')
        profile.save()
        self.token = DochadzkovyToken.objects.create(
            user=self.user,
            identifikator='EMP001',
            nazov='Hlavný token',
            typ='MANUAL',
        )

    def test_attendance_punch_creates_in_and_out_records(self):
        client = Client()

        first_response = client.post(reverse('attendance_punch'), {
            'identifikator': 'emp001',
            'pin': '123456',
        })
        self.assertEqual(first_response.status_code, 200)
        first_payload = json.loads(first_response.content.decode('utf-8'))
        self.assertEqual(first_payload['status'], 'ok')
        self.assertEqual(first_payload['typ_udalosti'], 'IN')

        first_record = DochadzkovyZaznam.objects.get(user=self.user)
        first_record.cas_udalosti = timezone.now() - timedelta(minutes=10)
        first_record.save(update_fields=['cas_udalosti'])

        second_response = client.post(reverse('attendance_punch'), {
            'identifikator': 'EMP001',
            'pin': '123456',
        })
        self.assertEqual(second_response.status_code, 200)
        second_payload = json.loads(second_response.content.decode('utf-8'))
        self.assertEqual(second_payload['status'], 'ok')
        self.assertEqual(second_payload['typ_udalosti'], 'OUT')
        self.assertEqual(DochadzkovyZaznam.objects.filter(user=self.user).count(), 2)

    def test_attendance_punch_rejects_invalid_pin(self):
        client = Client()
        response = client.post(reverse('attendance_punch'), {
            'identifikator': 'EMP001',
            'pin': '000000',
        })
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode('utf-8'))
        self.assertEqual(payload['status'], 'error')
        self.assertEqual(DochadzkovyZaznam.objects.count(), 0)


class AttendanceOperatorPanelApiTest(TestCase):
    def setUp(self):
        self.operator_group, _ = Group.objects.get_or_create(name='Operatori')
        self.user = User.objects.create_user('operator_panel_user', password='pass', first_name='Peter', last_name='Kovac')
        self.user.groups.add(self.operator_group)

        profile = UserProfile.objects.get(user=self.user)
        profile.set_pin('123456')
        profile.save()

        self.token = DochadzkovyToken.objects.create(
            user=self.user,
            identifikator='OPER-001',
            nazov='Panel token',
            typ='MANUAL',
        )

    def test_operator_session_returns_month_rows(self):
        client = Client()
        response = client.post(reverse('attendance_operator_session'), {
            'identifikator': 'OPER-001',
            'pin': '123456',
        })
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode('utf-8'))
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(payload['username'], 'operator_panel_user')
        self.assertTrue(isinstance(payload['rows'], list))

    def test_operator_session_accepts_username_without_token(self):
        self.token.delete()
        client = Client()
        response = client.post(reverse('attendance_operator_session'), {
            'identifikator': 'operator_panel_user',
            'pin': '123456',
        })
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode('utf-8'))
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(payload['username'], 'operator_panel_user')

    def test_manual_punch_rejects_out_without_previous_in(self):
        client = Client()
        response = client.post(reverse('attendance_manual_punch'), {
            'identifikator': 'OPER-001',
            'pin': '123456',
            'event_type': 'OUT',
        })
        payload = json.loads(response.content.decode('utf-8'))
        self.assertEqual(payload['status'], 'error')
        self.assertEqual(DochadzkovyZaznam.objects.count(), 0)

    def test_manual_punch_allows_explicit_in_then_out(self):
        client = Client()
        in_response = client.post(reverse('attendance_manual_punch'), {
            'identifikator': 'OPER-001',
            'pin': '123456',
            'event_type': 'IN',
        })
        self.assertEqual(json.loads(in_response.content.decode('utf-8'))['status'], 'ok')

        first_record = DochadzkovyZaznam.objects.get(user=self.user, typ_udalosti='IN')
        first_record.cas_udalosti = timezone.now() - timedelta(minutes=5)
        first_record.save(update_fields=['cas_udalosti'])

        out_response = client.post(reverse('attendance_manual_punch'), {
            'identifikator': 'OPER-001',
            'pin': '123456',
            'event_type': 'OUT',
        })
        out_payload = json.loads(out_response.content.decode('utf-8'))
        self.assertEqual(out_payload['status'], 'ok')
        self.assertEqual(DochadzkovyZaznam.objects.filter(user=self.user).count(), 2)

    def test_vacation_request_creates_pending_request(self):
        client = Client()
        start = date.today() + timedelta(days=(7 - date.today().weekday()) % 7 + 1)
        end = start + timedelta(days=2)

        response = client.post(reverse('attendance_vacation_request'), {
            'identifikator': 'OPER-001',
            'pin': '123456',
            'date_from': start.isoformat(),
            'date_to': end.isoformat(),
            'note': 'Rodinna dovolenka',
        })
        payload = json.loads(response.content.decode('utf-8'))
        self.assertEqual(payload['status'], 'ok')
        request_obj = DovolenkaZiadost.objects.get(user=self.user)
        self.assertEqual(request_obj.status, DovolenkaZiadost.STATUS_PENDING)

    def test_vacation_request_rejects_weekend_only_range(self):
        client = Client()
        today = date.today()
        days_until_saturday = (5 - today.weekday()) % 7
        saturday = today + timedelta(days=days_until_saturday)
        sunday = saturday + timedelta(days=1)

        response = client.post(reverse('attendance_vacation_request'), {
            'identifikator': 'OPER-001',
            'pin': '123456',
            'date_from': saturday.isoformat(),
            'date_to': sunday.isoformat(),
        })
        payload = json.loads(response.content.decode('utf-8'))
        self.assertEqual(payload['status'], 'error')
        self.assertEqual(DovolenkaZiadost.objects.count(), 0)

    def test_manager_can_approve_pending_request(self):
        manager = User.objects.create_user('attendance_manager_user', password='pass')
        manager_group, _ = Group.objects.get_or_create(name='attendance_manager')
        manager.groups.add(manager_group)

        vacation = DovolenkaZiadost.objects.create(
            user=self.user,
            date_from=date.today() + timedelta(days=1),
            date_to=date.today() + timedelta(days=2),
            status=DovolenkaZiadost.STATUS_PENDING,
        )

        client = Client()
        client.force_login(manager)
        response = client.post(reverse('attendance_vacation_decide', args=[vacation.id]), {
            'decision': 'approve',
            'decision_note': 'Schvalene',
        })
        payload = json.loads(response.content.decode('utf-8'))
        self.assertEqual(payload['status'], 'ok')

        vacation.refresh_from_db()
        self.assertEqual(vacation.status, DovolenkaZiadost.STATUS_APPROVED)
        self.assertEqual(vacation.decided_by, manager)

    def test_manager_page_requires_attendance_manager_role(self):
        client = Client()
        client.force_login(self.user)
        response = client.get(reverse('attendance_vacation_manager_page'))
        self.assertEqual(response.status_code, 403)

    def test_manager_page_renders_for_attendance_manager(self):
        manager = User.objects.create_user('attendance_page_manager', password='pass')
        manager_group, _ = Group.objects.get_or_create(name='attendance_manager')
        manager.groups.add(manager_group)

        client = Client()
        client.force_login(manager)
        response = client.get(reverse('attendance_vacation_manager_page'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Schvalovanie dovoleniek')

    def test_attendance_punch_rejects_inactive_token(self):
        self.token.aktivny = False
        self.token.save(update_fields=['aktivny', 'updated_at'])

        client = Client()
        response = client.post(reverse('attendance_punch'), {
            'identifikator': 'EMP001',
            'pin': '123456',
        })

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode('utf-8'))
        self.assertEqual(payload['status'], 'error')
        self.assertEqual(DochadzkovyZaznam.objects.count(), 0)


class AttendanceReportViewTest(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('attendance_manager', password='pass', is_staff=True)
        view_perm = Permission.objects.get(codename='view_dochadzkovyzaznam')
        self.staff.user_permissions.add(view_perm)

        self.user = User.objects.create_user('report_user', password='pass', first_name='Anna', last_name='Nováková')
        DochadzkovyToken.objects.create(user=self.user, identifikator='REPORT1', typ='MANUAL')
        now = timezone.now()
        DochadzkovyZaznam.objects.create(user=self.user, typ_udalosti='IN', zdroj='KIOSK', cas_udalosti=now - timedelta(hours=8))
        DochadzkovyZaznam.objects.create(user=self.user, typ_udalosti='OUT', zdroj='KIOSK', cas_udalosti=now - timedelta(hours=1))

    def test_attendance_report_renders_summary(self):
        client = Client()
        client.force_login(self.staff)
        response = client.get(reverse('attendance_report'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dochádzka')
        self.assertContains(response, 'Anna Nováková')

    def test_attendance_export_csv_returns_file(self):
        client = Client()
        client.force_login(self.staff)
        response = client.get(reverse('attendance_export_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertIn('Anna Nováková', response.content.decode('utf-8-sig'))

    def test_attendance_report_manual_entry_creates_admin_record(self):
        add_perm = Permission.objects.get(codename='add_dochadzkovyzaznam')
        self.staff.user_permissions.add(add_perm)

        client = Client()
        client.force_login(self.staff)
        response = client.post(reverse('attendance_report'), {
            'manual_user_id': str(self.user.id),
            'manual_typ_udalosti': 'IN',
            'manual_poznamka': 'Ručný zásah admin',
            'return_date': '2026-05-18',
            'return_user_id': str(self.user.id),
        })

        self.assertEqual(response.status_code, 302)
        record = DochadzkovyZaznam.objects.filter(user=self.user, zdroj='ADMIN').order_by('-id').first()
        self.assertIsNotNone(record)
        self.assertEqual(record.typ_udalosti, 'IN')
        self.assertEqual(record.zaznamenal, self.staff)
        self.assertEqual(record.poznamka, 'Ručný zásah admin')

    def test_attendance_report_manual_entry_rejects_out_without_in(self):
        add_perm = Permission.objects.get(codename='add_dochadzkovyzaznam')
        self.staff.user_permissions.add(add_perm)

        empty_user = User.objects.create_user('empty_attendance_user', password='pass')

        client = Client()
        client.force_login(self.staff)
        response = client.post(reverse('attendance_report'), {
            'manual_user_id': str(empty_user.id),
            'manual_typ_udalosti': 'OUT',
            'manual_poznamka': 'Test invalid out',
            'return_date': timezone.localdate().isoformat(),
            'return_user_id': '',
        })

        self.assertEqual(response.status_code, 302)
        self.assertFalse(DochadzkovyZaznam.objects.filter(user=empty_user, zdroj='ADMIN').exists())

    def test_attendance_report_manual_entry_rejects_double_in(self):
        add_perm = Permission.objects.get(codename='add_dochadzkovyzaznam')
        self.staff.user_permissions.add(add_perm)

        open_user = User.objects.create_user('open_attendance_user', password='pass')
        DochadzkovyZaznam.objects.create(user=open_user, typ_udalosti='IN', zdroj='KIOSK', cas_udalosti=timezone.now())

        client = Client()
        client.force_login(self.staff)
        response = client.post(reverse('attendance_report'), {
            'manual_user_id': str(open_user.id),
            'manual_typ_udalosti': 'IN',
            'manual_poznamka': 'Test duplicate in',
            'return_date': timezone.localdate().isoformat(),
            'return_user_id': '',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(DochadzkovyZaznam.objects.filter(user=open_user).count(), 1)

    def test_manager_overview_marks_manual_adjustments(self):
        add_perm = Permission.objects.get(codename='add_dochadzkovyzaznam')
        self.staff.user_permissions.add(add_perm)

        manual_dt = timezone.now() - timedelta(hours=2)
        DochadzkovyZaznam.objects.create(
            user=self.user,
            typ_udalosti='IN',
            zdroj='ADMIN',
            cas_udalosti=manual_dt,
            zaznamenal=self.staff,
            poznamka='Rucna uprava test',
        )

        client = Client()
        client.force_login(self.staff)
        response = client.get(reverse('attendance_manager_overview'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Upravene rucne')


class AdminManagementViewsTest(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('staff_user', password='pass', is_staff=True)
        self.nonstaff = User.objects.create_user('nonstaff_user', password='pass', is_staff=False)

    def test_admin_users_view_renders_for_authorized_staff(self):
        perm = Permission.objects.get(codename='view_user')
        self.staff.user_permissions.add(perm)

        client = Client()
        client.force_login(self.staff)
        response = client.get(reverse('admin_users_view'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Správa používateľov')

    def test_admin_groups_view_renders_for_authorized_staff(self):
        perm = Permission.objects.get(codename='view_group')
        self.staff.user_permissions.add(perm)

        client = Client()
        client.force_login(self.staff)
        response = client.get(reverse('admin_groups_view'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Skupiny a roly')

    def test_admin_permissions_view_renders_for_authorized_staff(self):
        perm = Permission.objects.get(codename='view_permission')
        self.staff.user_permissions.add(perm)

        client = Client()
        client.force_login(self.staff)
        response = client.get(reverse('admin_permissions_view'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Celkom oprávnení')

    def test_admin_users_view_denies_nonstaff(self):
        perm = Permission.objects.get(codename='view_user')
        self.nonstaff.user_permissions.add(perm)

        client = Client()
        client.force_login(self.nonstaff)
        response = client.get(reverse('admin_users_view'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nemáte prístup')

    def test_admin_users_view_can_create_attendance_token(self):
        view_perm = Permission.objects.get(codename='view_user')
        add_token_perm = Permission.objects.get(codename='add_dochadzkovytoken')
        self.staff.user_permissions.add(view_perm, add_token_perm)

        target_user = User.objects.create_user('token_user', password='pass')

        client = Client()
        client.force_login(self.staff)
        response = client.post(reverse('admin_users_view'), {
            'user_id': str(target_user.id),
            'nazov': 'Karta recepcia',
            'typ': 'MANUAL',
            'identifikator': '',
        })

        self.assertEqual(response.status_code, 302)
        token = DochadzkovyToken.objects.get(user=target_user)
        self.assertTrue(token.identifikator.startswith('EMP-'))
        self.assertEqual(token.nazov, 'Karta recepcia')

    def test_admin_users_view_can_toggle_attendance_token_status(self):
        view_perm = Permission.objects.get(codename='view_user')
        change_token_perm = Permission.objects.get(codename='change_dochadzkovytoken')
        self.staff.user_permissions.add(view_perm, change_token_perm)

        target_user = User.objects.create_user('toggle_token_user', password='pass')
        token = DochadzkovyToken.objects.create(
            user=target_user,
            identifikator='EMP-TOGGLE',
            typ='MANUAL',
            aktivny=True,
        )

        client = Client()
        client.force_login(self.staff)
        response = client.post(reverse('admin_users_view'), {
            'action': 'toggle-token',
            'token_id': str(token.id),
        })

        self.assertEqual(response.status_code, 302)
        token.refresh_from_db()
        self.assertFalse(token.aktivny)


class SeedAttendanceTokensCommandTest(TestCase):
    def test_seed_command_creates_tokens_only_for_missing_active_users(self):
        user_with_token = User.objects.create_user('with_token', password='pass', is_active=True)
        DochadzkovyToken.objects.create(user=user_with_token, identifikator='EMP-9999', typ='MANUAL')

        user_without_token = User.objects.create_user('without_token', password='pass', is_active=True)
        inactive_user = User.objects.create_user('inactive_user', password='pass', is_active=False)

        output = StringIO()
        call_command('seed_attendance_tokens', stdout=output)

        self.assertEqual(DochadzkovyToken.objects.filter(user=user_with_token).count(), 1)
        self.assertEqual(DochadzkovyToken.objects.filter(user=user_without_token).count(), 1)
        self.assertEqual(DochadzkovyToken.objects.filter(user=inactive_user).count(), 0)
        self.assertIn('Vytvorených tokenov: 1', output.getvalue())


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


class ObjednavkaMaterialShortageValidationTest(TestCase):
    def setUp(self):
        from .models import Material

        self.material = Material.objects.create(
            nazov='Test materiál shortage',
            kod='MAT-SHORT-001',
            jednotka='kg',
            aktualna_zasoba=Decimal('2.00'),
            minimalna_zasoba=Decimal('0.50'),
            kg_na_meter=Decimal('1.00'),
            tyc_dlzka_m=Decimal('6.00'),
        )
        self.produkt = Produkt.objects.create(
            nazov='Produkt shortage test',
            cislo_dielu='P-SHORT-001',
            material_ref=self.material,
            dlzka_na_kus_mm=Decimal('1000.00'),
            cas_vyroby=10,
            norma_hod=6,
        )

    def test_nova_objednavka_blocks_when_material_missing(self):
        user = User.objects.create_user('obj_add_user', password='pass')
        user.user_permissions.add(Permission.objects.get(codename='add_objednavka'))

        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('nova_objednavka'),
            data={
                'zakaznik': 'Shortage klient',
                'produkt': str(self.produkt.pk),
                'mnozstvo': '5',
                'datum_pozadovane': (date.today() + timedelta(days=7)).isoformat(),
                'poznamka': '',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nedostatok materiálu')
        self.assertEqual(Objednavka.objects.count(), 0)

    def test_upravit_objednavku_blocks_when_material_missing(self):
        user = User.objects.create_user('obj_change_user', password='pass')
        user.user_permissions.add(Permission.objects.get(codename='change_objednavka'))

        objednavka = Objednavka.objects.create(
            produkt=self.produkt,
            zakaznik='Edit shortage klient',
            mnozstvo=1,
            datum_pozadovane=date.today() + timedelta(days=7),
        )

        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('upravit_objednavku', kwargs={'pk': objednavka.pk}),
            data={
                'cislo_objednavky': objednavka.cislo_objednavky,
                'zakaznik': objednavka.zakaznik,
                'produkt': str(self.produkt.pk),
                'mnozstvo': '5',
                'datum_pozadovane': objednavka.datum_pozadovane.isoformat(),
                'poznamka': objednavka.poznamka,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nedostatok materiálu')
        objednavka.refresh_from_db()
        self.assertEqual(objednavka.mnozstvo, 1)


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


@override_settings(AI_MATERIAL_ENABLED=True)
class MaterialAiNavrhApiTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('ai_material_user', password='pass')
        self.user.user_permissions.add(Permission.objects.get(codename='add_material'))
        self.client.force_login(self.user)

    def test_navrh_rejects_non_allowed_domain(self):
        response = self.client.post(
            reverse('ai_material_navrh'),
            data=json.dumps({
                'query': 'ocelova gulatina C45',
                'source_url': 'https://example.com/material',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('Zdrojová URL nie je povolená', payload['message'])

    @patch('core.views._generate_material_ai_response')
    def test_navrh_creates_draft(self, mock_generate):
        mock_generate.return_value = {
            'model': 'gpt-4.1-mini',
            'raw_text': '{"nazov":"Oceľ C45","kod":"C45-20","typ":"SUROVINA"}',
            'data': {
                'nazov': 'Oceľ C45 Ø20',
                'kod': 'C45-20',
                'typ': 'SUROVINA',
                'jednotka': 'kg',
                'minimalna_zasoba': 100,
                'cena_za_jednotku': 1.8,
                'priemer_mm': 20,
                'tyc_dlzka_m': 6,
                'kg_na_meter': 2.47,
                'aktualna_zasoba': 0,
                'confidence': 0.82,
                'poznamka': 'Test návrh',
            },
        }

        response = self.client.post(
            reverse('ai_material_navrh'),
            data=json.dumps({
                'query': 'ocelova gulatina C45 20mm',
                'source_url': 'https://ferona.sk/ocel-c45',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(MaterialAINavrh.objects.count(), 1)
        navrh = MaterialAINavrh.objects.first()
        self.assertEqual(navrh.stav, 'DRAFT')
        self.assertEqual(navrh.navrh_data.get('kod'), 'C45-20')

    def test_potvrdenie_navrhu_vytvori_material(self):
        navrh = MaterialAINavrh.objects.create(
            query='ocel c45',
            source_url='https://ferona.sk/ocel-c45',
            source_domain='ferona.sk',
            ai_model='gpt-4.1-mini',
            navrh_data={
                'nazov': 'Oceľ C45 Ø20',
                'kod': 'C45-20-TEST',
                'typ': 'SUROVINA',
                'jednotka': 'kg',
            },
            created_by=self.user,
        )

        response = self.client.post(
            reverse('ai_material_navrh_potvrdit', kwargs={'pk': navrh.pk}),
            data=json.dumps({
                'nazov': 'Oceľ C45 Ø20',
                'kod': 'C45-20-TEST',
                'typ': 'SUROVINA',
                'jednotka': 'kg',
                'minimalna_zasoba': '50',
                'cena_za_jednotku': '1.75',
                'priemer_mm': '20',
                'tyc_dlzka_m': '6',
                'kg_na_meter': '2.47',
                'aktualna_zasoba': '0',
                'poznamka': 'potvrdene testom',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')
        self.assertTrue(Material.objects.filter(kod='C45-20-TEST').exists())

        navrh.refresh_from_db()
        self.assertEqual(navrh.stav, 'APPROVED')
        self.assertIsNotNone(navrh.material)


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


class ProduktFileUploadViewTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_novy_produkt_uploads_vykres_pdf(self):
        user = User.objects.create_user('add_produkt_user', password='pass')
        perm = Permission.objects.get(codename='add_produkt')
        user.user_permissions.add(perm)
        self.client.force_login(user)

        material = None
        try:
            from .models import Material
            material = Material.objects.create(
                nazov='Test material upload',
                kod='MAT-UPL-001',
                jednotka='kg',
                aktualna_zasoba=Decimal('100.00'),
                minimalna_zasoba=Decimal('10.00'),
            )
        except Exception:
            material = None

        data = {
            'nazov': 'Produkt upload test',
            'cislo_dielu': 'T-UPL-001',
            'cislo_vykresu': 'DRW-001',
            'index': '0',
            'material': 'Ocel',
            'rozmer_polotovaru': '10x10',
            'spotreba_ks': '1.00',
            'material_ref': str(material.pk) if material else '',
            'dlzka_na_kus_mm': '100.00',
            'cas_vyroby': '10',
            'norma_hod': '6',
            'vykres_pdf': SimpleUploadedFile('vykres.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
        }

        resp = self.client.post(reverse('novy_produkt'), data=data)
        self.assertEqual(resp.status_code, 302)

        produkt = Produkt.objects.get(cislo_dielu='T-UPL-001')
        self.assertTrue(bool(produkt.vykres_pdf), 'vykres_pdf nebol ulozeny')

    def test_upravit_produkt_uploads_vykres_pdf(self):
        user = User.objects.create_user('change_produkt_user', password='pass')
        perm = Permission.objects.get(codename='change_produkt')
        user.user_permissions.add(perm)
        self.client.force_login(user)

        produkt = _produkt('T-UPL-EDIT-001')
        data = {
            'nazov': produkt.nazov,
            'cislo_dielu': produkt.cislo_dielu,
            'cislo_vykresu': produkt.cislo_vykresu or '',
            'index': produkt.index or '0',
            'material': produkt.material or '',
            'rozmer_polotovaru': produkt.rozmer_polotovaru or '',
            'spotreba_ks': str(produkt.spotreba_ks),
            'material_ref': str(produkt.material_ref_id or ''),
            'dlzka_na_kus_mm': str(produkt.dlzka_na_kus_mm),
            'cas_vyroby': str(produkt.cas_vyroby),
            'norma_hod': str(produkt.norma_hod),
            'vykres_pdf': SimpleUploadedFile('vykres_edit.pdf', b'%PDF-1.4 test edit', content_type='application/pdf'),
        }

        resp = self.client.post(reverse('upravit_produkt', kwargs={'pk': produkt.pk}), data=data)
        self.assertEqual(resp.status_code, 302)

        produkt.refresh_from_db()
        self.assertTrue(bool(produkt.vykres_pdf), 'vykres_pdf nebol ulozeny pri uprave')


class ProduktEtapaAUlozenieOperaciiTest(TestCase):
    def test_uloz_kartu_produktu_etapa_a_nahradi_operacie_produktu(self):
        user = User.objects.create_user('etapa_a_operacie_user', password='pass')
        perm = Permission.objects.get(codename='change_produkt')
        user.user_permissions.add(perm)

        produkt = _produkt('T-ETAPA-OPER-001')
        povodny_stroj = _stroj()
        Operacia.objects.create(
            produkt=produkt,
            stroj=povodny_stroj,
            poradie=1,
            nazov_operacie='Povodna operacia',
            cas_pripravy=5,
            cas_kus=Decimal('2.00'),
        )
        novy_stroj = Stroj.objects.create(nazov='Novy stroj test')

        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('uloz_kartu_produktu_etapa_a', kwargs={'pk': produkt.pk}),
            {
                'material': '',
                'rozmer_polotovaru': '',
                'spotreba_ks': '0',
                'norma_hod': '0',
                'upozornenie_operator': '',
                'reklamacie_poznamky': '',
                'baliaci_predpis_text': '',
                'kalibre_poznamky': '',
                'vyrobny_postup_poznamky': 'Poznamka test',
                'operacie_json': json.dumps([
                    {
                        'poradie': '2',
                        'nazov_operacie': 'CNC sustruzenie',
                        'stroj_id': str(novy_stroj.pk),
                        'cas_pripravy': '12',
                        'cas_kus': '1.75',
                    }
                ]),
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')
        self.assertIn('operacie', payload['changed_fields'])

        operacie = list(Operacia.objects.filter(produkt=produkt).order_by('poradie'))
        self.assertEqual(len(operacie), 1)
        self.assertEqual(operacie[0].poradie, 2)
        self.assertEqual(operacie[0].nazov_operacie, 'CNC sustruzenie')
        self.assertEqual(operacie[0].stroj, novy_stroj)
        self.assertEqual(operacie[0].cas_pripravy, 12)
        self.assertEqual(operacie[0].cas_kus, Decimal('1.75'))

    def test_ulozenie_operacii_syncne_otvorenu_zakazku_pre_rovnaky_produkt(self):
        user = User.objects.create_user('etapa_a_sync_user', password='pass')
        perm = Permission.objects.get(codename='change_produkt')
        user.user_permissions.add(perm)

        produkt = _produkt('T-ETAPA-SYNC-001')
        objednavka = Objednavka.objects.create(
            cislo_objednavky='TEST-SYNC-001',
            zakaznik='Sync zakaznik',
            produkt=produkt,
            mnozstvo=25,
            datum_pozadovane=date.today() + timedelta(days=10),
            stav='nova',
        )
        stroj = Stroj.objects.create(nazov='Sync stroj test')

        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('uloz_kartu_produktu_etapa_a', kwargs={'pk': produkt.pk}),
            {
                'material': '',
                'rozmer_polotovaru': '',
                'spotreba_ks': '0',
                'norma_hod': '0',
                'upozornenie_operator': '',
                'reklamacie_poznamky': '',
                'typ_baliaceho_predpisu': 'Kovova prepravka - Hengstler',
                'baliaci_predpis_text': '',
                'kalibre_poznamky': '',
                'vyrobny_postup_poznamky': '',
                'operacie_json': json.dumps([
                    {
                        'poradie': '1',
                        'nazov_operacie': 'Meranie',
                        'stroj_id': str(stroj.pk),
                        'cas_pripravy': '8',
                        'cas_kus': '0.80',
                    }
                ]),
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(payload['synced_orders'], 1)
        self.assertEqual(payload['skipped_orders'], 0)

        operacie_zakazky = list(objednavka.operacie.order_by('poradie'))
        self.assertEqual(len(operacie_zakazky), 1)
        self.assertEqual(operacie_zakazky[0].nazov_operacie, 'Meranie')
        self.assertEqual(operacie_zakazky[0].stroj, stroj)
        self.assertEqual(operacie_zakazky[0].cas_pripravy, 8)
        self.assertEqual(operacie_zakazky[0].cas_kus, Decimal('0.80'))

    def test_ulozenie_operacii_neprepise_rozpracovanu_zakazku(self):
        user = User.objects.create_user('etapa_a_skip_user', password='pass')
        perm = Permission.objects.get(codename='change_produkt')
        user.user_permissions.add(perm)

        produkt = _produkt('T-ETAPA-SKIP-001')
        stroj_povodny = Stroj.objects.create(nazov='Rozprac stroj')
        sablona = Operacia.objects.create(
            produkt=produkt,
            stroj=stroj_povodny,
            poradie=1,
            nazov_operacie='Povodna operacia',
            cas_pripravy=4,
            cas_kus=Decimal('1.00'),
        )
        objednavka = Objednavka.objects.create(
            cislo_objednavky='TEST-SKIP-001',
            zakaznik='Skip zakaznik',
            produkt=produkt,
            mnozstvo=10,
            datum_pozadovane=date.today() + timedelta(days=5),
            stav='nova',
        )
        OperaciaVyroby.objects.create(
            objednavka=objednavka,
            operacia_sablona=sablona,
            stroj=stroj_povodny,
            poradie=1,
            nazov_operacie='Povodna operacia',
            cas_pripravy=4,
            cas_kus=Decimal('1.00'),
            stav='vyroba',
            vyrobene_kusy=3,
        )
        novy_stroj = Stroj.objects.create(nazov='Novy skip stroj')

        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('uloz_kartu_produktu_etapa_a', kwargs={'pk': produkt.pk}),
            {
                'material': '',
                'rozmer_polotovaru': '',
                'spotreba_ks': '0',
                'norma_hod': '0',
                'upozornenie_operator': '',
                'reklamacie_poznamky': '',
                'typ_baliaceho_predpisu': '',
                'baliaci_predpis_text': '',
                'kalibre_poznamky': '',
                'vyrobny_postup_poznamky': '',
                'operacie_json': json.dumps([
                    {
                        'poradie': '1',
                        'nazov_operacie': 'Balenie',
                        'stroj_id': '',
                        'cas_pripravy': '2',
                        'cas_kus': '0.50',
                    }
                ]),
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['synced_orders'], 0)
        self.assertEqual(payload['skipped_orders'], 1)

        operacia_zakazky = objednavka.operacie.get()
        self.assertEqual(operacia_zakazky.nazov_operacie, 'Povodna operacia')
        self.assertEqual(operacia_zakazky.stroj, stroj_povodny)
        self.assertEqual(operacia_zakazky.vyrobene_kusy, 3)

    def test_uloz_kartu_produktu_etapa_a_ulozi_typ_predpisu_a_default_stroj_pre_balenie(self):
        user = User.objects.create_user('etapa_a_balenie_user', password='pass')
        perm = Permission.objects.get(codename='change_produkt')
        user.user_permissions.add(perm)

        produkt = _produkt('T-ETAPA-BAL-001')
        stroj = Stroj.objects.create(nazov='Baliaci stroj test')

        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('uloz_kartu_produktu_etapa_a', kwargs={'pk': produkt.pk}),
            {
                'material': '',
                'rozmer_polotovaru': '',
                'spotreba_ks': '0',
                'norma_hod': '0',
                'upozornenie_operator': '',
                'reklamacie_poznamky': '',
                'typ_baliaceho_predpisu': 'Papierova krabica 500x400x300',
                'baliaci_predpis_text': 'Standard balenia',
                'kalibre_poznamky': '',
                'vyrobny_postup_poznamky': '',
                'operacie_json': json.dumps([
                    {
                        'poradie': '1',
                        'nazov_operacie': 'Balenie',
                        'stroj_id': '',
                        'cas_pripravy': '6',
                        'cas_kus': '0.40',
                    }
                ]),
            },
        )

        self.assertEqual(response.status_code, 200)
        operacia = Operacia.objects.get(produkt=produkt)
        self.assertEqual(operacia.typ_balenia, '')
        self.assertEqual(operacia.cas_pripravy, 0)
        self.assertEqual(operacia.stroj, stroj)


class OperaciaVyrobyDostupnostKusovTest(TestCase):
    def test_druha_operacia_moze_zacat_podla_kusov_na_vstupe(self):
        produkt = _produkt('T-OP-INPUT-001')
        objednavka = _objednavka(produkt=produkt, mnozstvo=50)
        stroj = _stroj()

        sablona_1 = Operacia.objects.create(
            produkt=produkt,
            stroj=stroj,
            poradie=1,
            nazov_operacie='Operacia 1',
            cas_pripravy=5,
            cas_kus=Decimal('1.00'),
        )
        sablona_2 = Operacia.objects.create(
            produkt=produkt,
            stroj=stroj,
            poradie=2,
            nazov_operacie='Operacia 2',
            cas_pripravy=5,
            cas_kus=Decimal('1.00'),
        )

        prva = OperaciaVyroby.objects.create(
            objednavka=objednavka,
            operacia_sablona=sablona_1,
            stroj=stroj,
            poradie=1,
            nazov_operacie='Operacia 1',
            cas_pripravy=5,
            cas_kus=Decimal('1.00'),
            vyrobene_kusy=0,
            kusy_na_vystupe=12,
        )
        druha = OperaciaVyroby.objects.create(
            objednavka=objednavka,
            operacia_sablona=sablona_2,
            stroj=stroj,
            poradie=2,
            nazov_operacie='Operacia 2',
            cas_pripravy=5,
            cas_kus=Decimal('1.00'),
            kusy_na_vstupe=12,
        )

        self.assertEqual(prva.kusy_na_vystupe, 12)
        self.assertEqual(druha.get_dostupne_kusy_na_vstupe(), 12)
        self.assertTrue(druha.moze_zacat())

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


# ---------------------------------------------------------------------------
# ERP Documents module tests
# ---------------------------------------------------------------------------

import shutil
import tempfile
from pathlib import Path

from django.contrib.auth.models import Group

from .docs_utils import (
    safe_resolve, is_extension_blocked, is_docs_admin,
    resolve_collision, safe_filename, to_rel,
)
from .models import DocumentAuditLog


class DocsUtilsPathSafetyTest(TestCase):
    """safe_resolve blocks path-traversal attempts."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / 'sub').mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_valid_subpath(self):
        result = safe_resolve('sub', self.tmp)
        self.assertEqual(result, (self.tmp / 'sub').resolve())

    def test_empty_path_returns_root(self):
        result = safe_resolve('', self.tmp)
        self.assertEqual(result, self.tmp.resolve())

    def test_dotdot_blocked(self):
        with self.assertRaises(ValueError):
            safe_resolve('../etc/passwd', self.tmp)

    def test_absolute_path_blocked(self):
        with self.assertRaises(ValueError):
            safe_resolve('/etc/passwd', self.tmp)

    def test_encoded_traversal_blocked(self):
        # Even if normalised forward slashes can still carry ..
        with self.assertRaises(ValueError):
            safe_resolve('sub/../../etc/passwd', self.tmp)

    def test_nested_valid_path(self):
        (self.tmp / 'a' / 'b').mkdir(parents=True)
        result = safe_resolve('a/b', self.tmp)
        self.assertEqual(result, (self.tmp / 'a' / 'b').resolve())


class DocsExtensionBlockTest(TestCase):
    def test_exe_blocked(self):
        self.assertTrue(is_extension_blocked('virus.exe'))

    def test_bat_blocked(self):
        self.assertTrue(is_extension_blocked('run.bat'))

    def test_ps1_blocked(self):
        self.assertTrue(is_extension_blocked('script.PS1'))

    def test_pdf_allowed(self):
        self.assertFalse(is_extension_blocked('drawing.pdf'))

    def test_dwg_allowed(self):
        self.assertFalse(is_extension_blocked('part.DWG'))

    def test_xlsx_allowed(self):
        self.assertFalse(is_extension_blocked('bom.xlsx'))


class DocsIsAdminTest(TestCase):
    def setUp(self):
        self.group = Group.objects.create(name='docs_admin')
        self.admin_user = User.objects.create_user('docs_admin_user', password='x')
        self.admin_user.groups.add(self.group)
        self.regular_user = User.objects.create_user('regular_user', password='x')
        self.superuser = User.objects.create_superuser('superuser', password='x')

    @override_settings(ERP_DOCS_ADMIN_GROUP='docs_admin')
    def test_group_member_is_admin(self):
        self.assertTrue(is_docs_admin(self.admin_user))

    @override_settings(ERP_DOCS_ADMIN_GROUP='docs_admin')
    def test_regular_user_not_admin(self):
        self.assertFalse(is_docs_admin(self.regular_user))

    def test_superuser_is_admin(self):
        self.assertTrue(is_docs_admin(self.superuser))

    def test_anonymous_not_admin(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(is_docs_admin(AnonymousUser()))


class DocsResolveCollisionTest(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_collision(self):
        path = self.tmp / 'file.pdf'
        result = resolve_collision(path)
        self.assertEqual(result, path)

    def test_collision_appends_number(self):
        path = self.tmp / 'file.pdf'
        path.touch()  # create it so collision happens
        result = resolve_collision(path)
        self.assertEqual(result, self.tmp / 'file (2).pdf')

    def test_multiple_collisions(self):
        base = self.tmp / 'file.pdf'
        base.touch()
        (self.tmp / 'file (2).pdf').touch()
        result = resolve_collision(base)
        self.assertEqual(result, self.tmp / 'file (3).pdf')


class DocsSafeFilenameTest(TestCase):
    def test_strips_path_separators(self):
        result = safe_filename('../etc/passwd')
        self.assertNotIn('/', result)
        self.assertNotIn('\\', result)

    def test_strips_leading_dots(self):
        result = safe_filename('.hidden')
        self.assertFalse(result.startswith('.'))

    def test_normal_name_unchanged(self):
        self.assertEqual(safe_filename('drawing.pdf'), 'drawing.pdf')


class DocsApiPermissionTest(TestCase):
    """API endpoints respect permission rules."""

    def setUp(self):
        self.tmp_docs = Path(tempfile.mkdtemp())
        self.tmp_trash = Path(tempfile.mkdtemp())
        self.tmp_tmp = Path(tempfile.mkdtemp())

        self.group = Group.objects.create(name='docs_admin')
        self.admin = User.objects.create_user('admin_doc', password='x')
        self.admin.groups.add(self.group)
        self.viewer = User.objects.create_user('viewer_doc', password='x')
        # Give viewer permission to view products
        from django.contrib.auth.models import Permission
        perm = Permission.objects.get(codename='view_produkt')
        self.viewer.user_permissions.add(perm)
        self.admin.user_permissions.add(perm)

        self.produkt = Produkt.objects.create(
            cislo_dielu='DOC-TEST-001',
            nazov='Doc test product',
            documents_path='',
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_docs, ignore_errors=True)
        shutil.rmtree(self.tmp_trash, ignore_errors=True)
        shutil.rmtree(self.tmp_tmp, ignore_errors=True)

    def _settings(self):
        return override_settings(
            ERP_DOCS_ROOT=str(self.tmp_docs),
            ERP_TRASH_ROOT=str(self.tmp_trash),
            ERP_TMP_ROOT=str(self.tmp_tmp),
            ERP_DOCS_ADMIN_GROUP='docs_admin',
        )

    def test_set_path_requires_admin(self):
        with self._settings():
            self.client.login(username='viewer_doc', password='x')
            resp = self.client.post(
                f'/api/docs/{self.produkt.pk}/set-path/',
                data=json.dumps({'path': ''}),
                content_type='application/json',
            )
            self.assertEqual(resp.status_code, 403)

    def test_set_path_admin_ok(self):
        (self.tmp_docs / 'folder1').mkdir()
        with self._settings():
            self.client.login(username='admin_doc', password='x')
            resp = self.client.post(
                f'/api/docs/{self.produkt.pk}/set-path/',
                data=json.dumps({'path': 'folder1'}),
                content_type='application/json',
            )
            self.assertEqual(resp.status_code, 200)
            data = json.loads(resp.content)
            self.assertEqual(data['status'], 'ok')
            self.produkt.refresh_from_db()
            self.assertEqual(self.produkt.documents_path, 'folder1')

    def test_upload_requires_admin(self):
        with self._settings():
            self.client.login(username='viewer_doc', password='x')
            resp = self.client.post(
                f'/api/docs/{self.produkt.pk}/upload/',
                data={'files': SimpleUploadedFile('test.pdf', b'data')},
            )
            self.assertEqual(resp.status_code, 403)

    def test_delete_requires_admin(self):
        with self._settings():
            self.client.login(username='viewer_doc', password='x')
            resp = self.client.post(
                f'/api/docs/{self.produkt.pk}/delete/',
                data=json.dumps({'subpath': 'somefile.pdf'}),
                content_type='application/json',
            )
            self.assertEqual(resp.status_code, 403)

    def test_tree_requires_login(self):
        with self._settings():
            resp = self.client.get('/api/docs/tree/')
            # Should redirect to login
            self.assertIn(resp.status_code, [302, 403])


class DocsMoveToTrashTest(TestCase):
    """Delete endpoint moves files to trash."""

    def setUp(self):
        self.tmp_docs = Path(tempfile.mkdtemp())
        self.tmp_trash = Path(tempfile.mkdtemp())
        self.tmp_tmp = Path(tempfile.mkdtemp())

        self.group = Group.objects.create(name='docs_admin_trash')
        self.admin = User.objects.create_user('admin_trash', password='x')
        self.admin.groups.add(self.group)
        # Permission to view products
        perm = Permission.objects.get(codename='view_produkt')
        self.admin.user_permissions.add(perm)

        # Create a file to delete
        self.folder = self.tmp_docs / 'myproduct'
        self.folder.mkdir()
        self.test_file = self.folder / 'drawing.pdf'
        self.test_file.write_bytes(b'PDF content')

        self.produkt = Produkt.objects.create(
            cislo_dielu='TRASH-TEST-001',
            nazov='Trash test product',
            documents_path='myproduct',
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_docs, ignore_errors=True)
        shutil.rmtree(self.tmp_trash, ignore_errors=True)
        shutil.rmtree(self.tmp_tmp, ignore_errors=True)

    def _settings(self):
        return override_settings(
            ERP_DOCS_ROOT=str(self.tmp_docs),
            ERP_TRASH_ROOT=str(self.tmp_trash),
            ERP_TMP_ROOT=str(self.tmp_tmp),
            ERP_DOCS_ADMIN_GROUP='docs_admin_trash',
        )

    def test_delete_moves_to_trash(self):
        with self._settings():
            self.client.login(username='admin_trash', password='x')
            resp = self.client.post(
                f'/api/docs/{self.produkt.pk}/delete/',
                data=json.dumps({'subpath': 'drawing.pdf'}),
                content_type='application/json',
            )
            self.assertEqual(resp.status_code, 200)
            data = json.loads(resp.content)
            self.assertEqual(data['status'], 'ok')

            # File should be gone from docs
            self.assertFalse(self.test_file.exists())

            # File should be in trash
            trash_files = list(self.tmp_trash.rglob('drawing.pdf'))
            self.assertEqual(len(trash_files), 1)

            # Audit log should have entry
            self.assertEqual(
                DocumentAuditLog.objects.filter(
                    action=DocumentAuditLog.ACTION_DELETE
                ).count(),
                1,
            )

    def test_path_traversal_in_delete_blocked(self):
        with self._settings():
            self.client.login(username='admin_trash', password='x')
            resp = self.client.post(
                f'/api/docs/{self.produkt.pk}/delete/',
                data=json.dumps({'subpath': '../../etc/passwd'}),
                content_type='application/json',
            )
            # Should return 400 Bad Request
            self.assertEqual(resp.status_code, 400)
