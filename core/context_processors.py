from django.conf import settings


def app_meta(request):
    return {
        "APP_VERSION": getattr(settings, "APP_VERSION", "n/a"),
        "APP_BUILD_TS": getattr(settings, "APP_BUILD_TS", "n/a"),
    }
