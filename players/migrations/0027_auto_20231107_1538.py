# Generated by Django 2.2.6 on 2023-11-07 12:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0026_auto_20231107_1538'),
    ]

    operations = [
        migrations.AlterField(
            model_name='goalie',
            name='birth_city',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
        migrations.AlterField(
            model_name='skater',
            name='birth_city',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
    ]
