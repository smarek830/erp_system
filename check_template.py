with open('core/templates/core/operator/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()
    
print('Počet riadkov:', content.count('\n') + 1)
print('Obsahuje Dostupné nové zakázky:', 'Dostupné nové zakázky' in content)
print('Obsahuje prevziatZakazku:', 'prevziatZakazku' in content)
print('Obsahuje nove_dostupne:', 'nove_dostupne' in content)

# Najdi </div> po Priradené zakázky
lines = content.split('\n')
for i, line in enumerate(lines, 1):
    if i >= 35 and i <= 60:
        print(f'{i:3}: {line}')
