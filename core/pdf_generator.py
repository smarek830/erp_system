from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Table, TableStyle
import qrcode
from io import BytesIO
from PIL import Image
import tempfile
import os

def generate_sprievodka_pdf(objednavka, request):
    """Generuje PDF sprievodku pre objednávku"""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # Nadpis
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(width / 2, height - 40, "VÝROBNÁ SPRIEVODKA")
    
    # Čiara pod nadpisom
    c.line(50, height - 50, width - 50, height - 50)
    
    # Informácie o objednávke
    y = height - 80
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Základné údaje:")
    
    y -= 25
    c.setFont("Helvetica", 10)
    c.drawString(70, y, f"Číslo objednávky: {objednavka.cislo_objednavky}")
    y -= 20
    c.drawString(70, y, f"Produkt: {objednavka.produkt.nazov}")
    y -= 20
    c.drawString(70, y, f"Číslo dielu: {objednavka.produkt.cislo_dielu}")
    y -= 20
    c.drawString(70, y, f"Materiál: {objednavka.produkt.material}")
    y -= 20
    c.drawString(70, y, f"Množstvo: {objednavka.mnozstvo} ks")
    y -= 20
    c.drawString(70, y, f"Termín: {objednavka.datum_pozadovane.strftime('%d.%m.%Y')}")
    y -= 20
    c.drawString(70, y, f"Zákazník: {objednavka.zakaznik}")
    
    # QR kód
    y -= 40
    qr_path = generate_qr_code(objednavka, request)
    c.drawImage(qr_path, 70, y - 100, width=100, height=100)
    c.setFont("Helvetica", 8)
    c.drawString(70, y - 115, "Naskenuj pre detail v appke")
    
    # Vymaž dočasný QR súbor
    os.remove(qr_path)
    
    # Operácie
    y -= 150
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Operácie:")
    
    y -= 20
    operacie = objednavka.produkt.operacie.all()
    
    data = [['#', 'Operácia', 'Stroj', 'Čas (min/ks)']]
    for op in operacie:
        data.append([
            str(op.poradie),
            op.nazov_operacie,
            op.stroj.nazov,
            str(op.cas_kus)
        ])
    
    table = Table(data, colWidths=[30, 200, 150, 80])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    
    table.wrapOn(c, width, height)
    table.drawOn(c, 50, y - len(data) * 20)
    
    y -= len(data) * 20 + 40
    
    # Podpisy operátorov
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Podpisy operátorov:")
    y -= 25
    
    c.setFont("Helvetica", 10)
    c.drawString(70, y, "Operátor 1: ________________________  Dátum: __________")
    y -= 25
    c.drawString(70, y, "Operátor 2: ________________________  Dátum: __________")
    y -= 25
    c.drawString(70, y, "Operátor 3: ________________________  Dátum: __________")
    
    y -= 40
    
    # Kontrolné parametre
    kontrolne = objednavka.produkt.kontrolne_parametre.all()
    if kontrolne.exists():
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "Kontrola kvality:")
        y -= 20
        
        data = [['Parameter', 'Nominál', 'Tolerancia', 'Nameraná hodnota']]
        for param in kontrolne:
            data.append([
                param.nazov,
                f"{param.hodnota_nominalna} {param.jednotka}",
                f"+{param.tolerancia_plus}/-{param.tolerancia_minus}",
                "___________"
            ])
        
        table = Table(data, colWidths=[120, 80, 80, 100])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        
        table.wrapOn(c, width, height)
        table.drawOn(c, 50, y - len(data) * 20)
    
    # Poznámky (na konci)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, 100, "Poznámky:")
    c.setFont("Helvetica", 9)
    c.line(50, 95, width - 50, 95)
    c.line(50, 75, width - 50, 75)
    c.line(50, 55, width - 50, 55)
    
    # Päta
    c.setFont("Helvetica", 8)
    c.drawString(50, 30, f"Vytvorené: {objednavka.datum_zadania.strftime('%d.%m.%Y %H:%M')}")
    c.drawRightString(width - 50, 30, f"Objednávka #{objednavka.cislo_objednavky}")
    
    c.save()
    buffer.seek(0)
    return buffer


def generate_qr_code(objednavka, request):
    """Generuje QR kód a uloží do dočasného súboru"""
    # URL na detail zakázky
    url = request.build_absolute_uri(f'/operator/zakazka/{objednavka.pk}/')
    
    # Vytvor QR kód
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Ulož do dočasného súboru
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
    img.save(temp_file.name)
    temp_file.close()
    
    return temp_file.name
