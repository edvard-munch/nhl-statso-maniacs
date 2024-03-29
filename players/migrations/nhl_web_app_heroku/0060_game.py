# Generated by Django 2.2 on 2019-09-25 07:31

import datetime
import django.contrib.postgres.fields.jsonb
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0059_delete_game'),
    ]

    operations = [
        migrations.CreateModel(
            name='Game',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('test', models.FloatField(default=1.0)),
                ('nhl_id', models.IntegerField(unique=True)),
                ('date', models.DateField(default=datetime.date(2018, 9, 25))),
                ('teams', models.CharField(max_length=100)),
                ('boxscore', django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict)),
            ],
        ),
    ]
