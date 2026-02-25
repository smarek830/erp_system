from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_kontrolakvality_extended'),
    ]

    operations = [
        migrations.AlterField(
            model_name='produkt',
            name='index',
            field=models.CharField(default='0', max_length=20, verbose_name='Index zmeny'),
        ),
    ]
