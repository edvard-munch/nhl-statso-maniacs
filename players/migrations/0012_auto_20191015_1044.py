# Generated by Django 2.2.6 on 2019-10-15 07:44

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0011_auto_20191015_1043'),
    ]

    operations = [
        migrations.AddField(
            model_name='goalie',
            name='new_gamelog_stats',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='skater',
            name='new_gamelog_stats',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict),
        ),
    ]
