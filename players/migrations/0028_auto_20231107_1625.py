# Generated by Django 2.2.6 on 2023-11-07 13:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0027_auto_20231107_1538'),
    ]

    operations = [
        migrations.AlterField(
            model_name='goalie',
            name='birth_city',
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AlterField(
            model_name='skater',
            name='birth_city',
            field=models.CharField(blank=True, max_length=128),
        ),
    ]
