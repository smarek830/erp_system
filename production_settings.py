# Pridaj do config/settings.py pre produkčné nasadenie

# Povolené hosty
ALLOWED_HOSTS = [
    '192.168.1.94',
    'localhost',
    'tvojemeno.synology.me',  # Tvoj DDNS
    # Alebo tvoja verejná IP
]

# Pre produkciu MUSÍŠ zmeniť
DEBUG = False  # NIKDY nepúšťaj DEBUG=True na internet!

# SECRET_KEY zo environment variable
import os
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'temporary-key-CHANGE-THIS')

# HTTPS settings (ak použiješ SSL)
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Firewall - rate limiting
# pip install django-ratelimit
