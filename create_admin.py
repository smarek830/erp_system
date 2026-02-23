#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

# Vymaž starý admin účet ak existuje
if User.objects.filter(username='admin').exists():
    User.objects.get(username='admin').delete()
    print('Starý admin účet vymazaný')

# Vytvor nový superuser
User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
print('✓ Superuser vytvorený!')
print('  Používateľ: admin')
print('  Heslo: admin123')
print('')
print('Prihlás sa na: http://192.168.1.94:8000/admin/')
