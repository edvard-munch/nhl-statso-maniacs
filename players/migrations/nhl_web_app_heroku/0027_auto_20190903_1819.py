# Generated by Django 2.2 on 2019-09-03 15:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0026_auto_20190903_1728'),
    ]

    operations = [
        migrations.AlterField(
            model_name='goalie',
            name='nation_abbr',
            field=models.CharField(blank=True, default='-', max_length=128),
        ),
        migrations.AlterField(
            model_name='skater',
            name='nation_abbr',
            field=models.CharField(blank=True, default='-', max_length=128),
        ),
    ]
