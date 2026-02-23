import requests

# Urob request na dashboard
try:
    s = requests.Session()
    
    # GET login page pre CSRF token
    login_url = 'http://127.0.0.1:8000/accounts/login/'
    dashboard_url = 'http://127.0.0.1:8000/operator/'
    
    response = s.get(login_url)
    csrftoken = response.cookies.get('csrftoken', '')
    
    # POST login
    login_data = {
        'username': 'test_operator',
        'password': 'test123',
        'csrfmiddlewaretoken': csrftoken
    }
    headers = {'Referer': login_url}
    r = s.post(login_url, data=login_data, headers=headers)
    
    # GET dashboard
    resp = s.get(dashboard_url)
    html = resp.text
    
    # Kontrola
    checks = [
        'Dostupné nové zakázky',
        'Prevziať zakázku',
        'prevziatZakazku'
    ]
    
    print('=== KONTROLA LIVE SERVERA NA http://127.0.0.1:8000 ===')
    for text in checks:
        if text in html:
            print(f'✅ {text}')
        else:
            print(f'❌ {text} CHÝBA!')
            
    # Spočítaj koľko tlačidiel je v HTML
    count = html.count('Prevziať zakázku')
    print(f'\nPočet tlačidiel: {count}')
    
    # Ulož HTML do súboru
    with open('debug_dashboard.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print('\n✅ HTML uložené do debug_dashboard.html')
    
    # Ukáž časť HTML kde by mala byť sekcia
    if 'Dostupné nové zakázky' in html:
        idx = html.index('Dostupné nové zakázky')
        print('\n=== HTML UKÁŽKA ===')
        print(html[idx:idx+300])
    else:
        print('\n=== PRVÝCH 1000 ZNAKOV HTML ===')
        print(html[:1000])
    
except Exception as e:
    print(f'Chyba: {e}')
    import traceback
    traceback.print_exc()
