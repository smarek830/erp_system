from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('offline/', views.offline_page, name='offline_page'),
    path('produkty/', views.zoznam_produktov, name='zoznam_produktov'),
    path('produkt/<int:pk>/', views.detail_produkt, name='detail_produkt'),
    path('plan/', views.plan_vyroby, name='plan_vyroby'),
    path('plan/export/', views.export_plan_excel, name='export_plan_excel'),
    path('zakazka/<int:pk>/', views.detail_zakazky, name='detail_zakazky'),
    path('stroje/', views.zoznam_strojov, name='zoznam_strojov'),

    # WEB FORMULÁRE - Nové objednávky a kontrakty
    path('objednavka/nova/', views.nova_objednavka, name='nova_objednavka'),
    path('objednavka/<int:pk>/upravit/', views.upravit_objednavku, name='upravit_objednavku'),
    path('kontrakt/novy/', views.novy_kontrakt, name='novy_kontrakt'),
    path('kontrakt/<int:pk>/upravit/', views.upravit_kontrakt, name='upravit_kontrakt'),

    # SKLADY - NOVÉ
    path('sklad/', views.sklad_hotovych_dielov, name='sklad_hotovych_dielov'),
    path('sklad/material/', views.sklad_materialu, name='sklad_materialu'),

    # Výrobné dávky
    path('kontrakt/<int:kontrakt_pk>/vytvor-davku/', views.vytvor_davku_z_kontraktu, name='vytvor_davku_z_kontraktu'),
    path('davka/<int:davka_pk>/vytvor-objednavku/', views.vytvor_objednavku_z_davky, name='vytvor_objednavku_z_davky'),

    # Operátorské URL
    path('operator/', views.operator_dashboard, name='operator_dashboard'),
    path('operator/zakazka/<int:pk>/', views.operator_zakazka_detail, name='operator_zakazka_detail'),
    path('operator/prevziat-zakazku/<int:pk>/', views.operator_prevziat_zakazku, name='operator_prevziat_zakazku'),

    # AJAX API
    path('api/operator/start/<int:objednavka_pk>/<int:operacia_pk>/', views.start_operation, name='start_operation'),
    path('api/operator/pause/<int:objednavka_pk>/<int:operacia_pk>/', views.pause_operation, name='pause_operation'),
    path('api/operator/end/<int:objednavka_pk>/<int:operacia_pk>/', views.end_operation, name='end_operation'),
    path('api/operator/end-work/<int:pk>/', views.end_work, name='end_work'),
    path('api/operator/report-problem/<int:pk>/', views.report_problem, name='report_problem'),
    path('api/sprievodka/<int:pk>/', views.download_sprievodka, name='download_sprievodka'),

    # Nové webové rozhrania
    path('stroj/novy/', views.novy_stroj, name='novy_stroj'),
    path('stroj/<int:pk>/upravit/', views.upravit_stroj, name='upravit_stroj'),
    path('produkt/novy/', views.novy_produkt, name='novy_produkt'),
    path('produkt/<int:pk>/upravit/', views.upravit_produkt, name='upravit_produkt'),
    path('kontrakt/<int:kontrakt_pk>/davka/nova/', views.nova_vyrobna_davka, name='nova_vyrobna_davka'),
    path('sklad/prijemka/nova/', views.nova_prijemka, name='nova_prijemka'),
    path('sklad/vydajka/nova/', views.nova_vydajka, name='nova_vydajka'),
]
