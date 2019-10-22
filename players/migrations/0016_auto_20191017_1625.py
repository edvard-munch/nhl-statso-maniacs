# Generated by Django 2.2.6 on 2019-10-17 13:25

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0015_auto_20191017_1625'),
    ]

    operations = [
        migrations.AddField(
            model_name='goalie',
            name='gamelog_stats',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='skater',
            name='gamelog_stats',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict),
        ),
    ]