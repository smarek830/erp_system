from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_material_kg_na_meter_material_priemer_mm_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='kontrolakvality',
            name='fotka_balenia',
            field=models.ImageField(blank=True, null=True, upload_to='kontrola_kvality/balenie/', verbose_name='Fotka balenia'),
        ),
        migrations.AddField(
            model_name='kontrolakvality',
            name='pocet_nok_kusov',
            field=models.PositiveIntegerField(default=0, verbose_name='NOK kusy v zázname'),
        ),
        migrations.AddField(
            model_name='kontrolakvality',
            name='pocet_ok_kusov',
            field=models.PositiveIntegerField(default=0, verbose_name='OK kusy v zázname'),
        ),
        migrations.AddField(
            model_name='kontrolakvality',
            name='typ_kontroly',
            field=models.CharField(choices=[('PRIEBEZNA', '🔬 Priebežná kontrola'), ('FINALNA', '📦 Finálne balenie')], default='PRIEBEZNA', max_length=20, verbose_name='Typ kontroly'),
        ),
        migrations.AlterField(
            model_name='kontrolakvality',
            name='namerana_hodnota',
            field=models.CharField(max_length=500, verbose_name='Nameraná hodnota'),
        ),
    ]
