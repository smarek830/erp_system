from django.contrib import admin
from django.urls import path, include  # <--- Pridaj 'include'
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from core import views as core_views

urlpatterns = [
    path('sw.js', core_views.service_worker, name='service_worker'),
    path('manifest.webmanifest', core_views.web_manifest, name='web_manifest'),
    path('pwa-icon.svg', core_views.pwa_icon, name='pwa_icon'),
    path('admin/logout/', core_views.quick_logout, name='admin_logout_quick'),
    path('admin/', admin.site.urls),
    path('logout/', core_views.quick_logout, name='logout_quick'),
    path('', include('core.urls')),  # <--- Toto prepojí tvoju appku
    path("accounts/", include("django.contrib.auth.urls")),  # login/logout
]

# Toto zabezpečí, že budú fungovať odkazy na PDF a obrázky
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
