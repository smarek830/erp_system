from django.conf import settings
from django.db.models import F
from .models import Material


def app_meta(request):
    material_shortages = []

    material_shortage_total = 0

    if getattr(request, 'user', None) and request.user.is_authenticated:
        shortage_qs = Material.objects.filter(aktualna_zasoba__lt=F('minimalna_zasoba')).order_by('nazov')
        material_shortage_total = shortage_qs.count()

        for material in shortage_qs[:5]:
            missing = float(material.minimalna_zasoba) - float(material.aktualna_zasoba)
            if missing <= 0:
                continue
            material_shortages.append({
                'nazov': material.nazov,
                'kod': material.kod,
                'typ': material.get_typ_display(),
                'missing': round(missing, 2),
                'jednotka': material.jednotka,
            })

    return {
        "APP_VERSION": getattr(settings, "APP_VERSION", "n/a"),
        "APP_BUILD_TS": getattr(settings, "APP_BUILD_TS", "n/a"),
        "material_shortage_total": material_shortage_total,
        "material_shortages": material_shortages,
    }
