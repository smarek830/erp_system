import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
from django.contrib.auth.models import User

# Vytvor testovací client
client = Client()

# Prihlás sa
user = User.objects.get(username='test_operator')
client.force_login(user)

# Zavolaj dashboard
response = client.get('/operator/')
print(f'Status code: {response.status_code}')

# Skontroluj HTML obsah
html = response.content.decode('utf-8')

checks = [
    ('Dostupné nové zakázky', 'Sekcia Dostupné nové zakázky'),
    ('Prevziať zakázku', 'Tlačidlo Prevziať zakázku'),
    ('prevziatZakazku', 'JavaScript funkcia'),
    ('nove_dostupne', 'Premenná nove_dostupne'),
]

print('\n=== KONTROLA OBSAHU ===')
for text, name in checks:
    if text in html:
        print(f'✅ {name}')
    else:
        print(f'❌ {name} CHÝBA')

# Vypíš relavantný úsek HTML
print('\n=== ÚSEK S DOSTUPNÝMI ZAKÁZKAMI ===')
if 'Dostupné nové zakázky' in html:
    idx = html.index('Dostupné nové zakázky')
    print(html[idx-50:idx+500])
else:
    print('Sekcia sa nenašla v HTML!')
    print('\n=== Celé HTML (prvých 3000 znakov) ===')
    print(html[:3000])
