from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('produkty/', views.zoznam_produktov, name='zoznam_produktov'),
    path('produkt/<int:pk>/', views.detail_produkt, name='detail_produkt'),
    path('plan/', views.plan_vyroby, name='plan_vyroby'),
    path('zakazka/<int:pk>/', views.detail_zakazky, name='detail_zakazky'),
    path('stroje/', views.zoznam_strojov, name='zoznam_strojov'),
]