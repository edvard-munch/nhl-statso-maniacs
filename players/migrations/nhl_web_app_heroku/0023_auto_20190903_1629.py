# Generated by Django 2.2 on 2019-09-03 13:29

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0022_auto_20190903_1621'),
    ]

    operations = [
        migrations.AlterField(
            model_name='goalie',
            name='nation_abbr',
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AlterField(
            model_name='skater',
            name='nation_abbr',
            field=models.CharField(blank=True, max_length=128),
        ),
    ]
