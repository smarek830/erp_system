from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('produkty/', views.zoznam_produktov, name='zoznam_produktov'),
    path('produkt/<int:pk>/', views.detail_produkt, name='detail_produkt'),
    path('plan/', views.plan_vyroby, name='plan_vyroby'),
    path('zakazka/<int:pk>/', views.detail_zakazky, name='detail_zakazky'),
    path('stroje/', views.zoznam_strojov, name='zoznam_strojov'),
    
    # OPERÁTORSKÉ ROZHRANIE
    path('operator/', views.operator_dashboard, name='operator_dashboard'),
    path('operator/zakazka/<int:pk>/', views.operator_zakazka_detail, name='operator_zakazka_detail'),
    
    # AJAX AKCIE
    path('api/operator/start/<int:pk>/', views.start_work, name='start_work'),
    path('api/operator/pause/<int:pk>/', views.pause_work, name='pause_work'),
    path('api/operator/end/<int:pk>/', views.end_work, name='end_work'),
    path('api/operator/report/<int:pk>/', views.report_problem, name='report_problem'),
]
