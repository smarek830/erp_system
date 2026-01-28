from django.contrib import admin
from django.urls import path, include  # <--- Pridaj 'include'
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),  # <--- Toto prepojí tvoju appku
    path("accounts/", include("django.contrib.auth.urls")),  # login/logout
]

# Toto zabezpečí, že budú fungovať odkazy na PDF a obrázky
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
