# Generated migration for ERP Documents module

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_materialainavrh'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='produkt',
            name='documents_path',
            field=models.CharField(
                blank=True,
                default='',
                help_text="Relatívna cesta od ERP_DOCS_ROOT (napr. 'AA Hengstler 2026/Database/006 - 3532011922')",
                max_length=500,
                verbose_name='Cesta k dokumentom',
            ),
        ),
        migrations.CreateModel(
            name='DocumentAuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp', models.DateTimeField(auto_now_add=True, verbose_name='Čas')),
                ('action', models.CharField(
                    choices=[
                        ('upload', 'Nahratie súboru'),
                        ('delete_to_trash', 'Presun do koša'),
                        ('restore', 'Obnovenie z koša'),
                        ('cleanup', 'Automatické vymazanie z koša'),
                        ('set_path', 'Nastavenie cesty dokumentov'),
                    ],
                    max_length=20,
                    verbose_name='Akcia',
                )),
                ('src_rel_path', models.CharField(blank=True, max_length=1000, verbose_name='Zdrojová cesta')),
                ('dest_rel_path', models.CharField(blank=True, max_length=1000, verbose_name='Cieľová cesta')),
                ('file_size', models.BigIntegerField(blank=True, null=True, verbose_name='Veľkosť (B)')),
                ('produkt', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='document_audit_logs',
                    to='core.produkt',
                    verbose_name='Produkt',
                )),
                ('user', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='document_audit_logs',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Používateľ',
                )),
            ],
            options={
                'verbose_name': 'Audit log dokumentov',
                'verbose_name_plural': 'Audit logy dokumentov',
                'ordering': ['-timestamp'],
            },
        ),
    ]
