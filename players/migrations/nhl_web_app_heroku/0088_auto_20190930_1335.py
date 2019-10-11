# Generated by Django 2.2 on 2019-09-30 10:35

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0087_auto_20190930_1255'),
    ]

    operations = [
        migrations.AlterField(
            model_name='goalie',
            name='new_gamelog_stats',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='skater',
            name='new_gamelog_stats',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict),
        ),
    ]